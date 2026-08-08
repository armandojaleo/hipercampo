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


def _cli(*args):
    """Run the CLI against a scratch database and parse its JSON."""
    env = dict(os.environ)
    env["HIPERCAMPO_DB"] = str(Path(tempfile.gettempdir()) / "hc_viewer_test" / "v.db")
    env["HIPERCAMPO_LOG"] = "0"
    Path(env["HIPERCAMPO_DB"]).parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", *args],
                       capture_output=True, text=True, env=env, cwd=ROOT)
    assert r.returncode == 0, f"{args} failed: {r.stderr}"
    return json.loads(r.stdout)


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


if __name__ == "__main__":
    raise SystemExit(run_tests(dict(globals())))
