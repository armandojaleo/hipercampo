"""
AUDIT automatic injection (the UserPromptSubmit hook runs on EVERY turn).
Measure what matters if hipercampo is to SAVE tokens instead of burning them:
  - actual cost per turn (mean/p95/max from the audit log)
  - injection rate (how many turns inject something rather than abstaining)
  - RELEVANCE: how much injected material comes from the right namespace rather
    than cross-project noise? (HIPERCAMPO_LINKED=* reads ALL projects.)

Usage:
  python scripts/injection_audit.py            # against the real memory
  python scripts/injection_audit.py --json
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipercampo.support import audit, budget                       # noqa: E402
from hipercampo.support.config import db_path                       # noqa: E402
from hipercampo.cycle.memory import Hipercampo                   # noqa: E402

# Battery labeled by expected topic (the namespace that SHOULD dominate injection).
# Spanish prompts are intentional retrieval samples.
PROMPTS = [
    ("proj-hipercampo", "¿cómo funciona el grafo navegable y el recall en hipercampo?"),
    ("proj-hipercampo", "¿qué decidimos sobre el rumbo del release y las ramas?"),
    ("proj-hipercampo", "recuérdame cómo va la fase de evidencia y el paper"),
    ("proj-hipercampo", "¿qué es la abstención y el olvido en la memoria?"),
    ("proj-hipercampo", "estado del visor y la extensión de VS Code"),
    ("proj-player", "¿cómo se comparten listas en M Player?"),
    ("proj-player", "¿cómo genera listas con IA el player?"),
    ("personal", "¿cómo prefiere Armando que le respondan?"),
    ("generic", "escribe un bucle for en python que sume una lista"),
    ("generic", "¿qué tiempo hace hoy en Madrid?"),
]


def actual_cost():
    """Return the injection-cost distribution from the real audit log."""
    toks = []
    for ln in audit.tail(0, action="tokens"):
        m = re.search(r"(\d+) tok", ln)
        if m and "inyect" in ln.lower():
            toks.append(int(m.group(1)))
    if not toks:
        return {}
    toks.sort()

    def p(q):
        return toks[min(len(toks) - 1, int(q * len(toks)))]
    return {"injections": len(toks), "mean": round(sum(toks) / len(toks)),
            "p50": p(0.5), "p95": p(0.95), "max": toks[-1],
            "expensive_>200": sum(1 for t in toks if t > 200)}


def audit_relevance(namespace, linked):
    hc = Hipercampo(db_path(), namespace=namespace, linked=linked)
    rows = []
    try:
        for topic, prompt in PROMPTS:
            result = hc.assist(prompt)
            action = result.get("action") or "nothing"
            memories = result.get("result") or []
            # Match hook cost: heading + memories, trimmed to the token budget.
            lines = [f"[memory · {action}] {result.get('why', '')}"] + \
                    [f"- {hit.get('text', '')}" for hit in memories]
            _, usage = budget.fit_budget(lines)
            namespaces = [hit.get("namespace") for hit in memories if hit.get("namespace")]
            cross = sum(1 for item in namespaces if item != topic) if topic != "generic" else 0
            rows.append({"topic": topic, "action": action, "n": len(memories),
                         "tokens": usage["tokens"], "namespaces": namespaces,
                         "cross": cross, "total_namespaces": len(namespaces)})
    finally:
        hc.close()
    return rows


def summarize(rows):
    injected = [row for row in rows if row["action"] != "nothing" and row["n"] > 0]
    total_namespaces = sum(row["total_namespaces"] for row in rows)
    cross = sum(row["cross"] for row in rows)
    tokens = [row["tokens"] for row in injected] or [0]
    return {
        "prompts": len(rows),
        "injection_rate": round(len(injected) / len(rows), 2),
        "mean_tokens_when_injecting": round(sum(tokens) / len(tokens)),
        "cross_namespace_rate": round(cross / total_namespaces, 3) if total_namespaces else 0.0,
        "injected_memories": total_namespaces, "from_another_topic": cross,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", default="proj-hipercampo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    audit.set_logfile(db_path())        # Read the REAL log next to the real database.
    audit._ENABLED = False
    cost = actual_cost()
    # Compare linking (like the real LINKED=* hook) with an isolated namespace.
    linked = summarize(audit_relevance(a.namespace, "*"))
    isolated = summarize(audit_relevance(a.namespace, ""))
    out = {"actual_log_cost": cost, "linked_*": linked, "isolated": isolated}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    print("INJECTION AUDIT")
    print("-" * 58)
    if cost:
        print(f"actual cost (log): {cost['injections']} injections · "
              f"mean {cost['mean']} · p50 {cost['p50']} · p95 {cost['p95']} · "
              f"max {cost['max']} tok · expensive(>200)={cost['expensive_>200']}")
    print()
    print(f"{'':<28}{'LINKED=*':>12}{'isolated':>12}")
    for key in ("injection_rate", "mean_tokens_when_injecting",
                "cross_namespace_rate", "from_another_topic"):
        print(f"{key:<28}{str(linked[key]):>12}{str(isolated[key]):>12}")
    print("-" * 58)
    print("A high cross_namespace_rate means memories from ANOTHER project are "
          "leaking in (noise that costs tokens on every turn).")


if __name__ == "__main__":
    main()
