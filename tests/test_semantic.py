"""
Test del puente SimHash (denso -> hipervector) SIN necesitar ningún modelo.

Validamos la propiedad clave: si dos vectores densos son parecidos (coseno alto),
sus hipervectores deben estar CERCA en Hamming; si son distintos, LEJOS. Eso es lo
que hace que la semántica de un embedding se traduzca a similitud VSA.

Ejecuta:  python tests/test_semantic.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                   # noqa: E402

from hipercampo.semantic import embedding_to_hv      # noqa: E402
from hipercampo.vsa import similarity                # noqa: E402


def test_preserva_similitud():
    rng = np.random.default_rng(7)
    base = rng.standard_normal(384)
    parecido = base + 0.05 * rng.standard_normal(384)     # casi igual
    distinto = rng.standard_normal(384)                   # sin relación

    h_base = embedding_to_hv(base)
    h_par = embedding_to_hv(parecido)
    h_dis = embedding_to_hv(distinto)

    sim_par = similarity(h_base, h_par)
    sim_dis = similarity(h_base, h_dis)
    assert sim_par > 0.75, f"vectores parecidos deberían dar Hamming bajo: {sim_par}"
    assert sim_dis < 0.60, f"vectores distintos deberían dar ~0.5: {sim_dis}"
    assert sim_par > sim_dis, "el puente no preservó el orden de similitud"


def test_determinista():
    v = np.random.default_rng(1).standard_normal(384)
    assert (embedding_to_hv(v) == embedding_to_hv(v)).all()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
