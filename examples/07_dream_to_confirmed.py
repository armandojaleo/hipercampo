"""
Use case 7 - From hypothesis to fact: the full dream -> confirm loop.
Run:  python examples/07_dream_to_confirmed.py

`dream` PROPOSES bridges between memories that share a hidden associate --
these are hypotheses, staged and inert, so speculation never contaminates
what's actually known. A human (or agent) reviews each one and either
`accept_bridge`s it into a real association, or `reject_bridge`s it away.
Only accepted bridges change what later recalls and `muse` calls can reach.
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

DB = "data/ex_dream.db"


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="researcher")

    print("-- Piling up loosely related observations (dream needs a real graph,")
    print("   at least a handful of memories with some already linked) --")
    for text, imp in [
        ("compressing a file finds the patterns already inside it", 0.5),
        ("a good scientific theory compresses many observations into one rule", 0.5),
        ("intelligence might just be very good compression", 0.4),
        ("gzip and a language model both predict the next byte to compress it", 0.5),
        ("Occam's razor prefers the simplest explanation that still fits", 0.4),
        ("a crossword gets easier once you see the pattern the setter reuses", 0.3),
        ("kids compress a whole afternoon of play into one drawing", 0.3),
    ]:
        hc.remember(text, imp)
        print(f"  remembered: «{text[:52]}»")

    # Recalling strengthens the associative edges dream walks (spreading
    # activation), the same co-activation that happens organically over a
    # real session -- we just do a few on purpose instead of waiting for them.
    for q in ("compression and intelligence", "finding patterns", "simple explanations"):
        hc.recall(q, k=3)

    print("\n-- Dreaming: propose bridges, don't commit to them yet --")
    dream = hc.dream(max_bridges=3, dry_run=False)
    bridges = dream.get("bridges", [])
    if not bridges:
        print("  (no bridge came up this run — the pool was too small or too similar)")
        hc.store.close()
        cleanup()
        return

    for b in bridges:
        print(f"  proposed: «{b['a'][:40]}» <-> «{b['b'][:40]}»")
        print(f"            via «{b['via'][:50]}»  (similarity {b['similarity']:.2f})")

    print("\n-- Reviewing each hypothesis on its own merit --")
    best = max(bridges, key=lambda b: b["similarity"])
    for b in bridges:
        if b is best:
            r = hc.accept_bridge(b["a_id"], b["b_id"])
            print(f"  ACCEPTED (strongest, similarity {b['similarity']:.2f}): {r}")
        else:
            r = hc.reject_bridge(b["a_id"], b["b_id"])
            print(f"  rejected (weaker alternative): {r}")

    print("\n-- muse reaches the confirmed pair through their shared bridge --")
    print("  querying with wording close to the bridge memory, not the pair itself:")
    for idea in hc.muse("a child drawing a whole day of play", k=3):
        via = f"  -> via: «{idea['connected_via'][:50]}»" if idea.get("connected_via") else ""
        print(f"  - «{idea['text'][:56]}»{via}")

    print("\n  Note: rejecting a bridge doesn't punish the memories involved --")
    print("  it just declines to wire them together. The hypothesis is gone,")
    print("  the observations stay exactly as reliable as they were. Only the")
    print("  ACCEPTED pair got a direct edge added to the graph; muse could")
    print("  already reach both through the shared 'via' before accepting --")
    print("  accepting makes that connection a fact about the graph itself,")
    print("  not just a one-off inference muse re-derives every time.")
    hc.store.close()
    cleanup()


if __name__ == "__main__":
    main()
