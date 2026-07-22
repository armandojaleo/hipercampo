"""
Tests de SALUD y AUTO-RECUPERACIÓN: si la memoria falla, avisa, reconecta y sigue.
Ejecuta:  python tests/test_resilience.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar, memoria      # noqa: E402


def test_health_dice_que_esta_sana():
    hc = memoria("res_health")
    h = hc.health()
    assert h["sana"] is True, h
    assert h["integridad"] == "ok" and h["esquema"] == "ok"
    assert h["escribible"] is True


def test_recall_se_recupera_de_una_conexion_caida():
    hc = memoria("res_recall")
    hc.remember("el servidor de produccion esta alojado en Frankfurt", 0.7)
    hc.store.db.close()                       # simula una caída de la BD
    hits = hc.recall("donde esta el servidor de produccion")
    assert isinstance(hits, list) and hits, "debió reconectar y responder"


def test_remember_se_recupera_de_una_conexion_caida():
    hc = memoria("res_remember")
    hc.remember("primer recuerdo antes de la caida", 0.6)
    hc.store.db.close()
    r = hc.remember("un recuerdo escrito despues de reconectar solo", 0.6)
    assert r.get("stored") is True, r


def test_stats_se_recupera():
    hc = memoria("res_stats")
    hc.remember("algo que contar en las estadisticas", 0.5)
    hc.store.db.close()
    s = hc.stats()
    assert s.get("total", 0) >= 1, s


def test_un_fallo_irrecuperable_devuelve_error_legible():
    hc = memoria("res_error")
    hc.remember("recuerdo previo al desastre", 0.5)
    # rompemos la conexión Y la ruta: la reconexión también fallará
    hc.store.db.close()
    hc.store.path = "Z:/ruta/que/no/existe/imposible.db"
    r = hc.recall("cualquier cosa")
    assert isinstance(r, dict) and "error" in r, f"debe avisar, no reventar: {r}"
    assert "doctor" in r.get("sugerencia", ""), r
    hc.store.path = ""                        # evitar que limpiar toque rutas raras


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
