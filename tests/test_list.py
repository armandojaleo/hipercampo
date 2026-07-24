"""
El volcado de memorias que alimenta al visor de VS Code (`hipercampo list --json`).

Lo que se exige:
  - que devuelva las memorias como dicts SIN el hipervector (una UI no quiere el blob),
  - que respete el aislamiento por contexto (solo el propio, salvo --all-namespaces),
  - que `--all-namespaces` sí vea todo el fichero (es inspección del propio dueño),
  - que el JSON de la CLI tenga la forma que el visor espera.

Ejecuta:  python -m pytest tests/test_list.py
"""

import contextlib
import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar     # noqa: E402
from hipercampo import cli                 # noqa: E402
from hipercampo.memory import Hipercampo   # noqa: E402
from hipercampo.store import Store         # noqa: E402

_DB = "data/_test_list.db"


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _sembrar():
    _clean()
    a = Hipercampo(_DB, namespace="alice")
    a.remember("alice guarda su primer recuerdo importante", 0.9)
    a.remember("alice tiene un segundo dato cualquiera", 0.4)
    a.close()
    b = Hipercampo(_DB, namespace="bob")
    b.remember("bob vive en otro contexto distinto", 0.6)
    b.close()


def test_dump_no_incluye_el_hipervector():
    _sembrar()
    s = Store(_DB, namespace="alice")
    filas = s.dump()
    s.close()
    assert filas, "debería haber memorias"
    assert all("hv" not in m for m in filas), "el volcado no debe llevar el blob hv"
    # y sí los campos que la UI pinta
    m = filas[0]
    for campo in ("id", "text", "kind", "importance", "confidence", "strength",
                  "access_count", "last_access", "dormant", "namespace"):
        assert campo in m, f"falta el campo {campo}"


def test_dump_respeta_el_contexto():
    _sembrar()
    s = Store(_DB, namespace="alice")
    propios = s.dump()
    todo = s.dump(all_namespaces=True)
    s.close()
    assert all(m["namespace"] == "alice" for m in propios), "no debía ver a bob"
    ns = {m["namespace"] for m in todo}
    assert {"alice", "bob"} <= ns, "con --all-namespaces debe verse todo el fichero"


def test_orden_por_importancia():
    _sembrar()
    s = Store(_DB, namespace="alice")
    filas = s.dump(order="importance")
    s.close()
    imps = [m["importance"] for m in filas]
    assert imps == sorted(imps, reverse=True), "no respetó el orden por importancia"


def test_cli_json_tiene_la_forma_que_espera_el_visor():
    _sembrar()
    r = subprocess.run(
        [sys.executable, "-m", "hipercampo.cli", "list", "--json", "--all-namespaces"],
        capture_output=True, text=True, encoding="utf-8",
        env={**_env(), "HIPERCAMPO_DB": _DB, "HIPERCAMPO_LOG": "0"})
    assert r.returncode == 0, r.stderr
    data = json.loads(r.stdout)
    assert data["all_namespaces"] is True
    assert data["count"] == len(data["memories"]) >= 3
    assert {"alice", "bob"} <= {m["namespace"] for m in data["memories"]}


def test_graph_solo_aristas_entre_nodos_mostrados():
    _sembrar()
    # crear una asociación entre dos recuerdos de alice
    a = Hipercampo(_DB, namespace="alice")
    ids = [r["id"] for r in a.store.all(only_active=False)]
    a.store.link(ids[0], ids[1], weight=0.8, type="lexical")
    a.store.commit()
    g = a.store
    nodos = g.dump()
    aristas = g.links_dump()
    a.close()
    node_ids = {n["id"] for n in nodos}
    for e in aristas:
        assert e["src"] in node_ids and e["dst"] in node_ids


def test_dormant_y_wake_por_id():
    _sembrar()
    a = Hipercampo(_DB, namespace="alice")
    mid = a.store.all(only_active=False)[0]["id"]
    a.store.set_dormant([mid], dormant=True)
    visibles = [m["id"] for m in a.store.dump(include_dormant=False)]
    assert mid not in visibles, "un latente no debe salir sin include_dormant"
    a.store.set_dormant([mid], dormant=False)
    visibles = [m["id"] for m in a.store.dump(include_dormant=False)]
    assert mid in visibles, "al despertar debe volver a verse"
    a.close()


def _cli(args):
    """Llama al CLI EN PROCESO (no subprocess) para que la cobertura cuente cli.py."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = cli.main(args)
    return code, buf.getvalue()


def test_cli_list_graph_dormant_en_proceso():
    _sembrar()
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ["HIPERCAMPO_LOG"] = "0"
    os.environ["HIPERCAMPO_NAMESPACE"] = "alice"
    try:
        code, out = _cli(["list", "--json", "--all-namespaces"])
        assert code == 0 and '"memories"' in out
        code, out = _cli(["list", "--all-namespaces", "--sort", "importance"])
        assert code == 0                                   # tabla legible
        code, out = _cli(["list", "--kind", "episodic", "--limit", "1"])
        assert code == 0
        code, out = _cli(["graph", "--all-namespaces"])
        assert code == 0 and '"edges"' in out and '"nodes"' in out
        # olvidar/despertar por id, en el propio contexto
        mid = json.loads(_cli(["list", "--json"])[1])["memories"][0]["id"]
        code, out = _cli(["dormant", "--ids", str(mid)])
        assert code == 0 and "adormecidos" in out
        code, out = _cli(["dormant", "--ids", str(mid), "--wake"])
        assert code == 0 and "despiertos" in out
        # entradas inválidas: se rechazan con código != 0, no revientan
        assert _cli(["dormant", "--ids", "no-numero"])[0] != 0
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)
        os.environ.pop("HIPERCAMPO_NAMESPACE", None)


def _env():
    return dict(os.environ)


if __name__ == "__main__":     # el bucle de cobertura de CI ejecuta este fichero como script
    limpiar()
    _clean()
    codigo = ejecutar(dict(globals()))
    _clean()
    sys.exit(codigo)
