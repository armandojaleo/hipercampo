"""Tests del álgebra VSA. Ejecuta: python -m pytest  (o python tests/test_vsa.py)"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.encoder import encode_text
from hipercampo.vsa import bind, bundle, random_hv, similarity


def test_bind_es_reversible():
    a, b = random_hv(1), random_hv(2)
    assert (bind(bind(a, b), b) == a).all()


def test_hv_distintos_son_casi_ortogonales():
    a, b = random_hv(1), random_hv(2)
    assert 0.45 < similarity(a, b) < 0.55   # ~0.5 = no relacionados


def test_bundle_se_parece_a_sus_componentes():
    a, b, c = random_hv(1), random_hv(2), random_hv(3)
    mezcla = bundle([a, b, c])
    for x in (a, b, c):
        assert similarity(mezcla, x) > 0.6   # el bundle recuerda a cada uno


def test_orden_importa():
    a = encode_text("el perro muerde al hombre")
    b = encode_text("el hombre muerde al perro")
    assert similarity(a, b) < 0.95           # mismas palabras, orden distinto


def test_texto_identico_es_identico():
    assert similarity(encode_text("hola mundo"), encode_text("hola mundo")) == 1.0


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
    print("todos los tests pasaron")
