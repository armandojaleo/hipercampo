"""
Tests de los guardrails de uso: redacción opcional de secretos y tope de cantidad
por contexto. Ejecuta:  python tests/test_guardrails.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import gc                                              # noqa: E402

import hipercampo.memory as M                         # noqa: E402
from hipercampo.memory import Hipercampo              # noqa: E402
from hipercampo.safety import redact_secrets          # noqa: E402

_DB = "data/_test_guard.db"
_cur = None


def _open(ns="g"):
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
    gc.collect()
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


# --- redacción ---------------------------------------------------------------
def test_redact_secrets_enmascara():
    r = redact_secrets("mi token es sk_live_ABCDEF123456 vale")
    assert "sk_live_ABCDEF123456" not in r and "redactado" in r
    r2 = redact_secrets("password: superclave123")
    assert "superclave123" not in r2 and "password" in r2


def test_remember_redacta_si_esta_activo():
    old = M.REDACT_SECRETS
    M.REDACT_SECRETS = True
    try:
        hc = _open()
        r = hc.remember("la clave es sk_live_ZZZ999aaa888 anótala", 0.6)
        assert r.get("redacted") is True
        guardado = hc.store.get(r["id"])["text"]
        assert "sk_live_ZZZ999aaa888" not in guardado, "el secreto debió enmascararse"
    finally:
        M.REDACT_SECRETS = old
        _clean()


# --- tope de cantidad --------------------------------------------------------
def test_tope_acota_la_memoria():
    old = M.MAX_MEMORIES
    M.MAX_MEMORIES = 5
    try:
        hc = _open()
        for i in range(10):
            hc.remember(f"recuerdo trivial numero {i} sobre cosas variadas zeta", 0.3)
        total = hc.stats()["total"]
        assert total <= 5, f"la memoria debería estar acotada a 5, hay {total}"
    finally:
        M.MAX_MEMORIES = old
        _clean()


def test_tope_protege_lo_importante():
    old = M.MAX_MEMORIES
    M.MAX_MEMORIES = 3
    try:
        hc = _open()
        hc.remember("dato critico que no debe perderse jamas de los jamases", 0.9)
        for i in range(6):
            hc.remember(f"ruido trivial intercambiable numero {i} pepino", 0.2)
        textos = [r["text"] for r in hc.store.all(only_active=False)]
        assert any("critico" in t for t in textos), "lo importante no debió podarse"
    finally:
        M.MAX_MEMORIES = old
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
