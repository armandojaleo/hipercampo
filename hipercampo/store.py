"""
Persistencia en SQLite. Guarda los recuerdos (episódicos y semánticos), sus
hipervectores empaquetados, y el grafo de asociaciones para la propagación de
activación.

Un solo fichero .db portátil. En Docker vive en el volumen /data.
"""

import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path

import numpy as np

from .vsa import from_blob, to_blob

# Precedencia de un enlace cuando se vuelve a observar el mismo par. Manda el de
# mayor rango; a igualdad, gana lo que ya había (la evidencia no se pisa a sí misma).
#
#   4  evidencia observada (lexical | update | consolidation) confirmada
#   3  hipótesis RECHAZADA — solo una observación real la resucita; volver a
#      proponerla, no (si no, insistir bastaría para colar lo ya descartado)
#   2  hipótesis de sueño ya CONFIRMADA
#   1  hipótesis de sueño solo PROPUESTA (no propaga)
def _rank(t: str, s: str) -> str:
    return (f"CASE WHEN {t}<>'dream' THEN 4 "
            f"WHEN {s}='rejected' THEN 3 "
            f"WHEN {s}='proposed' THEN 1 ELSE 2 END")


_RANK_NEW = _rank("excluded.type", "excluded.status")
_RANK_OLD = _rank("links.type", "links.status")

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
CREATE TABLE IF NOT EXISTS meta (
    namespace TEXT NOT NULL,
    key       TEXT NOT NULL,
    value     TEXT,
    PRIMARY KEY (namespace, key)
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
    def __init__(self, path: str = "data/hipercampo.db", namespace: str = "default",
                 linked: tuple = ()):
        self.path = path
        self.namespace = namespace          # dónde se ESCRIBE: siempre uno solo
        # Contextos ENLAZADOS: se pueden LEER, nunca escribir. Así un proyecto puede
        # inspirarse en lo aprendido en otro sin poder ensuciarlo ni ser ensuciado.
        self.linked = tuple(dict.fromkeys(n for n in linked if n and n != namespace))
        self._ns_lectura = (namespace, *self.linked)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._txn_depth = 0
        self._connect()

    def _connect(self) -> None:
        """Abre la conexión y deja el esquema al día. Reutilizable para reconectar."""
        # WAL + espera ante bloqueo: varios procesos/hilos pueden leer mientras uno
        # escribe, sin corromper. Base para acceso concurrente.
        self.db = sqlite3.connect(self.path, timeout=30.0)
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

    def matrix(self, rows) -> np.ndarray:
        """Matriz (N x 1250) con los hipervectores de esas filas, para comparar de
        una vez con similarity_batch. Evita repetir el mismo apilado por todo el código."""
        from .vsa import stack_hvs
        return stack_hvs([r["hv"] for r in rows])

    # --- salud y recuperación --------------------------------------------
    def health(self, full: bool = False) -> dict:
        """¿Está sana la memoria? Integridad del fichero, esquema y escritura REAL.

        Por defecto usa `quick_check` (barato aunque la memoria crezca); con
        `full=True` corre el `integrity_check` completo (`hipercampo doctor --full`)."""
        info = {"db": os.path.abspath(self.path), "namespace": self.namespace}
        try:
            comprobacion = "integrity_check" if full else "quick_check"
            info["integridad"] = self.db.execute(f"PRAGMA {comprobacion}").fetchone()[0]
            info["comprobacion"] = comprobacion
        except Exception as e:
            info["integridad"] = f"ERROR: {e}"
        try:
            tablas = {r[0] for r in self.db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            faltan = {"memories", "links", "facts", "meta"} - tablas
            info["esquema"] = "ok" if not faltan else f"faltan tablas: {sorted(faltan)}"
        except Exception as e:
            info["esquema"] = f"ERROR: {e}"
        try:
            self.db.execute("SELECT 1 FROM memories LIMIT 1").fetchone()
            info["lectura"] = "ok"
        except Exception as e:
            info["lectura"] = f"ERROR: {e}"
        # Escritura REAL, no permisos del directorio: os.access no ve el disco lleno,
        # ni un fichero .db de solo lectura, ni un WAL que no se puede crear. Escribimos
        # de verdad dentro de un SAVEPOINT y lo deshacemos: no deja rastro.
        try:
            self.db.execute("SAVEPOINT hc_health")
            self.db.execute(                       # sin set_meta: haría commit y
                "INSERT INTO meta(namespace,key,value) "   # soltaría el SAVEPOINT
                "VALUES(?,'_health_probe','1') "
                "ON CONFLICT(namespace,key) DO UPDATE SET value='1'", (self.namespace,))
            self.db.execute("ROLLBACK TO hc_health")
            self.db.execute("RELEASE hc_health")
            info["escribible"] = True
        except Exception as e:
            try:
                self.db.execute("RELEASE hc_health")
            except Exception:
                pass
            info["escribible"] = False
            info["escritura_error"] = str(e)

        for clave, etiqueta in (("schema_version", "version_esquema"),
                                ("last_sleep_success", "ultimo_sueno_ok"),
                                ("last_sleep_error", "ultimo_sueno_error"),
                                ("writes_since_sleep", "escrituras_sin_dormir")):
            try:
                info[etiqueta] = self.get_meta(clave, None)
            except Exception:
                info[etiqueta] = None
        try:
            wal = os.path.abspath(self.path) + "-wal"
            info["wal_bytes"] = os.path.getsize(wal) if os.path.exists(wal) else 0
        except Exception:
            info["wal_bytes"] = None

        info["sana"] = (info.get("integridad") == "ok" and info.get("esquema") == "ok"
                        and info.get("lectura") == "ok" and info["escribible"])
        return info

    def reconnect(self) -> None:
        """Reabre la conexión (recuperación ante un fallo de la BD)."""
        try:
            self.db.close()
        except Exception:
            pass
        self._connect()

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

    def _columnas(self, tabla: str) -> set:
        return {r[1] for r in self.db.execute(f"PRAGMA table_info({tabla})")}

    def _añadir(self, tabla: str, columna: str, ddl: str):
        """ALTER TABLE idempotente: si la columna ya está, no hace nada."""
        cols = self._columnas(tabla)
        if cols and columna not in cols:
            self.db.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {ddl}")

    # Migraciones VERSIONADAS. Cada una es idempotente y se aplica en una
    # transacción; al terminar se graba `PRAGMA user_version`. Una BD antigua
    # (user_version=0) las recorre todas: los pasos ya aplicados no hacen nada,
    # así que reanudar tras una interrupción es seguro.
    def _m001_confianza_y_relevo(self):
        self._añadir("memories", "superseded", "INTEGER NOT NULL DEFAULT 0")
        self._añadir("memories", "confidence", "REAL NOT NULL DEFAULT 0.5")

    def _m002_namespaces(self):
        self._añadir("memories", "namespace", "TEXT NOT NULL DEFAULT 'default'")
        self._añadir("links", "namespace", "TEXT NOT NULL DEFAULT 'default'")

    def _m003_latencia_y_enlaces_tipados(self):
        self._añadir("memories", "dormant", "INTEGER NOT NULL DEFAULT 0")
        self._añadir("links", "type", "TEXT NOT NULL DEFAULT 'lexical'")
        self._añadir("links", "status", "TEXT NOT NULL DEFAULT 'confirmed'")
        self._añadir("links", "created_at", "REAL")

    def _m004_hechos_con_historia(self):
        self._añadir("memories", "fact_id", "INTEGER")
        for col, ddl in (("valid_from", "REAL"), ("valid_to", "REAL"),
                         ("supersedes", "INTEGER"), ("source", "TEXT")):
            self._añadir("facts", col, ddl)

    def _m006_reescribir_filas_antiguas(self):
        """`ALTER TABLE ADD COLUMN ... NOT NULL DEFAULT` no reescribe las filas ya
        existentes: SQLite les sirve el valor por defecto al leer, pero el registro
        en disco sigue sin esa columna, y `integrity_check` lo denuncia
        ("NULL value in memories.confidence") en algunas versiones. Un UPDATE que
        no cambia nada sí reescribe el registro completo y lo deja consistente."""
        for tabla, columna in (("memories", "confidence"), ("memories", "superseded"),
                               ("memories", "namespace"), ("memories", "dormant"),
                               ("links", "namespace"), ("links", "type"),
                               ("links", "status")):
            if columna in self._columnas(tabla):
                self.db.execute(f"UPDATE {tabla} SET {columna} = {columna}")

    def _m005_metadatos_de_salud(self):
        # Un enlace solo puede estar en uno de estos estados; una BD antigua con
        # basura queda normalizada antes de que la máquina de estados dependa de ella.
        if not self._columnas("links"):
            return
        # Leer antes de escribir: si no hay nada que normalizar (el caso normal) no
        # pedimos el lock de escritura, y varios procesos pueden abrir a la vez.
        hay = self.db.execute(
            "SELECT 1 FROM links WHERE status NOT IN "
            "('proposed','confirmed','rejected') LIMIT 1").fetchone()
        if hay:
            self.db.execute("UPDATE links SET status='confirmed' "
                            "WHERE status NOT IN ('proposed','confirmed','rejected')")

    _MIGRACIONES = [
        (1, "confianza_y_relevo", _m001_confianza_y_relevo),
        (2, "namespaces", _m002_namespaces),
        (3, "latencia_y_enlaces_tipados", _m003_latencia_y_enlaces_tipados),
        (4, "hechos_con_historia", _m004_hechos_con_historia),
        (5, "metadatos_de_salud", _m005_metadatos_de_salud),
        (6, "reescribir_filas_antiguas", _m006_reescribir_filas_antiguas),
    ]
    SCHEMA_VERSION = 6

    # Columnas que _SCHEMA crea de fábrica: si están TODAS, la BD ya nació al día.
    _COLUMNAS_ACTUALES = {
        "memories": {"superseded", "confidence", "namespace", "dormant", "fact_id"},
        "links": {"namespace", "type", "status", "created_at"},
        "facts": {"valid_from", "valid_to", "supersedes", "source"},
    }

    def _al_dia(self) -> bool:
        """¿La BD acaba de nacer con el esquema actual? Exigimos las columnas de
        fábrica Y que esté vacía: una base heredada a medio migrar (con las columnas
        ya añadidas pero la versión sin sellar) debe recorrer los pasos igualmente."""
        try:
            if not all(esperadas <= self._columnas(tabla)
                       for tabla, esperadas in self._COLUMNAS_ACTUALES.items()):
                return False
            return not self.db.execute("SELECT 1 FROM memories LIMIT 1").fetchone()
        except sqlite3.Error:
            return False

    def _copia_previa(self, version: int):
        """Copia de seguridad ANTES de tocar el esquema de una BD con datos. Si algo
        sale mal, los recuerdos siguen ahí. No se hace para una BD recién creada
        (nada que perder) ni en memoria."""
        if self.path in ("", ":memory:") or not os.path.exists(self.path):
            return
        destino = f"{self.path}.bak-v{version}"
        if os.path.exists(destino):
            return                                  # ya hay copia de este salto
        try:
            if not self.db.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' "
                    "AND name='memories'").fetchone():
                return                              # BD nueva: nada que respaldar
            copia = sqlite3.connect(destino)        # `with` haría commit, no close
            try:
                self.db.backup(copia)               # copia consistente, no cp
            finally:
                copia.close()
        except Exception:
            pass          # una copia imposible no debe impedir abrir la memoria

    def _migrate(self):
        """Lleva la BD hasta SCHEMA_VERSION, paso a paso y registrando la versión.

        Antes se detectaban columnas sueltas sin dejar constancia de en qué versión
        estaba el fichero; eso ya provocó un fallo al abrir bases antiguas. Ahora
        cada paso es explícito, transaccional y comprobable."""
        actual = self.db.execute("PRAGMA user_version").fetchone()[0]
        if actual >= self.SCHEMA_VERSION:
            return
        # Una BD recién creada por _SCHEMA ya nace con el esquema al día: no hay
        # nada que migrar, solo que sellarlo. Sin esto, varios procesos abriendo a
        # la vez una base nueva se pelean por el lock de escritura para nada.
        if self._al_dia():
            try:
                self.db.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
                self.db.commit()
            except sqlite3.Error:
                pass                       # otro llegó primero: igual de bien
            return

        self._copia_previa(actual)
        for version, nombre, paso in self._MIGRACIONES:
            if version <= actual:
                continue
            try:
                self.db.execute("SAVEPOINT hc_migracion")
                paso(self)
                self.db.execute("RELEASE hc_migracion")
                self.db.execute(f"PRAGMA user_version = {version}")
                self.db.commit()
            except Exception as e:
                try:
                    self.db.execute("ROLLBACK TO hc_migracion")
                    self.db.execute("RELEASE hc_migracion")
                except Exception:
                    pass
                # Otro proceso puede estar migrando la misma BD a la vez: si ya la
                # dejó en esta versión, no hay nada que arreglar (no es un fallo).
                if self.db.execute("PRAGMA user_version").fetchone()[0] >= version:
                    continue
                raise RuntimeError(
                    f"falló la migración {version:03d}_{nombre}: {e} · "
                    f"la BD sigue en la versión {actual}; hay una copia en "
                    f"{self.path}.bak-v{actual}") from e

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

    # --- meta (contadores del propio sistema, por contexto) --------------
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
        # Al repetirse un enlace manda el de MAYOR rango (ver _RANK_SQL): una
        # observación real ASCIENDE una vieja hipótesis (incluso rechazada), pero
        # una hipótesis nunca degrada la evidencia ya confirmada. El peso solo se
        # refuerza si el enlace resultante no queda rechazado: lo descartado no
        # debe engordar a base de reproponerse.
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

    def set_link_status(self, a: int, b: int, status: str) -> int:
        """Resuelve una hipótesis del sueño: proposed → confirmed | rejected.

        SOLO toca enlaces `type='dream'` con `status='proposed'`: una asociación
        observada o ya confirmada no se puede rechazar por accidente, y una
        hipótesis ya resuelta no se re-resuelve. Devuelve cuántas filas cambió
        (0 = no había tal propuesta)."""
        if status not in ("confirmed", "rejected"):
            raise ValueError(f"transición no permitida: proposed → {status}")
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
    def all(self, kind=None, only_active=True, include_dormant=False,
            own_only=False) -> list[sqlite3.Row]:
        # Lectura: el contexto propio MÁS los enlazados (inspiración entre proyectos).
        # La escritura (add/touch/…) sigue acotada a self.namespace: leer no ensucia.
        # own_only=True es para el MANTENIMIENTO (consolidar/olvidar/soñar): cuidar
        # la memoria propia no debe ni leer la ajena — fundir episodios de otro
        # proyecto en un semántico propio sería copiarse su texto.
        ns = (self.namespace,) if own_only else self._ns_lectura
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
        return self.db.execute(q, args).fetchall()

    def get(self, mem_id: int):
        # Acotado a lo LEGIBLE (propio + enlazados): un contexto no enlazado sigue
        # siendo invisible, ni siquiera por id.
        marks = ",".join("?" * len(self._ns_lectura))
        return self.db.execute(
            f"SELECT * FROM memories WHERE id=? AND namespace IN ({marks})",
            (mem_id, *self._ns_lectura),
        ).fetchone()

    def neighbors(self, mem_id: int, include_proposed: bool = False) -> list[tuple[int, float]]:
        """Vecinos por asociaciones CONFIRMADAS. Las hipótesis (status='proposed')
        NO propagan activación hasta que se aceptan: lo especulativo no contamina
        la memoria observada."""
        estados = ("confirmed", "proposed") if include_proposed else ("confirmed",)
        marks = ",".join("?" * len(estados))
        ns_marks = ",".join("?" * len(self._ns_lectura))
        rows = self.db.execute(
            f"SELECT dst, weight FROM links WHERE src=? AND namespace IN ({ns_marks}) "
            f"  AND status IN ({marks}) "
            f"UNION SELECT src, weight FROM links WHERE dst=? AND namespace IN ({ns_marks}) "
            f"  AND status IN ({marks})",
            (mem_id, *self._ns_lectura, *estados, mem_id, *self._ns_lectura, *estados),
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
