"""
Where a session left off (support/checkpoint.py).

The bookmark is only worth anything if it says what HAPPENED, not what was
attempted: a failed Edit changed nothing, IDE blocks aren't the user's words,
and "si" is not a request. Each of those, if let through, makes the next
session start from a confident wrong picture.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT))
from hipercampo.support import checkpoint  # noqa: E402


def _write(path: Path, rows: list[dict]) -> str:
    path.write_text("\n".join(json.dumps(r) for r in rows) + "\nnot json\n",
                    encoding="utf-8")
    return str(path)


def _tool(tool_id: str, name: str, **args) -> dict:
    return {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": tool_id, "name": name, "input": args}]}}


def _result(tool_id: str, error: bool) -> dict:
    return {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": tool_id, "is_error": error}]}}


def test_a_failed_edit_is_not_reported_as_a_change(tmp_path):
    t = _write(tmp_path / "t.jsonl", [
        {"type": "user", "message": {"content": "arregla el contador de tokens"}},
        _tool("ok", "Edit", file_path=str(tmp_path / "a.py")),
        _result("ok", False),
        _tool("bad", "Edit", file_path=str(tmp_path / "b.py")),
        _result("bad", True),
    ])
    cp = checkpoint.extract(t, str(tmp_path))
    assert cp["files"] == ["a.py"], cp


def test_commit_subject_from_a_heredoc_and_from_dash_m(tmp_path):
    heredoc = ("git commit -m \"$(cat <<'EOF'\nShow a fact once\n\nBody.\n"
               "EOF\n)\"")
    t = _write(tmp_path / "t.jsonl", [
        _tool("c1", "Bash", command=heredoc), _result("c1", False),
        _tool("c2", "Bash", command='git add . && git commit -m "Fix the audit"'),
        _result("c2", False),
        _tool("c3", "Bash", command="git log --oneline"), _result("c3", False),
    ])
    assert checkpoint.extract(t)["commits"] == ["Show a fact once", "Fix the audit"]


def test_ide_noise_and_one_word_replies_are_not_requests(tmp_path):
    t = _write(tmp_path / "t.jsonl", [
        {"type": "user", "message": {"content": [{"type": "text", "text":
            "<ide_opened_file>the user opened cli.py</ide_opened_file> si"}]}},
        {"type": "user", "message": {"content": "dale"}},
        {"type": "user", "isMeta": True,
         "message": {"content": "Caveat: messages below were generated locally"}},
    ])
    assert checkpoint.extract(t) is None


def test_last_said_keeps_the_end_where_the_next_step_is(tmp_path):
    long = ("Primera frase que explica el contexto con bastante detalle. " * 20
            + "¿Empiezo por el punto 1?")
    cp = {"prompts": ["algo largo que pedir aqui"], "last_said": long, "at": 0}
    rendered = "\n".join(checkpoint.render(cp))
    assert "¿Empiezo por el punto 1?" in rendered, rendered


def test_missing_transcript_is_nothing_not_an_error(tmp_path):
    assert checkpoint.extract(str(tmp_path / "gone.jsonl")) is None


def test_a_tight_budget_drops_the_file_list_before_the_next_step():
    """Measured on a real session: cutting from the bottom dropped "last
    said" — the next step — and kept six file paths."""
    cp = {"title": "Abstencion y consolidacion", "at": 0,
          "prompts": ["Tengo este feedback sobre la abstencion", "si tu mismo"],
          "files": [f"tests/contracts/test_file_{i}.py" for i in range(12)],
          "commits": ["Make the injection audit read tokens"],
          "last_said": "Hecho y medido. ¿Sigo con el punto 2?"}
    rendered = "\n".join(checkpoint.render(cp, max_tokens=80))
    assert "¿Sigo con el punto 2?" in rendered, rendered
    assert "test_file_" not in rendered, rendered


def test_pasted_text_is_the_request_so_only_its_wrapper_goes(tmp_path):
    t = _write(tmp_path / "t.jsonl", [{"type": "user", "message": {"content":
        'Tengo este feedback: <pasted_content id="7f">los pesos no cambian'
        '</pasted_content id="7f">'}}])
    assert checkpoint.extract(t)["prompts"] == [
        "Tengo este feedback: los pesos no cambian"]
