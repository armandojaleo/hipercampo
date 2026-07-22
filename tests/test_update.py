"""
Tests de ACTUALIZACIÓN de hechos (supersesión) — la grieta de las contradicciones.
Ejecuta:  python tests/test_update.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_update.db"
_cur = None


def fresh():
    global _cur
    if _cur is not None:
        _cur.store.close()
    Path(_DB).unlink(missing_ok=True)
    _cur = Hipercampo(_DB)
    return _cur


def test_update_reemplaza_el_hecho_viejo():
    hc = fresh()
    hc.remember("el servidor de producción está alojado en Frankfurt", 0.7)
    r = hc.update("dónde está alojado el servidor de producción",
                  "el servidor de producción está alojado en Dublín")
    assert r["updated"] and r["superseded_id"] is not None
    # el recall debe devolver Dublín por encima de Frankfurt
    hits = hc.recall("¿dónde está el servidor de producción?", k=3)
    assert hits and "Dublín" in hits[0]["text"], f"esperaba Dublín primero: {hits[0]['text']}"


def test_lo_superado_queda_pero_demovido():
    hc = fresh()
    hc.remember("el certificado ssl caduca el quince de diciembre", 0.7)
    hc.update("cuándo caduca el certificado ssl",
              "el certificado ssl caduca el treinta de marzo")
    textos = [r["text"] for r in hc.store.all(only_active=False)]
    # ambas versiones existen (historia), pero la vieja está marcada superada
    assert any("diciembre" in t for t in textos)
    assert any("marzo" in t for t in textos)
    viejo = [r for r in hc.store.all(only_active=False) if "diciembre" in r["text"]][0]
    assert viejo["superseded"] == 1


def test_remember_avisa_de_posible_actualizacion():
    hc = fresh()
    hc.remember("Armando prefiere respuestas honestas y directas", 0.8)
    r = hc.remember("Armando prefiere respuestas honestas y directas y breves", 0.8)
    # muy parecido -> debe incluir el aviso para que el LLM decida usar hc_update
    assert "similar_to" in r, "debería avisar de un recuerdo parecido"


def test_hechos_distintos_no_se_pisan():
    hc = fresh()
    hc.remember("el servidor de producción está en Frankfurt", 0.7)
    r = hc.remember("el servidor de pruebas se reinicia los domingos", 0.7)
    # son distintos: el segundo se guarda normal y NO marca supersesión ni aviso fuerte
    assert r["stored"] is True
    assert "similar_to" not in r


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
