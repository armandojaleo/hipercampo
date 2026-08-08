"""
Schema and versioned migrations for the SQLite store.

Split out of `store.py` on its own: the CRUD/read/write API and the schema
evolution are two different concerns that used to live in one 1000+ line
file. This module knows the table DDL and how to walk an old database up to
`SCHEMA_VERSION`, step by step; it doesn't know how to read or write a
memory. `Store` in `store.py` owns the connection and calls into here.

Each migration step is idempotent and runs inside a transaction; when it
finishes, `PRAGMA user_version` is recorded. An old database
(user_version=0) walks through all of them: steps already applied are
no-ops, so resuming after an interruption is safe.
"""

import os
import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    kind         TEXT    NOT NULL DEFAULT 'episodic',   -- episodic | semantic
    hv           BLOB    NOT NULL,
    novelty      REAL    NOT NULL DEFAULT 1.0,          -- surprise at birth
    importance   REAL    NOT NULL DEFAULT 0.5,          -- how much it matters (per whoever said so)
    confidence   REAL    NOT NULL DEFAULT 0.5,          -- reliability / how certain it is
    strength     REAL    NOT NULL DEFAULT 1.0,          -- reinforced and decays
    access_count INTEGER NOT NULL DEFAULT 0,
    created      REAL    NOT NULL,
    last_access  REAL    NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0,            -- already absorbed into a semantic one
    superseded   INTEGER NOT NULL DEFAULT 0,            -- replaced by a newer one
    dormant      INTEGER NOT NULL DEFAULT 0,            -- forgotten-but-not-deleted (dormant)
    fact_id      INTEGER,                               -- text shadow of a VSA fact
    namespace    TEXT    NOT NULL DEFAULT 'default'     -- per-tenant isolation
);
CREATE TABLE IF NOT EXISTS links (
    src       INTEGER NOT NULL,
    dst       INTEGER NOT NULL,
    weight    REAL    NOT NULL DEFAULT 1.0,
    namespace TEXT    NOT NULL DEFAULT 'default',
    type      TEXT    NOT NULL DEFAULT 'lexical',    -- lexical|update|consolidation|dream|knn
    status    TEXT    NOT NULL DEFAULT 'confirmed',  -- confirmed|proposed|rejected
    created_at REAL,
    PRIMARY KEY (src, dst)
);
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace  TEXT    NOT NULL DEFAULT 'default',
    fields     TEXT    NOT NULL,   -- JSON {role: value}
    hv         BLOB    NOT NULL,   -- role-filler hypervector (bind/bundle)
    valid_from REAL,               -- since when it's true
    valid_to   REAL,               -- until when (NULL = currently true)
    supersedes INTEGER,            -- which fact it replaces (history, not deletion)
    source     TEXT                -- provenance (who/what stated it)
);
CREATE TABLE IF NOT EXISTS meta (
    namespace TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT,
    PRIMARY KEY (namespace, key)
);
CREATE TABLE IF NOT EXISTS surprise_counts (
    namespace TEXT NOT NULL,
    context   TEXT NOT NULL,
    token     TEXT NOT NULL,
    count     INTEGER NOT NULL,
    PRIMARY KEY (namespace, context, token)
);
CREATE TABLE IF NOT EXISTS surprise_history (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace TEXT NOT NULL,
    score     REAL NOT NULL
);
"""

# Indexes are SEPARATE and created AFTER migrating: on an old DB the columns
# being indexed (namespace…) don't exist yet, and creating the index first
# would fail with "no such column".
INDEXES = """
CREATE INDEX IF NOT EXISTS idx_kind ON memories(namespace, kind, consolidated);
CREATE INDEX IF NOT EXISTS idx_links_ns ON links(namespace);
CREATE INDEX IF NOT EXISTS idx_facts_ns ON facts(namespace);
CREATE INDEX IF NOT EXISTS idx_surprise_history_ns ON surprise_history(namespace, id);
CREATE INDEX IF NOT EXISTS idx_vivos ON memories(namespace, strength DESC, last_access DESC);
"""


def _columns(db: sqlite3.Connection, table: str) -> set:
    return {r[1] for r in db.execute(f"PRAGMA table_info({table})")}


def _add_column(db: sqlite3.Connection, table: str, column: str, ddl: str):
    """Idempotent ALTER TABLE: does nothing if the column is already there."""
    cols = _columns(db, table)
    if cols and column not in cols:
        db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")


def _m001_confidence_and_supersede(db):
    _add_column(db, "memories", "superseded", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "memories", "confidence", "REAL NOT NULL DEFAULT 0.5")


def _m002_namespaces(db):
    _add_column(db, "memories", "namespace", "TEXT NOT NULL DEFAULT 'default'")
    _add_column(db, "links", "namespace", "TEXT NOT NULL DEFAULT 'default'")


def _m003_dormancy_and_typed_links(db):
    _add_column(db, "memories", "dormant", "INTEGER NOT NULL DEFAULT 0")
    _add_column(db, "links", "type", "TEXT NOT NULL DEFAULT 'lexical'")
    _add_column(db, "links", "status", "TEXT NOT NULL DEFAULT 'confirmed'")
    _add_column(db, "links", "created_at", "REAL")


def _m004_facts_with_history(db):
    _add_column(db, "memories", "fact_id", "INTEGER")
    for col, ddl in (("valid_from", "REAL"), ("valid_to", "REAL"),
                     ("supersedes", "INTEGER"), ("source", "TEXT")):
        _add_column(db, "facts", col, ddl)


def _m005_health_metadata(db):
    # A link can only be in one of these states; an old DB with garbage
    # values gets normalized before the state machine comes to depend on it.
    if not _columns(db, "links"):
        return
    # Read before writing: if there's nothing to normalize (the normal
    # case), no write lock is requested, and several processes can open at once.
    any_bad = db.execute(
        "SELECT 1 FROM links WHERE status NOT IN "
        "('proposed','confirmed','rejected') LIMIT 1").fetchone()
    if any_bad:
        db.execute("UPDATE links SET status='confirmed' "
                   "WHERE status NOT IN ('proposed','confirmed','rejected')")


def _m006_rewrite_old_rows(db):
    """`ALTER TABLE ADD COLUMN ... NOT NULL DEFAULT` doesn't rewrite already
    existing rows: SQLite serves them the default value on read, but the
    on-disk record still lacks that column, and `integrity_check` flags it
    ("NULL value in memories.confidence") on some versions. An UPDATE that
    changes nothing does rewrite the full record and leaves it consistent."""
    for table, column in (("memories", "confidence"), ("memories", "superseded"),
                           ("memories", "namespace"), ("memories", "dormant"),
                           ("links", "namespace"), ("links", "type"),
                           ("links", "status")):
        if column in _columns(db, table):
            db.execute(f"UPDATE {table} SET {column} = {column}")


def _m007_persistent_surprise(db):
    db.execute(
        "CREATE TABLE IF NOT EXISTS surprise_counts ("
        "namespace TEXT NOT NULL, context TEXT NOT NULL, "
        "token TEXT NOT NULL, count INTEGER NOT NULL, "
        "PRIMARY KEY (namespace, context, token))"
    )
    db.execute(
        "CREATE TABLE IF NOT EXISTS surprise_history ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "namespace TEXT NOT NULL, score REAL NOT NULL)"
    )


STEPS = [
    (1, "confidence_and_supersede", _m001_confidence_and_supersede),
    (2, "namespaces", _m002_namespaces),
    (3, "dormancy_and_typed_links", _m003_dormancy_and_typed_links),
    (4, "facts_with_history", _m004_facts_with_history),
    (5, "health_metadata", _m005_health_metadata),
    (6, "rewrite_old_rows", _m006_rewrite_old_rows),
    (7, "persistent_surprise", _m007_persistent_surprise),
]
SCHEMA_VERSION = 7

# Columns that SCHEMA creates from scratch: if they're ALL present, the DB
# was already born up to date.
CURRENT_COLUMNS = {
    "memories": {"superseded", "confidence", "namespace", "dormant", "fact_id"},
    "links": {"namespace", "type", "status", "created_at"},
    "facts": {"valid_from", "valid_to", "supersedes", "source"},
    "surprise_counts": {"namespace", "context", "token", "count"},
    "surprise_history": {"id", "namespace", "score"},
}


def is_up_to_date(db: sqlite3.Connection) -> bool:
    """Was the DB just born with the current schema? Requires both the
    factory columns AND being empty: an inherited, half-migrated database
    (columns already added but the version never sealed) still has to walk
    the steps."""
    try:
        if not all(expected <= _columns(db, table)
                   for table, expected in CURRENT_COLUMNS.items()):
            return False
        return not db.execute("SELECT 1 FROM memories LIMIT 1").fetchone()
    except sqlite3.Error:
        return False


def has_current_columns_or_empty(db: sqlite3.Connection) -> bool:
    """Can it operate read-only? Yes, if the schema is already current."""
    try:
        return all(expected <= _columns(db, table)
                   for table, expected in CURRENT_COLUMNS.items())
    except sqlite3.Error:
        return False


def backup_before_migrating(db: sqlite3.Connection, path: str, version: int) -> None:
    """Backup BEFORE touching the schema of a DB with data. If something
    goes wrong, the memories are still there. Skipped for a freshly created
    DB (nothing to lose) or an in-memory one."""
    if path in ("", ":memory:") or not os.path.exists(path):
        return
    dest = f"{path}.bak-v{version}"
    if os.path.exists(dest):
        return                                  # already backed up this jump
    try:
        if not db.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' "
                "AND name='memories'").fetchone():
            return                              # new DB: nothing to back up
        copy = sqlite3.connect(dest)            # `with` would commit, not close
        try:
            db.backup(copy)                     # consistent copy, not a file cp
        finally:
            copy.close()
    except Exception:
        pass          # an impossible backup shouldn't block opening the memory


def migrate(db: sqlite3.Connection, path: str) -> None:
    """Walks the DB up to SCHEMA_VERSION, step by step, recording the
    version as it goes.

    Used to detect loose columns without recording which version the file
    was at; that already caused a failure opening old databases. Now every
    step is explicit, transactional and checkable."""
    current = db.execute("PRAGMA user_version").fetchone()[0]
    if current >= SCHEMA_VERSION:
        return
    # A DB just created by SCHEMA is already born with the current schema:
    # there's nothing to migrate, just to seal. Without this, several
    # processes opening a new DB at once fight over the write lock for nothing.
    if is_up_to_date(db):
        try:
            db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
            db.commit()
        except sqlite3.Error:
            pass                       # someone else got there first: just as good
        return

    backup_before_migrating(db, path, current)
    for version, name, step in STEPS:
        if version <= current:
            continue
        try:
            db.execute("SAVEPOINT hc_migration")
            step(db)
            db.execute("RELEASE hc_migration")
            db.execute(f"PRAGMA user_version = {version}")
            db.commit()
        except Exception as e:
            try:
                db.execute("ROLLBACK TO hc_migration")
                db.execute("RELEASE hc_migration")
            except Exception:
                pass
            # Another process might be migrating the same DB at the same
            # time: if it already left it at this version, there's nothing
            # to fix (not a failure).
            if db.execute("PRAGMA user_version").fetchone()[0] >= version:
                continue
            raise RuntimeError(
                f"migration {version:03d}_{name} failed: {e} · "
                f"the DB is still at version {current}; there's a backup at "
                f"{path}.bak-v{current}") from e
