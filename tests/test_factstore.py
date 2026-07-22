"""
Tests de la memoria de HECHOS integrada (RoleMemory + persistencia + aislamiento).
Ejecuta:  python tests/test_factstore.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_facts.db"


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def test_guardar_y_preguntar_por_rol():
    _clean()
    hc = Hipercampo(_DB, namespace="f")
    hc.remember_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"})
    # ¿quién muerde al hombre? -> perro
    r = hc.ask_role("subject", {"predicate": "muerde", "object": "hombre"})
    assert r["answer"] == "perro", r
    # ¿a quién muerde el perro? -> hombre
    r2 = hc.ask_role("object", {"subject": "perro", "predicate": "muerde"})
    assert r2["answer"] == "hombre", r2
    hc.store.close(); _clean()


def test_distingue_hechos_inversos():
    _clean()
    hc = Hipercampo(_DB, namespace="f")
    hc.remember_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"})
    hc.remember_fact({"subject": "hombre", "predicate": "muerde", "object": "perro"})
    # conociendo objeto=perro, ¿quién muerde? -> hombre (no perro)
    r = hc.ask_role("subject", {"predicate": "muerde", "object": "perro"})
    assert r["answer"] == "hombre", r
    hc.store.close(); _clean()


def test_persistencia_entre_reinicios():
    _clean()
    hc = Hipercampo(_DB, namespace="f")
    hc.remember_fact({"subject": "marta", "predicate": "curó", "object": "gato"})
    hc.store.close()
    hc2 = Hipercampo(_DB, namespace="f")             # "reiniciar"
    r = hc2.ask_role("subject", {"predicate": "curó", "object": "gato"})
    assert r["answer"] == "marta", r
    hc2.store.close(); _clean()


def test_aislamiento_por_namespace():
    _clean()
    a = Hipercampo(_DB, namespace="a")
    b = Hipercampo(_DB, namespace="b")
    a.remember_fact({"subject": "alice", "predicate": "tiene", "object": "secreto"})
    r = b.ask_role("subject", {"predicate": "tiene", "object": "secreto"})
    assert r.get("error") or r.get("answer") != "alice", "b no debe ver hechos de a"
    a.store.close(); b.store.close(); _clean()


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
