"""
SQLite persistence. Stores memories (episodic and semantic), their packed
hypervectors, and the association graph for spreading activation.

A single, portable .db file. In Docker it lives on the /data volume.

Schema and migrations live in `migrations.py`; this module owns the
connection and the read/write API.
"""

import os
import sqlite3
import time
from collections import Counter
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import numpy as np

from ..core.vsa import D, from_blob, similarity_batch, to_blob
from . import migrations

# Precedence of a link when the same pair is observed again. The higher
# rank wins; on a tie, whatever was already there wins (evidence doesn't
# overwrite itself).
#
#   4  observed evidence (lexical | update | consolidation) confirmed
#   3  REJECTED hypothesis — only a real observation revives it; proposing
#      it again does not (otherwise insisting would be enough to sneak in
#      something already discarded)
#   2  sleep hypothesis already CONFIRMED
#   1  sleep hypothesis only PROPOSED (doesn't propagate)
def _rank(t: str, s: str) -> str:
    return (f"CASE WHEN {t}='knn' THEN 0 "
            f"WHEN {t}<>'dream' THEN 4 "
            f"WHEN {s}='rejected' THEN 3 "
            f"WHEN {s}='proposed' THEN 1 ELSE 2 END")


_RANK_NEW = _rank("excluded.type", "excluded.status")
_RANK_OLD = _rank("links.type", "links.status")


class Store:
    def __init__(self, path: str = "data/hipercampo.db", namespace: str = "default",
                 linked: tuple = ()):
        self.path = path
        self.namespace = namespace          # where WRITES go: always a single one
        # LINKED contexts: can be READ, never written. So a project can draw
        # on what another one learned without being able to dirty it or be
        # dirtied by it.
        self.linked = tuple(dict.fromkeys(n for n in linked if n and n != namespace))
        self._read_ns = (namespace, *self.linked)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._txn_depth = 0
        self._nav_cache: dict[tuple[int, bool], tuple[int, object]] = {}
        self._connect()

    def _connect(self) -> None:
        """Opens the connection and brings the schema up to date. Reusable
        to reconnect."""
        # WAL + wait on lock: several processes/threads can read while one
        # writes, without corruption. The base for concurrent access.
        self.db = sqlite3.connect(self.path, timeout=30.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=30000")     # wait on lock
        try:
            # WAL is persistent at the file level: one connection setting it is enough.
            # Changing it requires an exclusive lock, so under concurrency it can
            # clash; it's best-effort (if someone else is setting it, we're fine either way).
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._txn_depth = 0
        self._nav_cache.clear()
        try:
            self.db.executescript(migrations.SCHEMA)     # 1) tables (IF NOT EXISTS)
            migrations.migrate(self.db, self.path)        # 2) new columns on old DBs
            self.db.executescript(migrations.INDEXES)    # 3) indexes, columns now present
            self.db.commit()
        except sqlite3.OperationalError as e:
            # A READ-ONLY DB must be openable for reading: if the schema is
            # already current there's nothing to write, so the failure is
            # harmless. If the schema ISN'T current (an old DB on read-only
            # media), it IS fatal: without migrating we can't serve it with
            # any guarantees.
            if ("readonly" not in str(e).lower()
                    or not migrations.has_current_columns_or_empty(self.db)):
                raise

    def matrix(self, rows) -> np.ndarray:
        """Matrix (N x 1250) with those rows' hypervectors, to compare all
        at once with similarity_batch. Avoids repeating the same stacking
        throughout the code."""
        from ..core.vsa import stack_hvs
        return stack_hvs([r["hv"] for r in rows])

    def _invalidate_nav(self) -> None:
        """Drops in-memory indexes after a change to nodes or edges."""
        self._nav_cache.clear()

    # --- health and recovery ----------------------------------------------
    def health(self, full: bool = False) -> dict:
        """Is the memory healthy? File integrity, schema, and REAL read/write.

        Uses `quick_check` by default (cheap even as the memory grows); with
        `full=True` runs the full `integrity_check` (`hipercampo doctor --full`)."""
        info: dict[str, Any] = {"db": os.path.abspath(self.path), "namespace": self.namespace}
        try:
            check = "integrity_check" if full else "quick_check"
            info["integrity"] = self.db.execute(f"PRAGMA {check}").fetchone()[0]
            info["check"] = check
        except Exception as e:
            info["integrity"] = f"ERROR: {e}"
        try:
            tables = {r[0] for r in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            missing = {"memories", "links", "facts", "meta",
                      "surprise_counts", "surprise_history"} - tables
            info["schema"] = "ok" if not missing else f"missing tables: {sorted(missing)}"
        except Exception as e:
            info["schema"] = f"ERROR: {e}"
        try:
            self.db.execute("SELECT 1 FROM memories LIMIT 1").fetchone()
            info["readable"] = "ok"
        except Exception as e:
            info["readable"] = f"ERROR: {e}"
        # REAL write, not directory permissions: os.access doesn't see a
        # full disk, a read-only .db file, or a WAL that can't be created.
        # We actually write inside a SAVEPOINT and undo it: leaves no trace.
        try:
            self.db.execute("SAVEPOINT hc_health")
            self.db.execute(                       # no set_meta: it would commit and
                "INSERT INTO meta(namespace,key,value) "   # release the SAVEPOINT
                "VALUES(?,'_health_probe','1') "
                "ON CONFLICT(namespace,key) DO UPDATE SET value='1'", (self.namespace,))
            self.db.execute("ROLLBACK TO hc_health")
            self.db.execute("RELEASE hc_health")
            info["writable"] = True
        except Exception as e:
            try:
                self.db.execute("RELEASE hc_health")
            except Exception:
                pass
            info["writable"] = False
            info["write_error"] = str(e)

        for key, label in (("schema_version", "schema_version"),
                                ("last_sleep_success", "last_sleep_success"),
                                ("last_sleep_error", "last_sleep_error"),
                                ("writes_since_sleep", "writes_since_sleep")):
            try:
                info[label] = self.get_meta(key, None)
            except Exception:
                info[label] = None
        try:
            wal = os.path.abspath(self.path) + "-wal"
            info["wal_bytes"] = os.path.getsize(wal) if os.path.exists(wal) else 0
        except Exception:
            info["wal_bytes"] = None

        info["healthy"] = (info.get("integrity") == "ok" and info.get("schema") == "ok"
                        and info.get("readable") == "ok" and info["writable"])
        return info

    def reconnect(self) -> None:
        """Reopens the connection (recovery from a DB failure)."""
        try:
            self.db.close()
        except Exception:
            pass
        self._connect()

    # --- transactions (reentrant via a depth counter) ----------------------
    def _commit(self):
        """Commit unless we're inside a larger transaction (atomicity)."""
        if self._txn_depth == 0:
            self.db.commit()

    @contextmanager
    def transaction(self):
        """Groups operations into an atomic transaction: if something fails
        halfway, everything is rolled back. Reentrant: only the outermost
        one commits or rolls back."""
        self._txn_depth += 1
        try:
            yield
        except Exception:
            if self._txn_depth == 1:
                self.db.rollback()
            self._txn_depth -= 1
            raise
        else:
            self._txn_depth -= 1
            if self._txn_depth == 0:
                self.db.commit()

    # --- writes -------------------------------------------------------------
    def add(self, text, hv, novelty, importance, confidence=0.5, kind="episodic",
            fact_id=None) -> int:
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO memories(text,kind,hv,novelty,importance,confidence,strength,"
            "created,last_access,namespace,fact_id) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (text, kind, to_blob(hv), novelty, importance, confidence, 1.0, now, now,
             self.namespace, fact_id),
        )
        self._commit()
        self._invalidate_nav()
        assert cur.lastrowid is not None                   # after a one-row INSERT
        return cur.lastrowid

    def dormant_fact_ids(self) -> set:
        """ids of facts whose text shadow is dormant or superseded (not current)."""
        rows = self.db.execute(
            "SELECT fact_id FROM memories WHERE namespace=? AND fact_id IS NOT NULL "
            "AND (dormant=1 OR superseded=1)", (self.namespace,)).fetchall()
        return {r[0] for r in rows}

    def add_fact(self, fields_json: str, hv, source: str | None = None,
                 supersedes: int | None = None, valid_from: float | None = None) -> int:
        cur = self.db.execute(
            "INSERT INTO facts(namespace, fields, hv, valid_from, supersedes, source) "
            "VALUES(?,?,?,?,?,?)",
            (self.namespace, fields_json, to_blob(hv),
             valid_from if valid_from is not None else time.time(), supersedes, source),
        )
        self._commit()
        self._invalidate_nav()
        assert cur.lastrowid is not None                   # after a one-row INSERT
        return cur.lastrowid

    # --- meta (the system's own counters, per context) ---------------------
    def get_meta(self, key: str, default=None):
        r = self.db.execute("SELECT value FROM meta WHERE namespace=? AND key=?",
                            (self.namespace, key)).fetchone()
        return r[0] if r else default

    def set_meta(self, key: str, value):
        self.db.execute(
            "INSERT INTO meta(namespace,key,value) VALUES(?,?,?) "
            "ON CONFLICT(namespace,key) DO UPDATE SET value=excluded.value",
            (self.namespace, key, str(value)))
        self._commit()

    def load_surprise(self):
        """Loads the namespace's incremental model, or None if it doesn't exist yet."""
        counts = list(self.db.execute(
            "SELECT context, token, count FROM surprise_counts WHERE namespace=?",
            (self.namespace,),
        ))
        recent = [row[0] for row in self.db.execute(
            "SELECT score FROM surprise_history WHERE namespace=? "
            "ORDER BY id DESC LIMIT 300", (self.namespace,),
        )][::-1]
        return (counts, recent) if counts or recent else None

    def seed_surprise(self, rows) -> None:
        """Initializes an older DB from its memories, once."""
        if self.load_surprise() is not None:
            return
        self.db.executemany(
            "INSERT INTO surprise_counts(namespace,context,token,count) "
            "VALUES(?,?,?,?) ON CONFLICT(namespace,context,token) DO NOTHING",
            ((self.namespace, context, token, count)
             for context, token, count in rows),
        )
        self._commit()

    def record_surprise(self, tokens: list[str], score: float | None = None,
                        history_limit: int = 300) -> None:
        """Adds an observation without storing its literal text."""
        unigrams = Counter(tokens)
        bigrams = Counter(zip(tokens, tokens[1:], strict=False))
        rows = [(self.namespace, "", token, count)
                for token, count in unigrams.items()]
        rows.extend((self.namespace, previous, token, count)
                    for (previous, token), count in bigrams.items())
        self.db.executemany(
            "INSERT INTO surprise_counts(namespace,context,token,count) "
            "VALUES(?,?,?,?) ON CONFLICT(namespace,context,token) DO UPDATE "
            "SET count=count+excluded.count", rows,
        )
        if score is not None:
            self.db.execute(
                "INSERT INTO surprise_history(namespace,score) VALUES(?,?)",
                (self.namespace, float(score)),
            )
            self.db.execute(
                "DELETE FROM surprise_history WHERE namespace=? AND id NOT IN "
                "(SELECT id FROM surprise_history WHERE namespace=? "
                "ORDER BY id DESC LIMIT ?)",
                (self.namespace, self.namespace, history_limit),
            )
        self._commit()

    def close_fact(self, fact_id: int, when: float | None = None):
        """Closes a fact's validity (stops being true NOW, but is kept:
        it's history, not a destroyed contradiction)."""
        self.db.execute(
            "UPDATE facts SET valid_to = ? WHERE id = ? AND namespace = ? AND valid_to IS NULL",
            (when if when is not None else time.time(), fact_id, self.namespace))
        self._commit()

    def all_facts(self, only_current: bool = False, at: float | None = None
                  ) -> list[sqlite3.Row]:
        """Facts in the context. `only_current`: only what's currently true.
        `at`: what was true at that instant (historical query)."""
        q = "SELECT * FROM facts WHERE namespace = ?"
        args: list = [self.namespace]
        if at is not None:
            q += (" AND (valid_from IS NULL OR valid_from <= ?)"
                  " AND (valid_to IS NULL OR valid_to > ?)")
            args += [at, at]
        elif only_current:
            q += " AND valid_to IS NULL"
        return self.db.execute(q, args).fetchall()

    def link(self, src: int, dst: int, weight: float = 1.0,
             type: str = "lexical", status: str = "confirmed"):
        """Creates/reinforces an association. `type` says where it came from
        (observed, update, consolidation or a sleep hypothesis) and `status`
        whether it's CONFIRMED evidence or just a proposal. Only confirmed
        links propagate activation."""
        if src == dst:
            return
        # Weight clamped to [0,1]: on repeats, it saturates towards 1 (doesn't
        # grow without bound, which would amplify propagation instead of
        # attenuating it). The link is tagged with the namespace: contexts
        # never cross.
        w = min(1.0, max(0.0, weight))
        # When a link repeats, the HIGHER rank wins (see _RANK_SQL): a real
        # observation PROMOTES an old hypothesis (even a rejected one), but a
        # hypothesis never downgrades already-confirmed evidence. The weight
        # only reinforces if the resulting link isn't left rejected: something
        # discarded shouldn't grow fatter by being re-proposed.
        self.db.execute(
            "INSERT INTO links(src,dst,weight,namespace,type,status,created_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(src,dst) DO UPDATE SET "
            f"  type   = CASE WHEN {_RANK_NEW} > {_RANK_OLD} THEN excluded.type"
            "                 ELSE links.type END,"
            f"  status = CASE WHEN {_RANK_NEW} > {_RANK_OLD} THEN excluded.status"
            "                 ELSE links.status END,"
            f"  weight = CASE WHEN {_RANK_NEW} > {_RANK_OLD} THEN excluded.weight"
            "                 WHEN links.status='rejected' THEN links.weight"
            "                 ELSE links.weight + 0.3 * (1.0 - links.weight) END",
            (src, dst, w, self.namespace, type, status, time.time()),
        )
        self._commit()
        self._invalidate_nav()

    def set_link_status(self, a: int, b: int, status: str) -> int:
        """Resolves a sleep hypothesis: proposed -> confirmed | rejected.

        ONLY touches `type='dream'` links with `status='proposed'`: an
        observed or already-confirmed association can't be rejected by
        accident, and an already-resolved hypothesis isn't re-resolved.
        Returns how many rows changed (0 = no such proposal existed)."""
        if status not in ("confirmed", "rejected"):
            raise ValueError(f"transition not allowed: proposed -> {status}")
        cur = self.db.execute(
            "UPDATE links SET status=? WHERE namespace=? AND type='dream' "
            "AND status='proposed' AND ((src=? AND dst=?) OR (src=? AND dst=?))",
            (status, self.namespace, a, b, b, a))
        n = cur.rowcount
        self._commit()
        return n

    def proposed_links(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM links WHERE namespace=? AND status='proposed'",
            (self.namespace,)).fetchall()

    def touch(self, ids: list[int], boost: float = 0.5):
        """Reinforces used memories: raises strength, access_count, last_access."""
        now = time.time()
        self.db.executemany(
            "UPDATE memories SET access_count = access_count + 1, "
            "last_access = ?, strength = strength + ? WHERE id = ? AND namespace = ?",
            [(now, boost, i, self.namespace) for i in ids],
        )
        self._commit()

    def reinforce(self, mem_id: int, boost: float = 0.7):
        self.db.execute(
            "UPDATE memories SET strength = strength + ?, access_count = access_count + 1 "
            "WHERE id = ? AND namespace = ?",
            (boost, mem_id, self.namespace),
        )
        self._commit()

    def set_strength(self, mem_id: int, strength: float):
        self.db.execute("UPDATE memories SET strength=? WHERE id=? AND namespace=?",
                        (strength, mem_id, self.namespace))

    def set_strengths(self, pairs: list[tuple[int, float]]):
        """Sets the strength of MANY memories at once (forgetting's decay
        touches the whole context). Like `set_strength`, doesn't commit:
        the caller decides when to close the transaction."""
        if not pairs:
            return
        self.db.executemany(
            "UPDATE memories SET strength=? WHERE id=? AND namespace=?",
            [(s, i, self.namespace) for i, s in pairs])

    def mark_superseded(self, ids: list[int]):
        """Marks memories as replaced by a newer one and weakens them
        (not deleted: they stay as history, but stop dominating retrieval)."""
        self.db.executemany(
            "UPDATE memories SET superseded = 1, strength = MIN(strength, 0.3), "
            "confidence = MIN(confidence, 0.3) WHERE id = ? AND namespace = ?",
            [(i, self.namespace) for i in ids],
        )
        self._commit()

    def mark_consolidated(self, ids: list[int]):
        self.db.executemany(
            "UPDATE memories SET consolidated = 1 WHERE id = ? AND namespace = ?",
            [(i, self.namespace) for i in ids],
        )
        self._commit()

    def delete(self, ids: list[int], secure: bool = False):
        """Deletes rows (and their links) from the namespace. With
        `secure=True` turns on `PRAGMA secure_delete`, which makes SQLite
        OVERWRITE the freed content with zeros instead of leaving it
        readable on free pages of the file: that's what turns a delete into
        a real delete for a secret. Reclaiming the disk space is separate
        (VACUUM); this only ensures the text isn't there anymore."""
        if secure:
            # Per-connection and transient: restored afterwards so the
            # overwrite overhead isn't paid on normal writes.
            self.db.execute("PRAGMA secure_delete = ON")
        try:
            self.db.executemany("DELETE FROM memories WHERE id = ? AND namespace = ?",
                                [(i, self.namespace) for i in ids])
            self.db.executemany(
                "DELETE FROM links WHERE (src=? OR dst=?) AND namespace = ?",
                [(i, i, self.namespace) for i in ids])
            self._commit()
            self._invalidate_nav()
        finally:
            if secure:
                self.db.execute("PRAGMA secure_delete = OFF")

    def vacuum(self) -> None:
        """Rewrites the file, compacting it: reclaims the space of what was
        deleted and, along the way, clears out any leftovers a normal
        DELETE would have left on free pages. CANNOT run inside a
        transaction, so anything pending is committed first. This is a
        GLOBAL operation (the whole file, all namespaces): it rewrites the
        entire database, which can take a while on large ones."""
        if self._txn_depth:
            raise RuntimeError("VACUUM cannot run inside a transaction")
        self.db.commit()                       # nothing can be left open
        self.db.execute("VACUUM")
        self.db.commit()

    def mark_dormant(self, ids: list[int]):
        """Makes memories dormant: forgotten-but-NOT-deleted. Leave normal
        retrieval, but stay latent and can resurface (see Hipercampo.muse)."""
        self.db.executemany(
            "UPDATE memories SET dormant = 1 WHERE id = ? AND namespace = ?",
            [(i, self.namespace) for i in ids],
        )
        self._commit()

    def reactivate(self, ids: list[int]):
        """Wakes up dormant memories (a memory that resurfaces)."""
        self.db.executemany(
            "UPDATE memories SET dormant = 0, last_access = ? WHERE id = ? AND namespace = ?",
            [(time.time(), i, self.namespace) for i in ids],
        )
        self._commit()

    # --- reads (always scoped to the store's namespace) ---------------------
    def all(self, kind=None, only_active=True, include_dormant=False,
            own_only=False, limit: int | None = None) -> list[sqlite3.Row]:
        # Reading: the own context PLUS the linked ones (cross-project
        # inspiration). Writing (add/touch/…) stays scoped to self.namespace:
        # reading doesn't dirty anything. own_only=True is for MAINTENANCE
        # (consolidate/forget/dream): tending to one's own memory shouldn't
        # even read someone else's — fusing another project's episodes into
        # one's own semantic memory would be copying their text.
        #
        # limit=N caps how many rows come back (RAM and recall time on an
        # embedded device). The most ALIVE ones are picked —strength
        # (reinforcement*decay) and recency— because that's what an
        # agent/robot most likely needs when everything doesn't fit. The
        # LIMIT is in SQL, so 100k hypervector blobs aren't loaded just to
        # throw away 99k of them.
        ns = (self.namespace,) if own_only else self._read_ns
        marks = ",".join("?" * len(ns))
        q = f"SELECT * FROM memories WHERE namespace IN ({marks})"
        args: list = [*ns]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        if only_active:
            q += " AND consolidated = 0"
        if not include_dormant:
            q += " AND dormant = 0"
        if limit is not None:
            q += " ORDER BY strength DESC, last_access DESC LIMIT ?"
            args.append(int(limit))
        return self.db.execute(q, args).fetchall()

    _DUMP_FIELDS = ("id", "text", "kind", "novelty", "importance", "confidence",
                    "strength", "access_count", "created", "last_access",
                    "consolidated", "superseded", "dormant", "namespace")

    def _select_visible(self, fields: str, table: str, all_namespaces: bool,
                        conditions: list[str], args: list) -> tuple[str, list]:
        """Builds a SELECT with the context filter already applied.

        Shared by `dump` and `links_dump`, which used to repeat the same
        dance of placeholders and deciding whether the next filter needs
        WHERE or AND —two copies that had to be fixed together, and where
        an extra `WHERE` only showed up when a new filter was added."""
        where, params = list(conditions), list(args)
        if not all_namespaces:      # own context + linked ones (read-only)
            marks = ",".join("?" * len(self._read_ns))
            where.insert(0, f"namespace IN ({marks})")
            params[:0] = self._read_ns
        q = f"SELECT {fields} FROM {table}"
        if where:
            q += " WHERE " + " AND ".join(where)
        return q, params

    def dump(self, all_namespaces: bool = False, include_dormant: bool = True,
             kind: str | None = None, limit: int | None = None,
             order: str = "recent") -> list[dict]:
        """Dumps memories as dicts WITHOUT the hypervector (for
        inspection/UI), not as raw rows. By default only the own context;
        `all_namespaces=True` looks at the WHOLE file — it's an inspection
        read by the owner of their own memory (like `backup`/`stats`), not a
        cross-context read during an operation."""
        cond: list[str] = []
        args: list = []
        if kind:
            cond.append("kind = ?"); args.append(kind)
        if not include_dormant:
            cond.append("dormant = 0")
        q, args = self._select_visible(", ".join(self._DUMP_FIELDS), "memories",
                                       all_namespaces, cond, args)
        order_by = {"recent": "last_access DESC", "importance": "importance DESC",
                 "access": "access_count DESC", "created": "created DESC"}.get(
                     order, "last_access DESC")
        q += f" ORDER BY {order_by}"
        if limit:
            q += " LIMIT ?"; args.append(int(limit))
        return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def links_dump(self, all_namespaces: bool = False,
                   include_proposed: bool = True) -> list[dict]:
        """Association graph edges as dicts (src, dst, weight, type,
        status). For the viewer's network map. By default the own context;
        with `all_namespaces` the whole file (owner inspection, like `dump`)."""
        cond = [] if include_proposed else ["status != 'proposed'"]
        q, args = self._select_visible("src, dst, weight, type, status, namespace",
                                       "links", all_namespaces, cond, [])
        return [dict(r) for r in self.db.execute(q, args).fetchall()]

    def set_dormant(self, ids: list[int], dormant: bool):
        """Makes memories dormant or wakes them by id (for the viewer).
        Scoped to the own namespace: can't touch another context's or a
        linked one's (read-only)."""
        if dormant:
            self.mark_dormant(ids)
        else:
            self.reactivate(ids)

    def reindex_navgraph(self, M: int = 12) -> int:
        """Weaves the NEIGHBOR graph over the own context's memories: links
        each one with its M closest matches (type='knn'). It's owner
        curation over their own graph: the map goes from sparse to
        connected, and spreading activation gains the real associations
        that were missing. Does NOT overwrite existing links (INSERT OR
        IGNORE) nor add random shortcuts (those are navigation-only and come
        with navigable recall, so as not to pollute activation). Returns how
        many new links it wove.

        Vectorized O(N^2): this is maintenance (like backup/consolidate),
        not the hot path. At scale, incremental construction via navigation
        (navgraph) avoids the scan; here, over the own context, the exact
        sweep is simple and correct."""
        rows = self.all(only_active=False, own_only=True, include_dormant=True)
        if len(rows) < 3:
            return 0
        ids = [r["id"] for r in rows]
        mat = self.matrix(rows)
        now = time.time()
        woven = 0
        with self.transaction():
            for i in range(len(rows)):
                sims = similarity_batch(mat[i], mat)
                # Only the top M+1 are needed (M neighbors + itself), not the
                # full order: argpartition splits them in O(N) and only that
                # handful gets sorted. With large N, sorting N similarities
                # per row was the dominant cost of weaving the map.
                cutoff = min(len(sims), M + 1)
                head = np.argpartition(-sims, cutoff - 1)[:cutoff]
                order = head[np.argsort(-sims[head], kind="stable")]
                added = 0
                for j in order:
                    if j == i:
                        continue
                    a, b = sorted((ids[i], ids[int(j)]))
                    cur = self.db.execute(
                        "INSERT OR IGNORE INTO links(src,dst,weight,namespace,type,"
                        "status,created_at) VALUES(?,?,?,?,?,?,?)",
                        (a, b, float(sims[int(j)]), self.namespace, "knn", "confirmed", now))
                    woven += cur.rowcount
                    added += 1
                    if added >= M:
                        break
        self._invalidate_nav()
        return woven

    def navgraph(self, shortcuts: int = 2, adaptive_shortcuts: bool = True):
        """Builds the NAVIGATION index for the own context: nodes = memories
        (with their hypervector), edges = the map's knn links + ephemeral
        shortcuts. It's the 'GPS' for recalling by navigating instead of
        scanning. Built from what's already stored; the shortcuts live only
        here (not in the map or in activation). Adaptive mode skips them
        only when the base topology already offers enough expansion;
        adaptive_shortcuts=False keeps the fixed ablation."""
        from ..core.navgraph import NavGraph
        data_version = int(self.db.execute("PRAGMA data_version").fetchone()[0])
        cache_key = (shortcuts, adaptive_shortcuts)
        cached = self._nav_cache.get(cache_key)
        if cached is not None and cached[0] == data_version:
            return cached[1]
        # Narrow path: the GPS doesn't need text or metadata. Iterating
        # cursors with only the useful columns avoids materializing two full
        # dumps at 100k+.
        count = int(self.db.execute(
            "SELECT COUNT(*) FROM memories WHERE namespace=?", (self.namespace,)
        ).fetchone()[0])
        code_matrix = np.empty((count, D // 8), dtype=np.uint8)
        code_ids: list[int] = []
        code_rows = self.db.execute(
            "SELECT id, hv FROM memories WHERE namespace=?", (self.namespace,)
        )
        for pos, (mid, hv) in enumerate(code_rows):
            code_ids.append(int(mid))
            code_matrix[pos] = np.frombuffer(hv, dtype=np.uint8)
        edge_rows = self.db.execute(
            "SELECT src, dst FROM links WHERE namespace=? AND type='knn'",
            (self.namespace,),
        )
        edges = ((int(src), int(dst)) for src, dst in edge_rows)
        graph = NavGraph.from_links(
            {}, edges, shortcuts=shortcuts, compact=True,
            code_ids=code_ids, code_matrix=code_matrix,
            adaptive_shortcuts=adaptive_shortcuts,
        )
        self._nav_cache[cache_key] = (data_version, graph)
        return graph

    def reclassify(self, ids: list[int], to_namespace: str) -> int:
        """Moves OWN memories to another context: owner curation over their
        own memory. Only touches the own namespace (never a linked one,
        which is read-only, nor another context's). Links get relocated:
        those with BOTH ends in the destination move with them; those that
        would cross contexts are DELETED (a link between contexts would
        break isolation). Returns how many were moved."""
        destination = str(to_namespace or "").strip()
        if not destination:
            raise ValueError("empty destination context")
        ids = [int(i) for i in ids]
        if not ids:
            return 0
        marks = ",".join("?" * len(ids))
        with self.transaction():
            own = [r[0] for r in self.db.execute(
                f"SELECT id FROM memories WHERE namespace=? AND id IN ({marks})",
                (self.namespace, *ids)).fetchall()]
            if not own:
                return 0
            moved = set(own)
            pm = ",".join("?" * len(own))
            affected = self.db.execute(
                f"SELECT src, dst FROM links WHERE namespace=? "
                f"AND (src IN ({pm}) OR dst IN ({pm}))",
                (self.namespace, *own, *own)).fetchall()
            self.db.execute(
                f"UPDATE memories SET namespace=? WHERE namespace=? AND id IN ({pm})",
                (destination, self.namespace, *own))
            for src, dst in affected:
                if src in moved and dst in moved:      # the link moves whole
                    self.db.execute("UPDATE links SET namespace=? WHERE src=? AND dst=?",
                                    (destination, src, dst))
                else:                                      # would cross contexts: cut it
                    self.db.execute("DELETE FROM links WHERE src=? AND dst=?", (src, dst))
        self._invalidate_nav()
        return len(own)

    def get(self, mem_id: int):
        # Scoped to what's READABLE (own + linked): a non-linked context
        # stays invisible, even by id.
        marks = ",".join("?" * len(self._read_ns))
        return self.db.execute(
            f"SELECT * FROM memories WHERE id=? AND namespace IN ({marks})",
            (mem_id, *self._read_ns),
        ).fetchone()

    def get_many(self, ids) -> dict[int, sqlite3.Row]:
        """Several memories by id in ONE query, {id: row}. Scoped to what's
        readable, same as `get`. ids that don't exist (or aren't visible)
        simply don't show up: the caller decides what to do about the missing ones."""
        ids = [int(i) for i in ids]
        if not ids:
            return {}
        ns_marks = ",".join("?" * len(self._read_ns))
        out: dict[int, sqlite3.Row] = {}
        # SQLite caps a statement's parameters (999 in older builds), so
        # requests go in batches instead of assuming they all fit.
        batch = 400
        for start in range(0, len(ids), batch):
            chunk = ids[start:start + batch]
            marks = ",".join("?" * len(chunk))
            for row in self.db.execute(
                    f"SELECT * FROM memories WHERE id IN ({marks}) "
                    f"AND namespace IN ({ns_marks})", (*chunk, *self._read_ns)):
                out[row["id"]] = row
        return out

    def neighbors(self, mem_id: int, include_proposed: bool = False) -> list[tuple[int, float]]:
        """Neighbors via CONFIRMED associations. Hypotheses
        (status='proposed') do NOT propagate activation until accepted:
        speculation doesn't pollute observed memory."""
        statuses = ("confirmed", "proposed") if include_proposed else ("confirmed",)
        marks = ",".join("?" * len(statuses))
        ns_marks = ",".join("?" * len(self._read_ns))
        rows = self.db.execute(
            f"SELECT dst, weight FROM links WHERE src=? AND namespace IN ({ns_marks}) "
            f"  AND status IN ({marks}) "
            f"UNION SELECT src, weight FROM links WHERE dst=? AND namespace IN ({ns_marks}) "
            f"  AND status IN ({marks})",
            (mem_id, *self._read_ns, *statuses, mem_id, *self._read_ns, *statuses),
        ).fetchall()
        # One neighbor, ONCE: if a pair is joined by two links (one in each
        # direction, e.g. a knn and a lexical with different weights), the
        # UNION used to return it TWICE. That broke dream (pairs (x,x)) and
        # doubled propagation. We keep the best weight per neighbor.
        best: dict[int, float] = {}
        for dst, w in rows:
            if dst != mem_id and (dst not in best or w > best[dst]):
                best[dst] = w
        return list(best.items())

    def neighbors_all(self, ids=None, include_proposed: bool = False
                      ) -> dict[int, dict[int, float]]:
        """Neighbors of ALL readable memories, in ONE query: {id: {neighbor: weight}}.

        Same semantics as `neighbors` (only confirmed links unless
        hypotheses are requested, no self-links, best weight per neighbor),
        but for whoever needs all of them —dream, which used to fire one
        query per memory—. With `ids` it's trimmed to that set on BOTH ends,
        so no neighbor shows up that the caller won't be able to look at."""
        statuses = ("confirmed", "proposed") if include_proposed else ("confirmed",)
        marks = ",".join("?" * len(statuses))
        ns_marks = ",".join("?" * len(self._read_ns))
        rows = self.db.execute(
            f"SELECT src, dst, weight FROM links WHERE namespace IN ({ns_marks}) "
            f"AND status IN ({marks})",
            (*self._read_ns, *statuses)).fetchall()
        allowed = None if ids is None else set(ids)
        out: dict[int, dict[int, float]] = {}
        if allowed is not None:
            out = {i: {} for i in allowed}
        for src, dst, w in rows:
            if src == dst:
                continue
            if allowed is not None and (src not in allowed or dst not in allowed):
                continue
            for a, b in ((src, dst), (dst, src)):
                neigh = out.setdefault(a, {})
                if w > neigh.get(b, -1.0):
                    neigh[b] = w
        return out

    def hv_of(self, row) -> np.ndarray:
        return from_blob(row["hv"])

    def commit(self):
        self.db.commit()
        self._invalidate_nav()

    def close(self):
        # Checkpoint + truncate the WAL: leaves the file consistent and
        # removes the -wal/-shm (avoids leftover locks, especially on Windows).
        try:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        self.db.close()
