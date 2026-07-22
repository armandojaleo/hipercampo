"""
Demo tocable — ejecuta:  python scripts/demo.py

Muestra las dos cosas que hacen a hipercampo distinto de una base vectorial:
  A) El álgebra VSA distingue "el perro muerde al hombre" de su inverso.
  B) El ciclo completo: sorpresa -> recuerdo asociativo -> sueño -> olvido.
"""

import sys
from pathlib import Path

# Salida UTF-8 aunque se redirija (en Windows, cp1252 rompe con «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.memory import Hipercampo             # noqa: E402
from hipercampo.vsa import similarity                # noqa: E402


def parte_A():
    print("=" * 60)
    print("A) VSA distingue el ORDEN (lo que un embedding denso difumina)")
    print("=" * 60)
    a = encode_text("el perro muerde al hombre")
    b = encode_text("el hombre muerde al perro")
    c = encode_text("el gato persigue al ratón")
    print(f"  'perro muerde hombre' vs 'hombre muerde perro' : {similarity(a, b):.3f}")
    print(f"  'perro muerde hombre' vs 'gato persigue ratón'  : {similarity(a, c):.3f}")
    print("  -> mismas palabras, orden distinto = similitud claramente < 1\n")


def parte_B():
    print("=" * 60)
    print("B) El ciclo de memoria completo")
    print("=" * 60)
    hc = Hipercampo(":memory:" if False else "data/demo.db")

    frases = [
        ("Armando prefiere respuestas honestas directas sin humo", 0.9),
        ("Armando prefiere respuestas honestas directas y claras", 0.5),  # casi igual
        ("Armando prefiere respuestas honestas directas al grano", 0.5),  # casi igual
        ("El proyecto hipercampo usa hipervectores", 0.7),
        ("El proyecto hipercampo usa hipervectores no embeddings", 0.7),
        ("Hoy hace sol en Madrid", 0.2),
    ]
    print("\n-- Escritura por sorpresa --")
    for texto, imp in frases:
        r = hc.remember(texto, importance=imp)
        estado = "GUARDADO" if r["stored"] else "redundante->reforzado"
        print(f"  [{estado:22}] novedad={r['novelty']:.2f}  «{texto[:45]}»")

    print("\n-- Recuerdo por similitud + propagación --")
    for m in hc.recall("¿qué prefiere Armando?", k=3):
        print(f"  score={m['score']:.2f}  «{m['text'][:50]}»")

    print("\n-- Consolidación (sueño) --")
    print("  ", hc.consolidate())

    print("\n-- Olvido activo (ensayo) --")
    print("  ", hc.forget(dry_run=True))

    print("\n-- Estado final --")
    print("  ", hc.stats())


if __name__ == "__main__":
    parte_A()
    parte_B()
