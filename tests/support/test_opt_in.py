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
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, clean, run_tests  # noqa: E402


def _fresh(tmp_name):
    """A scratch database directory and two project directories."""
    base = Path("data") / f"_t_optin_{tmp_name}"
    for sub in ("db", "proj_a", "proj_b"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    for f in (base / "db").glob("*"):
        f.unlink()
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


if __name__ == "__main__":
    code = run_tests(dict(globals()))
    clean()
    sys.exit(code)
