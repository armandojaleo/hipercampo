"""
Atomización en `remember()`: la jugada grande, cableada en el ciclo.

Medido (scripts/atom_probe.py): un hecho enterrado en un texto de varias ideas es casi
irrecuperable en un bundle monolítico (acierto@1 0.15 a 64 hechos) y perfecto atomizado.
Aquí se congela el CONTRATO de la integración:
  - un texto de varias ideas se ATOMIZA: se guarda la fuente y cada átomo enlazado a ella,
  - un hecho enterrado se RECUPERA con una pista corta (lo que un monolito no logra),
  - un texto de una sola idea se guarda entero (como siempre),
  - se puede DESACTIVAR (para quien quiera el comportamiento monolítico).

Ejecuta:  python tests/test_atomize_remember.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar, memoria     # noqa: E402
from hipercampo import memory as _mem                # noqa: E402

# Un DOCUMENTO largo (>500 chars, varios hechos): esto SÍ se atomiza. Una nota corta
# no (ver test_nota_corta_no_se_atomiza): atomizarla la fragmentaría en trozos inútiles.
_LARGO = ("El servidor de produccion esta alojado en Frankfurt desde el ultimo "
          "traslado. La reunion diaria del equipo es a las nueve de la manana en la "
          "sala grande. La clave del wifi de la oficina es girasol2024 y cambia cada "
          "trimestre. El cliente principal es una empresa de logistica maritima con "
          "sede en Rotterdam. El ultimo despliegue de la version dos fallo por un "
          "timeout de red en el balanceador. La copia de seguridad nocturna se guarda "
          "en el almacen frio del proveedor. El responsable de guardia esta localizable "
          "por el canal de incidencias del movil corporativo.")


def test_atomiza_y_enlaza_a_la_fuente():
    hc = memoria("atom_rem")
    r = hc.remember(_LARGO, 0.7)
    assert r.get("atomized") is True, r
    n = r.get("atoms")
    assert n >= 4 and r.get("atoms_created") == n, r
    # fuente + n átomos
    assert len(hc.store.all(only_active=False)) == n + 1
    # cada átomo cuelga de la fuente (type='atom')
    enlaces_atom = [e for e in hc.store.links_dump() if e["type"] == "atom"]
    assert len(enlaces_atom) == n, enlaces_atom
    hc.close()


def test_nota_corta_no_se_atomiza():
    """Una nota de pocas frases se guarda ENTERA: atomizarla la fragmentaría en trozos
    inútiles ('", consultable por rol.') que ensucian la memoria. Solo documentos largos."""
    hc = memoria("atom_corta")
    r = hc.remember("El servidor esta en Frankfurt. La reunion es a las nueve.", 0.7)
    assert not r.get("atomized"), r
    assert len(hc.store.all(only_active=False)) == 1
    hc.close()


def test_hecho_enterrado_se_recupera():
    hc = memoria("atom_buried")
    hc.remember(_LARGO, 0.7)
    for pista, esperado in [("clave del wifi", "girasol2024"),
                            ("logistica maritima", "logistica maritima"),
                            ("timeout de red", "timeout")]:
        hits = hc.recall(pista, k=3)
        assert hits and any(esperado in h["text"] for h in hits), \
            f"no recuperó el hecho enterrado '{pista}': {[h['text'][:40] for h in hits]}"
    hc.close()


def test_una_sola_idea_no_se_fragmenta():
    hc = memoria("atom_uno")
    r = hc.remember("el faro de alejandria guiaba a los barcos de noche", 0.7)
    assert not r.get("atomized"), r
    assert len(hc.store.all(only_active=False)) == 1
    hc.close()


def test_se_puede_desactivar():
    previo = _mem.ATOMIZE_ON_REMEMBER
    _mem.ATOMIZE_ON_REMEMBER = False
    try:
        hc = memoria("atom_off")
        r = hc.remember(_LARGO, 0.7)
        assert not r.get("atomized"), "con atomización OFF, un texto largo es un recuerdo"
        assert len(hc.store.all(only_active=False)) == 1
        hc.close()
    finally:
        _mem.ATOMIZE_ON_REMEMBER = previo


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
