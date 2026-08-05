"""
El atomizador (`hipercampo/atomize.py`): trocear en unidades atómicas.

La jugada grande, medida (scripts/atom_probe.py): un hecho enterrado en un texto largo
es casi irrecuperable en un bundle monolítico (acierto@1 ≈ 0.15 a 64 hechos) y perfecto
si se atomiza. Aquí se congela el CONTRATO del atomizador, no la mejora de recall (esa
vive en el benchmark). Lo exigible:
  - un texto de varias oraciones se parte en varios átomos, en orden,
  - una oración muy larga se parte en cláusulas,
  - un texto corto/atómico se devuelve entero (no fragmentar lo que ya es un átomo),
  - no rompe en abreviaturas ni decimales comunes,
  - entradas vacías/raras no revientan.

Ejecuta:  python tests/test_atomize.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar     # noqa: E402
from hipercampo.atomize import atomize     # noqa: E402


def test_varias_oraciones_varios_atomos():
    t = ("El servidor de producción está en Frankfurt. La reunión diaria es a las "
         "nueve. La clave del wifi es girasol2024.")
    a = atomize(t)
    assert len(a) == 3, a
    assert "Frankfurt" in a[0] and "nueve" in a[1] and "girasol2024" in a[2]


def test_texto_corto_no_se_fragmenta():
    assert atomize("perro muerde hombre") == ["perro muerde hombre"]
    assert atomize("Frankfurt") == ["Frankfurt"]


def test_oracion_muy_larga_se_parte_en_clausulas():
    t = ("La batería del robot R7 cae rápidamente en el pasillo norte porque el sensor "
         "de temperatura falla con la humedad alta, y luego el motor vibra a tres mil "
         "revoluciones mientras los tornillos se aflojan poco a poco cada jornada.")
    a = atomize(t)
    assert len(a) >= 3, f"una oración larga debería trocearse: {a}"
    assert any("R7" in x for x in a) and any("sensor" in x for x in a)


def test_no_rompe_en_abreviaturas():
    a = atomize("El Dr. Ramón vive en EE.UU. y trabaja en la clínica. Todo va bien.")
    assert len(a) == 2, f"no debe cortar en Dr. ni EE.UU.: {a}"
    assert "Ramón" in a[0]


def test_entradas_raras_no_revientan():
    assert atomize("") == []
    assert atomize("   ") == []
    assert atomize("...") == ["..."]
    assert isinstance(atomize("¿?"), list)


def test_orden_se_conserva():
    a = atomize("Primero A pasa aquí. Segundo B pasa allá. Tercero C pasa lejos.")
    assert a[0].startswith("Primero") and a[2].startswith("Tercero")


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
