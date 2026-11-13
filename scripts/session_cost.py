"""
What a long session really costs: context read per API call, from Claude
Code's own transcripts (the `usage` block of every assistant message).

This is the number the bookmark (support/checkpoint.py) is about. Every call
re-reads the whole context, so a session's cost grows with its length; what
hipercampo injects per turn (50-350 tok) is noise next to it. Measured on
2026-11-12, one session went from 43.5k to 155.7k tokens per call over 60
calls. A fresh session starts again near the baseline (system prompt +
tools), and the bookmark is what lets it do that without losing the thread.

Tokens, not money: most of that context is a cache read, billed cheaper.

Usage:
  python scripts/session_cost.py                 # this project's sessions
  python scripts/session_cost.py --dir <path> --last 20
"""
import argparse
import glob
import json
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _default_dir() -> str:
    # Claude Code names the folder after the project path: E:\a\b -> e--a-b
    cwd = os.path.abspath(os.getcwd())
    slug = cwd.replace(":", "-").replace("\\", "-").replace("/", "-")
    base = os.path.join(os.path.expanduser("~"), ".claude", "projects")
    for name in (slug, slug[0].lower() + slug[1:]):
        if os.path.isdir(os.path.join(base, name)):
            return os.path.join(base, name)
    return os.path.join(base, slug)


def context_per_call(path: str) -> list[int]:
    """Context tokens read by each API call, in order. One message id can
    appear on several rows (one per content block): counted once."""
    seen, out = set(), []
    with open(path, encoding="utf-8") as f:
        for raw in f:
            try:
                row = json.loads(raw)
            except ValueError:
                continue
            if row.get("type") != "assistant":
                continue
            msg = row.get("message") or {}
            usage = msg.get("usage")
            if not usage or msg.get("id") in seen:
                continue
            seen.add(msg.get("id"))
            out.append(usage.get("input_tokens", 0)
                       + usage.get("cache_read_input_tokens", 0)
                       + usage.get("cache_creation_input_tokens", 0))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--dir", default=_default_dir())
    ap.add_argument("--last", type=int, default=10, help="most recent sessions")
    ap.add_argument("--min-calls", type=int, default=10)
    args = ap.parse_args(argv)

    files = sorted(glob.glob(os.path.join(args.dir, "*.jsonl")), key=os.path.getmtime)
    if not files:
        print(f"no transcripts in {args.dir}")
        return 1
    print(f"{'session':10} {'calls':>5} {'first':>8} {'last':>8} {'growth':>7} "
          f"{'total read':>11}")
    for path in files[-args.last:]:
        ctx = context_per_call(path)
        if len(ctx) < args.min_calls:
            continue
        print(f"{os.path.basename(path)[:8]:10} {len(ctx):5d} {ctx[0]:8d} "
              f"{ctx[-1]:8d} {ctx[-1] / max(ctx[0], 1):6.1f}x {sum(ctx):11d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
