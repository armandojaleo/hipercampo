"""
The JSON the VS Code viewer consumes.

There is a seam here that nothing else covers: the CLI emits JSON in Python and
`editor/media/viewer.js` reads it in JavaScript. No Python test imports the
viewer, and no JS test runs the CLI, so a renamed output key breaks the panel
SILENTLY — the value just renders empty, and everything stays green.

That is not hypothetical. Migrating the output keys to English renamed
`metodo` -> `method`, and the viewer kept reading `s.metodo`: the "how tokens
were counted" note went blank and no test noticed.

So this reads the actual keys the viewer asks for and checks the CLI really
produces them.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, run_tests  # noqa: E402

VIEWER = ROOT / "editor" / "media" / "viewer.js"


_DB = Path(tempfile.gettempdir()) / "hc_viewer_test" / "v.db"


def _cli(*args):
    """Run the CLI against a scratch database and parse its JSON."""
    env = dict(os.environ)
    env["HIPERCAMPO_DB"] = str(_DB)
    env["HIPERCAMPO_LOG"] = "1"          # the log panel needs entries to bind against
    _DB.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, f"{args} failed: {r.stderr}"
    return json.loads(r.stdout)


def _seeded():
    """A scratch memory holding a memory, a fact and a log entry.

    The tests below bind viewer field names against the FIRST element of each
    payload, so an empty payload would make them pass while checking nothing —
    the vacuous-test trap this file exists to prevent. Rather than skip on empty,
    they seed what they need, so they always have something to check."""
    import hipercampo.support.audit as audit
    from hipercampo.cycle.memory import Hipercampo
    _DB.parent.mkdir(parents=True, exist_ok=True)
    # The same namespace the CLI will read: `_cli` runs with HIPERCAMPO_NAMESPACE
    # unset, so it looks at "default". Seeding elsewhere left graph and facts empty
    # — which the non-empty guards above caught, as intended.
    hc = Hipercampo(str(_DB), namespace="default")
    try:
        hc.remember("the viewer binds node fields by name, so they are a contract", 0.6)
        hc.remember("a second memory, so the map has an edge to draw", 0.6)
        hc.remember_fact({"subject": "viewer", "predicate": "reads", "object": "json"})
        audit.set_logfile(str(_DB))
        audit.log("recall", "a log entry for the panel to bind against")
    finally:
        hc.close()


def test_status_stats_has_every_key_the_viewer_reads():
    """The viewer's stats panel reads `st.<key>` off `status.stats`."""
    js = VIEWER.read_text(encoding="utf-8", errors="replace")
    wanted = set(re.findall(r"\bst\.([a-z_]+)", js)) - {"tokens"}
    stats = _cli("status")["stats"]
    available = set(stats) | set(stats.get("tokens") or {})
    missing = wanted - available
    assert not missing, (
        f"the viewer reads keys that `status` no longer emits: {sorted(missing)}\n"
        f"available: {sorted(available)}")


def test_tokens_summary_has_every_key_the_viewer_reads():
    """The token panel reads its summary keys. Checked by name against the
    literal accesses in the viewer, which is how the `metodo`/`method` mismatch
    would have been caught."""
    summary = _cli("tokens")["summary"]
    # Only the accesses inside the token panel: elsewhere `s` is a different
    # object (SVG nodes, the status payload), so a blind `s.*` sweep would be
    # all false positives.
    js = VIEWER.read_text(encoding="utf-8", errors="replace")
    panel = js[js.find("tEstimacion") - 4000:js.find("tEstimacion") + 500]
    wanted = {k for k in re.findall(r"\bs\.([a-z_]+)", panel)}
    missing = wanted - set(summary)
    assert not missing, (
        f"the viewer reads token keys that `tokens` no longer emits: {sorted(missing)}\n"
        f"available: {sorted(summary)}")


def _render_body(name: str) -> str:
    """The body of a render function in viewer.js, so a `x.key` scan stays inside
    the panel that owns `x`. Single-letter names are reused all over the file, and
    a blind sweep would be mostly false positives."""
    js = VIEWER.read_text(encoding="utf-8", errors="replace")
    start = js.find(f"function {name}(")
    assert start != -1, f"{name}() is gone from viewer.js — this test needs updating"
    return js[start:start + 2500]


def test_log_entries_have_every_key_the_viewer_reads():
    """The log panel is where the "?" rows came from. The producer was fixed, but
    nothing checked that what the CLI emits is what the panel reads — and the panel
    prints "?" when `action` is missing, so a rename would look like data loss
    rather than a bug."""
    _seeded()
    entries = _cli("log", "--json", "-n", "5")["entries"]
    assert entries, "no log entries: the binding would go unchecked"
    wanted = set(re.findall(r"\be\.([a-z_]+)", _render_body("renderLog")))
    missing = wanted - set(entries[0])
    assert not missing, (
        f"the viewer reads log keys the CLI does not emit: {sorted(missing)}\n"
        f"emitted: {sorted(entries[0])}")


# Fields the viewer reads off `m` that come from a RECALL RESULT, not from a stored
# memory: the map and the search results share the same rendering code and the same
# variable. They are not part of the graph payload and must not be demanded of it.
RECALL_ONLY = {"score", "score_components", "recall_mode", "visited"}


def test_graph_nodes_have_every_key_the_viewer_reads():
    """The map is the viewer's whole point, and it binds memory fields by name.

    Scanned over the whole file rather than one function: the memory object is
    passed around and rendered in several places, so limiting the scan to
    `renderGraph` bound a single key — a contract of one field is barely a
    contract."""
    _seeded()
    nodes = _cli("graph").get("nodes") or []
    assert nodes, "no nodes: the binding would go unchecked"
    js = VIEWER.read_text(encoding="utf-8", errors="replace")
    wanted = set(re.findall(r"\bm\.([a-z_]+)", js)) - RECALL_ONLY
    assert len(wanted) >= 10, f"only {len(wanted)} fields bound: the scan broke"
    missing = wanted - set(nodes[0])
    assert not missing, (
        f"the viewer reads node keys `graph` does not emit: {sorted(missing)}\n"
        f"emitted: {sorted(nodes[0])}")


def test_facts_have_every_key_the_viewer_reads():
    """Structured facts are the VSA differentiator, and the panel showing them is
    the least exercised of all."""
    _seeded()
    facts = _cli("facts", "--json")["facts"]
    assert facts, "no facts: the binding would go unchecked"
    # `f`, not `h`: guessing the variable name bound ZERO keys, so the first
    # version of this test passed while checking nothing.
    wanted = set(re.findall(r"\bf\.([a-z_]+)", _render_body("renderFacts")))
    assert wanted, "no fields bound: the scan broke and this test proves nothing"
    missing = wanted - set(facts[0])
    assert not missing, (
        f"the viewer reads fact keys `facts` does not emit: {sorted(missing)}\n"
        f"emitted: {sorted(facts[0])}")


def test_projects_json_has_every_key_the_viewer_reads():
    """The opt-in banner reads `PROJECT.<key>` off `hipercampo projects --json`.

    This nearly went wrong the same way `metodo`/`method` did: the viewer was first
    written against `PROJECT.enabled` while the CLI emits `enabled_here`. Nothing
    would have raised — the banner would just have claimed the project was off,
    always."""
    js = VIEWER.read_text(encoding="utf-8", errors="replace")
    wanted = set(re.findall(r"\bPROJECT\.([a-z_]+)", js))
    emitted = set(_cli("projects", "--json"))
    # `none` is set by the extension, not the CLI: it means "no folder open".
    missing = wanted - emitted - {"none"}
    assert not missing, (
        f"the viewer reads project keys the CLI does not emit: {sorted(missing)}\n"
        f"emitted: {sorted(emitted)}")


if __name__ == "__main__":
    raise SystemExit(run_tests(dict(globals())))
