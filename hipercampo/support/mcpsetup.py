"""`hipercampo install`: register the MCP server for a project and choose,
explicitly, whether it joins a shared memory or gets its own isolated drawer.

Exists because registering the server (`claude mcp add`, or hand-editing
`.mcp.json` / `~/.claude.json`) and choosing a namespace were always two
separate, manual, undocumented-in-practice steps — the same gap that left a
project sharing the "personal" namespace with everything else without anyone
having decided that on purpose. See docs/INSTALL.md's "Isolating contexts"
section for the underlying model this automates.
"""

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

_ENTRY_NAME = "hipercampo"


def slug_namespace(path: str) -> str:
    """`proj-<directory-name>`, lowercased and safe — matches the convention
    already used throughout docs/INSTALL.md's examples (proj-webshop, ...)."""
    name = Path(os.path.abspath(path)).name or "project"
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"
    return f"proj-{slug}"


def _server_entry(namespace: str, extra_env: dict[str, str] | None = None) -> dict:
    env = {"HIPERCAMPO_NAMESPACE": namespace}
    if extra_env:
        env.update(extra_env)
    return {"command": sys.executable, "args": ["-m", "hipercampo.server"], "env": env}


def _load_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def project_mcp_path(path: str) -> Path:
    return Path(path) / ".mcp.json"


def global_mcp_path() -> Path:
    return Path(os.path.expanduser("~")) / ".claude.json"


def find_global_hipercampo_server() -> tuple[str, str] | None:
    """(server_name, namespace) of an EXISTING user-scope registration that
    already runs `hipercampo.server`, or None. Used by --shared: if one
    exists, a new project should join it rather than create a second one."""
    data = _load_json(global_mcp_path())
    for name, cfg in (data.get("mcpServers") or {}).items():
        if not isinstance(cfg, dict):
            continue
        args = cfg.get("args") or []
        if any("hipercampo.server" in str(a) for a in args):
            ns = (cfg.get("env") or {}).get("HIPERCAMPO_NAMESPACE", "default")
            return name, ns
    return None


def install_isolated(path: str) -> dict:
    """Writes/merges this project's OWN `.mcp.json`, with its own namespace
    in the shared DB file — nothing else reads or writes it, per
    docs/INSTALL.md's recommended namespace-isolation pattern. Additive: an
    existing `.mcp.json` keeps whatever other servers it already declares."""
    target = project_mcp_path(path)
    data = _load_json(target)
    servers = data.setdefault("mcpServers", {})
    if _ENTRY_NAME in servers:
        return {"action": "already_present", "path": str(target),
                "namespace": (servers[_ENTRY_NAME].get("env") or {}).get(
                    "HIPERCAMPO_NAMESPACE", "?")}
    namespace = slug_namespace(path)
    servers[_ENTRY_NAME] = _server_entry(namespace)
    _write_json(target, data)
    return {"action": "created", "path": str(target), "namespace": namespace}


def install_shared(path: str) -> dict:
    """Joins an EXISTING user-scope hipercampo registration if there is one
    (nothing to write — the project just needs `enable`); otherwise creates
    one at user scope under namespace "shared", the deliberately generic
    drawer every --shared project ends up in together."""
    existing = find_global_hipercampo_server()
    if existing:
        name, namespace = existing
        return {"action": "joined_existing", "server": name, "namespace": namespace,
                "path": str(global_mcp_path())}
    target = global_mcp_path()
    data = _load_json(target)
    servers = data.setdefault("mcpServers", {})
    servers[_ENTRY_NAME] = _server_entry("shared")
    _write_json(target, data)
    return {"action": "created", "path": str(target), "namespace": "shared"}


def install(path: str, mode: str) -> dict[str, Any]:
    """`mode` is "isolated" or "shared". Registration only — enabling the
    project and installing the SYNAPTIC hook are separate, existing steps
    (`config.set_project_enabled`, `hooksetup.install_hook`) that
    `cmd_install` in cli.py composes with this."""
    if mode not in ("isolated", "shared"):
        raise ValueError('mode must be "isolated" or "shared"')
    return install_isolated(path) if mode == "isolated" else install_shared(path)
