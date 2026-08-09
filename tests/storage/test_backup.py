"""
Tests de COPIA DE SEGURIDAD y RESTAURACIÓN.

Es el código que salva los datos: si falla en silencio, el usuario se entera el
día que ya no hay nada que recuperar. Aquí se comprueba que la copia es
consistente (aunque haya alguien escribiendo), que la vuelta atrás funciona, y
que restaurar NUNCA destruye sin dejar red.

Ejecuta:  python tests/test_backup.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean, memory      # noqa: E402
from hipercampo.storage.backup import backup, restore       # noqa: E402
from hipercampo.cycle.memory import Hipercampo            # noqa: E402

_COPIA = "data/_t_copia.db"


def _limpiar_copias():
    for p in Path("data").glob("_t_copia*"):
        p.unlink(missing_ok=True)
    for p in Path("data").glob("*.before-restore"):
        p.unlink(missing_ok=True)


def test_backup_preserves_memories():
    hc = memory("bk_basico")
    hc.remember("el faro de alejandria fue uno de los siete prodigios", 0.8)
    hc.remember("la biblioteca de alejandria ardio y se perdio mucho saber", 0.8)
    _limpiar_copias()
    destino = backup(_COPIA, src=hc.store.path)
    assert Path(destino).exists()

    copia = Hipercampo(_COPIA, namespace="test")
    textos = [r["text"] for r in copia.store.all(only_active=False)]
    assert any("faro" in t for t in textos) and any("biblioteca" in t for t in textos)
    assert copia.health(full=True)["healthy"] is True, "la copia debe estar sana"
    copia.store.close()
    _limpiar_copias()


def test_backup_is_consistent_with_live_memory():
    """La API de backup de SQLite copia en caliente: no hace falta parar el servidor."""
    hc = memory("bk_caliente")
    for i in range(20):
        hc.remember(f"recuerdo numero {i} escrito mientras se copia la memoria", 0.5)
    _limpiar_copias()
    destino = backup(_COPIA, src=hc.store.path)     # sin cerrar la memoria viva
    con = sqlite3.connect(destino)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    n = con.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
    con.close()
    assert n >= 20, f"la copia en caliente perdió filas: {n}"
    _limpiar_copias()


def test_restore_returns_previous_contents():
    hc = memory("bk_ida_vuelta")
    hc.remember("dato original que hay que poder recuperar entero", 0.8)
    ruta = hc.store.path
    _limpiar_copias()
    backup(_COPIA, src=ruta)

    hc.remember("dato posterior a la copia que se perdera al restaurar", 0.7)
    hc.store.close()

    restore(_COPIA, dst=ruta)
    vuelto = Hipercampo(ruta, namespace="test")
    textos = [r["text"] for r in vuelto.store.all(only_active=False)]
    assert any("dato original" in t for t in textos), "no restauró lo de la copia"
    assert not any("posterior" in t for t in textos), "restauró de más"
    vuelto.store.close()
    _limpiar_copias()


def test_restore_backs_up_replaced_data():
    """Restaurar la copia equivocada es fácil: debe quedar red de seguridad."""
    hc = memory("bk_red")
    hc.remember("memoria viva que no quiero perder por un despiste", 0.9)
    ruta = hc.store.path
    _limpiar_copias()
    otra = Hipercampo(_COPIA, namespace="test")     # una copia con OTRO contenido
    otra.remember("contenido distinto que voy a restaurar por error", 0.5)
    otra.store.close()
    hc.store.close()

    restore(_COPIA, dst=ruta)
    previa = Path(ruta + ".before-restore")
    assert previa.exists(), "restauró sin guardar lo que destruía"
    con = sqlite3.connect(str(previa))
    textos = [r[0] for r in con.execute("SELECT text FROM memories")]
    con.close()
    assert any("no quiero perder" in t for t in textos), "la red de seguridad está vacía"
    previa.unlink(missing_ok=True)
    _limpiar_copias()


def test_does_not_restore_non_memory_file():
    hc = memory("bk_basura")
    hc.remember("memoria buena que no debe destruirse por un fichero roto", 0.8)
    ruta = hc.store.path
    hc.store.close()
    basura = Path("data/_t_basura.db")
    basura.write_bytes(b"esto no es una base de datos, es texto suelto")
    try:
        restore(str(basura), dst=ruta)
        raise AssertionError("aceptó restaurar un fichero que no es una memoria")
    except ValueError:
        pass
    vuelto = Hipercampo(ruta, namespace="test")     # la buena sigue intacta
    textos = [r["text"] for r in vuelto.store.all(only_active=False)]
    assert any("memoria buena" in t for t in textos), "destruyó la memoria buena"
    vuelto.store.close()
    basura.unlink(missing_ok=True)
    _limpiar_copias()


def test_warns_when_there_is_nothing_to_back_up():
    try:
        backup("data/_t_no_importa.db", src="data/_t_no_existe_jamas.db")
        raise AssertionError("debió avisar de que no hay memoria que respaldar")
    except FileNotFoundError:
        pass
    try:
        restore("data/_t_copia_inexistente.db", dst="data/_t_da_igual.db")
        raise AssertionError("debió avisar de que no existe la copia")
    except FileNotFoundError:
        pass


if __name__ == "__main__":
    clean()
    _limpiar_copias()
    codigo = run_tests(dict(globals()))
    _limpiar_copias()
    sys.exit(codigo)
