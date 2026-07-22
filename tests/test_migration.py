"""
Test de MIGRACIÓN desde esquemas antiguos. Blinda la regresión que tumbó el
servidor: los índices se creaban ANTES de añadir las columnas que indexan
("no such column: namespace") al abrir una base de datos vieja.
Ejecuta:  python tests/test_migration.py
"""

import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_migr.db"


def _clean():
    for suf in ("", "-wal", "-shm", ".bak-v0"):
        Path(_DB + suf).unlink(missing_ok=True)


def _crear_bd_v0():
    """Esquema ORIGINAL (v0): sin namespace, confidence, superseded, dormant, fact_id."""
    _clean()
    db = sqlite3.connect(_DB)
    db.executescript("""
        CREATE TABLE memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'episodic', hv BLOB NOT NULL,
            novelty REAL NOT NULL DEFAULT 1.0, importance REAL NOT NULL DEFAULT 0.5,
            strength REAL NOT NULL DEFAULT 1.0, access_count INTEGER NOT NULL DEFAULT 0,
            created REAL NOT NULL, last_access REAL NOT NULL,
            consolidated INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE links (src INTEGER NOT NULL, dst INTEGER NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0, PRIMARY KEY (src, dst));
    """)
    now = time.time()
    db.execute("INSERT INTO memories(text,hv,created,last_access) VALUES(?,?,?,?)",
               ("un recuerdo de la version antigua", b"\x00" * 1250, now, now))
    db.commit(); db.close()


def test_abre_una_bd_antigua_sin_romper():
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="proyecto")      # antes: OperationalError
    assert hc.stats()["total"] >= 0
    hc.store.close(); _clean()


def test_migra_y_conserva_los_datos_viejos():
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="default")       # los viejos quedan en 'default'
    textos = [r["text"] for r in hc.store.all(only_active=False)]
    assert any("version antigua" in t for t in textos), "no debe perder lo ya guardado"
    hc.store.close(); _clean()


def test_migra_sin_perder_enlaces():
    """Una BD anterior conserva sus asociaciones (y pasan a ser 'confirmed')."""
    _crear_bd_v0()
    db = sqlite3.connect(_DB)
    now = time.time()
    db.execute("INSERT INTO memories(text,hv,created,last_access) VALUES(?,?,?,?)",
               ("otro recuerdo viejo enlazado", b"\x01" * 1250, now, now))
    db.execute("INSERT INTO links(src,dst,weight) VALUES(1,2,0.9)")
    db.commit(); db.close()

    hc = Hipercampo(_DB, namespace="default")
    vecinos = [d for d, _ in hc.store.neighbors(1)]
    assert 2 in vecinos, "el enlace anterior debe sobrevivir a la migración"
    hc.store.close(); _clean()


def test_registra_la_version_del_esquema():
    """Una BD migrada debe DECIR en qué versión está: sin eso no hay migración
    reanudable ni forma de saber qué pasos faltan."""
    from hipercampo.store import Store
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="default")
    v = hc.store.db.execute("PRAGMA user_version").fetchone()[0]
    assert v == Store.SCHEMA_VERSION, f"esquema sin versionar: {v}"
    hc.store.close(); _clean()


def test_migrar_dos_veces_no_hace_nada_la_segunda():
    """Idempotencia: reabrir una BD ya migrada no vuelve a tocar el esquema."""
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="default"); hc.store.close()
    hc = Hipercampo(_DB, namespace="default")     # segunda apertura
    textos = [r["text"] for r in hc.store.all(only_active=False)]
    assert any("version antigua" in t for t in textos), f"se perdieron datos: {textos}"
    salud = hc.health()
    assert salud["sana"] is True, salud
    hc.store.close(); _clean()


def test_deja_copia_de_seguridad_antes_de_migrar():
    """Si la migración destruyera algo, los recuerdos siguen en la copia."""
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="default")
    hc.store.close()
    copia = Path(_DB + ".bak-v0")
    assert copia.exists(), "migró una BD con datos sin respaldarla"
    db = sqlite3.connect(str(copia))
    n = db.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    db.close(); copia.unlink(missing_ok=True)
    assert n >= 1, "la copia previa está vacía"
    _clean()


def test_normaliza_estados_de_enlace_invalidos():
    """Una BD vieja con estados raros queda normalizada (migración 005)."""
    _crear_bd_v0()
    db = sqlite3.connect(_DB)
    now = time.time()
    db.execute("INSERT INTO memories(text,hv,created,last_access) VALUES(?,?,?,?)",
               ("segundo recuerdo viejo", b"" * 1250, now, now))
    db.execute("INSERT INTO links(src,dst,weight) VALUES(1,2,0.8)")
    db.commit(); db.close()
    hc = Hipercampo(_DB, namespace="default")
    estados = {r[0] for r in hc.store.db.execute("SELECT status FROM links")}
    assert estados <= {"proposed", "confirmed", "rejected"}, estados
    hc.store.close(); _clean()


def test_puede_escribir_tras_migrar():
    _crear_bd_v0()
    hc = Hipercampo(_DB, namespace="default")
    r = hc.remember("algo nuevo despues de migrar el esquema viejo", 0.6)
    assert r["stored"] is True
    hc.store.close(); _clean()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print(f"ok   {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1; print(f"ERROR {name}: {e}")
    _clean()
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
