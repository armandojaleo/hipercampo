"""
Persistencia en SQLite. Guarda los recuerdos (episódicos y semánticos), sus
hipervectores empaquetados, y el grafo de asociaciones para la propagación de
activación.

Un solo fichero .db portátil. En Docker vive en el volumen /data.
"""

import sqlite3
import time
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
    namespace    TEXT    NOT NULL DEFAULT 'default'     -- aislamiento por inquilino
);
CREATE TABLE IF NOT EXISTS links (
    src    INTEGER NOT NULL,
    dst    INTEGER NOT NULL,
    weight REAL    NOT NULL DEFAULT 1.0,
    PRIMARY KEY (src, dst)
);
CREATE INDEX IF NOT EXISTS idx_kind ON memories(namespace, kind, consolidated);
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
        self.db.executescript(_SCHEMA)
        self._migrate()
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

    # --- escritura -------------------------------------------------------
    def add(self, text, hv, novelty, importance, confidence=0.5, kind="episodic") -> int:
        now = time.time()
        cur = self.db.execute(
            "INSERT INTO memories(text,kind,hv,novelty,importance,confidence,strength,"
            "created,last_access,namespace) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (text, kind, to_blob(hv), novelty, importance, confidence, 1.0, now, now,
             self.namespace),
        )
        self.db.commit()
        return cur.lastrowid

    def link(self, src: int, dst: int, weight: float = 1.0):
        if src == dst:
            return
        # Peso acotado a [0,1]: al repetir, se satura hacia 1 (no crece sin límite,
        # que amplificaría la propagación en vez de atenuarla).
        w = min(1.0, max(0.0, weight))
        self.db.execute(
            "INSERT INTO links(src,dst,weight) VALUES(?,?,?) "
            "ON CONFLICT(src,dst) DO UPDATE SET weight = weight + 0.3 * (1.0 - weight)",
            (src, dst, w),
        )
        self.db.commit()

    def touch(self, ids: list[int], boost: float = 0.5):
        """Reforzar recuerdos usados: sube strength, access_count, last_access."""
        now = time.time()
        self.db.executemany(
            "UPDATE memories SET access_count = access_count + 1, "
            "last_access = ?, strength = strength + ? WHERE id = ?",
            [(now, boost, i) for i in ids],
        )
        self.db.commit()

    def reinforce(self, mem_id: int, boost: float = 0.7):
        self.db.execute(
            "UPDATE memories SET strength = strength + ?, access_count = access_count + 1 "
            "WHERE id = ?",
            (boost, mem_id),
        )
        self.db.commit()

    def set_strength(self, mem_id: int, strength: float):
        self.db.execute("UPDATE memories SET strength=? WHERE id=?", (strength, mem_id))

    def mark_superseded(self, ids: list[int]):
        """Marca recuerdos como reemplazados por otro más nuevo y los debilita
        (no se borran: quedan como historia, pero dejan de dominar la recuperación)."""
        self.db.executemany(
            "UPDATE memories SET superseded = 1, strength = MIN(strength, 0.3), "
            "confidence = MIN(confidence, 0.3) WHERE id = ?",
            [(i,) for i in ids],
        )
        self.db.commit()

    def mark_consolidated(self, ids: list[int]):
        self.db.executemany(
            "UPDATE memories SET consolidated = 1 WHERE id = ?", [(i,) for i in ids]
        )
        self.db.commit()

    def delete(self, ids: list[int]):
        self.db.executemany("DELETE FROM memories WHERE id = ?", [(i,) for i in ids])
        self.db.executemany("DELETE FROM links WHERE src=? OR dst=?",
                            [(i, i) for i in ids])
        self.db.commit()

    # --- lectura (siempre acotada al namespace del store) ----------------
    def all(self, kind=None, only_active=True) -> list[sqlite3.Row]:
        q = "SELECT * FROM memories WHERE namespace = ?"
        args: list = [self.namespace]
        if kind:
            q += " AND kind = ?"
            args.append(kind)
        if only_active:
            q += " AND consolidated = 0"
        return self.db.execute(q, args).fetchall()

    def get(self, mem_id: int):
        # También acotado al namespace: un inquilino no puede leer id de otro.
        return self.db.execute(
            "SELECT * FROM memories WHERE id=? AND namespace=?",
            (mem_id, self.namespace),
        ).fetchone()

    def neighbors(self, mem_id: int) -> list[tuple[int, float]]:
        rows = self.db.execute(
            "SELECT dst, weight FROM links WHERE src=? "
            "UNION SELECT src, weight FROM links WHERE dst=?",
            (mem_id, mem_id),
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    def hv_of(self, row) -> np.ndarray:
        return from_blob(row["hv"])

    def commit(self):
        self.db.commit()

    def close(self):
        self.db.close()
