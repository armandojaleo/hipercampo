"""
How many tokens does hipercampo cost? Measure it; do not guess.

A memory that occupies half the context window does not help; it gets in the way.
This script measures the TWO very different sources of cost:

  1. MCP tool descriptions, sent with EVERY request in the session. This fixed,
     permanent cost occupies context even when memory is never used. It is often
     the largest and least visible cost.
  2. Hook injection, paid only on turns that trigger it.

Usage:
    python scripts/tokens.py              # measure against the real database
    python scripts/tokens.py --json       # machine-readable before/after output
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipercampo.support.budget import is_estimate, estimate_tokens, method  # noqa: E402

# Prompts representative of a real session: some should trigger memory and others
# should NOT. Non-triggers matter just as much: memory speaking when nobody asked
# is pure waste.
PROMPTS = [
    ("pregunta con contexto", "¿cómo se comparten las listas en el proyecto?", True),
    ("pregunta genérica", "¿qué hago ahora?", False),
    ("afirmación trivial", "mañana compraré pan", False),
    ("orden técnica corta", "arregla el bug del botón", False),
    ("saludo", "buenas", False),
    ("pregunta de arquitectura", "¿qué es VSA y por qué no embeddings?", True),
]


def _hook(prompt: str, env: dict) -> str:
    """Run the hook as Claude Code does and return the injected context."""
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", "hook"],
                       input=json.dumps({"prompt": prompt}), capture_output=True,
                       text=True, encoding="utf-8", env=env)
    try:
        d = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    return d.get("hookSpecificOutput", {}).get("additionalContext", "")


def _tools(env: dict) -> tuple[int, int]:
    """Perform a raw MCP handshake and return (tool count, definition tokens)."""
    msgs = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "t", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})])
    r = subprocess.run([sys.executable, "-m", "hipercampo.server"], input=msgs,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    for line in r.stdout.splitlines():
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2:
            tools = d.get("result", {}).get("tools", [])
            return len(tools), estimate_tokens(json.dumps(tools, ensure_ascii=False))
    return 0, 0


def main() -> int:
    env = dict(os.environ, HIPERCAMPO_LOG="0")
    n_tools, t_tools = _tools(env)

    rows, triggers, false_triggers = [], 0, 0
    for label, prompt, should_trigger in PROMPTS:
        ctx = _hook(prompt, env)
        tk = estimate_tokens(ctx)
        if tk:
            triggers += 1
            if not should_trigger:
                false_triggers += 1
        rows.append({"case": label, "tokens": tk, "expected": should_trigger,
                     "waste": bool(tk and not should_trigger)})

    per_turn = sum(row["tokens"] for row in rows) / len(rows)
    report = {
        "estimated": is_estimate(), "method": method(),
        "tools": {"count": n_tools, "tokens_per_request": t_tools},
        "hook": {"average_per_turn": round(per_turn),
                 "triggered_turns": f"{triggers}/{len(rows)}",
                 "false_triggers": false_triggers, "detail": rows},
        # Typical 30-turn session. Tool definitions are paid on every request;
        # hook context is paid only on turns that trigger it.
        "thirty_turn_session": {"tools": t_tools * 30,
                                "hook": round(per_turn * 30),
                                "total": round(t_tools * 30 + per_turn * 30)},
    }

    if "--json" in sys.argv:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0

    notice = f" (ESTIMATED: {method()})"
    print(f"\nHIPERCAMPO TOKEN COST{notice}\n" + "=" * 60)
    print(f"\n1. MCP tools: {n_tools} · {t_tools} tokens ON EVERY REQUEST")
    print("   (fixed cost: occupies context even when memory is unused)")
    print("\n2. Hook, per turn:")
    for row in rows:
        marker = ("  ← WASTE" if row["waste"]
                  else ("" if row["tokens"] else "  (correctly silent)"))
        print(f"   {row['case']:24} {row['tokens']:5} tok{marker}")
    print(f"\n   average per turn: {round(per_turn)} tok · triggers on {triggers}/{len(rows)}"
          f" · false triggers: {false_triggers}")
    s = report["thirty_turn_session"]
    print(f"\n3. 30-turn session: {s['tools']} (tools) + {s['hook']}"
          f" (hook) = {s['total']} tokens")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
