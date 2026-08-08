"""
Invariants that must survive a refactor: the concrete bugs that were fixed, and
the equivalences that have to hold when a loop is vectorised or N queries are
collapsed into one.

Every test in here was written because something was WRONG, not because it looked
tidy. Each one has been checked to FAIL against the old code — a regression test
that never went red proves nothing.
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ejecutar, memoria  # noqa: E402
from hipercampo.core.vsa import (  # noqa: E402
    _TIEBREAK, D, bundle, hamming, random_hv, similarity,
)
from hipercampo.storage.store import Store  # noqa: E402


# --- 1. the vectorised bundle must produce THE SAME BITS ---------------------
def _reference_bundle(hvs):
    """The original definition, bit by bit: majority vote with +-1 and a fixed
    tie-break pattern."""
    acc = np.zeros(D, dtype=np.int32)
    for h in hvs:
        acc += np.unpackbits(h)[:D].astype(np.int32) * 2 - 1
    return np.packbits(np.where(acc > 0, 1, np.where(acc < 0, 0, _TIEBREAK)).astype(np.uint8))


def test_bundle_identical_to_the_definition():
    """It now counts ONES in batches instead of +-1: it must be indistinguishable.

    EVEN sizes are included on purpose (that is where ties happen and the
    tie-break decides) along with sizes that straddle the batch boundary, which
    is where a badly sized accumulator or a mis-cut batch would show up."""
    for n in (1, 2, 3, 6, 7, 63, 64, 65, 128, 129, 300):
        hvs = [random_hv(i) for i in range(n)]
        assert (bundle(hvs) == _reference_bundle(hvs)).all(), f"bundle differs at n={n}"


def test_hamming_identical_to_unpacking():
    """Counting bits 16 at a time must total the same as unpacking bit by bit."""
    for s in range(20):
        a, b = random_hv(s), random_hv(s + 100)
        expected = int(np.unpackbits(np.bitwise_xor(a, b)).sum())
        assert hamming(a, b) == expected
        assert abs(similarity(a, b) - (1.0 - expected / D)) < 1e-12


# --- 2. forget() must not commit somebody else's transaction ------------------
def test_forget_does_not_break_an_enclosing_transaction():
    """`forget` used to commit with `store.commit()`, which commits the whole
    CONNECTION.

    Nested inside another transaction — which is what happens when automatic sleep
    fires from an atomised write — that half-committed the caller's work: the
    all-or-nothing stopped being all-or-nothing. Here a transaction is opened, a
    row written, forget called, and then a failure forced: NOTHING may survive."""
    hc = memoria("forget_txn")
    hc.remember("some earlier memory so that there is something to decay")
    before = len(hc.store.all(only_active=False, include_dormant=True))

    try:
        with hc.store.transaction():
            hc.store.add("a write that must be rolled back entirely",
                         hc.store.hv_of(hc.store.all()[0]), 1.0, 0.5, 0.5)
            hc.forget(dry_run=False)      # before: commit -> the row above survived
            raise RuntimeError("failure halfway through the transaction")
    except RuntimeError:
        pass

    after = len(hc.store.all(only_active=False, include_dormant=True))
    assert after == before, f"the transaction did not roll back entirely: {before} -> {after}"


def test_autosleep_does_not_run_inside_a_transaction():
    """Maintenance must not run nested inside somebody else's write: it could
    consolidate the very atoms that transaction is still writing."""
    hc = memoria("autosleep_txn")
    with hc.store.transaction():
        assert hc._autosleep() is None, "autosleep must not run inside a transaction"


# --- 3. _self_store returns a Store, not an error dictionary ------------------
def test_self_store_returns_a_store():
    hc = memoria("self_store")
    assert isinstance(hc._self_store(), Store)


def test_learn_gives_a_readable_error_when_the_db_fails():
    """The actual bug: `_self_store` carried @resiliente, and that decorator
    returns an error DICT when the database fails. Callers expect a Store, so the
    "readable message" it promises turned into
    `AttributeError: 'dict' object has no attribute 'all'` — which also escaped
    learn's own `except sqlite3.Error`, taking down the agent using the memory.

    With the decorator where it belongs (on learn, which does return dicts), a
    database failure comes back as a readable error."""
    import sqlite3

    import hipercampo.cycle.memory as M

    hc = memoria("learn_broken_db")
    hc._ss = None                                  # force it to open again
    original = M.Store

    def broken_store(*a, **kw):
        raise sqlite3.OperationalError("no such table: memories")

    M.Store = broken_store
    try:
        r = hc.learn("some rule", tipo="regla")
    finally:
        M.Store = original
    assert isinstance(r, dict), f"learn should return a dict, it returned {type(r)}"
    assert "error" in r, f"expected a readable error, got {r}"


def test_learn_still_works_on_repeated_use():
    """Identity has to survive ordinary repeated use — the path that goes through
    _self_store on every call."""
    hc = memoria("learn_ok")
    r1 = hc.learn("measure before believing", tipo="regla")
    assert r1.get("learned") is True
    r2 = hc.learn("measure before believing", tipo="regla")     # already known
    assert r2.get("learned") is False and r2.get("reinforced") == r1["id"]


# --- 4. batched queries must say the same as one-at-a-time queries ------------
def test_neighbors_all_matches_neighbors():
    """`neighbors_all` replaces N calls to `neighbors` in dream: same result (only
    confirmed links, no self-links, best weight per neighbour)."""
    hc = memoria("neigh_all")
    for i in range(8):
        hc.remember(f"note number {i} about associative memory and sparse vectors")
    rows = hc.store.all(only_active=False, include_dormant=True)
    ids = [r["id"] for r in rows]
    batched = hc.store.neighbors_all(ids=ids)
    for i in ids:
        one = {d: w for d, w in hc.store.neighbors(i) if d in set(ids)}
        assert batched.get(i, {}) == one, f"different neighbours for {i}"


def test_get_many_matches_get():
    hc = memoria("get_many")
    for i in range(5):
        hc.remember(f"another memory unlike the previous one, number {i}, with its own text")
    ids = [r["id"] for r in hc.store.all(only_active=False)]
    many = hc.store.get_many(ids + [999999])          # a missing id is just omitted
    assert 999999 not in many
    for i in ids:
        assert many[i]["text"] == hc.store.get(i)["text"]


# --- 5. renaming the identity types must not orphan stored rows --------------
def test_legacy_spanish_identity_types_still_work():
    """The identity `kind` keys were Spanish and are WRITTEN INTO the stored text
    (`"leccion: ..."`). Renaming them to English could not be a plain rename: every
    row already on a user's disk carries the old prefix, and dropping it wouldn't
    raise anything — it would quietly file every stored rule and decision under
    "lesson" and lose the distinction for good."""
    from hipercampo.cycle.identity import format_identity, normalise_type

    assert normalise_type("regla") == "rule"
    assert normalise_type("leccion") == "lesson"
    assert normalise_type("preferencia") == "preference"
    assert normalise_type("rule") == "rule"          # the new ones, unchanged
    assert normalise_type("nonsense") is None

    # a memory written BEFORE the rename must still read as what it is
    legacy = [{"text": "regla: measure before believing"},
              {"text": "leccion: linux-only CI hides bugs"}]
    salida = format_identity(legacy)
    assert "RULES" in salida and "measure before believing" in salida
    assert "LESSONS" in salida and "linux-only CI hides bugs" in salida
    assert "regla:" not in salida, "the legacy prefix leaked into the output"


def test_learn_accepts_the_old_parameter_name_and_values():
    """`hc_learn(tipo="regla")` was the public signature. Both the old parameter
    name and the old values keep working; new rows are stored in English."""
    hc = memoria("legacy_learn")
    r = hc.learn("a rule stored the old way", tipo="regla")
    assert r.get("learned") is True, r
    assert r["kind"] == "rule", r
    assert r["text"].startswith("rule: "), r["text"]
    assert hc.learn("something", tipo="not-a-type").get("error")


if __name__ == "__main__":
    raise SystemExit(ejecutar(dict(globals())))
