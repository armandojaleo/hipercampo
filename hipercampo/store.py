"""
Persistencia en SQLite. Guarda los recuerdos (episódicos y semánticos), sus
hipervectores empaquetados, y el grafo de asociaciones para la propagación de
activación.

Un solo fichero .db portátil. En Docker vive en el volumen /data.
"""

import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .vsa import from_blob, to_blob

_SCHEMA = """
CREATE TABLE IF NOT EXISTS memories (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    text         TEXT    NOT NULL,
    kind         TEXT    NOT NULL DEFAULT 'episodic',   -- episodic | semantic
    hv           BLOB    NOT NULL,
    novelty      REAL    NOT NULL DEFAULT 1.0,          -- sorpresa al nacer
    importance   REAL    NOT NULL DEFAULT 0.5,          -- cuánto importa (quien lo dice)
    confidence   REAL    NOT NULL DEFAULT 0.5,          -- fiabilidad / cuán cierto es
    strength     REAL    NOT NULL DEFAULT 1.0,          -- se refuerza y decae
    access_count INTEGER NOT NULL DEFAULT 0,
    created      REAL    NOT NULL,
    last_access  REAL    NOT NULL,
    consolidated INTEGER NOT NULL DEFAULT 0,            -- ya absorbido en semántico
    superseded   INTEGER NOT NULL DEFAULT 0,            -- reemplazado por uno más nuevo
    dormant      INTEGER NOT NULL DEFAULT 0,            -- olvidado-pero-no-borrado (latente)
    fact_id      INTEGER,                               -- sombra textual de un hecho VSA
    namespace    TEXT    NOT NULL DEFAULT 'default'     -- aislamiento por inquilino
);
CREATE TABLE IF NOT EXISTS links (
    src       INTEGER NOT NULL,
    dst       INTEGER NOT NULL,
    weight    REAL    NOT NULL DEFAULT 1.0,
    namespace TEXT    NOT NULL DEFAULT 'default',
    type      TEXT    NOT NULL DEFAULT 'lexical',    -- lexical|update|consolidation|dream
    status    TEXT    NOT NULL DEFAULT 'confirmed',  -- confirmed|proposed|rejected
    created_at REAL,
    PRIMARY KEY (src, dst)
);
CREATE TABLE IF NOT EXISTS facts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    namespace  TEXT    NOT NULL DEFAULT 'default',
    fields     TEXT    NOT NULL,   -- JSON {rol: valor}
    hv         BLOB    NOT NULL,   -- hipervector role-filler (bind/bundle)
    valid_from REAL,               -- desde cuándo es cierto
    valid_to   REAL,               -- hasta cuándo (NULL = vigente ahora)
    supersedes INTEGER,            -- a qué hecho sustituye (historia, no borrado)
    source     TEXT                -- procedencia (quién/qué lo afirmó)
);
"""

# Los índices van APARTE y se crean DESPUÉS de migrar: en una BD antigua las
# columnas que indexan (namespace…) aún no existen, y crear el índice antes
# rompería con "no such column".
_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_kind ON memories(namespace, kind, consolidated);
CREATE INDEX IF NOT EXISTS idx_links_ns ON links(namespace);
CREATE INDEX IF NOT EXISTS idx_facts_ns ON facts(namespace);
"""


class Store:
    def __init__(self, path: str = "data/hipercampo.db", namespace: str = "default"):
        self.path = path
        self.namespace = namespace
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        # WAL + espera ante bloqueo: varios procesos/hilos pueden leer mientras uno
        # escribe, sin corromper. Base para acceso concurrente (multiusuario).
        self.db = sqlite3.connect(path, timeout=30.0)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA busy_timeout=30000")     # esperar ante bloqueo
        try:
            # WAL es persistente a nivel de fichero: basta que lo fije una conexión.
            # Cambiarlo exige lock exclusivo, así que bajo concurrencia puede chocar;
            # es best-effort (si otro lo está fijando, seguimos igual).
            self.db.execute("PRAGMA journal_mode=WAL")
        except sqlite3.OperationalError:
            pass
        self.db.execute("PRAGMA synchronous=NORMAL")
        self._txn_depth = 0
        self.db.executescript(_SCHEMA)     # 1) tablas (IF NOT EXISTS)
        self._migrate()                    # 2) columnas nuevas en BDs antiguas
        self.db.executescript(_INDEXES)    # 3) índices, ya con las columnas presentes
        self.db.commit()

    # --- transacciones (reentrantes vía contador de profundidad) ---------
    def _commit(self):
        """Commit salvo que estemos dentro de una transacción mayor (atomicidad)."""
        if self._txn_depth == 0:
            self.db.commit()

    @contextmanager
    def transaction(self):
        """Agrupa operaciones en una transacción atómica: si algo falla a mitad, se
        revierte todo. Reentrante: solo la más externa confirma o revierte."""
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

    def _migrate(self):
        """Añade columnas nuevas a BDs creadas con versiones anteriores."""
        cols = {r[1] for r in self.db.execute("PRAGMA table_info(memories)")}
        if "superseded" not in cols:
            self.db.execute(
                "ALTER TABLE memories ADD COLUMN superseded INTEGER NOT NULL DEFAULT 0")
        if "confidence" not in cols:
            self.db.execute(
                "ALTER TABLE memories ADD COLUMN confidence REAL NOT NULL DEFAULT 0.5")
        if "namespace" not in cols:
            self.db.execute(
                "ALTER TABLE memories ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default'")
        if "dormant" not in cols:
            self.db.execute(
                "ALTER TABLE memories ADD COLUMN dormant INTEGER NOT NULL DEFAULT 0")
        if "fact_id" not in cols:
            self.db.execute("ALTER TABLE memories ADD COLUMN fact_id INTEGER")
        lcols = {r[1] for r in self.db.execute("PRAGMA table_info(links)")}
        if lcols and "namespace" not in lcols:
            self.db.execute(
                "ALTER TABLE links ADD COLUMN namespace TEXT NOT NULL DEFAULT 'default'")
        if lcols and "type" not in lcols:
            self.db.execute(
                "ALTER TABLE links ADD COLUMN type TEXT NOT NULL DEFAULT 'lexical'")
        if lcols and "status" not in lcols:
            self.db.execute(
                "ALTER TABLE links ADD COLUMN status TEXT NOT NULL DEFAULT 'confirmed'")
        if lcols and "created_at" not in lcols:
            self.db.execute("ALTER TABLE links ADD COLUMN created_at REAL")
        fcols = {r[1] for r in self.db.execute("PRAGMA table_info(facts)")}
        for col, ddl in (("valid_from", "REAL"), ("valid_to", "REAL"),
                         ("supersedes", "INTEGER"), ("source", "TEXT")):
            if fcols and col not in fcols:
                self.db.execute(f"ALTER TABLE facts ADD COLUMN {col} {ddl}")

    # --- escritura -------------------------------------------------------
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
        return cur.lastrowid

    def dormant_fact_ids(self) -> set:
        """ids de hechos cuya sombra textual está latente o superada (no vigentes)."""
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
        return cur.lastrowid

    def close_fact(self, fact_id: int, when: float | None = None):
        """Cierra la vigencia de un hecho (deja de ser cierto AHORA, pero se conserva:
        es historia, no una contradicción destruida)."""
        self.db.execute(
            "UPDATE facts SET valid_to = ? WHERE id = ? AND namespace = ? AND valid_to IS NULL",
            (when if when is not None else time.time(), fact_id, self.namespace))
        self._commit()

    def all_facts(self, only_current: bool = False, at: float | None = None
                  ) -> list[sqlite3.Row]:
        """Hechos del contexto. `only_current`: solo los vigentes. `at`: los que eran
        ciertos en ese instante (consulta histórica)."""
        q = "SELECT * FROM facts WHERE namespace = ?"
        args: list = [self.namespace]
        if at is not None:
            q += " AND (valid_from IS NULL OR valid_from <= ?) AND (valid_to IS NULL OR valid_to > ?)"
            args += [at, at]
        elif only_current:
            q += " AND valid_to IS NULL"
        return self.db.execute(q, args).fetchall()

    def link(self, src: int, dst: int, weight: float = 1.0,
             type: str = "lexical", status: str = "confirmed"):
        """Crea/refuerza una asociación. `type` dice de dónde viene (observada,
        actualización, consolidación o hipótesis de sueño) y `status` si es evidencia
        CONFIRMADA o solo una propuesta. Solo lo confirmado propaga activación."""
        if src == dst:
            return
        # Peso acotado a [0,1]: al repetir, se satura hacia 1 (no crece sin límite,
        # que amplificaría la propagación en vez de atenuarla). Enlace etiquetado
        # con el namespace: nunca se cruzan contextos.
        w = min(1.0, max(0.0, weight))
        self.db.execute(
            "INSERT INTO links(src,dst,weight,namespace,type,status,created_at) "
            "VALUES(?,?,?,?,?,?,?) "
            "ON CONFLICT(src,dst) DO UPDATE SET weight = weight + 0.3 * (1.0 - weight)",
            (src, dst, w, self.namespace, type, status, time.time()),
        )
        self._commit()

    def set_link_status(self, a: int, b: int, status: str):
        """Confirma o rechaza una hipótesis (enlace propuesto)."""
        self.db.execute(
            "UPDATE links SET status=? WHERE namespace=? AND "
            "((src=? AND dst=?) OR (src=? AND dst=?))",
            (status, self.namespace, a, b, b, a))
        self._commit()

    def proposed_links(self) -> list[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM links WHERE namespace=? AND status='proposed'",
            (self.namespace,)).fetchall()

    def touch(self, ids: list[int], boost: float = 0.5):
        """Reforzar recuerdos usados: sube strength, access_count, last_access."""
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

    def mark_superseded(self, ids: list[int]):
        """Marca recuerdos como reemplazados por otro más nuevo y los debilita
        (no se borran: quedan como historia, pero dejan de dominar la recuperación)."""
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

    def delete(self, ids: list[int]):
        self.db.executemany("DELETE FROM memories WHERE id = ? AND namespace = ?",
                            [(i, self.namespace) for i in ids])
        self.db.executemany(
            "DELETE FROM links WHERE (src=? OR dst=?) AND namespace = ?",
            [(i, i, self.namespace) for i in ids])
        self._commit()

    def mark_dormant(self, ids: list[int]):
        """Adormece recuerdos: olvidados-pero-NO-borrados. Salen de la recuperación
        normal, pero quedan latentes y pueden resurgir (ver Hipercampo.muse)."""
        self.db.executemany(
            "UPDATE memories SET dormant = 1 WHERE id = ? AND namespace = ?",
            [(i, self.namespace) for i in ids],
        )
        self._commit()

    def reactivate(self, ids: list[int]):
        """Despierta recuerdos latentes (un recuerdo que resurge)."""
        self.db.executemany(
            "UPDATE memories SET dormant = 0, last_access = ? WHERE id = ? AND namespace = ?",
            [(time.time(), i, self.namespace) for i in ids],
        )
        self._commit()

    # --- lectura (siempre acotada al namespace del store) ----------------
    def all(self, kind=None, only_active=True, include_dormant=False) -> list[sqlite3.Row]:
        q = "SELECT * FROM memories WHERE namespace = ?"
        args: list = [self.namespace]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        if only_active:
            q += " AND consolidated = 0"
        if not include_dormant:
            q += " AND dormant = 0"
        return self.db.execute(q, args).fetchall()

    def get(self, mem_id: int):
        # También acotado al namespace: un inquilino no puede leer id de otro.
        return self.db.execute(
            "SELECT * FROM memories WHERE id=? AND namespace=?",
            (mem_id, self.namespace),
        ).fetchone()

    def neighbors(self, mem_id: int, include_proposed: bool = False) -> list[tuple[int, float]]:
        """Vecinos por asociaciones CONFIRMADAS. Las hipótesis (status='proposed')
        NO propagan activación hasta que se aceptan: lo especulativo no contamina
        la memoria observada."""
        estados = ("confirmed", "proposed") if include_proposed else ("confirmed",)
        marks = ",".join("?" * len(estados))
        rows = self.db.execute(
            f"SELECT dst, weight FROM links WHERE src=? AND namespace=? AND status IN ({marks}) "
            f"UNION SELECT src, weight FROM links WHERE dst=? AND namespace=? AND status IN ({marks})",
            (mem_id, self.namespace, *estados, mem_id, self.namespace, *estados),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def hv_of(self, row) -> np.ndarray:
        return from_blob(row["hv"])

    def commit(self):
        self.db.commit()

    def close(self):
        # Checkpoint + truncado del WAL: deja el fichero consistente y elimina los
        # -wal/-shm (evita bloqueos residuales, sobre todo en Windows).
        try:
            self.db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        self.db.close()
