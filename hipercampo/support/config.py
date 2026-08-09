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


# --- per-project activation (opt-in) ----------------------------------------
# hipercampo must not switch itself on in a project nobody asked it to. The same
# rule policy.py already applies to writes ("nothing enters memory without
# intent"), one level up: being present in a project is also a decision.
#
# The project is identified by its DIRECTORY, not by its namespace. That is not a
# preference, it is forced: a server registered at user scope carries a single
# HIPERCAMPO_NAMESPACE, so every project without its own `.mcp.json` shares it.
# The namespace cannot tell two projects apart; the path can.
#
# The registry lives next to the database rather than as a marker file inside each
# project: hipercampo should not litter repositories that are not its own, and one
# central list is what lets the viewer show "where is this active" and toggle it.
# It is read HOT on every call, like `paused()`, so the viewer changes take effect
# without restarting the MCP server.

def _projects_file() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(db_path())) or ".",
                        "hipercampo.projects")


def _normalise(path: str) -> str:
    r"""One canonical spelling per directory, so C:\Proj and c:/proj/ are one entry."""
    return os.path.normcase(os.path.abspath(os.path.expanduser(path or ".")))


def enabled_projects() -> list[str] | None:
    """The directories where hipercampo is active, or None if never configured.

    None is NOT an empty list, and the difference is the whole migration story:
    `None` means the user has not adopted opt-in yet (see `project_enabled`)."""
    try:
        with open(_projects_file(), encoding="utf-8") as f:
            return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]
    except OSError:
        return None


def set_project_enabled(path: str, on: bool) -> bool:
    """Add or remove a project from the registry. Returns the resulting state.

    Writing the registry for the first time is what ADOPTS opt-in: from then on,
    anything not listed is off."""
    entry = _normalise(path)
    current = enabled_projects()
    entries = list(current) if current is not None else []
    entries = [e for e in entries if e != entry]
    if on:
        entries.append(entry)
    try:
        os.makedirs(os.path.dirname(_projects_file()) or ".", exist_ok=True)
        with open(_projects_file(), "w", encoding="utf-8") as f:
            f.write("# Projects where hipercampo is active. Managed by the viewer\n"
                    "# and by `hipercampo enable` / `hipercampo disable`.\n")
            for e in entries:
                f.write(e + "\n")
    except OSError:
        pass
    return on


def project_enabled(path: str | None = None) -> bool:
    """Is hipercampo active for this project directory?

    Three cases, and the middle one is what keeps an upgrade from silently
    switching off a setup that works today:

      registry exists            -> listed = on, unlisted = OFF (the opt-in model)
      no registry, memory exists -> ON. The user has been using hipercampo since
                                    before opt-in existed; turning their memory off
                                    on upgrade, with no error to explain it, would
                                    be exactly the silent failure this project keeps
                                    getting bitten by. `hipercampo status` reports
                                    that opt-in is available but not adopted.
      no registry, no memory     -> OFF. A fresh install starts opted out, which is
                                    the point: you add hipercampo to a project on
                                    purpose.
    """
    if os.environ.get("HIPERCAMPO_FORCE_ENABLED") == "1":
        return True                       # escape hatch for CI and embedded use
    registry = enabled_projects()
    if registry is not None:
        return _normalise(path or os.getcwd()) in registry
    return _has_existing_memory()


def _has_existing_memory() -> bool:
    """Does the database already hold memories? Cheap and failure-tolerant: if it
    cannot be answered, assume yes, because the costly mistake here is switching
    someone's memory off, not leaving it on."""
    import sqlite3
    path = db_path()
    if not os.path.exists(path):
        return False
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=2.0)
        try:
            return con.execute("SELECT 1 FROM memories LIMIT 1").fetchone() is not None
        finally:
            con.close()
    except sqlite3.Error:
        return True


def opt_in_adopted() -> bool:
    """Whether the registry exists at all (for `status` to report honestly)."""
    return enabled_projects() is not None
