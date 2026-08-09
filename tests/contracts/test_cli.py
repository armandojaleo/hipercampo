"""
CLI tests for the HOOK entry point used on every turn.

If `hipercampo hook` fails or stalls, the conversation continues but silently loses
memory. These tests verify Claude Code's exact JSON contract, quiet abstention when
nothing should be said, and safe handling of unusual input.

Run: python tests/contracts/test_cli.py
"""

import io
import json
import os
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean               # noqa: E402
from hipercampo.cli import main                     # noqa: E402

_DB = "data/_t_cli.db"


def _limpiar_db():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _correr(*args) -> tuple[int, str]:
    """Run the CLI against a test database and return (code, output)."""
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ["HIPERCAMPO_LOG"] = "0"
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args))
    return code, buf.getvalue()


def _hook(prompt: str) -> dict:
    """Simulate the hook with Claude Code's JSON on stdin."""
    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"prompt": prompt}))
    try:
        _, output = _correr("hook")
    finally:
        sys.stdin = original
    return json.loads(output)


# --- hook contract ----------------------------------------------------------

def test_hook_returns_json_expected_by_claude_code():
    _limpiar_db()
    _correr("remember", "el servidor de produccion esta alojado en Frankfurt")
    r = _hook("¿donde esta alojado el servidor de produccion?")
    salida = r.get("hookSpecificOutput", {})
    assert salida.get("hookEventName") == "UserPromptSubmit", r
    assert "Frankfurt" in salida.get("additionalContext", ""), r
    assert r.get("suppressOutput") is True, "must not pollute the transcript"
    _limpiar_db()


def test_hook_stays_quiet_when_nothing_is_known():
    _limpiar_db()
    _correr("remember", "algo totalmente ajeno sobre jardineria y macetas")
    r = _hook("¿cual es la capital de Mongolia?")
    assert r == {}, f"should abstain instead of inventing context: {r}"
    _limpiar_db()


def test_hook_ignores_ide_noise():
    """Blocks injected by the IDE are not the user's words."""
    _limpiar_db()
    r = _hook("<ide_opened_file>C:/algo/fichero.py</ide_opened_file>")
    assert r == {}, f"made a decision based on IDE noise: {r}"
    _limpiar_db()


def test_hook_never_crashes_on_garbage_input():
    _limpiar_db()
    for basura in ("", "   ", "\x00\x01", "{" * 500):
        r = _hook(basura)
        assert isinstance(r, dict), f"did not return JSON for {basura!r}"
    original = sys.stdin
    sys.stdin = io.StringIO("esto no es json en absoluto")
    try:
        codigo, salida = _correr("hook")
    finally:
        sys.stdin = original
    assert codigo == 0 and json.loads(salida) == {}, salida
    _limpiar_db()


def test_startup_hook_injects_identity():
    """SessionStart has no query, so the hook should restore identity."""
    _limpiar_db()
    os.environ["HIPERCAMPO_DB"] = _DB
    from hipercampo.cycle.memory import Hipercampo
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


def test_startup_without_identity_stays_quiet():
    _limpiar_db()
    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps({"hook_event_name": "SessionStart"}))
    try:
        _, salida = _correr("hook")
    finally:
        sys.stdin = original
    assert json.loads(salida) == {}, salida
    _limpiar_db()


# --- commands ---------------------------------------------------------------

def test_remember_and_recall_through_cli():
    _limpiar_db()
    codigo, salida = _correr("remember", "las ballenas azules son los mayores animales")
    assert codigo == 0 and '"stored": true' in salida.lower(), salida
    # Query with SHARED vocabulary. The old query used a pure synonym; with the
    # calibrated ANSWER_MIN_SCORE floor, memory correctly abstains because lexical
    # mode does not cover paraphrases without common words. This test covers CLI
    # PLUMBING, not semantic quality.
    codigo, salida = _correr("recall", "cuales son los mayores animales", "--plain")
    assert codigo == 0 and "ballenas" in salida, salida
    _limpiar_db()


def test_recall_abstains_on_pure_synonym_in_lexical_mode():
    """The honest inverse of the test above: without shared words, lexical mode
    abstains. If that changes, it must be a measured decision rather than a silent
    regression."""
    _limpiar_db()
    _correr("remember", "las ballenas azules son los mayores animales")
    codigo, salida = _correr("recall", "cual es el animal mas grande", "--plain")
    assert codigo == 0, salida
    assert "ballenas" not in salida, salida
    _limpiar_db()


def test_stats_and_doctor_report_without_failure():
    _limpiar_db()
    _correr("remember", "un dato cualquiera para que haya algo que contar")
    codigo, salida = _correr("stats")
    assert codigo == 0 and "total" in salida, salida
    codigo, salida = _correr("doctor")
    assert codigo == 0, salida
    assert "HEALTHY" in salida and "schema" in salida, salida
    _limpiar_db()


def test_version_and_help():
    codigo, salida = _correr("version")
    assert codigo == 0 and salida.strip(), salida
    codigo, salida = _correr()
    assert codigo == 0 and "hipercampo" in salida


def test_empty_text_is_rejected_with_error_code():
    _limpiar_db()
    codigo, _ = _correr("remember")
    assert codigo != 0, "remembering without text must fail rather than store garbage"
    _limpiar_db()


if __name__ == "__main__":
    clean()
    _limpiar_db()
    codigo = run_tests(dict(globals()))
    _limpiar_db()
    sys.exit(codigo)
