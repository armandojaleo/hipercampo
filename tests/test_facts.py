"""
`hipercampo facts`: hacer VISIBLES los hechos estructurados (role-records).

El diferenciador VSA estaba integrado pero invisible. Este comando (y la pestaña del
visor) lo muestran. Lo exigible:
  - vuelca los hechos del contexto con sus campos por rol,
  - `--all-namespaces` agrega de TODOS los contextos, etiquetando cada hecho,
  - refleja la validez temporal (un hecho cerrado por una verdad posterior se marca),
  - no lleva el blob hv.

Ejecuta:  python tests/test_facts.py
"""

import contextlib
import io
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar, memoria     # noqa: E402
from hipercampo import cli                           # noqa: E402


def _facts_json(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(argv)
    return code, json.loads(buf.getvalue())


def test_facts_json_del_contexto():
    hc = memoria("facts_ns", namespace="proj-a")
    hc.remember_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"})
    db = hc.store.path
    hc.close()
    os.environ["HIPERCAMPO_DB"] = db
    os.environ["HIPERCAMPO_NAMESPACE"] = "proj-a"
    try:
        code, d = _facts_json(["facts", "--json"])
        assert code == 0
        assert d["count"] == 1
        f = d["facts"][0]
        assert f["fields"]["subject"] == "perro" and "hv" not in f
        assert f["vigente"] is True
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)
        os.environ.pop("HIPERCAMPO_NAMESPACE", None)


def test_facts_all_namespaces_y_validez_temporal():
    hc = memoria("facts_all", namespace="proj-a")
    hc.remember_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"})
    hc.remember_fact({"subject": "perro", "predicate": "muerde", "object": "cartero"})
    db = hc.store.path
    hc.close()
    from hipercampo.memory import Hipercampo
    b = Hipercampo(db, namespace="proj-b")
    b.remember_fact({"subject": "gato", "predicate": "bebe", "object": "leche"})
    b.close()

    os.environ["HIPERCAMPO_DB"] = db
    try:
        code, d = _facts_json(["facts", "--json", "--all-namespaces"])
        assert code == 0
        ctxs = {f["context"] for f in d["facts"]}
        assert {"proj-a", "proj-b"} <= ctxs, ctxs
        # el primer perro→hombre quedó CERRADO por perro→cartero (validez temporal)
        cerrados = [f for f in d["facts"] if not f["vigente"]]
        assert any(f["fields"].get("object") == "hombre" for f in cerrados), \
            "la verdad anterior debe quedar cerrada, no borrada"
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
