"""
Coverage badges that cannot rot.

A badge with a number typed by hand is a claim nobody re-checks — the exact failure
this project keeps finding. So the numbers live in `.github/badges/*.json` (shields
reads them straight from the repository, no third-party service holding our data),
and CI VERIFIES them:

    python scripts/badges.py --check     measured coverage must be >= the badge
    python scripts/badges.py --write     regenerate after a real improvement

The check is one-sided on purpose. If coverage DROPS below what the badge claims, CI
fails: the badge is never allowed to overstate. If coverage rises above it, the badge
merely understates until someone runs `--write`, which is harmless and is the nudge
to update it.

Python coverage is read from an existing `.coverage` file; the viewer's comes from
`editor/coverage-tmp/summary.json`, written by `npm run coverage` in the extension.
Each side is checked by the CI job that can actually measure it.
"""

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BADGES = ROOT / ".github" / "badges"


def _colour(pct: float) -> str:
    """Shields colours. Deliberately not generous: 74% is not 'green'."""
    if pct >= 90:
        return "brightgreen"
    if pct >= 80:
        return "green"
    if pct >= 70:
        return "yellowgreen"
    if pct >= 60:
        return "yellow"
    return "orange"


def _badge(label: str, pct: float) -> dict:
    """TRUNCATES, never rounds. Rounding 72.6 up to 73 makes the badge claim more
    than was measured — the one thing this file exists to prevent — and it made
    the badge fail its own check. Truncating guarantees badge <= measured."""
    import math
    shown = math.floor(pct)
    return {"schemaVersion": 1, "label": label,
            "message": f"{shown}%", "color": _colour(shown)}


def measured_python() -> float | None:
    """Total coverage of the package from the current `.coverage` file."""
    try:
        from coverage import Coverage
    except ImportError:
        return None
    data = ROOT / ".coverage"
    if not data.exists():
        return None
    cov = Coverage(data_file=str(data))
    cov.load()
    import io
    return float(cov.report(include=["hipercampo/*"], file=io.StringIO()))


def measured_viewer() -> float | None:
    """Viewer coverage, written by `npm run coverage` in editor/."""
    summary = ROOT / "editor" / "coverage-tmp" / "summary.json"
    if not summary.exists():
        return None
    return float(json.loads(summary.read_text(encoding="utf-8"))["pct"])


def claimed(name: str) -> float | None:
    f = BADGES / f"coverage-{name}.json"
    if not f.exists():
        return None
    return float(json.loads(f.read_text(encoding="utf-8"))["message"].rstrip("%"))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="regenerate the badges")
    ap.add_argument("--check", action="store_true", help="fail if a badge overstates")
    args = ap.parse_args()

    targets = {"python": (measured_python(), "coverage (core)"),
               "viewer": (measured_viewer(), "coverage (viewer)")}
    BADGES.mkdir(parents=True, exist_ok=True)
    problems = []

    for name, (measured, label) in targets.items():
        stated = claimed(name)
        if measured is None:
            print(f"  {name:<7} not measurable here (skipped); badge says "
                  f"{stated if stated is not None else '—'}")
            continue
        if args.write:
            # A laptop may LOWER a badge but never raise one. Coverage is not
            # identical everywhere: CI measured the viewer at 72.1% where a Windows
            # machine measured 74.3%, and writing the local figure put the badge
            # above what the gate could reproduce — CI went red on the very commit
            # that added the badge. CI is the reference because CI is the gate.
            import os
            en_ci = os.environ.get("CI", "").lower() == "true"
            if stated is not None and measured > stated and not en_ci:
                print(f"  {name:<7} measured {measured:.1f}% here, badge stays at "
                      f"{stated:.0f}% (only CI may raise it)")
                continue
            (BADGES / f"coverage-{name}.json").write_text(
                json.dumps(_badge(label, measured), indent=2) + "\n", encoding="utf-8")
            print(f"  {name:<7} badge written: {measured:.1f}%")
            continue
        if stated is None:
            problems.append(f"{name}: no badge file; run --write")
            continue
        # No slack: the badge is truncated when written, so it can never sit above
        # the measurement. A tolerance here would quietly re-allow overstating.
        ok = measured >= stated
        print(f"  {name:<7} measured {measured:.1f}%  badge {stated:.0f}%  "
              f"{'ok' if ok else 'OVERSTATED'}")
        if not ok:
            problems.append(
                f"{name}: the badge claims {stated:.0f}% but coverage is {measured:.1f}%")

    if args.check and problems:
        for p in problems:
            print(f"::error::{p}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
