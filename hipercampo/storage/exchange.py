"""
Export and import: one memory, several machines.

The problem this solves is not backup (that is `backup.py`, and it copies the
whole file over the destination). It is the other one: two machines that BOTH
grew memories while apart, and neither copy may win over the other.

Copying the .db around cannot do that, and neither can a sync client: SQLite is
one binary blob, so Dropbox/OneDrive/git all resolve a divergence by picking a
side. The side not picked disappears with no error to notice. So the exchange
format is not the database — it is a text log of what the database MEANS.

    {"hipercampo": 1, "schema": 7, "machine": "laptop", ...}   <- header
    {"t": "memory", "uid": "9f2c…", "text": "…", …}
    {"t": "fact",   "uid": "0ab1…", "fields": {…}, …}
    {"t": "link",   "src": "9f2c…", "dst": "4d70…", …}

JSON Lines, because it appends without rewriting and one corrupt line costs one
record instead of the file.

NO LOCAL IDS TRAVEL. Every record is addressed by `uid`, a hash of its content
(see `memory_uid`). This is what dissolves the id problem: `memories.id` is
AUTOINCREMENT, so machine A's id 7 and machine B's id 7 are different memories,
and `links`, `memories.fact_id` and `facts.supersedes` all point by id. A format
carrying ids would need a remapping table and would corrupt the graph the first
time it got one wrong. Carrying uids means the endpoints are RESOLVED on arrival
against whatever local ids exist, and a link whose endpoint is unknown is
reported and dropped rather than silently pointing at a stranger.

MERGE RULES. Import must be safe to run repeatedly, in any order, from any
number of machines. That forces every rule to be idempotent and commutative:

  - accumulators take the MAX (`strength`, `access_count`, `last_access`).
    Deliberately NOT the sum: an append-only log gets imported more than once,
    and summing would inflate a memory a little more on every pass.
  - `created` (and `novelty`, which is the surprise measured at that birth)
    takes the MIN: a memory is born once, on whichever machine saw it first.
  - judgements (`importance`, `confidence`, `dormant`, `superseded`,
    `consolidated`) are LAST-WRITER-WINS by `last_access`: the side that touched
    the memory most recently is the side that has an opinion about it.

Together those are a small CRDT, which is what makes "import both files on both
machines" converge instead of ping-ponging.

WHAT THIS DOES NOT DO, and it matters:

  - `purge` does not propagate. Physical deletion leaves nothing behind to
    export, so a memory purged on one machine comes BACK from the other on the
    next import. Forgetting propagates fine (it is the `dormant` flag, a normal
    field); destroying a secret does not. Purge on every machine, or purge and
    then re-export everywhere before importing.
  - `type='knn'` links are never exported. They are derived, `reindex_navgraph`
    rebuilds them from the hypervectors, and shipping them would be shipping a
    cache. Run `hipercampo reindex` after importing.
  - `surprise_counts` are not exported. They are cumulative token counters
    feeding the novelty threshold; merging them across machines would move the
    threshold by an amount nobody can reason about.
"""

import base64
import hashlib
import json
import os
import sqlite3
import sys
import time
from typing import Any, Iterator

from ..core.vsa import to_blob

FORMAT = 1

# Fields that merge by taking the larger value (monotone, so re-importing is a
# no-op) and the ones that take the smaller.
_MAX_FIELDS = ("strength", "access_count", "last_access")
# Judgements: whoever touched it last owns them. See the module docstring.
_LWW_FIELDS = ("importance", "confidence", "consolidated", "superseded", "dormant")


def _canonical(fields: Any) -> str:
    """One spelling per fact, so key order cannot make the same fact hash twice."""
    if isinstance(fields, str):
        fields = json.loads(fields)
    return json.dumps(fields, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _uid(*parts: str) -> str:
    """Content address. NUL-joined so that ("ab","c") and ("a","bc") differ."""
    return hashlib.sha256("\0".join(parts).encode("utf-8")).hexdigest()[:32]


def memory_uid(namespace: str, kind: str, text: str) -> str:
    """A memory's identity across machines.

    Content-addressed, so the same memory written independently on two machines
    converges to one instead of doubling. The cost is that two DISTINCT memories
    with byte-identical text in the same context collapse into one — acceptable,
    because the admission policy already vetoes writing the same text twice, so
    such a pair is a duplicate anyway.
    """
    return _uid(namespace, kind, text)


def fact_uid(namespace: str, fields: Any) -> str:
    return _uid(namespace, _canonical(fields))


# --- export -----------------------------------------------------------------

def _reproducible_hv(text: str, stored: bytes) -> bool:
    """Can this hypervector be recomputed from the text on arrival?

    For ordinary memories it can: `encode_text` is seeded with sha256 of each
    token, so it yields the same vector on any machine, and leaving 1250 bytes
    out of every record is most of the file size.

    It is NOT always true, which is the whole reason this check exists rather
    than a blanket assumption. A consolidated semantic memory carries the
    BUNDLE of the memories it absorbed, not the encoding of its own label, and
    an identity memory encodes "kind: text" rather than the bare text. Both
    would come back subtly wrong — degraded retrieval, no error — so when the
    stored vector does not match, the record carries it verbatim instead.
    """
    from ..core.encoder import encode_text
    try:
        return to_blob(encode_text(text)) == stored
    except Exception:
        return False


def _rows(db: sqlite3.Connection, sql: str, args=()) -> list[sqlite3.Row]:
    return db.execute(sql, args).fetchall()


def export_records(db_path: str, namespaces: list[str] | None = None,
                   machine: str | None = None) -> Iterator[dict]:
    """Yields the header and then every exportable record.

    Reads the WHOLE file (optionally narrowed with `namespaces`). That is a
    deliberate asymmetry with import: dumping your own memory is an inspection
    by its owner, like `backup` or `list --all-namespaces`, while WRITING is
    what has to stay inside one context.
    """
    db = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30.0)
    db.row_factory = sqlite3.Row
    try:
        where, args = "", []
        if namespaces:
            where = f" WHERE namespace IN ({','.join('?' * len(namespaces))})"
            args = list(namespaces)

        present = {r[0] for r in _rows(db, "SELECT namespace FROM memories" + where, args)}
        yield {"hipercampo": FORMAT,
               "schema": _schema_version(db),
               "machine": machine or _machine_name(),
               "exported": time.time(),
               "namespaces": sorted(present)}

        # memories first: links and facts are resolved against them on arrival.
        fact_uids: dict[int, str] = {}
        for r in _rows(db, "SELECT * FROM facts" + where, args):
            fact_uids[r["id"]] = fact_uid(r["namespace"], r["fields"])

        for r in _rows(db, "SELECT * FROM memories" + where, args):
            rec = {"t": "memory",
                   "uid": memory_uid(r["namespace"], r["kind"], r["text"]),
                   "namespace": r["namespace"], "kind": r["kind"], "text": r["text"],
                   "novelty": r["novelty"], "importance": r["importance"],
                   "confidence": r["confidence"], "strength": r["strength"],
                   "access_count": r["access_count"],
                   "created": r["created"], "last_access": r["last_access"],
                   "consolidated": r["consolidated"], "superseded": r["superseded"],
                   "dormant": r["dormant"]}
            if r["fact_id"] is not None and r["fact_id"] in fact_uids:
                rec["fact_uid"] = fact_uids[r["fact_id"]]
            if not _reproducible_hv(r["text"], r["hv"]):
                rec["hv"] = base64.b64encode(r["hv"]).decode("ascii")
            yield rec

        for r in _rows(db, "SELECT * FROM facts" + where, args):
            rec = {"t": "fact", "uid": fact_uids[r["id"]], "namespace": r["namespace"],
                   "fields": json.loads(r["fields"]),
                   "valid_from": r["valid_from"], "valid_to": r["valid_to"],
                   "source": r["source"],
                   "hv": base64.b64encode(r["hv"]).decode("ascii")}
            if r["supersedes"] is not None and r["supersedes"] in fact_uids:
                rec["supersedes_uid"] = fact_uids[r["supersedes"]]
            yield rec

        # Links travel by endpoint uid. knn edges are excluded on purpose: they
        # are a rebuildable index, not knowledge (see the module docstring).
        uid_of = {r["id"]: memory_uid(r["namespace"], r["kind"], r["text"])
                  for r in _rows(db, "SELECT id, namespace, kind, text FROM memories"
                                     + where, args)}
        for r in _rows(db, "SELECT * FROM links WHERE type <> 'knn'"
                       + (" AND" + where[6:] if where else ""), args):
            if r["src"] in uid_of and r["dst"] in uid_of:
                yield {"t": "link", "namespace": r["namespace"],
                       "src": uid_of[r["src"]], "dst": uid_of[r["dst"]],
                       "weight": r["weight"], "type": r["type"], "status": r["status"]}
    finally:
        db.close()


def export_to(out_path: str, db_path: str, namespaces: list[str] | None = None,
              machine: str | None = None) -> dict:
    """Writes the export to `out_path`, or to stdout if it is "-".

    To a file, it goes through a temporary name and gets renamed: an export
    interrupted halfway must not leave a truncated log where a valid one used
    to be, and that file is very often the thing about to be pushed somewhere.

    "-" exists for the encrypted case, and it is not a convenience. Piping
    straight into `age`/`gpg` is what keeps a plaintext copy of somebody's
    whole memory from ever touching the disk — a temporary file that gets
    deleted has still been written, and on a shared or backed-up machine that
    is the copy that outlives everything.
    """
    counts: dict[str, int] = {"memory": 0, "fact": 0, "link": 0}
    header: dict = {}

    def _write(f) -> None:
        nonlocal header
        for rec in export_records(db_path, namespaces, machine):
            if "hipercampo" in rec:
                header = rec
            else:
                counts[rec["t"]] = counts.get(rec["t"], 0) + 1
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    if out_path == "-":
        _write(sys.stdout)
        sys.stdout.flush()
        destination = "-"
    else:
        tmp = out_path + ".partial"
        os.makedirs(os.path.dirname(os.path.abspath(out_path)) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8", newline="\n") as f:
            _write(f)
        os.replace(tmp, out_path)
        destination = os.path.abspath(out_path)
    return {"file": destination, "machine": header.get("machine"),
            "namespaces": header.get("namespaces", []), **counts}


def _schema_version(db: sqlite3.Connection) -> int:
    try:
        return int(db.execute("PRAGMA user_version").fetchone()[0])
    except sqlite3.Error:
        return 0


def _machine_name() -> str:
    import socket
    return os.environ.get("HIPERCAMPO_MACHINE") or socket.gethostname() or "unknown"


# --- import -----------------------------------------------------------------

def read_records(src: str) -> tuple[dict, list[dict]]:
    """Parses an export, from a file or from stdin if `src` is "-".

    A malformed line is skipped rather than fatal — the format exists to be
    appended to and shipped through git, so surviving one bad line with the
    rest intact is worth more than strictness.
    """
    header: dict = {}
    records: list[dict] = []
    stream = sys.stdin if src == "-" else open(src, encoding="utf-8")
    try:
        for line in stream:
            line = line.strip().lstrip("﻿")
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if "hipercampo" in rec and not records:
                header = rec
            elif rec.get("t"):
                records.append(rec)
    finally:
        if stream is not sys.stdin:
            stream.close()
    if header.get("hipercampo", FORMAT) > FORMAT:
        raise ValueError(
            f"the export was written in format {header['hipercampo']} and this "
            f"hipercampo understands up to {FORMAT}: upgrade before importing")
    return header, records


def _merge_memory(local: sqlite3.Row, inc: dict) -> tuple[dict, list[dict]]:
    """Field-by-field merge of an incoming memory over the local one.

    Returns the changes to apply and the list of judgements that were
    OVERWRITTEN with a different value — reported rather than applied quietly,
    because that is the only place in the whole merge where something a human
    decided on this machine stops being true.
    """
    changes: dict[str, Any] = {}
    overwritten: list[dict] = []

    for field in _MAX_FIELDS:
        if inc.get(field) is not None and inc[field] > local[field]:
            changes[field] = inc[field]

    # A memory is born once. The earliest birth wins, and `novelty` is the
    # surprise measured at that birth, so it travels with it or it describes a
    # moment that no longer exists in the record.
    if inc.get("created") is not None and inc["created"] < local["created"]:
        changes["created"] = inc["created"]
        if inc.get("novelty") is not None:
            changes["novelty"] = inc["novelty"]

    # Judgements: newer `last_access` wins. On a tie the local value stays —
    # converging is the goal, but churning identical data is not.
    if (inc.get("last_access") or 0) > local["last_access"]:
        for field in _LWW_FIELDS:
            if inc.get(field) is None or inc[field] == local[field]:
                continue
            changes[field] = inc[field]
            overwritten.append({"field": field, "local": local[field],
                                "incoming": inc[field]})
    return changes, overwritten


def import_from(src: str, db_path: str, namespace: str | None = None,
                all_namespaces: bool = False, dry_run: bool = True) -> dict:
    """Merges an export into the local memory.

    Unlike export, this one respects write isolation: by default it only lands
    records belonging to `namespace`, and everything else is COUNTED AND
    REPORTED rather than dropped in silence, so a mismatched context looks like
    a mismatched context and not like an empty file. `all_namespaces=True` is
    the owner curating their own file, the same escape hatch `reclassify` and
    `list -A` already provide.

    With `dry_run` (the default) nothing is written: the report says exactly
    what would land. Restoring the wrong thing into a live memory is cheap to
    do and expensive to discover late, so the safe mode is the default one and
    applying is the explicit choice.
    """
    header, records = read_records(src)
    target = namespace or os.environ.get("HIPERCAMPO_NAMESPACE", "default")

    report: dict[str, Any] = {
        "source": os.path.abspath(src), "from_machine": header.get("machine"),
        "dry_run": dry_run, "applied": False,
        "memories": {"new": 0, "merged": 0, "unchanged": 0},
        "facts": {"new": 0, "unchanged": 0},
        "links": {"new": 0, "existing": 0, "dangling": 0},
        "overwrites": [], "skipped_namespaces": {},
    }

    wanted: list[dict] = []
    for rec in records:
        ns = rec.get("namespace", "default")
        if all_namespaces or ns == target:
            wanted.append(rec)
        else:
            report["skipped_namespaces"][ns] = report["skipped_namespaces"].get(ns, 0) + 1

    db = sqlite3.connect(db_path, timeout=30.0)
    db.row_factory = sqlite3.Row
    try:
        # The schema has to exist before anything is matched against it: this
        # can perfectly well be the first thing a fresh machine ever does.
        from . import migrations
        db.executescript(migrations.SCHEMA)
        migrations.migrate(db, db_path)
        db.executescript(migrations.INDEXES)

        local_mem: dict[str, sqlite3.Row] = {}
        for r in db.execute("SELECT * FROM memories"):
            local_mem[memory_uid(r["namespace"], r["kind"], r["text"])] = r
        local_facts: dict[str, int] = {}
        for r in db.execute("SELECT id, namespace, fields FROM facts"):
            local_facts[fact_uid(r["namespace"], r["fields"])] = r["id"]

        pending_facts = [r for r in wanted if r["t"] == "fact"]
        pending_mem = [r for r in wanted if r["t"] == "memory"]
        pending_links = [r for r in wanted if r["t"] == "link"]

        # uid -> local id, filled as records land. Links and fact_id resolve
        # through this and never through an id that came out of the file.
        resolved: dict[str, int] = {u: r["id"] for u, r in local_mem.items()}

        db.execute("BEGIN")

        for rec in pending_facts:
            if rec["uid"] in local_facts:
                report["facts"]["unchanged"] += 1
                continue
            report["facts"]["new"] += 1
            if dry_run:
                continue
            supersedes = local_facts.get(rec.get("supersedes_uid", ""))
            cur = db.execute(
                "INSERT INTO facts(namespace, fields, hv, valid_from, valid_to, "
                "supersedes, source) VALUES(?,?,?,?,?,?,?)",
                (rec["namespace"], _canonical(rec["fields"]),
                 base64.b64decode(rec["hv"]), rec.get("valid_from"),
                 rec.get("valid_to"), supersedes, rec.get("source")))
            local_facts[rec["uid"]] = int(cur.lastrowid or 0)

        for rec in pending_mem:
            uid = rec["uid"]
            local = local_mem.get(uid)
            if local is None:
                report["memories"]["new"] += 1
                if dry_run:
                    continue
                hv = (base64.b64decode(rec["hv"]) if rec.get("hv")
                      else _encode_blob(rec["text"]))
                cur = db.execute(
                    "INSERT INTO memories(text,kind,hv,novelty,importance,confidence,"
                    "strength,access_count,created,last_access,consolidated,superseded,"
                    "dormant,fact_id,namespace) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rec["text"], rec["kind"], hv, rec.get("novelty", 1.0),
                     rec.get("importance", 0.5), rec.get("confidence", 0.5),
                     rec.get("strength", 1.0), rec.get("access_count", 0),
                     rec.get("created", time.time()), rec.get("last_access", time.time()),
                     rec.get("consolidated", 0), rec.get("superseded", 0),
                     rec.get("dormant", 0),
                     local_facts.get(rec.get("fact_uid", "")), rec["namespace"]))
                resolved[uid] = int(cur.lastrowid or 0)
                continue

            changes, overwritten = _merge_memory(local, rec)
            for o in overwritten:
                report["overwrites"].append(
                    {"namespace": rec["namespace"], "text": rec["text"][:70], **o})
            if not changes:
                report["memories"]["unchanged"] += 1
                continue
            report["memories"]["merged"] += 1
            if dry_run:
                continue
            sets = ",".join(f"{k}=?" for k in changes)
            db.execute(f"UPDATE memories SET {sets} WHERE id=?",
                       (*changes.values(), local["id"]))

        for rec in pending_links:
            src_id, dst_id = resolved.get(rec["src"]), resolved.get(rec["dst"])
            if src_id is None or dst_id is None or src_id == dst_id:
                # An endpoint this machine has never seen. Reported, not
                # invented: a link pointing at the wrong memory is worse than
                # a missing one, and reindex can re-derive proximity anyway.
                report["links"]["dangling"] += 1
                continue
            exists = db.execute(
                "SELECT 1 FROM links WHERE src=? AND dst=?", (src_id, dst_id)).fetchone()
            if exists:
                report["links"]["existing"] += 1
                continue
            report["links"]["new"] += 1
            if dry_run:
                continue
            db.execute(
                "INSERT OR IGNORE INTO links(src,dst,weight,namespace,type,status,"
                "created_at) VALUES(?,?,?,?,?,?,?)",
                (src_id, dst_id, rec.get("weight", 1.0), rec["namespace"],
                 rec.get("type", "lexical"), rec.get("status", "confirmed"),
                 time.time()))

        if dry_run:
            db.rollback()
        else:
            db.commit()
            report["applied"] = True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    if report["links"]["new"] or report["memories"]["new"]:
        report["next"] = "run `hipercampo reindex` to reweave the neighbour graph"
    return report


def _encode_blob(text: str) -> bytes:
    from ..core.encoder import encode_text
    return to_blob(encode_text(text))
