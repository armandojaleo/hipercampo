"""
Tests del sueño creativo (dream): propone puentes por asociado común SIN contaminar
la memoria hasta que se confirman. Ejecuta:  python tests/test_dream.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

_DB = "data/_test_dream.db"
_cur = None


def _open(ns="d"):
    global _cur
    if _cur is not None:
        _cur.close()
    _clean()
    _cur = Hipercampo(_DB, namespace=ns)
    return _cur


def _clean():
    global _cur
    if _cur is not None:
        _cur.close(); _cur = None
    for suf in ("", "-wal", "-shm"):
        try:
            Path(_DB + suf).unlink(missing_ok=True)
        except PermissionError:
            pass


def _trio(hc):
    """X se enlaza a A y a B al escribirse; A y B NO se enlazan entre sí."""
    hc.remember("el hipocampo guarda los recuerdos por la noche mientras duermes", 0.5)
    a = hc.remember("el hipocampo guarda los recuerdos de la infancia lejana", 0.5)["id"]
    b = hc.remember("guarda por la noche lo que aprendes mientras duermes profundamente",
                    0.5)["id"]
    return a, b


def test_dream_proposes_through_common_associate():
    hc = _open()
    _trio(hc)
    res = hc.dream(max_bridges=5)
    assert res["bridges"], "debería proponer un puente por asociado común"
    assert res["dry_run"] is True, "por defecto solo propone"


# --- lo esencial: una hipótesis NO contamina la memoria --------------------
def test_dry_run_writes_nothing():
    hc = _open()
    a, b = _trio(hc)
    antes = len(hc.store.neighbors(a))
    hc.dream()                                    # dry_run por defecto
    assert len(hc.store.neighbors(a)) == antes, "dry_run no debe crear enlaces"
    assert hc.store.proposed_links() == [], "dry_run no debe registrar propuestas"
    _clean()


def test_recorded_hypothesis_does_not_propagate_until_confirmed():
    hc = _open()
    a, b = _trio(hc)
    hc.dream(dry_run=False)                       # registra como 'proposed'
    assert hc.store.proposed_links(), "debería haber una hipótesis registrada"
    # una hipótesis NO propaga: b no es vecino de a todavía
    assert b not in [d for d, _ in hc.store.neighbors(a)], \
        "una hipótesis no confirmada no debe propagar activación"
    # ...pero sí se puede consultar como propuesta
    assert b in [d for d, _ in hc.store.neighbors(a, include_proposed=True)]
    _clean()


def test_accepting_hypothesis_turns_it_into_association():
    hc = _open()
    a, b = _trio(hc)
    hc.dream(dry_run=False)
    hc.accept_bridge(a, b)
    assert b in [d for d, _ in hc.store.neighbors(a)], \
        "tras confirmarla, la asociación ya debe propagar"
    _clean()


def test_rejecting_hypothesis_disables_it():
    hc = _open()
    a, b = _trio(hc)
    hc.dream(dry_run=False)
    hc.reject_bridge(a, b)
    assert b not in [d for d, _ in hc.store.neighbors(a, include_proposed=True)], \
        "una hipótesis rechazada no debe seguir viva"
    _clean()


def test_accepting_twice_is_idempotent():
    hc = _open()
    a, b = _trio(hc)
    hc.dream(dry_run=False)
    hc.accept_bridge(a, b)
    hc.accept_bridge(a, b)                        # otra vez: no debe duplicar
    vecinos = [d for d, _ in hc.store.neighbors(a)]
    assert vecinos.count(b) == 1, f"debería haber exactamente un enlace: {vecinos}"
    _clean()


# --- la puntuación creativa: pico en el ideal, cero fuera de banda ---------
def test_creative_fit_is_maximum_at_ideal():
    from hipercampo.cycle.memory import DREAM_HIGH, DREAM_IDEAL, DREAM_LOW, creative_fit
    assert creative_fit(DREAM_IDEAL) == 1.0
    assert creative_fit(DREAM_IDEAL) > creative_fit(DREAM_IDEAL - 0.05)
    assert creative_fit(DREAM_IDEAL) > creative_fit(DREAM_IDEAL + 0.05)
    assert creative_fit(DREAM_LOW - 0.01) == 0.0, "fuera de banda debe ser cero"
    assert creative_fit(DREAM_HIGH + 0.01) == 0.0, "fuera de banda debe ser cero"
    assert creative_fit(0.99) == 0.0, "lo casi idéntico no es creativo"
    assert creative_fit(0.50) == 0.0, "lo ajeno no es creativo"


def test_dream_without_pairs_does_not_fail():
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
