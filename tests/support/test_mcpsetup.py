"""
`hipercampo install`: registering the MCP server with an explicit isolated/
shared choice, instead of a project ending up wherever the last `claude mcp
add` happened to point.

Covers the two modes plus the two cases each depends on getting right: a
second `--isolated` project must NOT collide with the first project's
namespace, and a second `--shared` project must JOIN the existing
registration rather than create a duplicate one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT  # noqa: E402

sys.path.insert(0, str(ROOT))
from hipercampo.support import mcpsetup  # noqa: E402


def test_slug_namespace_from_directory_name():
    assert mcpsetup.slug_namespace("/code/My Cool Project!") == "proj-my-cool-project"


def test_isolated_creates_project_mcp_json_with_own_namespace(tmp_path):
    result = mcpsetup.install_isolated(str(tmp_path))
    assert result["action"] == "created"

    written = json.loads((tmp_path / ".mcp.json").read_text("utf-8"))
    entry = written["mcpServers"]["hipercampo"]
    assert entry["env"]["HIPERCAMPO_NAMESPACE"] == mcpsetup.slug_namespace(str(tmp_path))
    assert entry["args"] == ["-m", "hipercampo.server"]


def test_isolated_is_idempotent_and_reports_existing_namespace(tmp_path):
    first = mcpsetup.install_isolated(str(tmp_path))
    second = mcpsetup.install_isolated(str(tmp_path))
    assert second["action"] == "already_present"
    assert second["namespace"] == first["namespace"]


def test_isolated_preserves_other_servers_already_in_mcp_json(tmp_path):
    (tmp_path / ".mcp.json").write_text(
        json.dumps({"mcpServers": {"other": {"command": "echo"}}}), encoding="utf-8")
    mcpsetup.install_isolated(str(tmp_path))
    written = json.loads((tmp_path / ".mcp.json").read_text("utf-8"))
    assert written["mcpServers"]["other"] == {"command": "echo"}
    assert "hipercampo" in written["mcpServers"]


def test_isolated_two_different_projects_get_different_namespaces(tmp_path):
    a = tmp_path / "webshop"
    b = tmp_path / "blog"
    a.mkdir()
    b.mkdir()
    ra = mcpsetup.install_isolated(str(a))
    rb = mcpsetup.install_isolated(str(b))
    assert ra["namespace"] != rb["namespace"]


def test_shared_creates_a_user_scope_entry_when_none_exists(tmp_path, monkeypatch):
    monkeypatch.setattr(mcpsetup, "global_mcp_path", lambda: tmp_path / ".claude.json")
    result = mcpsetup.install_shared(str(tmp_path / "proj"))
    assert result["action"] == "created"
    written = json.loads((tmp_path / ".claude.json").read_text("utf-8"))
    assert written["mcpServers"]["hipercampo"]["env"]["HIPERCAMPO_NAMESPACE"] == "shared"


def test_shared_second_project_joins_the_existing_registration(tmp_path, monkeypatch):
    monkeypatch.setattr(mcpsetup, "global_mcp_path", lambda: tmp_path / ".claude.json")
    mcpsetup.install_shared(str(tmp_path / "proj_a"))
    second = mcpsetup.install_shared(str(tmp_path / "proj_b"))

    assert second["action"] == "joined_existing"
    assert second["namespace"] == "shared"
    # Only one entry — a second project must not create a competing one.
    written = json.loads((tmp_path / ".claude.json").read_text("utf-8"))
    assert list(written["mcpServers"].keys()) == ["hipercampo"]


def test_shared_finds_a_differently_named_existing_server(tmp_path, monkeypatch):
    """A user may have registered hipercampo under any server name (the docs'
    own examples use "personal"). --shared must recognise it by what it RUNS,
    not by assuming the entry is literally called "hipercampo"."""
    target = tmp_path / ".claude.json"
    target.write_text(json.dumps({"mcpServers": {"personal": {
        "command": "python", "args": ["-m", "hipercampo.server"],
        "env": {"HIPERCAMPO_NAMESPACE": "personal"},
    }}}), encoding="utf-8")
    monkeypatch.setattr(mcpsetup, "global_mcp_path", lambda: target)

    result = mcpsetup.install_shared(str(tmp_path / "proj"))

    assert result == {"action": "joined_existing", "server": "personal",
                      "namespace": "personal", "path": str(target)}


def test_cli_install_refuses_instead_of_crashing_on_closed_stdin(tmp_path):
    """Found live: `sys.stdin.isatty()` reported True under a redirected/
    empty stdin (git-bash on Windows), so `input()` hit an uncaught EOFError
    instead of the intended refusal message — a crash with a traceback where
    a clean "re-run with a flag" was supposed to be. `subprocess.DEVNULL`
    reproduces the same closed-stdin shape regardless of platform."""
    env = dict(os.environ)
    env["HOME"] = str(tmp_path)
    env["USERPROFILE"] = str(tmp_path)
    (tmp_path / "proj").mkdir()

    r = subprocess.run(
        [sys.executable, "-m", "hipercampo.cli", "install", str(tmp_path / "proj")],
        capture_output=True, text=True, cwd=str(ROOT), env=env,
        stdin=subprocess.DEVNULL,
    )

    assert r.returncode == 2, r.stderr
    assert "Traceback" not in r.stderr, r.stderr
    assert "re-run" in r.stderr.lower(), r.stderr
