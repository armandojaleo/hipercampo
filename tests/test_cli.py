"""
Tests del CLI — la puerta por la que entra el HOOK en cada turno.

Si `hipercampo hook` falla o tarda, no rompe la conversación pero la deja sin
memoria y sin avisar. Aquí se comprueba que responde el JSON exacto que Claude
Code espera, que se calla cuando no tiene nada que decir, y que ningún comando
revienta ante una entrada rara.

Ejecuta:  python tests/test_cli.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar               # noqa: E402
from hipercampo.cli import main                     # noqa: E402

_DB = "data/_t_cli.db"


def _limpiar_db():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _correr(*args) -> tuple[int, str]:
    """Ejecuta el CLI contra una BD de prueba y devuelve (código, salida)."""
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ["HIPERCAMPO_LOG"] = "0"
    buf = io.StringIO()
    with redirect_stdout(buf):
        codigo = main(list(args))
    return codigo, buf.getvalue()


def _hook(prompt: str) -> dict:
    """Simula el hook: stdin es el JSON que manda Claude Code."""
    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"prompt": prompt}))
    try:
        _, salida = _correr("hook")
    finally:
        sys.stdin = original
    return json.loads(salida)


# --- el contrato del hook ---------------------------------------------------

def test_el_hook_devuelve_el_json_que_espera_claude_code():
    _limpiar_db()
    _correr("remember", "el servidor de produccion esta alojado en Frankfurt")
    r = _hook("¿donde esta alojado el servidor de produccion?")
    salida = r.get("hookSpecificOutput", {})
    assert salida.get("hookEventName") == "UserPromptSubmit", r
    assert "Frankfurt" in salida.get("additionalContext", ""), r
    assert r.get("suppressOutput") is True, "no debe ensuciar el transcript"
    _limpiar_db()


def test_el_hook_se_calla_cuando_no_sabe_nada():
    _limpiar_db()
    _correr("remember", "algo totalmente ajeno sobre jardineria y macetas")
    r = _hook("¿cual es la capital de Mongolia?")
    assert r == {}, f"debió callarse en vez de inventar contexto: {r}"
    _limpiar_db()


def test_el_hook_ignora_el_ruido_del_ide():
    """Los bloques que inyecta el IDE no son palabras del usuario."""
    _limpiar_db()
    r = _hook("<ide_opened_file>C:/algo/fichero.py</ide_opened_file>")
    assert r == {}, f"decidió sobre ruido del IDE: {r}"
    _limpiar_db()


def test_el_hook_nunca_revienta_con_entrada_basura():
    _limpiar_db()
    for basura in ("", "   ", "\x00\x01", "{" * 500):
        r = _hook(basura)
        assert isinstance(r, dict), f"no devolvió JSON con {basura!r}"
    original = sys.stdin
    sys.stdin = io.StringIO("esto no es json en absoluto")
    try:
        codigo, salida = _correr("hook")
    finally:
        sys.stdin = original
    assert codigo == 0 and json.loads(salida) == {}, salida
    _limpiar_db()


def test_el_hook_de_arranque_inyecta_la_identidad():
    """SessionStart: al empezar no hay pregunta, lo que toca es recordar quién eres."""
    _limpiar_db()
    os.environ["HIPERCAMPO_DB"] = _DB
    from hipercampo.memory import Hipercampo
    hc = Hipercampo(_DB, namespace="default")
    hc.learn("medir antes de creer y decir la verdad de los limites", "regla")
    hc.close()

    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"hook_event_name": "SessionStart",
                                        "source": "startup"}))
    try:
        _, salida = _correr("hook")
    finally:
        sys.stdin = original
    r = json.loads(salida)
    ctx = r.get("hookSpecificOutput", {})
    assert ctx.get("hookEventName") == "SessionStart", r
    assert "medir antes de creer" in ctx.get("additionalContext", ""), r
    _limpiar_db()


def test_el_arranque_sin_identidad_se_calla():
    _limpiar_db()
    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"hook_event_name": "SessionStart"}))
    try:
        _, salida = _correr("hook")
    finally:
        sys.stdin = original
    assert json.loads(salida) == {}, salida
    _limpiar_db()


# --- comandos ---------------------------------------------------------------

def test_remember_y_recall_por_terminal():
    _limpiar_db()
    codigo, salida = _correr("remember", "las ballenas azules son los mayores animales")
    assert codigo == 0 and '"stored": true' in salida.lower(), salida
    codigo, salida = _correr("recall", "cual es el animal mas grande", "--plain")
    assert codigo == 0 and "ballenas" in salida, salida
    _limpiar_db()


def test_stats_y_doctor_informan_sin_fallar():
    _limpiar_db()
    _correr("remember", "un dato cualquiera para que haya algo que contar")
    codigo, salida = _correr("stats")
    assert codigo == 0 and "total" in salida, salida
    codigo, salida = _correr("doctor")
    assert codigo == 0, salida
    assert "SANA" in salida and "esquema" in salida, salida
    _limpiar_db()


def test_version_y_ayuda():
    codigo, salida = _correr("version")
    assert codigo == 0 and salida.strip(), salida
    codigo, salida = _correr()
    assert codigo == 0 and "hipercampo" in salida


def test_texto_vacio_se_rechaza_con_codigo_de_error():
    _limpiar_db()
    codigo, _ = _correr("remember")
    assert codigo != 0, "guardar sin texto debe fallar, no guardar basura"
    _limpiar_db()


if __name__ == "__main__":
    limpiar()
    _limpiar_db()
    codigo = ejecutar(dict(globals()))
    _limpiar_db()
    sys.exit(codigo)
