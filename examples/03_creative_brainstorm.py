"""
Use case 3 - Creative brainstorming with memories that resurface.
Run:  python examples/03_creative_brainstorm.py

The mind doesn't erase: it buries. And sometimes a distant memory comes back
and ties into a new idea. hc_muse looks for INDIRECT connections and
includes dormant ones, also saying WHY each thing connected (the bridge memory).
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

DB = "data/ex_muse.db"


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="creative")

    memories = [
        ("mycorrhizal fungi connect trees underground and share nutrients", 0.4),
        ("as a kid I read about 19th century telegraph networks", 0.3),
        ("an ant swarm solves routes with no central leader", 0.4),
        ("I'm designing a distributed system with no single coordinator", 0.7),
        ("neurons reinforce each other when they fire together", 0.5),
    ]
    for t, imp in memories:
        hc.remember(t, imp)

    # time buries what's barely reinforced
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.45",
                        (time.time() - 120 * 86400,))
    hc.store.commit()
    hc.forget(dry_run=False)
    print(f"Time passed. Dormant: {hc.stats()['dormant']}\n")

    print("Thinking: «a distributed system with no coordinator, that self-organizes»")
    print("-> muse brings unexpected connections:\n")
    for idea in hc.muse("a distributed system that self-organizes with no leader", k=3):
        mark = " ✨(resurfaced from dormant)" if idea["resurfaced"] else ""
        print(f"  - «{idea['text']}»{mark}")
        if idea.get("connected_via"):
            print(f"      -> connected via: «{idea['connected_via']}»")

    print("\n  A forgotten read about telegraphs or fungi in a forest can inspire")
    print("  today's design. That's creative incubation.")
    hc.store.close()
    cleanup()


if __name__ == "__main__":
    main()
