"""
Caso de uso 2 · Base de conocimiento de un proyecto, con HECHOS estructurados.
Ejecuta:  python examples/02_project_knowledge.py

Claude guarda hechos técnicos como relaciones (sujeto-predicado-objeto) y luego
responde "¿quién/qué/dónde?" por ROL — algo que un buscador por parecido no hace.
"""

import sys
from pathlib import Path

# Salida UTF-8 aunque se redirija (en Windows, cp1252 rompe con «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

DB = "data/ex_project.db"


def limpiar():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    limpiar()
    hc = Hipercampo(DB, namespace="proyecto-orion")

    print("── Registrando hechos del proyecto ──")
    hechos = [
        {"subject": "auth-service", "predicate": "usa", "object": "PostgreSQL"},
        {"subject": "billing-service", "predicate": "usa", "object": "Stripe"},
        {"subject": "Marta", "predicate": "mantiene", "object": "auth-service"},
        {"subject": "el deploy", "predicate": "corre", "object": "cada noche", "time": "3am"},
    ]
    for f in hechos:
        hc.remember_fact(f)
        print(f"  · {f}")

    print("\n── Preguntas por rol (unbinding VSA) ──")
    consultas = [
        ("object", {"subject": "auth-service", "predicate": "usa"}, "¿qué usa auth-service?"),
        ("subject", {"predicate": "mantiene", "object": "auth-service"},
         "¿quién mantiene auth-service?"),
        ("subject", {"predicate": "usa", "object": "Stripe"}, "¿qué servicio usa Stripe?"),
    ]
    for role, known, pregunta in consultas:
        r = hc.ask_role(role, known)
        print(f"  {pregunta}\n     → {r.get('answer')}  (encaje {r.get('match_score')})")

    hc.store.close()
    limpiar()


if __name__ == "__main__":
    main()
