"""
Differentiator demo: COMPOSITIONAL memory with roles.
Run: python scripts/roles_demo.py

Shows what BM25 and embeddings CANNOT do: query by ROLE ("who did what to whom?")
and recover the correct value through unbinding.
"""

import sys
from pathlib import Path

# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.roles import ItemMemory, encode_fact, query_role   # noqa: E402


def rule(c="─"):
    print(c * 60)


def main():
    im = ItemMemory()
    for v in ["perro", "hombre", "gato", "raton", "muerde", "persigue",
              "veterinaria", "marta", "curó", "frankfurt", "servidor", "aloja"]:
        im.add(v)

    facts = {
        "El perro muerde al hombre":
            {"subject": "perro", "predicate": "muerde", "object": "hombre"},
        "El hombre muerde al perro":
            {"subject": "hombre", "predicate": "muerde", "object": "perro"},
        "Marta curó al gato":
            {"subject": "marta", "predicate": "curó", "object": "gato"},
    }
    records = {sentence: encode_fact(fact, im) for sentence, fact in facts.items()}

    rule("═")
    print("  Compositional memory: who did what to whom?")
    rule("═")
    for sentence, record in records.items():
        s = query_role(record, "subject", im)[0]
        p = query_role(record, "predicate", im)[0]
        o = query_role(record, "object", im)[0]
        print(f"\n  «{sentence}»")
        print(f"     who?     → {s[0]:8} ({s[1]:.2f})")
        print(f"     did what?→ {p[0]:8} ({p[1]:.2f})")
        print(f"     to whom? → {o[0]:8} ({o[1]:.2f})")

    rule("═")
    print("  The key: 'dog bites man' and 'man bites dog' contain the SAME values,")
    print("  but their recovered subject/object roles are REVERSED.")
    print("  A dense embedding places them at almost the same point. VSA does not.")
    rule("═")


if __name__ == "__main__":
    main()
