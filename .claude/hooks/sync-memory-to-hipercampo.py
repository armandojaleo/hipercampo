#!/usr/bin/env python3
"""PostToolUse hook (Write|Edit): whenever Claude Code writes or updates one of its
own auto-memory files (~/.claude/projects/<project>/memory/*.md), mirror that file's
content into hipercampo too, under this project's namespace.

Deliberately silent on any failure: this is a convenience mirror, not something that
should ever interrupt or fail a turn. MEMORY.md (the index, not a memory) is skipped.
"""
import json
import os
import re
import subprocess
import sys

NAMESPACE = "proj-hipercampo"


def main() -> None:
    try:
        data = json.load(sys.stdin)
    except (ValueError, OSError):
        return

    path = (data.get("tool_input") or {}).get("file_path") or ""
    norm = path.replace("\\", "/")
    if not re.search(r"/memory/[^/]+\.md$", norm) or norm.endswith("/MEMORY.md"):
        return

    try:
        text = open(path, encoding="utf-8").read().strip()
    except OSError:
        return
    # Strip the YAML frontmatter (name/description/metadata): it's bookkeeping for
    # the memory file itself, not prose worth atomizing into hipercampo.
    text = re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.S).strip()
    if not text:
        return

    env = dict(os.environ, HIPERCAMPO_NAMESPACE=NAMESPACE)
    try:
        subprocess.run(
            [sys.executable, "-m", "hipercampo.cli", "remember", text, "--importance", "0.6"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        pass


if __name__ == "__main__":
    main()
