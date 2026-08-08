"""
Use case 2 - A project's knowledge base, with structured FACTS.
Run:  python examples/02_project_knowledge.py

Claude stores technical facts as relations (subject-predicate-object) and
then answers "who/what/where?" BY ROLE — something a similarity search can't do.
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

DB = "data/ex_project.db"


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="project-orion")

    print("-- Recording project facts --")
    facts = [
        {"subject": "auth-service", "predicate": "uses", "object": "PostgreSQL"},
        {"subject": "billing-service", "predicate": "uses", "object": "Stripe"},
        {"subject": "Marta", "predicate": "maintains", "object": "auth-service"},
        {"subject": "the deploy", "predicate": "runs", "object": "every night", "time": "3am"},
    ]
    for f in facts:
        hc.remember_fact(f)
        print(f"  - {f}")

    print("\n-- Questions by role (VSA unbinding) --")
    queries = [
        ("object", {"subject": "auth-service", "predicate": "uses"}, "what does auth-service use?"),
        ("subject", {"predicate": "maintains", "object": "auth-service"},
         "who maintains auth-service?"),
        ("subject", {"predicate": "uses", "object": "Stripe"}, "which service uses Stripe?"),
    ]
    for role, known, question in queries:
        r = hc.ask_role(role, known)
        print(f"  {question}\n     -> {r.get('answer')}  (match {r.get('match_score')})")

    hc.store.close()
    cleanup()


if __name__ == "__main__":
    main()
