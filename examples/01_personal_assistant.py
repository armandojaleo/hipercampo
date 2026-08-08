"""
Use case 1 - Personal assistant with memory across sessions.
Run:  python examples/01_personal_assistant.py

Claude remembers who you are and your preferences, updates them when they
change, and tells the important from the trivial apart. Simulates three "sessions".
"""

import sys
from pathlib import Path

# UTF-8 output even when redirected (on Windows, cp1252 breaks on «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

DB = "data/ex_assistant.db"


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="user")

    print("-- Session 1: gets to know you --")
    for text, imp in [("my name is Ana and I'm a UX designer", 0.9),
                       ("I prefer visual explanations with examples", 0.8),
                       ("I use Figma daily", 0.6),
                       ("I have a headache today", 0.2)]:
        r = hc.remember(text, imp)
        print(f"  stored: «{text}»" if r["stored"] else "  (already knew that)")

    print("\n-- Session 2: a fact changes --")
    r = hc.update("I use Figma daily", "I now use Penpot daily instead of Figma")
    if r.get("superseded_id"):
        print(f"  updated: Figma -> Penpot  "
              f"(the old #{r['superseded_id']} stays as history)")
    else:
        print("  stored as a new fact (no reliable match to replace)")

    print("\n-- Session 3: Claude checks before answering --")
    for question in ["what's their name and what do they do?",
                     "what design tool do they use now?",
                     "how do they prefer explanations?"]:
        hits = hc.recall(question, k=1)
        resp = hits[0]["text"] if hits else "(don't know)"
        print(f"  Q: {question}\n     -> {resp}")

    print("\n  Note: 'Figma' stayed as history (superseded by Penpot); 'headache'")
    print("  is trivial and will fade. What matters persists.")
    hc.store.close()
    cleanup()


if __name__ == "__main__":
    main()
