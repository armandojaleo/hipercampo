"""
Use case 4 (long) - A night of incubation: surprise, sleep, pruning and EUREKA.
Run:  python examples/04_the_long_night.py

Follows a researcher over several weeks: piles up memories (work + life),
SLEEPS (consolidates), time PRUNES the trivial ones into dormant state,
DREAMS (weaves bridges between distant ideas) and, at the end, `muse` ties a
buried memory to the current problem: the eureka moment. Everything emerges
from the mechanics, none of it is scripted.
"""

import sys
import time
from pathlib import Path


# UTF-8 output even when redirected (on Windows, cp1252 breaks on «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

DB = "data/ex_long.db"


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def heading(t):
    print("\n" + "=" * 66 + f"\n  {t}\n" + "=" * 66)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="researcher")

    heading("WEEKS 1-3 - Piles up memories (work and life)")
    memories = [
        # the problem and its technical context (will keep reinforcing/associating)
        ("trying to get many sensors to agree on a common time with no central clock", 0.7),
        ("the sensors only talk to their nearest neighbors in the network", 0.6),
        ("a central clock would be a single point of failure I want to avoid", 0.6),
        ("each sensor nudges its clock by looking at its neighbors', bit by bit", 0.6),
        # life and tangential reading (barely reinforced: will get buried)
        ("as a kid I watched fireflies in the garden blink all at once", 0.3),
        ("read that fireflies sync up with no one leading them", 0.35),
        ("the corner cafe changed its roast blend this month", 0.2),
        ("my grandmother told stories of fishermen at dusk", 0.2),
        ("the heart beats thanks to cells that pace each other", 0.4),
    ]
    for t, imp in memories:
        r = hc.remember(t, imp)
        print(f"  {'- remembered' if r['stored'] else '- (already knew that)'}: {t[:52]}")

    heading("END OF WEEK - Sleeps: consolidates what repeats")
    print("  ", hc.consolidate())

    heading("WEEKS PASS - Time prunes the trivial (into dormant)")
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.45",
                        (time.time() - 120 * 86400,))
    hc.store.commit()
    print("  forget:", hc.forget(dry_run=False))
    print("  status:", {k: hc.stats()[k] for k in ("active_episodic", "dormant")})

    heading("LATE AT NIGHT - Dreams: PROPOSES bridges between distant ideas")
    dream = hc.dream(max_bridges=3, dry_run=False)   # records as hypotheses
    for b in dream.get("bridges", []):
        print(f"  hypothesis: {b['hypothesis']}")
    if not dream.get("bridges"):
        print("  (no new bridges came up tonight)")
    print("\n  Note: these are HYPOTHESES. They don't affect the memory until confirmed")
    print("  with hc_accept_bridge — speculation doesn't contaminate what's observed.")

    heading("THE NEXT MORNING - Still stuck. Thinking out loud:")
    print("  «I need the network to agree on its own, with nobody in charge»\n")
    print("  -> muse looks for inspiration (includes what's buried):\n")
    ideas = hc.muse("getting the network to sync on its own with nobody in charge", k=4)
    for idea in ideas:
        mark = " ✨ RESURFACED from childhood/reading" if idea["resurfaced"] else ""
        print(f"  - «{idea['text']}»{mark}")
        if idea.get("connected_via"):
            print(f"      -> via: «{idea['connected_via'][:55]}»")

    eureka = next((i for i in ideas if i["resurfaced"]), None)
    heading("EUREKA")
    if eureka:
        print("  A buried memory resurfaced and tied the problem to an analogy:")
        print(f"    «{eureka['text']}»")
        print("  -> What if the sensors sync up LIKE FIREFLIES: no leader,")
        print("    just watching their neighbors and adjusting... there's the solution!")
    else:
        print("  (Nothing resurfaced this time; incubation doesn't always pay off —")
        print("   just like in a real mind. Try again another night.)")
    hc.close()          # not hc.store.close(): stats() opens the identity
                        # store too, and leaving it open locks the file on Windows
    cleanup()


if __name__ == "__main__":
    main()
