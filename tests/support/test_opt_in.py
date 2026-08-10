"""
Per-project opt-in: hipercampo does not switch itself on where nobody asked.

The rule policy.py already applies to writes ("nothing enters memory without
intent"), one level up: being present in a project is a decision too.

The three cases that matter, and the middle one is the one that bites:

    registry exists            -> listed on, unlisted OFF
    no registry, memory exists -> ON (an upgrade must not silently switch off a
                                  setup that works today)
    no registry, no memory     -> OFF (a fresh install starts opted out)
"""

import json
import os
import pathlib
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, clean, run_tests  # noqa: E402


def _fresh(tmp_name):
    """A scratch database directory and two project directories.

    Wipes DIRECTORIES too, not just files: one of the tests below creates a
    directory where a file is expected (to make a write fail), and `unlink` on it
    raised PermissionError on the *next* run — a test that passed the first time
    and failed afterwards, which is the leftover-state trap this suite keeps
    stepping in."""
    import shutil
    base = Path("data") / f"_t_optin_{tmp_name}"
    shutil.rmtree(base / "db", ignore_errors=True)
    for sub in ("db", "proj_a", "proj_b"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    return base


def _env(base, **extra):
    env = dict(os.environ)
    env["HIPERCAMPO_DB"] = str((base / "db" / "hc.db").resolve())
    env["HIPERCAMPO_LOG"] = "0"
    env.pop("HIPERCAMPO_FORCE_ENABLED", None)
    env.update(extra)
    return env


def _cli(base, *args, cwd=None, env_extra=None, stdin=None):
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", *args],
                       capture_output=True, text=True, cwd=str(cwd or ROOT),
                       env=_env(base, **(env_extra or {})), input=stdin)
    assert r.returncode == 0, f"{args}: {r.stderr}"
    return r.stdout


def test_fresh_install_starts_disabled():
    """A brand-new install with no memory is OFF. That is the point of the feature:
    you add hipercampo to a project on purpose."""
    base = _fresh("fresh")
    out = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_a"))
    assert out["enabled_here"] is False, out
    assert out["opt_in_adopted"] is False, out


def test_enabling_one_project_does_not_enable_another():
    base = _fresh("two")
    _cli(base, "enable", cwd=base / "proj_a")
    a = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_a"))
    b = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_b"))
    assert a["enabled_here"] is True, a
    assert b["enabled_here"] is False, b
    assert b["opt_in_adopted"] is True, "the registry exists once anyone opts in"


def test_disable_turns_it_back_off():
    base = _fresh("toggle")
    _cli(base, "enable", cwd=base / "proj_a")
    _cli(base, "disable", cwd=base / "proj_a")
    out = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_a"))
    assert out["enabled_here"] is False, out


def test_an_existing_memory_is_not_switched_off_by_the_upgrade():
    """THE migration case. Someone using hipercampo before opt-in existed must not
    find their memory silently dead after an upgrade, with no error to explain it.
    While no registry exists, an installation that already holds memories stays on
    and `projects` says so out loud."""
    base = _fresh("legacy")
    _cli(base, "remember", "a memory from before opt-in existed",
         cwd=base / "proj_b", env_extra={"HIPERCAMPO_FORCE_ENABLED": "1"})
    out = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_b"))
    assert out["enabled_here"] is True, out
    assert out["opt_in_adopted"] is False, out
    assert "note" in out, "the un-adopted state must be reported, not left implicit"


def test_the_hook_stays_quiet_in_a_project_that_did_not_opt_in():
    """The hook fires on its own, every turn: it is the part that must never run
    where it was not invited. Quiet, and cheap: an empty payload injects nothing."""
    base = _fresh("hook")
    _cli(base, "enable", cwd=base / "proj_a")          # adopt opt-in, a only
    payload = json.dumps({"hook_event_name": "UserPromptSubmit",
                          "prompt": "what do you remember?",
                          "cwd": str((base / "proj_b").resolve())})
    out = _cli(base, "hook", cwd=base / "proj_b", stdin=payload)
    assert json.loads(out) == {}, f"the hook spoke where it was not enabled: {out}"


def test_the_gate_can_be_forced_for_ci_and_embedded_use():
    """Embedded users and CI drive the core directly, with no project to opt in."""
    base = _fresh("forced")
    out = json.loads(_cli(base, "projects", "--json", cwd=base / "proj_a",
                          env_extra={"HIPERCAMPO_FORCE_ENABLED": "1"}))
    assert out["enabled_here"] is True, out


# --- the branches a subprocess test cannot reach ----------------------------
# The tests above drive the real CLI, which is the right way to check behaviour but
# runs in another process: coverage of this module reads 59% while the logic is in
# fact exercised. What those tests genuinely cannot reach are the failure branches —
# an unreadable database, a registry that cannot be written — and those are the ones
# that decide whether somebody's memory goes quiet. They are unit-tested here.

def _config_on(base):
    """Reload config pointed at a scratch database, with the gate not forced."""
    import importlib
    os.environ["HIPERCAMPO_DB"] = str((base / "db" / "hc.db").resolve())
    os.environ.pop("HIPERCAMPO_FORCE_ENABLED", None)
    from hipercampo.support import config
    importlib.reload(config)
    return config


def test_the_same_directory_spelled_differently_is_one_entry():
    """A path is compared as text, so `C:\\Proj`, `c:/proj/` and a relative walk to
    the same place must collapse to one entry — otherwise enabling a project from
    the viewer would not match enabling it from the shell."""
    base = _fresh("paths")
    config = _config_on(base)
    project = (base / "proj_a").resolve()
    config.set_project_enabled(str(project), True)
    for spelling in (str(project), str(project).upper(), str(project) + os.sep):
        assert config.project_enabled(spelling), f"not recognised: {spelling}"


def test_an_unreadable_database_leaves_the_memory_ON():
    """The fail-safe. With no registry the answer depends on whether the database
    holds memories, and if that cannot be determined the answer must be YES: the
    costly mistake here is switching someone's memory off, not leaving it on. A
    file that is not a database stands in for a locked or corrupt one."""
    base = _fresh("unreadable")
    config = _config_on(base)
    db = pathlib.Path(os.environ["HIPERCAMPO_DB"])
    db.write_text("this is not a database", encoding="utf-8")
    assert config._has_existing_memory() is True, "an unreadable DB must not switch it off"
    assert config.project_enabled(str(base / "proj_a")) is True


def test_a_missing_database_starts_opted_out():
    """The other side: nothing installed yet means nothing to protect, so a fresh
    install starts off. This is the branch that makes the feature a feature."""
    base = _fresh("missing")
    config = _config_on(base)
    assert config._has_existing_memory() is False
    assert config.project_enabled(str(base / "proj_a")) is False


def test_a_registry_that_cannot_be_written_does_not_raise():
    """Turning the memory on or off must never crash the caller. If the registry
    cannot be written the state simply does not persist — the viewer shows it
    unchanged — which is preferable to taking down the agent using the memory."""
    base = _fresh("readonly")
    config = _config_on(base)
    blocked = base / "db" / "a_directory_not_a_file"
    blocked.mkdir(exist_ok=True)          # a directory cannot be opened for writing
    original = config._projects_file
    config._projects_file = lambda: str(blocked)
    try:
        # Asserting the return value alone would prove nothing: it echoes the
        # requested state whether or not the write happened. What has to be checked
        # is the observable consequence — no crash, and no registry.
        assert config.set_project_enabled(str(base / "proj_a"), True) is True
        assert config.enabled_projects() is None, "a failed write must not leave a registry"
    finally:
        config._projects_file = original


def test_comments_in_the_registry_are_not_treated_as_projects():
    """The file is written with a header explaining itself, and a user may add
    notes. A comment line must not become a directory nobody can match."""
    base = _fresh("comments")
    config = _config_on(base)
    config.set_project_enabled(str(base / "proj_a"), True)
    with open(config._projects_file(), "a", encoding="utf-8") as f:
        f.write("# a note added by hand\n\n")
    entries = config.enabled_projects()
    assert all(not e.startswith("#") for e in entries), entries
    assert len(entries) == 1, entries


if __name__ == "__main__":
    code = run_tests(dict(globals()))
    clean()
    sys.exit(code)
