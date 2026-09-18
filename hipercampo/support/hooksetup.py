"""Installs the SYNAPTIC-mode hook (SessionStart + UserPromptSubmit calling
`hipercampo hook`) into a Claude Code settings.json — global or per-project.

This exists because the hook being documented (docs/INSTALL.md, "SYNAPTIC
mode") was not enough: a real session opened in an old project, with
hipercampo enabled for it and the MCP server registered, still had no idea
hipercampo existed — nothing had ever called `hipercampo hook`, because
nobody had hand-copied the JSON from the guide into their global settings.
`hipercampo enable` now offers to fix this once, everywhere, instead of
depending on someone having read that section.
"""

import json
import os
from pathlib import Path
from typing import Any

_COMMAND = "python -m hipercampo.cli hook"
_EVENTS = {
    "SessionStart": "recordando quién soy trabajando...",
    "UserPromptSubmit": "consultando la memoria...",
}


def settings_path(scope: str) -> Path:
    """`scope` is "global" (~/.claude/settings.json) or "project" (the given
    directory's .claude/settings.json)."""
    if scope == "global":
        return Path(os.path.expanduser("~")) / ".claude" / "settings.json"
    raise ValueError('settings_path(scope) only accepts "global" here; '
                     "project scope takes an explicit path — see project_settings_path")


def project_settings_path(path: str) -> Path:
    return Path(path) / ".claude" / "settings.json"


def _has_our_hook(groups: Any, event: str) -> bool:
    """True if some hook entry under this event already runs our command.
    Loose match (command CONTAINS "hipercampo" and "hook") so a slightly
    different invocation (full path to python, `hipercampo hook` without
    `-m`, …) still counts as already installed rather than being duplicated."""
    if not isinstance(groups, list):
        return False
    for group in groups:
        for entry in (group or {}).get("hooks", []) if isinstance(group, dict) else []:
            cmd = str(entry.get("command", "")) if isinstance(entry, dict) else ""
            if "hipercampo" in cmd and "hook" in cmd:
                return True
    return False


def hook_installed(scope: str, path: str | None = None) -> bool:
    """Is the hook already present (global, or for this project directory)?
    Missing/unreadable settings.json counts as "not installed", never as an
    error — this is a read used to decide whether to SUGGEST, not act."""
    target = settings_path(scope) if scope == "global" else project_settings_path(path or ".")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks = data.get("hooks", {}) if isinstance(data, dict) else {}
    return all(_has_our_hook(hooks.get(event), event) for event in _EVENTS)


def install_hook(scope: str, path: str | None = None) -> dict:
    """Merges the SessionStart + UserPromptSubmit hook into the target
    settings.json, preserving whatever else is already there (other hooks,
    other top-level keys). Idempotent: running it twice does not duplicate
    entries. Returns {"installed": [...], "already_present": [...], "path": str}."""
    target = settings_path(scope) if scope == "global" else project_settings_path(path or ".")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            data = {}
    except (OSError, ValueError):
        data = {}

    hooks = data.setdefault("hooks", {})
    installed, present = [], []
    for event, status_message in _EVENTS.items():
        groups = hooks.setdefault(event, [])
        if not isinstance(groups, list):
            # Someone hand-edited this into something unexpected: leave it
            # alone rather than guess and risk breaking their config.
            continue
        if _has_our_hook(groups, event):
            present.append(event)
            continue
        groups.append({"hooks": [{
            "type": "command", "command": _COMMAND, "timeout": 15,
            "statusMessage": status_message,
        }]})
        installed.append(event)

    if installed:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
    return {"path": str(target), "installed": installed, "already_present": present}
