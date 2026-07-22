"""
Tests del sueño creativo (dream): propone puentes entre recuerdos conectables.
Ejecuta:  python tests/test_dream.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_dream.db"
_cur = None


def _open(ns="d"):
    global _cur
    if _cur is not None:
        _cur.store.close()
    _clean()
    _cur = Hipercampo(_DB, namespace=ns)
    return _cur


def _clean():
    global _cur
    if _cur is not None:
        _cur.store.close(); _cur = None
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def test_dream_puentea_por_asociado_comun():
    hc = _open()
    # X se enlaza a A y a B al escribirse; A y B NO se enlazan entre sí (distintos).
    hc.remember("el hipocampo guarda los recuerdos por la noche mientras duermes", 0.5)  # X
    a = hc.remember("el hipocampo guarda los recuerdos de la infancia lejana", 0.5)["id"]  # A
    b = hc.remember("guarda por la noche lo que aprendes mientras duermes profundamente",
                    0.5)["id"]                                                             # B
    n_antes = len(hc.store.neighbors(a))
    res = hc.dream(max_bridges=5)
    assert res["bridges"], "debería proponer un puente por asociado común"
    # se creó un enlace nuevo A-B (la asociación que no existía)
    assert b in [d for d, _ in hc.store.neighbors(a)], "el puente A-B debería persistir"
    assert len(hc.store.neighbors(a)) > n_antes
    _clean()


def test_dream_sin_pares_no_falla():
    hc = _open()
    hc.remember("un unico recuerdo aislado sin pareja posible", 0.5)
    assert hc.dream()["bridges"] == []
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
