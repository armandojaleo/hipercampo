"""
Use case 5 - A fact that changes, and asking what was true THEN.
Run:  python examples/05_temporal_facts.py

`remember_fact` never overwrites: when the same subject+predicate gets a new
object, the old fact is CLOSED (not deleted) and stays queryable as history.
`ask_role(..., at=timestamp)` answers what was true at that point in time,
not just what's true now — something a plain vector store can't do, because
it has no notion of a fact's validity window.
"""

import sys
import time
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

DB = "data/ex_temporal.db"
DAY = 86400


def cleanup():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    cleanup()
    hc = Hipercampo(DB, namespace="oncall")
    now = time.time()

    print("-- Three months of on-call rotation, recorded as they happened --")
    rotation = [
        ("Marta", now - 90 * DAY),
        ("Diego", now - 60 * DAY),
        ("Priya", now - 30 * DAY),
        ("Marta", now - 3 * DAY),   # back on rotation
    ]
    fact_ids = []
    for person, _timestamp in rotation:      # the timestamps are applied below
        r = hc.remember_fact({"subject": "on-call", "predicate": "is", "object": person})
        fact_ids.append(r["id"])
        if r.get("supersedes"):
            print(f"  {person} takes over  (closes fact #{r['supersedes'][0]} as history)")
        else:
            print(f"  {person} takes over  (first record)")

    # `remember_fact` has no "backdate" argument -- it stamps validity at
    # call time, same as a real agent would. To DEMONSTRATE months of
    # history without actually waiting months, we backdate the validity
    # window directly, the same way examples/04 fast-forwards `last_access`.
    # strict=True is not just to satisfy the linter: the three lists line up by
    # construction, so a mismatch would mean `rotation` was edited without the
    # windows following, and silently pairing the wrong dates is worse than raising.
    windows = list(zip(fact_ids, [w for _, w in rotation],
                       [w for _, w in rotation[1:]] + [None], strict=True))
    for fid, valid_from, valid_to in windows:
        hc.store.db.execute("UPDATE facts SET valid_from = ?, valid_to = ? WHERE id = ?",
                            (valid_from, valid_to, fid))
    hc.store.commit()

    print("\n-- What's true NOW --")
    now_answer = hc.ask_role("object", {"subject": "on-call", "predicate": "is"})
    print(f"  who's on-call right now? -> {now_answer['answer']}"
          f"  (confidence {now_answer['confidence']})")

    print("\n-- What was true 45 days ago, when the incident happened --")
    past_answer = hc.ask_role("object", {"subject": "on-call", "predicate": "is"},
                              at=now - 45 * DAY)
    if past_answer.get("unknown"):
        print(f"  who was on-call then?    -> don't know ({past_answer['reason']})")
    else:
        print(f"  who was on-call then?    -> {past_answer['answer']}"
              f"  (confidence {past_answer['confidence']})")

    print("\n  Note: nothing was overwritten. Every past rotation is still on")
    print("  disk as closed history — `at=` is a query, not a different store.")
    hc.store.close()
    cleanup()


if __name__ == "__main__":
    main()
