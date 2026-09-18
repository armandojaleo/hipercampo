"""
`hipercampo hook-install`: writing the SYNAPTIC hook into settings.json.

Found live, 2026-09-18: a session opened in an old project, enabled and with
the MCP server registered, still had no idea hipercampo existed — nothing had
ever called `hipercampo hook`, because the SessionStart/UserPromptSubmit hook
from docs/INSTALL.md had never been hand-copied into anyone's settings.json.
This covers the fix: `install_hook` must be additive (never clobber existing
hooks or other top-level keys) and idempotent (never duplicate on a second run).
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT))
from hipercampo.support import hooksetup  # noqa: E402


def test_project_scope_creates_settings_from_scratch(tmp_path):
    result = hooksetup.install_hook("project", str(tmp_path))
    assert result["installed"] == ["SessionStart", "UserPromptSubmit"]
    assert result["already_present"] == []

    written = json.loads((tmp_path / ".claude" / "settings.json").read_text("utf-8"))
    for event in ("SessionStart", "UserPromptSubmit"):
        cmds = [h["command"] for g in written["hooks"][event] for h in g["hooks"]]
        assert "python -m hipercampo.cli hook" in cmds


def test_preserves_unrelated_hooks_and_keys(tmp_path):
    settings = tmp_path / ".claude"
    settings.mkdir(parents=True)
    original = {
        "permissions": {"allow": ["Bash(ls)"]},
        "hooks": {
            "PostToolUse": [{"matcher": "Write",
                             "hooks": [{"type": "command", "command": "echo hi"}]}],
        },
    }
    (settings / "settings.json").write_text(json.dumps(original), encoding="utf-8")

    hooksetup.install_hook("project", str(tmp_path))

    written = json.loads((settings / "settings.json").read_text("utf-8"))
    assert written["permissions"] == {"allow": ["Bash(ls)"]}
    assert written["hooks"]["PostToolUse"] == original["hooks"]["PostToolUse"]
    assert "SessionStart" in written["hooks"]
    assert "UserPromptSubmit" in written["hooks"]


def test_idempotent_second_run_does_not_duplicate(tmp_path):
    hooksetup.install_hook("project", str(tmp_path))
    result = hooksetup.install_hook("project", str(tmp_path))

    assert result["installed"] == []
    assert set(result["already_present"]) == {"SessionStart", "UserPromptSubmit"}

    written = json.loads((tmp_path / ".claude" / "settings.json").read_text("utf-8"))
    for event in ("SessionStart", "UserPromptSubmit"):
        assert len(written["hooks"][event]) == 1, (
            f"{event} was duplicated on a second install: {written['hooks'][event]}")


def test_hook_installed_true_only_when_both_events_present(tmp_path):
    assert hooksetup.hook_installed("project", str(tmp_path)) is False
    hooksetup.install_hook("project", str(tmp_path))
    assert hooksetup.hook_installed("project", str(tmp_path)) is True


def test_hook_installed_false_on_missing_settings_file(tmp_path):
    assert hooksetup.hook_installed("project", str(tmp_path / "nowhere")) is False


def test_loose_match_recognises_a_differently_spelled_existing_command(tmp_path):
    """A hook that already calls hipercampo, just spelled differently (a full
    interpreter path, or `hipercampo hook` without `-m`), must count as already
    installed — not get a second, redundant entry appended next to it."""
    settings = tmp_path / ".claude"
    settings.mkdir(parents=True)
    existing = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command",
                                         "command": "hipercampo hook"}]}],
            "UserPromptSubmit": [{"hooks": [{"type": "command",
                                             "command":
                                                 "/usr/bin/python3 -m hipercampo.cli hook"}]}],
        }
    }
    (settings / "settings.json").write_text(json.dumps(existing), encoding="utf-8")

    result = hooksetup.install_hook("project", str(tmp_path))

    assert result["installed"] == []
    assert set(result["already_present"]) == {"SessionStart", "UserPromptSubmit"}
