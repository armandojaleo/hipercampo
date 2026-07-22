"""
Tests de las correcciones de robustez (auditoría externa). Ejecuta:
    python tests/test_hardening.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_hard.db"
_cur = None


def fresh():
    global _cur
    if _cur is not None:
        _cur.store.close()
    Path(_DB).unlink(missing_ok=True)
    _cur = Hipercampo(_DB)
    return _cur


# recall ABSTIENE ante ruido y NO refuerza falsos positivos ------------------
def test_recall_se_abstiene_ante_ruido():
    hc = fresh()
    hc.remember("el gato duerme en el sofá", 0.5)
    hc.remember("python es un lenguaje de programación", 0.5)
    hits = hc.recall("xylófono cuántico marciano zzzz qwerty", k=3)
    assert hits == [], f"debería abstenerse ante ruido: {hits}"


def test_recall_no_refuerza_irrelevantes():
    hc = fresh()
    mid = hc.remember("la factura del cliente vence el día diez", 0.5)["id"]
    hc.recall("tema totalmente ajeno plutonio banana", k=3)   # no debe tocar nada
    ac = hc.store.get(mid)["access_count"]
    assert ac == 0, f"un recuerdo irrelevante no debería reforzarse: access={ac}"


# hc_update SEGURO ------------------------------------------------------------
def test_update_sin_match_no_pisa_nada():
    hc = fresh()
    victima = hc.remember("el color corporativo es azul", 0.6)["id"]
    r = hc.update("algo completamente distinto sobre cohetes lunares",
                  "los cohetes usan hidrógeno líquido")
    assert r["updated"] is False, "no debería reemplazar sin match fiable"
    assert hc.store.get(victima)["superseded"] == 0, "no debió tocar la víctima"


def test_update_por_id_es_exacto():
    hc = fresh()
    a = hc.remember("dato uno", 0.5)["id"]
    b = hc.remember("dato dos completamente diferente", 0.5)["id"]
    r = hc.update("", "dato uno corregido", memory_id=a)
    assert r["updated"] and r["superseded_id"] == a
    assert hc.store.get(b)["superseded"] == 0


# recall excluye historia por defecto ----------------------------------------
def test_recall_excluye_superados_por_defecto():
    hc = fresh()
    hc.remember("el servidor está en Frankfurt", 0.6)
    hc.update("dónde está el servidor", "el servidor está en Dublín")
    sin = hc.recall("dónde está el servidor", k=5)
    assert not any("Frankfurt" in h["text"] for h in sin), "Frankfurt está superado"
    con = hc.recall("dónde está el servidor", k=5, include_history=True)
    assert any("Frankfurt" in h["text"] for h in con), "con historia sí debe verse"


# pesos de asociación acotados a <= 1 ----------------------------------------
def test_pesos_de_link_acotados():
    hc = fresh()
    a = hc.remember("alfa bravo charlie delta", 0.5)["id"]
    b = hc.remember("alfa bravo charlie echo", 0.5)["id"]
    for _ in range(20):                       # martillear el mismo enlace
        hc.store.link(a, b, 0.9)
    pesos = [w for _, w in hc.store.neighbors(a)]
    assert pesos and max(pesos) <= 1.0, f"los pesos no deben superar 1.0: {pesos}"


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
