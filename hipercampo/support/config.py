"""Shared configuration: where the memory lives."""

import os


def default_db() -> str:
    """Database path if HIPERCAMPO_DB isn't set.

    - In Docker (if /data exists, usually a volume): /data/hipercampo.db
    - Locally: ~/.hipercampo/hipercampo.db  (predictable and easy to back up)
    """
    # The /data branch is for Linux containers (Docker). On Windows "/data"
    # would accidentally resolve to <drive>:\data, so it's required to be POSIX.
    if os.name == "posix" and os.path.isdir("/data"):
        return "/data/hipercampo.db"
    return os.path.join(os.path.expanduser("~"), ".hipercampo", "hipercampo.db")


def db_path() -> str:
    """The effective path: HIPERCAMPO_DB if set, otherwise the default."""
    return os.environ.get("HIPERCAMPO_DB", default_db())


def _pause_flag() -> str:
    """The 'memory paused' flag file, next to the database."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path())) or ".",
                        "hipercampo.paused")


def paused() -> bool:
    """Is the memory PAUSED ('do not record' mode)? Checked on every write.

    Two sources, both valid and checked LIVE (never cached), so the viewer
    can flip the mode on/off without restarting the MCP server or the hook:
      - the HIPERCAMPO_PAUSED=1 variable (a session that starts paused), and
      - a flag file next to the .db (the switch the viewer toggles).
    While active, no new memories are recorded and existing ones aren't
    reinforced; READING keeps working. Nothing is deleted: it just stops writing.
    """
    if os.environ.get("HIPERCAMPO_PAUSED", "") not in ("", "0", "false", "False"):
        return True
    try:
        return os.path.isfile(_pause_flag())
    except OSError:
        return False


def set_paused(on: bool) -> bool:
    """Turns the pause on or off by creating/removing the flag file. Returns
    the resulting state. The environment variable, if set, overrides this."""
    flag = _pause_flag()
    try:
        if on:
            os.makedirs(os.path.dirname(flag) or ".", exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("memory paused ('do not record' mode)\n")
        else:
            if os.path.isfile(flag):
                os.remove(flag)
    except OSError:
        pass
    return paused()


def _budget_file() -> str:
    """File holding the hook's token budget, next to the database.
    Persisting it here (not just in an environment variable) lets the viewer
    adjust it and the HOOK honor it on the next turn, without touching
    configs by hand."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path())) or ".",
                        "hipercampo.budget")


def hook_budget_persisted() -> int | None:
    """The budget saved to file, or None if never set (use the factory
    default). The HIPERCAMPO_HOOK_BUDGET variable, if set, overrides this."""
    try:
        with open(_budget_file(), encoding="utf-8") as f:
            return max(0, int(f.read().strip()))
    except (OSError, ValueError):
        return None


def set_hook_budget(tokens: int | None) -> None:
    """Sets (or clears, with None) the hook's budget. Read LIVE: the next
    hook already uses the new value, nothing needs restarting."""
    flag = _budget_file()
    try:
        if tokens is None:
            if os.path.isfile(flag):
                os.remove(flag)
        else:
            os.makedirs(os.path.dirname(flag) or ".", exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write(str(max(0, int(tokens))))
    except OSError:
        pass
