"""
Hands-on demo — run: python scripts/demo.py

Shows the two things that distinguish hipercampo from a vector database:
  A) VSA algebra distinguishes "the dog bites the man" from its inverse.
  B) The complete cycle: surprise -> associative recall -> dreaming -> forgetting.
"""

import sys
from pathlib import Path

# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.core.encoder import encode_text          # noqa: E402
from hipercampo.cycle.memory import Hipercampo             # noqa: E402
from hipercampo.core.vsa import similarity                # noqa: E402


def part_a():
    print("=" * 60)
    print("A) VSA distinguishes ORDER (which dense embeddings blur)")
    print("=" * 60)
    a = encode_text("el perro muerde al hombre")
    b = encode_text("el hombre muerde al perro")
    c = encode_text("el gato persigue al ratón")
    print(f"  'perro muerde hombre' vs 'hombre muerde perro' : {similarity(a, b):.3f}")
    print(f"  'perro muerde hombre' vs 'gato persigue ratón'  : {similarity(a, c):.3f}")
    print("  -> same words, different order = similarity clearly < 1\n")


def part_b():
    print("=" * 60)
    print("B) The complete memory cycle")
    print("=" * 60)
    hc = Hipercampo(":memory:" if False else "data/demo.db")

    phrases = [
        ("Armando prefiere respuestas honestas directas sin humo", 0.9),
        ("Armando prefiere respuestas honestas directas y claras", 0.5),  # Nearly identical.
        ("Armando prefiere respuestas honestas directas al grano", 0.5),  # Nearly identical.
        ("El proyecto hipercampo usa hipervectores", 0.7),
        ("El proyecto hipercampo usa hipervectores no embeddings", 0.7),
        ("Hoy hace sol en Madrid", 0.2),
    ]
    print("\n-- Surprise-based writing --")
    for text, importance in phrases:
        r = hc.remember(text, importance=importance)
        state = "STORED" if r["stored"] else "redundant->reinforced"
        print(f"  [{state:22}] novelty={r['novelty']:.2f}  «{text[:45]}»")

    print("\n-- Recall by similarity + propagation --")
    for m in hc.recall("¿qué prefiere Armando?", k=3):
        print(f"  score={m['score']:.2f}  «{m['text'][:50]}»")

    print("\n-- Consolidation (dreaming) --")
    print("  ", hc.consolidate())

    print("\n-- Active forgetting (dry run) --")
    print("  ", hc.forget(dry_run=True))

    print("\n-- Final state --")
    print("  ", hc.stats())


if __name__ == "__main__":
    part_a()
    part_b()
