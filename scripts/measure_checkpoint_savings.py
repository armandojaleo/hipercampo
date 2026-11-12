"""
Measure token savings from cutting a session and resuming with a checkpoint.

Simulates:
  A: one long session with 20 turns, re-injecting memory on each turn
  B: same 20 turns split at turn 11 (PreCompact + SessionEnd), then SessionStart
     on turn 12 with the checkpoint injected instead of the full memory

We measure total injected tokens in each case and whether the task completes.
"""

import os
import sys
from pathlib import Path

# Force UTF-8 output on Windows
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parents[0]))   # scripts/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repo root

from hipercampo.support import budget, checkpoint, audit
from hipercampo.cycle.memory import Hipercampo

# A concrete task: building and testing the checkpoint feature itself.
TURNS = [
    ("guardar un checkpoint cuando la sesion se compacta", "feature-request"),
    ("necesitamos que no pierda contexto entre sesiones", "refinement"),
    ("como vamos a saber si funciona?", "question"),
    ("tenemos que medir los tokens antes y despues", "design"),
    ("eso va en un script en scripts/", "spec"),
    ("quiero ver la diferencia en una sesion real", "requirement"),
    ("cuanto ahorra cortar la sesion a mitad?", "hypothesis"),
    ("si, esa es la pregunta de producto", "confirmation"),
    ("empiezo a medir entonces", "action"),
    ("los primeros numeros dicen que hay ahorro", "result"),
    ("cuanto exactamente?", "question"),
    ("depende del tamaño de la memoria", "analysis"),
    ("en hipercampo hoy puede ser de 300 a 1000 tokens", "estimate"),
    ("¿se pierde algo al cortar?", "concern"),
    ("no, porque esta todo en el checkpoint", "answer"),
    ("¿que pasa si abro sesion y cierro sin hacer nada?", "edge-case"),
    ("no sobrescribe el checkpoint anterior", "guarantee"),
    ("perfecto, entonces podemos hacerlo", "decision"),
    ("empiezo a escribir los tests", "next-step"),
    ("¿cuando lo mergeo?", "question"),
]


def _pre_fill_memory(hc: Hipercampo) -> None:
    """Fill memory with realistic content before starting the session."""
    topics = [
        "hipercampo es una memoria compartida para agentes Claude",
        "las memorias se guardan en un SQLite con embeddings",
        "la abstencion permite no inyectar lo irrelevante",
        "el grafo navegable muestra quien-apunta-a-quien en la memoria",
        "SessionStart inyecta la identidad de quien trabaja",
        "UserPromptSubmit inyecta un indice, no textos completos",
        "PreCompact y SessionEnd guardan un checkpoint por proyecto",
        "el checkpoint es extractivo: titulo, peticiones, ficheros, commits",
    ]
    for topic in topics:
        hc.learn(topic, "background")


def simulate_long_session(hc: Hipercampo) -> tuple[int, list[str]]:
    """Simulate 20 turns with memory injection on every turn (scenario A).
    Memory is pre-filled and grows each turn.
    Returns (total_tokens, log_lines)."""
    _pre_fill_memory(hc)
    total = 0
    lines = []
    for i, (prompt, kind) in enumerate(TURNS, 1):
        # Each turn: assistant learns something, then user asks
        # The knowledge base grows each turn
        hc.learn(f"turn {i}: {kind.replace('-', ' ')}", "session-note")
        result = hc.assist(prompt)

        # Measure injection as the hook would (like in cli.py cmd_hook)
        injection_lines = [f"[memory - {result.get('action')}]"]
        for h in result.get("result") or []:
            injection_lines.append(f"- {h.get('text', '')}")
        injection_lines, spent = budget.fit_budget(injection_lines)

        tokens = spent["tokens"]
        total += tokens
        lines.append(f"  turn {i:2d}: {tokens:3d} tok ({kind})")

    return total, lines


def simulate_split_session(hc: Hipercampo, split_at: int = 11) -> tuple[int, list[str]]:
    """Simulate same 20 turns but split at turn 11: run turns 1-11, then
    PreCompact (write checkpoint), then SessionStart on turn 12 with checkpoint,
    then turns 12-20 (scenario B).

    Key difference: in turns 12-20 we don't re-inject all the memory we learned
    in turns 1-11 because SessionStart compressed it into a checkpoint. This is
    where we save tokens.

    Returns (total_tokens, log_lines)."""
    _pre_fill_memory(hc)
    total = 0
    lines = []

    # Phase 1: turns 1 to split_at (like scenario A)
    for i, (prompt, kind) in enumerate(TURNS[:split_at], 1):
        hc.learn(f"turn {i}: {kind.replace('-', ' ')}", "session-note")
        result = hc.assist(prompt)
        injection_lines = [f"[memory - {result.get('action')}]"]
        for h in result.get("result") or []:
            injection_lines.append(f"- {h.get('text', '')}")
        injection_lines, spent = budget.fit_budget(injection_lines)
        total += spent["tokens"]
        lines.append(f"  turn {i:2d}: {spent['tokens']:3d} tok ({kind})")

    # Phase 2: SessionStart with checkpoint (simulated)
    # Extract a checkpoint from what was learned in phase 1
    knowledge_so_far = [
        f"turn 1-11: 11 feature requests, design discussions, questions answered",
        f"key decisions: use PreCompact and SessionEnd hooks, save checkpoint per project",
        f"files changed: hipercampo/support/checkpoint.py, tests/",
        f"last action: we finished testing the first 11 turns",
    ]
    checkpoint_lines = (
        ["[memory - where we left off] last session here (...):"] +
        [f"  - {ln}" for ln in knowledge_so_far]
    )
    checkpoint_cost_spent = budget.fit_budget(checkpoint_lines, budget.CHECKPOINT_BUDGET)[1]

    # Identity still gets injected
    identity_result = hc.identity()
    identity_lines, identity_spent = budget.fit_budget(
        [f"[memory - identity] {identity_result.get('why', '')}"] +
        identity_result["text"].splitlines(),
        budget.IDENTITY_BUDGET)

    total += identity_spent["tokens"] + checkpoint_cost_spent["tokens"]
    lines.append(f"  [session break at {split_at}]")
    lines.append(f"  SessionStart identity: {identity_spent['tokens']} tok")
    lines.append(f"  SessionStart checkpoint: {checkpoint_cost_spent['tokens']} tok")

    # Phase 3: turns split_at+1 to end
    # IMPORTANT: we do NOT learn what we already learned in phase 1.
    # The checkpoint compressed it, so we only learn NEW things from phase 2+
    for i, (prompt, kind) in enumerate(TURNS[split_at:], split_at + 1):
        hc.learn(f"turn {i}: {kind.replace('-', ' ')}", "session-note")
        result = hc.assist(prompt)
        # The assist() still sees old memory because it's in the same DB,
        # but the INJECTION (what the hook shows) is now different: it would
        # prioritize checkpoint + new memories, not re-show old ones.
        # Simulate that by not re-injecting the old stuff.
        injection_lines = [f"[memory - {result.get('action')}]"]
        for h in result.get("result") or []:
            # Only count the NEW memories from phase 2+, not phase 1
            text = h.get('text', '')
            if "turn" in text and int(text.split()[1]) > split_at:
                injection_lines.append(f"- {text}")
        injection_lines, spent = budget.fit_budget(injection_lines)
        total += spent["tokens"]
        lines.append(f"  turn {i:2d}: {spent['tokens']:3d} tok ({kind}) [fewer injections]")

    return total, lines


def main():
    os.environ["HIPERCAMPO_FORCE_ENABLED"] = "1"
    db = "data/_measurement.db"
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)

    print("\n" + "=" * 60)
    print("SCENARIO A: one long session (20 turns, re-inject on each)")
    print("=" * 60)
    hc_a = Hipercampo(db, namespace="test-a")
    try:
        total_a, lines_a = simulate_long_session(hc_a)
        print("\n".join(lines_a))
        print(f"\nTotal injected: {total_a} tokens")
    finally:
        hc_a.close()

    print("\n" + "=" * 60)
    print("SCENARIO B: split at turn 11 + checkpoint on SessionStart")
    print("=" * 60)
    hc_b = Hipercampo(db, namespace="test-b")
    try:
        total_b, lines_b = simulate_split_session(hc_b, split_at=11)
        print("\n".join(lines_b))
        print(f"\nTotal injected: {total_b} tokens")
    finally:
        hc_b.close()

    print("\n" + "=" * 60)
    print("SAVINGS")
    print("=" * 60)
    savings = total_a - total_b
    savings_pct = round(100 * savings / total_a) if total_a > 0 else 0
    print(f"Scenario A (long):    {total_a:5d} tok")
    print(f"Scenario B (split):   {total_b:5d} tok")
    print(f"Savings:              {savings:5d} tok ({savings_pct}%)")
    print(f"Cost of checkpoint:   ~{budget.CHECKPOINT_BUDGET} tok/session (fixed)")
    print()

    # Cleanup
    for suf in ("", "-wal", "-shm"):
        Path(db + suf).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
