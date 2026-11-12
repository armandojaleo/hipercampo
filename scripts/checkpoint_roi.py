"""
Realistic ROI of checkpoint: as a session grows, so does injection cost.

Real data shows injections of 50-353 tok/turn. As memory grows:
  - Turn 1:  maybe 5 tok (nothing relevant yet)
  - Turn 10: maybe 50 tok (some relevant memories)
  - Turn 20: maybe 100 tok (lots of relevant memories)

Without checkpoint, each turn re-injects ALL accumulated memory.
With checkpoint at turn 11, turns 12-20 see a COMPRESSED version of turns 1-11,
plus only NEW memories.

This is the ROI calculation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.support import budget


def injection_cost(turn: int, total_turns: int) -> int:
    """Estimate injection cost at each turn.
    As the session grows and memory accumulates, injection cost grows linearly."""
    # Start at 5 tokens (cold start), ramp to 150 by the last turn
    min_cost, max_cost = 5, 150
    progress = turn / total_turns
    return min_cost + int((max_cost - min_cost) * progress)


def scenario_a(turns: int) -> tuple[int, list[str]]:
    """One long session: every turn re-injects all accumulated memory.
    As turns accumulate, injection cost grows each turn."""
    total = 0
    lines = []
    for turn in range(1, turns + 1):
        cost = injection_cost(turn, turns)
        total += cost
        lines.append(f"  turn {turn:2d}: {cost:3d} tok (memory keeps growing)")
    return total, lines


def scenario_b_split_at(turns: int, split_at: int) -> tuple[int, list[str]]:
    """Session split at turn N: turns 1..N, then PreCompact/SessionStart,
    then turns N+1..total.

    At the split: we compress all the accumulated memory (which was being
    re-injected every turn) into a checkpoint. Then turns N+1..total don't
    re-inject that accumulated stuff, only new things.
    """
    total = 0
    lines = []

    # Phase 1: turns 1 to split_at (same as scenario A)
    for turn in range(1, split_at + 1):
        cost = injection_cost(turn, turns)
        total += cost
        lines.append(f"  turn {turn:2d}: {cost:3d} tok (memory accumulates)")

    # Phase 2: PreCompact/SessionStart
    # Compress all of phase 1 into a checkpoint (say ~150 tokens)
    # Plus identity (~50 tokens)
    checkpoint_cost = min(budget.CHECKPOINT_BUDGET, 150)
    identity_cost = 50
    total += checkpoint_cost + identity_cost
    lines.append(f"  [break at turn {split_at}]")
    lines.append(f"  SessionStart checkpoint: {checkpoint_cost} tok (compressed)")
    lines.append(f"  SessionStart identity:   {identity_cost} tok")

    # Phase 3: turns split_at+1 to total
    # NEW injections only (not re-running the old stuff from phase 1)
    # Cost is lower: only growth from new memories
    for turn in range(split_at + 1, turns + 1):
        # Instead of injection_cost(turn, turns), which would be 150,
        # we now only inject growth from new memories
        old_cost = injection_cost(turn, turns)
        # Estimate: only the "new" part, not the 1..split_at part that's now in checkpoint
        new_cost = int(old_cost * (turn - split_at) / (turns - split_at))
        total += new_cost
        lines.append(f"  turn {turn:2d}: {new_cost:3d} tok (only new memories)")

    return total, lines


def main():
    print("\n" + "=" * 70)
    print("CHECKPOINT ROI: realistic injection cost growth during a session")
    print("=" * 70)

    test_cases = [
        (20, 11),
        (30, 15),
        (40, 20),
        (60, 30),
    ]

    for total_turns, split_at in test_cases:
        print(f"\n{'-' * 70}")
        print(f"Total turns: {total_turns}, Split at: {split_at}")
        print(f"{'-' * 70}")

        print("\nSCENARIO A: one long session")
        print("-" * 35)
        total_a, lines_a = scenario_a(total_turns)
        print("\n".join(lines_a[:5] + ["  ..."] + lines_a[-5:]))
        print(f"Total:  {total_a} tokens")

        print("\nSCENARIO B: split at turn", split_at)
        print("-" * 35)
        total_b, lines_b = scenario_b_split_at(total_turns, split_at)
        phase1_line = f"  turn {split_at:2d}"
        idx = next(i for i, l in enumerate(lines_b) if phase1_line in l)
        print("\n".join(lines_b[:5] + ["  ..."] + lines_b[idx:idx+4]))
        print(f"Total:  {total_b} tokens")

        savings = total_a - total_b
        savings_pct = round(100 * savings / total_a) if total_a > 0 else 0
        status = "SAVINGS" if savings > 0 else "COST"
        print(f"\n{status}: {abs(savings):4d} tokens ({abs(savings_pct):+d}%)")


if __name__ == "__main__":
    main()
