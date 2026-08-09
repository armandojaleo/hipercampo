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

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean, memory     # noqa: E402
from hipercampo.cycle import memory as _mem                # noqa: E402

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


def test_atomizes_and_links_to_source():
    hc = memory("atom_rem")
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


def test_repeating_document_reuses_source_and_atoms():
    """Reforzar el mismo documento no crea copias ni pierde la jerarquía."""
    hc = memory("atom_repetido")
    primero = hc.remember(_LARGO, 0.7)
    filas_antes = len(hc.store.all(only_active=False))
    segundo = hc.remember(_LARGO, 0.7)
    enlaces = [e for e in hc.store.links_dump() if e["type"] == "atom"]
    assert segundo.get("atomized") is True, segundo
    assert not segundo.get("stored")
    assert segundo.get("id") == primero.get("id")
    assert segundo.get("atoms_created") == 0
    assert segundo.get("atoms_linked") == segundo.get("atoms")
    assert len(hc.store.all(only_active=False)) == filas_antes
    assert len(enlaces) == segundo.get("atoms")
    hc.close()

def test_short_note_is_not_atomized():
    """Una nota de pocas frases se guarda ENTERA: atomizarla la fragmentaría en trozos
    inútiles ('", consultable por rol.') que ensucian la memoria. Solo documentos largos."""
    hc = memory("atom_corta")
    r = hc.remember("El servidor esta en Frankfurt. La reunion es a las nueve.", 0.7)
    assert not r.get("atomized"), r
    assert len(hc.store.all(only_active=False)) == 1
    hc.close()


def test_buried_fact_is_retrieved():
    hc = memory("atom_buried")
    hc.remember(_LARGO, 0.7)
    for pista, esperado in [("clave del wifi", "girasol2024"),
                            ("logistica maritima", "logistica maritima"),
                            ("timeout de red", "timeout")]:
        hits = hc.recall(pista, k=3)
        assert hits and any(esperado in h["text"] for h in hits), \
            f"no recuperó el hecho enterrado '{pista}': {[h['text'][:40] for h in hits]}"
    hc.close()


def test_single_idea_is_not_fragmented():
    hc = memory("atom_uno")
    r = hc.remember("el faro de alejandria guiaba a los barcos de noche", 0.7)
    assert not r.get("atomized"), r
    assert len(hc.store.all(only_active=False)) == 1
    hc.close()


def test_atomization_can_be_disabled():
    previo = _mem.ATOMIZE_ON_REMEMBER
    _mem.ATOMIZE_ON_REMEMBER = False
    try:
        hc = memory("atom_off")
        r = hc.remember(_LARGO, 0.7)
        assert not r.get("atomized"), "con atomización OFF, un texto largo es un recuerdo"
        assert len(hc.store.all(only_active=False)) == 1
        hc.close()
    finally:
        _mem.ATOMIZE_ON_REMEMBER = previo


def test_only_persistable_text_is_atomized():
    """Nada posterior al límite de la fuente puede filtrarse como átomo suelto."""
    hc = memory("atom_limite")
    prefijo = (_LARGO + " ") * ((_mem.MAX_TEXT_LEN // len(_LARGO)) + 2)
    marcador = "MARCADOR_QUE_ESTA_FUERA_DEL_LIMITE"
    r = hc.remember(prefijo[:_mem.MAX_TEXT_LEN] + marcador, 0.7)
    assert r.get("atomized") is True, r
    textos = [row["text"] for row in hc.store.all(only_active=False)]
    assert textos and all(marcador not in texto for texto in textos)
    assert max(map(len, textos)) <= _mem.MAX_TEXT_LEN
    hc.close()


def test_memory_cap_preserves_source_and_coherent_group():
    """El lote se acota sin desalojar su fuente ni dejar enlaces colgantes."""
    previo = _mem.MAX_MEMORIES
    _mem.MAX_MEMORIES = 4
    try:
        hc = memory("atom_cap")
        r = hc.remember(_LARGO, 0.7)
        filas = hc.store.all(only_active=False)
        ids = {row["id"] for row in filas}
        enlaces = [e for e in hc.store.links_dump() if e["type"] == "atom"]
        assert r.get("atomized") is True, r
        assert r.get("id") in ids
        assert len(filas) == 4
        assert r.get("atoms_created") == 3
        assert r.get("atoms_skipped") == r.get("atoms") - 3
        assert len(enlaces) == 3
        assert all(e["src"] in ids and e["dst"] in ids for e in enlaces)
        hc.close()
    finally:
        _mem.MAX_MEMORIES = previo

def test_link_failure_rolls_back_all_atomization():
    """Fuente y átomos no deben sobrevivir como una escritura parcial."""
    hc = memory("atom_rollback")
    link_real = hc.store.link

    def link_con_fallo(src, dst, weight=1.0, type="lexical"):
        if type == "atom":
            raise sqlite3.OperationalError("fallo simulado al enlazar átomo")
        return link_real(src, dst, weight=weight, type=type)

    hc.store.link = link_con_fallo
    r = hc.remember(_LARGO, 0.7)
    assert not r.get("stored") and "error" in r, r
    assert hc.store.all(only_active=False) == []
    hc.close()

if __name__ == "__main__":
    clean()
    codigo = run_tests(dict(globals()))
    clean()
    sys.exit(codigo)
