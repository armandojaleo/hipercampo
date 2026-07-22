"""
Demo del diferenciador: memoria COMPOSICIONAL con roles.
Ejecuta:  python scripts/roles_demo.py

Muestra lo que BM25 y los embeddings NO pueden: preguntar por ROL
("¿quién hizo qué a quién?") y recuperar el valor correcto por unbinding.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.roles import ItemMemory, encode_fact, query_role   # noqa: E402


def linea(c="─"):
    print(c * 60)


def main():
    im = ItemMemory()
    for v in ["perro", "hombre", "gato", "raton", "muerde", "persigue",
              "veterinaria", "marta", "curó", "frankfurt", "servidor", "aloja"]:
        im.add(v)

    hechos = {
        "El perro muerde al hombre":
            {"subject": "perro", "predicate": "muerde", "object": "hombre"},
        "El hombre muerde al perro":
            {"subject": "hombre", "predicate": "muerde", "object": "perro"},
        "Marta curó al gato":
            {"subject": "marta", "predicate": "curó", "object": "gato"},
    }
    records = {frase: encode_fact(f, im) for frase, f in hechos.items()}

    linea("═")
    print("  Memoria composicional: ¿quién hizo qué a quién?")
    linea("═")
    for frase, rec in records.items():
        s = query_role(rec, "subject", im)[0]
        p = query_role(rec, "predicate", im)[0]
        o = query_role(rec, "object", im)[0]
        print(f"\n  «{frase}»")
        print(f"     ¿quién?  → {s[0]:8} ({s[1]:.2f})")
        print(f"     ¿qué?    → {p[0]:8} ({p[1]:.2f})")
        print(f"     ¿a quién?→ {o[0]:8} ({o[1]:.2f})")

    linea("═")
    print("  Lo clave: 'perro muerde hombre' y 'hombre muerde perro' tienen los")
    print("  MISMOS valores, pero el sujeto/objeto recuperados están INVERTIDOS.")
    print("  Un embedding denso los pone casi en el mismo punto. VSA no.")
    linea("═")


if __name__ == "__main__":
    main()
