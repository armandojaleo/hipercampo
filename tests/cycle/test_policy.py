"""
Tests de la política conversacional: qué hacer en cada momento del diálogo.
Ejecuta:  python tests/test_policy.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

_DB = "data/_test_policy.db"
_cur = None


def _open(ns="p"):
    global _cur
    _clean()
    _cur = Hipercampo(_DB, namespace=ns)
    return _cur


def _clean():
    global _cur
    if _cur is not None:
        _cur.close()
        _cur = None
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _sembrar(hc):
    hc.remember("me llamo Armando y prefiero respuestas directas y honestas", 0.9)
    hc.remember("el servidor de produccion esta alojado en Frankfurt", 0.7)
    hc.remember("el pipeline de datos corre cada noche a las tres", 0.6)


def test_question_triggers_recall():
    hc = _open(); _sembrar(hc)
    r = hc.assist("¿dónde está alojado el servidor de producción?")
    assert r["action"] == "recall", r
    assert any("Frankfurt" in h["text"] for h in r["result"])
    _clean()


def test_irrelevant_input_causes_abstention():
    hc = _open(); _sembrar(hc)
    r = hc.assist("mañana llueve en Reikiavik y compraré pan de centeno")
    assert r["action"] == "nothing", f"debería abstenerse: {r}"
    _clean()


def test_new_statement_recommends_saving():
    hc = _open(); _sembrar(hc)
    r = hc.assist("me gusta programar de madrugada con música ambiental")
    assert r["action"] in ("remember?", "update?"), r
    assert "suggestion" in r
    _clean()


def test_writes_are_only_recommended_never_executed():
    hc = _open(); _sembrar(hc)
    antes = hc.stats()["total"]
    hc.assist("me llamo Armando y trabajo en un proyecto de memoria")
    assert hc.stats()["total"] == antes, "assist NO debe escribir por su cuenta"
    _clean()


def test_empty_message_does_nothing():
    hc = _open()
    assert hc.assist("")["action"] == "nothing"
    assert hc.assist("   ")["action"] == "nothing"
    _clean()


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
