"""
Narrated REAL-WORLD use cases — run:  python scripts/scenarios.py

This tells the story of an assistant (Claude) using hipercampo as memory across
several sessions with a user. It is not an assertion-based test, but a readable
demonstration that the system provides real value.
"""

import sys
import time
from pathlib import Path


# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402


def line(char="─"):
    print(char * 64)


def session(title):
    print()
    line("═")
    print(f"  {title}")
    line("═")


def main():
    Path("data/scenarios.db").unlink(missing_ok=True)
    hc = Hipercampo("data/scenarios.db")

    # ---- Session 1: the user introduces himself --------------------------
    session("SESSION 1 · The user shares some personal details")
    facts = [
        ("me llamo Armando y soy desarrollador", 0.9),
        ("prefiero respuestas honestas y directas sin rodeos", 0.9),
        ("estoy construyendo un proyecto llamado hipercampo", 0.8),
        ("odio que me hagan la pelota", 0.7),
        ("hoy he dormido mal", 0.2),                       # trivial, ephemeral
    ]
    for text, importance in facts:
        result = hc.remember(text, importance)
        marker = "✓ remembered" if result["stored"] else "· already known"
        print(f"  user: «{text}»\n           {marker} (novelty {result['novelty']:.2f})")

    # ---- Session 2: attempts to add redundant information ----------------
    session("SESSION 2 · Repeats the same fact (no duplicate expected)")
    result = hc.remember("me llamo Armando y soy desarrollador", 0.9)
    print("  user: «me llamo Armando y soy desarrollador»")
    verdict = '✓ remembered' if result['stored'] else '· recognized as known → reinforced'
    print(f"           {verdict}")

    # ---- Claude needs to remember before answering -----------------------
    session("SESSION 3 · Claude checks memory before answering")
    questions = [
        ("Who is the user and what do they do?", "Armando desarrollador"),
        ("How should I answer them?", "respuestas honestas directas"),
        ("Which project are they building?", "proyecto hipercampo"),
    ]
    for display_question, retrieval_query in questions:
        print(f"\n  Claude asks: {display_question}")
        for hit in hc.recall(retrieval_query, k=2):
            print(f"     ↳ remembers «{hit['text']}»  (score {hit['score']:.2f})")

    # ---- Dream phase -----------------------------------------------------
    session("SESSION 4 · End of day: Claude 'sleeps' (consolidates)")
    # Add several similar episodes about the project.
    for extra in ("usa hipervectores", "usa hipervectores no embeddings",
                  "usa hipervectores binarios"):
        hc.remember(f"hipercampo {extra}", 0.6)
    print("  before sleep:", hc.stats())
    print("  consolidating...", hc.consolidate())
    print("  after waking:  ", hc.stats())
    print("  → several separate episodes have merged into semantic knowledge")

    # ---- Time passes: trivial information fades --------------------------
    session("SESSION 5 · Weeks pass: trivial details fade, important ones remain")
    old_timestamp = time.time() - 60 * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ?", (old_timestamp,))
    hc.store.commit()
    trial = hc.forget(dry_run=True)
    print(f"  forgetting dry run → {trial['forgotten']} trivial memories would fade")
    hc.forget(dry_run=False)
    print("  after forgetting:", hc.stats())

    print("\n  Does it still remember what matters?")
    for hit in hc.recall("Armando respuestas honestas directas", k=2):
        print(f"     ↳ «{hit['text']}»")
    print("\n  What about the trivial detail (sleeping badly)?")
    hits = hc.recall("el usuario durmió mal", k=1)
    survivors = [hit for hit in hits if "dormido mal" in hit["text"]]
    print("     ↳", "still remembered" if survivors else "forgotten, as expected")

    hc.store.close()
    line("═")
    print("  Done. This is what hipercampo gives Claude: a memory that")
    print("  distinguishes, prioritizes, consolidates, and forgets — like a hippocampus.")
    line("═")


if __name__ == "__main__":
    main()
