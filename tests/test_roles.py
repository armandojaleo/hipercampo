"""
Tests de la memoria COMPOSICIONAL con roles (unbinding VSA).
Ejecuta:  python tests/test_roles.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.roles import ItemMemory, encode_fact, query_role   # noqa: E402


def _mundo(*valores):
    im = ItemMemory()
    for v in valores:
        im.add(v)
    return im


def test_recupera_por_rol():
    im = _mundo("perro", "hombre", "muerde")
    f = encode_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"}, im)
    assert query_role(f, "subject", im)[0][0] == "perro"
    assert query_role(f, "object", im)[0][0] == "hombre"
    assert query_role(f, "predicate", im)[0][0] == "muerde"


def test_distingue_el_inverso():
    """Lo que un embedding NO puede: mismos valores, roles cruzados = respuestas opuestas."""
    im = _mundo("perro", "hombre", "muerde")
    f1 = encode_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"}, im)
    f2 = encode_fact({"subject": "hombre", "predicate": "muerde", "object": "perro"}, im)
    assert query_role(f1, "subject", im)[0][0] == "perro"
    assert query_role(f2, "subject", im)[0][0] == "hombre"   # ¡invertido!
    assert query_role(f1, "object", im)[0][0] == "hombre"
    assert query_role(f2, "object", im)[0][0] == "perro"


def test_margen_claro():
    im = _mundo("perro", "hombre", "gato", "raton", "muerde", "persigue")
    f = encode_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"}, im)
    top = query_role(f, "subject", im, top=2)
    assert top[0][0] == "perro"
    assert top[0][1] - top[1][1] > 0.1, f"margen insuficiente: {top}"


def test_capacidad_cinco_roles():
    im = _mundo("usuario", "muerde", "gato", "ayer", "madrid", "perro", "hombre")
    f = encode_fact({"subject": "usuario", "predicate": "muerde", "object": "gato",
                     "time": "ayer", "source": "madrid"}, im)
    for role, val in [("subject", "usuario"), ("predicate", "muerde"),
                      ("object", "gato"), ("time", "ayer"), ("source", "madrid")]:
        assert query_role(f, role, im)[0][0] == val, f"falló el rol {role}"


def test_rol_desconocido_falla():
    im = _mundo("perro")
    f = encode_fact({"subject": "perro"}, im)
    try:
        query_role(f, "lugar", im)
        raise AssertionError("debería rechazar un rol desconocido")
    except ValueError:
        pass


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print(f"ok   {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
