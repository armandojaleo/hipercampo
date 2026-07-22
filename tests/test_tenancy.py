"""
Tests de aislamiento por inquilino (namespaces) y concurrencia básica — cimientos
para multiusuario. Ejecuta:  python tests/test_tenancy.py
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_tenancy.db"


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def test_un_inquilino_no_ve_lo_de_otro():
    _clean()
    alice = Hipercampo(_DB, namespace="alice")
    bob = Hipercampo(_DB, namespace="bob")
    alice.remember("el secreto de alice es el número 42", 0.8)
    bob.remember("a bob le gusta el senderismo", 0.5)

    # alice recupera lo suyo, nunca lo de bob
    ha = alice.recall("cuál es el secreto", k=5)
    assert any("alice" in h["text"] for h in ha)
    assert not any("bob" in h["text"] for h in ha), "¡fuga entre inquilinos!"

    # bob no ve el secreto de alice ni buscándolo
    hb = bob.recall("el número 42 secreto de alice", k=5)
    assert not any("alice" in h["text"] for h in hb), "¡fuga entre inquilinos!"

    assert alice.stats()["total"] == 1
    assert bob.stats()["total"] == 1
    alice.store.close(); bob.store.close()
    _clean()


def test_get_no_cruza_namespace():
    _clean()
    alice = Hipercampo(_DB, namespace="alice")
    bob = Hipercampo(_DB, namespace="bob")
    mid = alice.remember("dato privado de alice", 0.7)["id"]
    assert bob.store.get(mid) is None, "bob no debería poder leer un id de alice"
    assert alice.store.get(mid) is not None
    alice.store.close(); bob.store.close()
    _clean()


def test_escrituras_concurrentes_no_corrompen():
    _clean()

    def escribir(ns, n):
        hc = Hipercampo(_DB, namespace=ns)
        for i in range(n):
            hc.remember(f"{ns} recuerdo distinto numero {i} zeta", 0.5)
        hc.store.close()

    hilos = [threading.Thread(target=escribir, args=(f"t{t}", 10)) for t in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()

    # cada inquilino ve exactamente los suyos
    for t in range(4):
        hc = Hipercampo(_DB, namespace=f"t{t}")
        assert hc.stats()["total"] == 10, f"t{t} deberia tener 10"
        hc.store.close()
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
