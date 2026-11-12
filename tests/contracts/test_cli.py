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


def test_hook_injects_an_index_line_for_long_memories():
    # Measured before the index: ~300 tok per injecting turn, paid whether
    # the memory was read or not. A long memory now enters as ONE line with
    # its #id, and the agent reads the rest on demand.
    _limpiar_db()
    largo = ("El servidor de produccion esta alojado en Frankfurt. "
             + "La migracion se hizo en marzo porque la latencia desde Madrid "
               "era de ochenta milisegundos y el proveedor anterior subio el precio "
               "un cuarenta por ciento sin previo aviso, cosa que nadie esperaba. " * 2
             + "COLA_QUE_NO_DEBE_ENTRAR")
    _correr("remember", largo)
    r = _hook("¿donde esta alojado el servidor de produccion?")
    ctx = r["hookSpecificOutput"]["additionalContext"]
    assert "Frankfurt" in ctx, ctx
    assert "COLA_QUE_NO_DEBE_ENTRAR" not in ctx, ctx
    assert "- #" in ctx and "hc_recall(ids=" in ctx, ctx
    _limpiar_db()


def test_atom_and_its_source_are_shown_once():
    # Seen in the real memory: an atom and its own source back to back,
    # the same sentence twice. The source becomes a pointer on the atom.
    _limpiar_db()
    texto = ("El servidor de produccion esta alojado en Frankfurt desde marzo. "
             "La base de datos usa PostgreSQL dieciseis con replicas en Dublin. "
             "Las copias de seguridad se hacen cada noche a las tres en punto. "
             "El dominio principal se renueva cada mes de octubre sin falta. "
             "Los certificados TLS los emite Let's Encrypt de forma automatica. "
             "El equipo de guardia rota cada semana entre cuatro personas fijas. "
             "Los registros se guardan noventa dias antes de borrarse del todo. "
             "La monitorizacion avisa por Telegram cuando algo cae mas de un minuto.")
    r = json.loads(_correr("remember", texto)[1] or "{}")
    assert r.get("atomized"), r
    ctx = _hook("¿donde esta alojado el servidor de produccion?")[
        "hookSpecificOutput"]["additionalContext"]
    assert ctx.count("Frankfurt") == 1, ctx
    assert f"(more: #{r['id']})" in ctx, ctx
    _limpiar_db()


def test_short_memory_goes_in_whole_without_index_marks():
    _limpiar_db()
    _correr("remember", "el servidor de produccion esta alojado en Frankfurt")
    ctx = _hook("¿donde esta alojado el servidor de produccion?")[
        "hookSpecificOutput"]["additionalContext"]
    assert "- #" not in ctx and "hc_recall(ids=" not in ctx, ctx
    _limpiar_db()


def test_get_by_id_returns_full_text_and_reinforces():
    from hipercampo.cycle.memory import Hipercampo
    _limpiar_db()
    hc = Hipercampo(_DB)
    try:
        mid = hc.remember("dato unico para leer por id, con su cola entera", 0.5)["id"]
        antes = hc.store.get(mid)["access_count"]
        got = hc.get([mid, 999999])
        assert [g["id"] for g in got] == [mid], got
        assert got[0]["text"].endswith("cola entera"), got
        assert hc.store.get(mid)["access_count"] == antes + 1
        # The identity index points into __self__: those ids must resolve too.
        sid = hc.learn("una leccion larga de identidad", "leccion")["id"]
        assert [g["id"] for g in hc.get([sid])] == [sid]
    finally:
        hc.close()
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


def _hook_payload(payload: dict) -> dict:
    original = sys.stdin
    sys.stdin = io.StringIO(json.dumps(payload))
    try:
        _, salida = _correr("hook")
    finally:
        sys.stdin = original
    return json.loads(salida)


def _fake_transcript(path: Path, prompts: list[str], edited: list[str]) -> None:
    """The shape of a Claude Code transcript (.jsonl), reduced to what matters."""
    rows = [{"type": "ai-title", "aiTitle": "Checkpoint al cerrar la sesion"}]
    for p in prompts:
        rows.append({"type": "user", "message": {"role": "user", "content": p}})
    for i, f in enumerate(edited):
        rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "Edit",
             "input": {"file_path": f}}]}})
    rows.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": "Siguiente paso: medir el ahorro de tokens."}]}})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_session_end_leaves_a_checkpoint_the_next_session_starts_from(tmp_path):
    """A long session is expensive because every turn re-sends the whole
    history; the way out is a NEW session, and that's only free if nothing
    is lost. Before this, closing or compacting saved nothing: the next
    session started from the identity alone."""
    _limpiar_db()
    transcript = tmp_path / "s.jsonl"
    _fake_transcript(transcript,
                     ["guardar un checkpoint cuando la sesion se compacta", "si"],
                     [str(tmp_path / "hipercampo" / "support" / "checkpoint.py")])
    r = _hook_payload({"hook_event_name": "PreCompact", "cwd": str(tmp_path),
                       "session_id": "a", "transcript_path": str(transcript)})
    assert r == {}, r                    # PreCompact has nothing to say back

    r = _hook_payload({"hook_event_name": "SessionStart", "source": "startup",
                       "cwd": str(tmp_path), "session_id": "b"})
    ctx = r.get("hookSpecificOutput", {}).get("additionalContext", "")
    assert "where we left off" in ctx, r
    assert "guardar un checkpoint" in ctx, ctx
    assert "checkpoint.py" in ctx, ctx
    assert "medir el ahorro" in ctx, ctx
    _limpiar_db()


def test_an_empty_session_does_not_erase_the_previous_checkpoint(tmp_path):
    """Opening a session and closing it straight away must not overwrite real
    work with nothing — that would be losing context, the very failure."""
    _limpiar_db()
    full, empty = tmp_path / "full.jsonl", tmp_path / "empty.jsonl"
    _fake_transcript(full, ["refactorizar el modulo de presupuesto"], [])
    empty.write_text(json.dumps({"type": "user", "message": {"content": "si"}}),
                     encoding="utf-8")
    for t in (full, empty):
        _hook_payload({"hook_event_name": "SessionEnd", "cwd": str(tmp_path),
                       "session_id": t.stem, "transcript_path": str(t)})
    r = _hook_payload({"hook_event_name": "SessionStart", "source": "startup",
                       "cwd": str(tmp_path), "session_id": "next"})
    assert "refactorizar" in r.get("hookSpecificOutput", {}).get(
        "additionalContext", ""), r
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
