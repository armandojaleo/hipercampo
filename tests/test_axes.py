"""
Tests de los CUATRO EJES separados (novedad/importancia/fiabilidad/utilidad).
Cada eje debe tener un efecto DISTINTO y comprobable. Ejecuta:
    python tests/test_axes.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_axes.db"
_cur = None


def fresh():
    global _cur
    if _cur is not None:
        _cur.store.close()
    Path(_DB).unlink(missing_ok=True)
    _cur = Hipercampo(_DB)
    return _cur


def _envejecer(hc, dias):
    hc.store.db.execute("UPDATE memories SET last_access = ?", (time.time() - dias * 86400,))
    hc.store.commit()


# FIABILIDAD afecta al RANKING de recuperación --------------------------------
def test_fiabilidad_sube_el_ranking():
    hc = fresh()
    r = hc.remember("el número de soporte es el 900 123 456", importance=0.5,
                    confidence=0.2)
    mid = r["id"]
    antes = hc.recall("cuál es el número de soporte", k=1)[0]["score"]
    hc.store.db.execute("UPDATE memories SET confidence = 0.95 WHERE id = ?", (mid,))
    hc.store.commit()
    despues = hc.recall("cuál es el número de soporte", k=1)[0]["score"]
    assert despues > antes, f"más fiabilidad debería subir el score: {antes} -> {despues}"


# UTILIDAD (uso real) protege del OLVIDO --------------------------------------
def test_utilidad_protege_del_olvido():
    hc = fresh()
    a = hc.remember("nota trivial: la sala grande es la B", importance=0.2)["id"]
    b = hc.remember("nota trivial: la sala pequeña es la C", importance=0.2)["id"]
    # 'a' se ha usado mucho (alta utilidad); 'b' nunca
    hc.store.db.execute("UPDATE memories SET access_count = 9 WHERE id = ?", (a,))
    hc.store.commit()
    _envejecer(hc, 90)                                  # las dos, viejas
    hc.forget(dry_run=False)
    vivos = {r["id"] for r in hc.store.all(only_active=False)}
    assert a in vivos, "lo MUY usado no debería olvidarse aunque sea trivial"
    assert b not in vivos, "lo trivial y nunca usado sí debería olvidarse"


# IMPORTANCIA protege del OLVIDO (independiente del uso) -----------------------
def test_importancia_protege_aunque_no_se_use():
    hc = fresh()
    imp = hc.remember("dato crítico: el disyuntor general está en el sótano", 0.9)["id"]
    triv = hc.remember("dato trivial: hoy hubo niebla", 0.2)["id"]
    _envejecer(hc, 120)
    hc.forget(dry_run=False)
    vivos = {r["id"] for r in hc.store.all(only_active=False)}
    assert imp in vivos and triv not in vivos


# Los ejes se EXPONEN en el recall --------------------------------------------
def test_recall_expone_los_ejes():
    hc = fresh()
    hc.remember("el wifi de invitados es abierto", importance=0.4, confidence=0.9)
    h = hc.recall("wifi de invitados", k=1)[0]
    assert "confidence" in h and "utility" in h and "strength" in h


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print(f"ok   {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL {name}: {e}")
    if _cur is not None:
        _cur.store.close()
    Path(_DB).unlink(missing_ok=True)
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
