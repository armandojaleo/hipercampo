"""
Simulaciones de FALLO REAL: lo que pasa cuando el mundo se rompe de verdad.

No basta con clasificar errores en @resiliente: aquí se PROVOCAN — base de solo
lectura, disco que no admite más bytes, proceso matado a mitad de una escritura o
de un sueño — y se comprueba la promesa: avisar sin mentir, no corromper nunca,
y poder continuar donde se pudo.

Ejecuta:  python tests/test_failures.py
"""

import os
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar, memoria      # noqa: E402
from hipercampo.memory import Hipercampo            # noqa: E402


# --- base de datos de SOLO LECTURA ------------------------------------------

def test_bd_de_solo_lectura_avisa_sin_reintentar():
    hc = memoria("fail_ro")
    hc.remember("un recuerdo previo al bloqueo de escritura", 0.6)
    hc.store.close()
    ruta = hc.store.path
    os.chmod(ruta, stat.S_IREAD)                    # el fichero pasa a solo lectura
    try:
        ro = Hipercampo(ruta, namespace="test")     # abrir para leer debe poder
        r = ro.remember("esto no deberia poder grabarse", 0.6)
        assert isinstance(r, dict) and "error" in r, f"debió avisar: {r}"
        assert r.get("reintentado") is False, (
            f"reintentó una escritura en una BD de solo lectura: {r}")
        hits = ro.recall("recuerdo previo al bloqueo")
        assert hits and "previo" in hits[0]["text"], "leer sí debe funcionar"
        ro.store.close()
    finally:
        os.chmod(ruta, stat.S_IWRITE | stat.S_IREAD)


# --- disco lleno (simulado en el punto exacto de la escritura) --------------

def test_disco_lleno_avisa_y_no_corrompe():
    hc = memoria("fail_full")
    hc.remember("lo que ya estaba guardado antes de llenarse el disco", 0.7)

    original = hc.store.add
    def add_sin_espacio(*a, **kw):
        raise sqlite3.OperationalError("database or disk is full")
    hc.store.add = add_sin_espacio

    r = hc.remember("este recuerdo no cabe en el disco", 0.6)
    assert isinstance(r, dict) and "error" in r, f"debió avisar: {r}"
    assert r.get("reintentado") is False, f"reintentó con el disco lleno: {r}"

    hc.store.add = original                         # el disco "se vacía"
    assert hc.health()["sana"] is True, "el fallo de espacio no debe corromper"
    hits = hc.recall("lo que estaba guardado antes de llenarse")
    assert hits, "lo anterior debe seguir ahí"
    r2 = hc.remember("con espacio de nuevo si que se puede", 0.6)
    assert r2.get("stored") is True, "recuperado el espacio, debe funcionar"


# --- proceso MATADO a mitad de escritura ------------------------------------

_GUION_ESCRITOR = r"""
import sys, os
sys.path.insert(0, {raiz!r})
os.environ["HIPERCAMPO_LOG"] = "0"
from hipercampo.memory import Hipercampo
hc = Hipercampo({db!r}, namespace="test")
for i in range(1000):
    hc.remember(f"recuerdo numero {{i}} escrito justo antes de morir el proceso", 0.6)
    print(i, flush=True)                    # el padre nos matará en plena faena
"""


def _matar_a_mitad(guion: str) -> None:
    p = subprocess.Popen([sys.executable, "-c", guion], stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True)
    for linea in p.stdout:                          # esperar a que esté escribiendo
        if linea.strip() == "5":
            p.kill()                                # muerte súbita, sin despedidas
            break
    p.wait(timeout=30)


def test_proceso_matado_escribiendo_no_corrompe():
    limpiar()
    db = "data/_t_fail_kill.db"
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)
    raiz = str(Path(__file__).resolve().parent.parent)
    _matar_a_mitad(_GUION_ESCRITOR.format(raiz=raiz, db=db))

    hc = Hipercampo(db, namespace="test")           # reabrir tras la muerte
    h = hc.health(full=True)
    assert h["integridad"] == "ok", f"la muerte súbita corrompió la BD: {h}"
    total = hc.stats()["total_fisico"]
    assert total >= 5, f"se perdieron escrituras confirmadas: {total}"
    r = hc.remember("la vida sigue despues del proceso muerto", 0.6)
    assert r.get("stored") is True
    hc.store.close()
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)


# --- proceso MATADO a mitad de un sueño -------------------------------------

_GUION_DURMIENTE = r"""
import sys, os
sys.path.insert(0, {raiz!r})
os.environ["HIPERCAMPO_LOG"] = "0"
from hipercampo import memory
from hipercampo.memory import Hipercampo
hc = Hipercampo({db!r}, namespace="test")
for i in range(12):
    hc.remember(f"episodio repetitivo sobre el mismo tema numero {{i}}", 0.6)

_consolidar = hc.consolidate
def consolidar_y_avisar():
    print("durmiendo", flush=True)          # señal: el padre nos mata AQUI
    import time; time.sleep(10)             # ventana amplia para el kill
    return _consolidar()
hc.consolidate = consolidar_y_avisar
hc.sleep()
"""


def test_proceso_matado_durmiendo_no_corrompe_y_reintenta():
    limpiar()
    db = "data/_t_fail_sleep.db"
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)
    raiz = str(Path(__file__).resolve().parent.parent)
    p = subprocess.Popen([sys.executable, "-c",
                          _GUION_DURMIENTE.format(raiz=raiz, db=db)],
                         stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    for linea in p.stdout:
        if linea.strip() == "durmiendo":
            p.kill()
            break
    p.wait(timeout=30)

    hc = Hipercampo(db, namespace="test")
    h = hc.health(full=True)
    assert h["integridad"] == "ok", f"morir durmiendo corrompió la BD: {h}"
    # el sueño no llegó a completarse: el contador NO debe decir que sí
    assert not hc.store.get_meta("last_sleep_success", None), (
        "afirma haber dormido un sueño que fue interrumpido")
    r = hc.sleep()                                  # reintentar el sueño, ya en paz
    assert "error" not in r, f"el sueño debe poder completarse después: {r}"
    hc.store.close()
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
