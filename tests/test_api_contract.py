"""
El CONTRATO de la API — congelado de cara a la beta.

Si este test falla, no es un bug del test: es que se ha roto compatibilidad.
Cambiar un nombre, quitar un parámetro o alterar la forma de una respuesta exige
una decisión consciente (y una entrada en el CHANGELOG), no un despiste.

Ejecuta:  python tests/test_api_contract.py
"""

import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar, memoria      # noqa: E402

# herramienta -> parámetros (nombre: ¿tiene valor por defecto?)
HERRAMIENTAS = {
    "hc_remember":      {"text": False, "importance": True, "confidence": True},
    "hc_recall":        {"query": False, "k": True, "include_history": True},
    "hc_update":        {"target": True, "new_text": True, "importance": True,
                         "memory_id": True, "confidence": True},
    "hc_remember_fact": {"subject": True, "predicate": True, "object": True,
                         "time": True, "source": True},
    "hc_ask_role":      {"role": False, "subject": True, "predicate": True,
                         "object": True, "time": True, "source": True,
                         "days_ago": True},
    "hc_muse":          {"query": False, "k": True},
    "hc_dream":         {"max_bridges": True, "dry_run": True},
    "hc_accept_bridge": {"a_id": False, "b_id": False},
    "hc_reject_bridge": {"a_id": False, "b_id": False},
    "hc_assist":        {"message": False, "k": True},
    "hc_sleep":         {},
    "hc_consolidate":   {},
    "hc_forget":        {"dry_run": True},
    "hc_learn":         {"text": False, "tipo": True},
    "hc_identity":      {"k": True},
    "hc_unlearn":       {"memory_id": False},
    "hc_health":        {"full": True},
    "hc_stats":         {},
    # Añadida, no sustituye a nada: la puerta a las herramientas que ya no se
    # anuncian de entrada para no gastar tokens en cada petición. Las 18 de arriba
    # siguen existiendo con la misma firma; lo que cambia es CUÁNDO se anuncian.
    "hc_tools":         {"name": True, "args": True},
}


def _tools():
    import hipercampo.server as server
    return {n: f for n, f in vars(server).items() if n.startswith("hc_")}


def test_estan_todas_y_ninguna_de_mas():
    vivas = set(_tools())
    assert vivas == set(HERRAMIENTAS), (
        f"faltan: {set(HERRAMIENTAS) - vivas} · sobran: {vivas - set(HERRAMIENTAS)}")


def test_los_parametros_no_cambian_sin_querer():
    for nombre, fn in _tools().items():
        firma = inspect.signature(fn)
        params = {p.name: (p.default is not inspect.Parameter.empty)
                  for p in firma.parameters.values()}
        assert params == HERRAMIENTAS[nombre], (
            f"{nombre}: la firma cambió\n  contrato: {HERRAMIENTAS[nombre]}"
            f"\n  código:   {params}")


def test_todas_documentadas():
    for nombre, fn in _tools().items():
        assert fn.__doc__ and len(fn.__doc__.strip()) > 40, f"{nombre} sin docstring útil"


# --- formas de respuesta (las claves que un cliente puede asumir) -----------

def test_forma_de_remember():
    hc = memoria("api_rem")
    r = hc.remember("un dato totalmente nuevo para el contrato", 0.6)
    assert {"stored", "id", "novelty", "surprise", "importance"} <= set(r), r


def test_forma_de_recall():
    hc = memoria("api_rec")
    hc.remember("el faro de alejandria guiaba a los barcos de noche", 0.7)
    hits = hc.recall("faro que guiaba a los barcos")
    assert hits, "debió recordar"
    assert {"id", "text", "kind", "score", "activation",
            "strength", "confidence", "utility"} <= set(hits[0]), hits[0]


def test_forma_de_stats_y_health():
    hc = memoria("api_st")
    s = hc.stats()
    assert {"episodicos_activos", "semanticos", "archivados", "latentes",
            "total", "total_fisico", "db"} <= set(s), s
    h = hc.health()
    assert {"db", "namespace", "integridad", "esquema", "lectura",
            "escribible", "sana"} <= set(h), h


def test_forma_de_error_resiliente():
    hc = memoria("api_err")
    hc.store.db.close()
    hc.store.path = "Z:/no/existe.db"
    r = hc.recall("lo que sea")
    assert {"error", "sugerencia"} <= set(r), r
    hc.store.path = ""


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
