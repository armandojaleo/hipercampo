"""
Reclasificar: mover recuerdos PROPIOS a otro contexto (curación del dueño).

Es la pieza que faltaba: hipercampo sabía aislar y consolidar DENTRO de un contexto,
pero no re-clasificar un recuerdo que nació en el sitio equivocado (p. ej. cosas de
proyecto que cayeron en 'personal'). Reclasificar es curación del dueño sobre su
propia memoria; NO es cruzar contextos (eso sigue prohibido):
  - solo mueve lo del propio contexto (nunca lo enlazado ni lo ajeno),
  - los enlaces con los dos extremos movidos se mudan con ellos,
  - los enlaces que quedarían cruzando contextos se eliminan (aislamiento).

Ejecuta:  python tests/test_reclassify.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar, memoria     # noqa: E402
from hipercampo.store import Store                  # noqa: E402


def _abrir(hc, ns):
    return Store(hc.store.path, namespace=ns)


def test_mueve_los_propios_a_otro_contexto():
    hc = memoria("rc_mueve", namespace="personal")
    hc.remember("una nota de proyecto que cayó en personal", 0.7)
    ids = [m["id"] for m in hc.store.all(only_active=False)]
    n = hc.store.reclassify(ids, "proj-x")
    assert n == len(ids)
    assert len(hc.store.dump()) == 0, "ya no debe quedar nada en el origen"
    destino = _abrir(hc, "proj-x")
    assert len(destino.dump()) == len(ids), "deben estar todos en el destino"
    destino.close(); hc.close()


def test_solo_toca_lo_propio():
    """Pasar ids de OTRO contexto no los mueve: reclasificar es sobre lo propio."""
    hc = memoria("rc_aisla", namespace="personal")
    hc.remember("dato personal", 0.6)
    otro = _abrir(hc, "proj-y")
    from hipercampo.encoder import encode_text
    txt = "dato de otro proyecto"
    ajeno_id = otro.add(txt, encode_text(txt), 1.0, 0.6, 0.6)
    otro.commit(); otro.close()
    # intento mover el ajeno desde 'personal': no es suyo -> no se mueve
    movidos = hc.store.reclassify([ajeno_id], "personal")
    assert movidos == 0, "no puede mover lo de otro contexto"
    comprobar = _abrir(hc, "proj-y")
    assert any(m["id"] == ajeno_id for m in comprobar.dump()), "el ajeno sigue en su sitio"
    comprobar.close(); hc.close()


def test_enlace_con_ambos_extremos_movidos_se_muda():
    hc = memoria("rc_enlace", namespace="personal")
    a = hc.remember("windows rechaza rutas largas con 400", 0.7)["id"]
    b = hc.remember("los datos largos van por query string", 0.7)["id"]
    hc.store.link(a, b, weight=0.8, type="lexical"); hc.store.commit()
    assert len(hc.store.links_dump()) == 1
    hc.store.reclassify([a, b], "proj-mplayer")
    destino = _abrir(hc, "proj-mplayer")
    assert len(destino.links_dump()) == 1, "el enlace debe mudarse con sus dos extremos"
    destino.close(); hc.close()


def test_enlace_que_cruzaria_contextos_se_corta():
    hc = memoria("rc_corta", namespace="personal")
    a = hc.remember("recuerdo A", 0.7)["id"]
    b = hc.remember("recuerdo B asociado a A", 0.7)["id"]
    hc.store.link(a, b, weight=0.8, type="lexical"); hc.store.commit()
    hc.store.reclassify([a], "proj-z")      # solo A se va; el enlace cruzaría -> se corta
    assert len(hc.store.dump()) == 1, "B se queda en personal"
    destino = _abrir(hc, "proj-z")
    assert len(destino.links_dump()) == 0 and len(hc.store.links_dump()) == 0, \
        "un enlace entre contextos no puede sobrevivir"
    destino.close(); hc.close()


def test_destino_vacio_es_error():
    hc = memoria("rc_err", namespace="personal")
    hc.remember("algo", 0.6)
    ids = [m["id"] for m in hc.store.all(only_active=False)]
    movido = None
    try:
        hc.store.reclassify(ids, "  ")
    except ValueError:
        movido = "error"
    assert movido == "error", "un destino vacío debe fallar, no mover a la nada"
    hc.close()


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
