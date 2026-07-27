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
        assert code == 0 and '"edges"' in out and '"nodes"' in out and '"db"' in out
        # ideas (puentes del sueño) en JSON para el visor: dry-run, bien formado.
        code, out = _cli(["dream", "--json", "--max", "5"])
        assert code == 0
        ideas = json.loads(out)
        assert "bridges" in ideas and isinstance(ideas["bridges"], list)
        assert ideas.get("dry_run") is True, "el visor NUNCA debe persistir ideas"
        # estado de salud: CLI + BD + MCP + registro
        code, out = _cli(["status"])
        assert code == 0
        estado = json.loads(out)
        assert estado["db"]["healthy"] is True
        assert "mcp" in estado and "log" in estado and "version" in estado
        # registro y factura de tokens en JSON (para las pestañas del visor). No
        # dependen de que el log esté activo: con HIPERCAMPO_LOG=0 (como en el CI de
        # cobertura) `log --json` devuelve una lista vacía y código 0, no un error.
        code, out = _cli(["log", "-n", "20", "--json"])
        assert code == 0 and "entries" in json.loads(out)
        code, out = _cli(["tokens"])
        assert code == 0
        tok = json.loads(out)
        assert "summary" in tok and "series" in tok
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


def test_registro_y_tokens_con_log_activo():
    """Ejercita las ramas REALES de log/tokens/status con el registro encendido
    (el CI de cobertura corre con HIPERCAMPO_LOG=0, que no las tocaría). Forzamos el
    flag del módulo a mano para no depender del entorno."""
    from hipercampo import audit
    _sembrar()
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ["HIPERCAMPO_NAMESPACE"] = "alice"
    previo = audit._ENABLED
    audit._ENABLED = True
    try:
        _cli(["remember", "un dato que deja rastro en el registro"])
        _cli(["recall", "dato rastro"])
        code, out = _cli(["log", "-n", "50", "--json"])
        assert code == 0
        d = json.loads(out)
        assert d["entries"], "con el log activo debería haber entradas"
        assert all("accion" in e and "ts" in e for e in d["entries"])
        code, out = _cli(["tokens"])
        assert code == 0 and "series" in json.loads(out)
        code, out = _cli(["status"])
        assert code == 0 and json.loads(out)["log"]["enabled"] is True
    finally:
        audit._ENABLED = previo
        os.environ.pop("HIPERCAMPO_DB", None)
        os.environ.pop("HIPERCAMPO_NAMESPACE", None)


def test_pausa_no_recordar():
    """En pausa no se graba ni se refuerza; al reanudar, vuelve a grabar. Y no borra
    nada: leer sigue funcionando. Es el modo 'no recordar'."""
    from hipercampo import config
    _clean()
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_PAUSED", None)
    try:
        config.set_paused(False)
        hc = Hipercampo(_DB, namespace="p")
        assert hc.remember("esto sí se graba", 0.6).get("stored") is True

        config.set_paused(True)
        assert config.paused() is True
        r = hc.remember("esto NO debe grabarse", 0.6)
        assert r.get("stored") is False and r.get("paused") is True
        assert hc.learn("una regla que tampoco se aprende").get("paused") is True
        # leer sigue vivo aunque esté en pausa
        assert isinstance(hc.recall("esto"), list)

        config.set_paused(False)
        assert hc.remember("otra vez se graba", 0.6).get("stored") is True
        # total: 2 grabados, el de en medio no
        assert len(hc.store.all(only_active=False)) == 2
        hc.close()
    finally:
        config.set_paused(False)
        os.environ.pop("HIPERCAMPO_DB", None)


def test_pausa_por_variable_de_entorno_manda():
    """HIPERCAMPO_PAUSED=1 fuerza la pausa por encima del fichero-bandera."""
    from hipercampo import config
    _clean()
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ["HIPERCAMPO_PAUSED"] = "1"
    try:
        config.set_paused(False)          # el fichero dice 'no', pero la env manda
        assert config.paused() is True
    finally:
        os.environ.pop("HIPERCAMPO_PAUSED", None)
        os.environ.pop("HIPERCAMPO_DB", None)
        config.set_paused(False)


def _env():
    return dict(os.environ)


if __name__ == "__main__":     # el bucle de cobertura de CI ejecuta este fichero como script
    limpiar()
    _clean()
    codigo = ejecutar(dict(globals()))
    _clean()
    sys.exit(codigo)
