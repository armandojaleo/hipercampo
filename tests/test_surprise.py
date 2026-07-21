"""
Tests de la sorpresa por error de predicción (compresión/MDL).
Ejecuta:  python tests/test_surprise.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.surprise import SurpriseModel        # noqa: E402


def test_frio_es_maxima_sorpresa():
    m = SurpriseModel()
    assert m.surprise("cualquier cosa nueva bajo el sol") > 0.9


def test_repetir_reduce_sorpresa():
    m = SurpriseModel()
    t = "el pipeline corre cada noche a las tres"
    s0 = m.surprise(t)
    m.learn(t)
    s1 = m.surprise(t)
    for _ in range(30):
        m.learn(t)
    s2 = m.surprise(t)
    assert s0 > s1 > s2, f"la sorpresa debe decrecer al aprender: {s0} {s1} {s2}"


def test_lo_nuevo_sorprende_mas_que_lo_conocido():
    m = SurpriseModel()
    conocido = "el equipo se reune los lunes por la manana"
    for _ in range(5):
        m.learn(conocido)
    s_conocido = m.surprise(conocido)
    s_nuevo = m.surprise("un meteorito de iridio cruzo la estratosfera")
    assert s_nuevo > s_conocido


def test_determinista():
    m1, m2 = SurpriseModel(), SurpriseModel()
    for t in ("hola mundo", "otro dato mas"):
        m1.learn(t); m2.learn(t)
    assert m1.surprise("prueba de determinismo") == m2.surprise("prueba de determinismo")


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
