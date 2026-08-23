"""
Export/import: the same memory grown on two machines, merged without a loser.

What these tests actually guard, in order of how much it would hurt to get wrong:

  - LINKS LAND ON THE RIGHT MEMORIES. `memories.id` is AUTOINCREMENT, so the
    same memory has different ids on different machines. A format that shipped
    ids would rewire the graph to strangers, and the graph is silent when it is
    wrong: recall just gets worse. So the round trip here is deliberately run
    against a destination whose ids are OFFSET from the source's, and it asserts
    on the TEXTS at the ends of each edge, never on ids.
  - IMPORTING TWICE CHANGES NOTHING. These files get shipped through git and
    re-imported for years. Every merge rule is monotone for this reason, and the
    test that would catch a `+=` sneaking in is `test_importing_twice_...`.
  - A HYPERVECTOR THAT CANNOT BE RECOMPUTED SURVIVES. Consolidated semantic
    memories carry the bundle of what they absorbed, not the encoding of their
    label. Recomputing those from text loses the consolidation with no error
    anywhere — it just retrieves worse. See `test_unreproducible_hv_...`.

Run:  python tests/storage/test_exchange.py
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, run_tests  # noqa: E402

from hipercampo.core.encoder import encode_text  # noqa: E402
from hipercampo.core.vsa import to_blob  # noqa: E402
from hipercampo.storage import exchange  # noqa: E402
from hipercampo.storage.store import Store  # noqa: E402

_DIR = Path("data")
_A = str(_DIR / "_t_exch_a.db")
_B = str(_DIR / "_t_exch_b.db")
_OUT = str(_DIR / "_t_exch.jsonl")
_NS = "proj"


def _wipe():
    _DIR.mkdir(parents=True, exist_ok=True)
    for base in (_A, _B):
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(base + suffix).unlink(missing_ok=True)
            except PermissionError:
                pass          # A live Windows handle will make the test fail visibly.
    Path(_OUT).unlink(missing_ok=True)


def _store(path, namespace=_NS) -> Store:
    return Store(path, namespace=namespace)


def _add(store, text, **kw) -> int:
    """A memory whose hypervector IS the encoding of its text (the ordinary case)."""
    return store.add(text, encode_text(text), kw.pop("novelty", 1.0),
                     kw.pop("importance", 0.5), **kw)


def _texts(path, namespace=_NS) -> set:
    db = sqlite3.connect(path)
    try:
        return {r[0] for r in db.execute(
            "SELECT text FROM memories WHERE namespace=?", (namespace,))}
    finally:
        db.close()


def _edges(path, namespace=_NS) -> set:
    """Edges as pairs of TEXTS. Ids are meaningless across machines, which is
    the entire point of the format, so the assertions must not use them."""
    db = sqlite3.connect(path)
    try:
        rows = db.execute(
            "SELECT a.text, b.text FROM links l "
            "JOIN memories a ON a.id = l.src JOIN memories b ON b.id = l.dst "
            "WHERE l.namespace=? AND l.type <> 'knn'", (namespace,)).fetchall()
        return {tuple(sorted(r)) for r in rows}
    finally:
        db.close()


def _row(path, text):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    try:
        return db.execute("SELECT * FROM memories WHERE text=?", (text,)).fetchone()
    finally:
        db.close()


def _seed_source() -> None:
    """Machine A: three linked memories."""
    s = _store(_A)
    one = _add(s, "the deploy runs on fly.io from the main branch")
    two = _add(s, "migrations are applied by hand before the deploy")
    three = _add(s, "the staging database is reset every monday")
    s.link(one, two, 0.8)
    s.link(two, three, 0.5)
    s.close()


def test_round_trip_into_an_empty_machine():
    """Everything arrives: texts and the graph joining them."""
    _wipe()
    _seed_source()
    exchange.export_to(_OUT, _A)
    report = exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    assert report["applied"] is True, report
    assert report["memories"]["new"] == 3, report
    assert _texts(_B) == _texts(_A), "the memories did not all arrive"
    assert _edges(_B) == _edges(_A), f"the graph did not survive: {_edges(_B)}"


def test_links_land_on_the_right_memories_when_ids_differ():
    """The bug the uid format exists to prevent.

    The destination is seeded with unrelated memories FIRST, so its autoincrement
    is offset and the same memory carries a different id on each side. If the
    format leaked ids, the edges would connect real memories with plausible
    weights — to the wrong ones.
    """
    _wipe()
    _seed_source()

    b = _store(_B)
    for i in range(7):                      # push B's ids out of step with A's
        _add(b, f"unrelated local note number {i}")
    b.close()

    exchange.export_to(_OUT, _A)
    exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    ids_a = {t: _row(_A, t)["id"] for t in _texts(_A)}
    ids_b = {t: _row(_B, t)["id"] for t in _texts(_A)}
    assert ids_a != ids_b, "the ids did not diverge: this test would prove nothing"
    assert _edges(_B) == _edges(_A), (
        f"edges rewired to the wrong memories:\n  A={_edges(_A)}\n  B={_edges(_B)}")


def test_importing_twice_changes_nothing():
    """Idempotency. These logs get re-imported forever; a `+=` anywhere would
    inflate a memory a little on every pass and nothing would ever complain."""
    _wipe()
    _seed_source()
    exchange.export_to(_OUT, _A)
    exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)
    before = {t: dict(_row(_B, t)) for t in _texts(_B)}

    second = exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    assert second["memories"]["new"] == 0, second
    assert second["memories"]["merged"] == 0, second
    assert second["memories"]["unchanged"] == 3, second
    after = {t: dict(_row(_B, t)) for t in _texts(_B)}
    assert before == after, "a second import moved values that should be settled"


def test_merge_keeps_the_strongest_and_the_earliest():
    """Accumulators take the max, birth takes the min, so the merge does not
    depend on which machine happens to import first."""
    _wipe()
    a = _store(_A)
    mid = _add(a, "the API rate limit is 100 requests per minute")
    a.db.execute("UPDATE memories SET access_count=9, strength=2.5, created=1000, "
                 "last_access=1000 WHERE id=?", (mid,))
    a.db.commit()
    a.close()

    b = _store(_B)
    bid = _add(b, "the API rate limit is 100 requests per minute")
    b.db.execute("UPDATE memories SET access_count=2, strength=9.0, created=500, "
                 "last_access=500 WHERE id=?", (bid,))
    b.db.commit()
    b.close()

    exchange.export_to(_OUT, _A)
    exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    row = _row(_B, "the API rate limit is 100 requests per minute")
    assert row["access_count"] == 9, f"accesses should take the max: {row['access_count']}"
    assert row["strength"] == 9.0, f"strength should take the max: {row['strength']}"
    assert row["created"] == 500, f"birth should take the earliest: {row['created']}"


def test_forgetting_propagates_and_is_reported():
    """`dormant` is last-writer-wins by last_access, so forgetting on one machine
    reaches the other — and the report says a local judgement was overwritten,
    because that is the one place the merge costs someone something."""
    _wipe()
    a = _store(_A)
    mid = _add(a, "the old redis cache was removed in january")
    a.db.execute("UPDATE memories SET dormant=1, last_access=9000 WHERE id=?", (mid,))
    a.db.commit()
    a.close()

    b = _store(_B)
    bid = _add(b, "the old redis cache was removed in january")
    b.db.execute("UPDATE memories SET dormant=0, last_access=100 WHERE id=?", (bid,))
    b.db.commit()
    b.close()

    exchange.export_to(_OUT, _A)
    report = exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    assert _row(_B, "the old redis cache was removed in january")["dormant"] == 1
    fields = [o["field"] for o in report["overwrites"]]
    assert "dormant" in fields, f"the overwrite was not reported: {report['overwrites']}"


def test_unreproducible_hv_survives_the_trip():
    """A consolidated semantic memory carries the BUNDLE of what it absorbed,
    not the encoding of its own label. Recomputing it from text would lose the
    consolidation silently, so the export has to carry the vector verbatim."""
    _wipe()
    a = _store(_A)
    label = "[grouped x2]\n- deploys on friday go wrong\n- the friday freeze exists"
    odd_hv = encode_text("something else entirely")        # deliberately NOT the label
    a.add(label, odd_hv, 1.0, 0.5, kind="semantic")
    plain = "the friday freeze exists"
    _add(a, plain)
    a.close()

    exchange.export_to(_OUT, _A)
    _, records = exchange.read_records(_OUT)
    carried = {r["text"]: ("hv" in r) for r in records if r["t"] == "memory"}
    assert carried[label] is True, "the unreproducible vector was not carried"
    assert carried[plain] is False, "an ordinary vector was carried for nothing"

    exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)
    assert _row(_B, label)["hv"] == to_blob(odd_hv), "the bundle came back wrong"
    assert _row(_B, plain)["hv"] == to_blob(encode_text(plain))


def test_knn_links_are_not_exported():
    """They are a rebuildable index, not knowledge. Shipping them would ship a
    cache keyed on ids that mean nothing on the far side."""
    _wipe()
    a = _store(_A)
    one = _add(a, "postgres runs in the same fly.io region as the app")
    two = _add(a, "the app has one worker process per core")
    a.link(one, two, 0.4, type="knn")
    a.close()

    exchange.export_to(_OUT, _A)
    _, records = exchange.read_records(_OUT)
    assert not [r for r in records if r["t"] == "link"], "a knn edge was exported"


def test_dry_run_writes_nothing():
    """The default mode has to be the safe one: importing the wrong file into a
    live memory is easy to do and expensive to notice late."""
    _wipe()
    _seed_source()
    exchange.export_to(_OUT, _A)
    b = _store(_B)
    _add(b, "the only memory this machine had")
    b.close()

    report = exchange.import_from(_OUT, _B, namespace=_NS)      # dry_run defaults True

    assert report["dry_run"] is True and report["applied"] is False, report
    assert report["memories"]["new"] == 3, report
    assert _texts(_B) == {"the only memory this machine had"}, "a dry run wrote"


def test_other_contexts_are_skipped_and_counted():
    """Import respects write isolation. Records from another context do not land,
    and they are REPORTED: a mismatched namespace must not look like an empty file."""
    _wipe()
    a = _store(_A, namespace="other-project")
    _add(a, "a secret belonging to a different project")
    a.close()

    exchange.export_to(_OUT, _A)
    report = exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    assert report["memories"]["new"] == 0, report
    assert report["skipped_namespaces"].get("other-project") == 1, report
    assert _texts(_B, "other-project") == set()


def test_a_link_with_an_unknown_end_is_reported_not_invented():
    """If one endpoint never arrives, the edge is dropped and counted. A link
    pointing at the wrong memory is worse than a missing one."""
    _wipe()
    _seed_source()
    exchange.export_to(_OUT, _A)

    # Drop one memory from the log, keeping its edges: exactly what a partial or
    # hand-trimmed export looks like.
    kept = []
    with open(_OUT, encoding="utf-8") as f:
        for line in f:
            rec = json.loads(line)
            if rec.get("t") == "memory" and rec["text"].startswith("the staging"):
                continue
            kept.append(line)
    with open(_OUT, "w", encoding="utf-8") as f:
        f.writelines(kept)

    report = exchange.import_from(_OUT, _B, namespace=_NS, dry_run=False)

    assert report["links"]["dangling"] == 1, report
    assert report["memories"]["new"] == 2, report


def test_two_machines_converge_whoever_imports_first():
    """Both sides exchange logs and end up holding the same thing. Order must not
    matter, or a sync between three machines would never settle."""
    _wipe()
    a = _store(_A)
    _add(a, "only machine A knew about the nginx timeout")
    a.close()
    b = _store(_B)
    _add(b, "only machine B knew about the certificate renewal")
    b.close()

    out_a, out_b = _OUT, _OUT + ".b"
    try:
        exchange.export_to(out_a, _A)
        exchange.export_to(out_b, _B)
        exchange.import_from(out_b, _A, namespace=_NS, dry_run=False)
        exchange.import_from(out_a, _B, namespace=_NS, dry_run=False)

        assert _texts(_A) == _texts(_B), f"diverged: {_texts(_A) ^ _texts(_B)}"
        assert len(_texts(_A)) == 2, _texts(_A)
    finally:
        Path(out_b).unlink(missing_ok=True)


def test_the_cli_pipes_through_stdout_and_stdin():
    """`export -` and `import -` are what keep a plaintext copy of a whole
    memory off the disk when it is going through age/gpg into a shared repo.
    A documented path with no test is how the seams in this project break, and
    this one has two: the summary must not land in the encrypted stream, and
    the reader must accept stdin.
    """
    import subprocess
    _wipe()
    _seed_source()

    env = dict(os.environ)
    env.update({"HIPERCAMPO_NAMESPACE": _NS, "HIPERCAMPO_FORCE_ENABLED": "1",
                "HIPERCAMPO_LOG": "0", "HIPERCAMPO_DB": os.path.abspath(_A)})
    cli = [sys.executable, "-m", "hipercampo.cli"]
    exported = subprocess.run(cli + ["export", "-"], capture_output=True, text=True,
                              env=env, cwd=str(ROOT))
    assert exported.returncode == 0, exported.stderr
    for line in exported.stdout.splitlines():
        assert line.strip().startswith("{"), f"non-log line in the stream: {line!r}"
    assert '"machine"' in exported.stderr, "the summary did not go to stderr"

    env["HIPERCAMPO_DB"] = os.path.abspath(_B)
    landed = subprocess.run(cli + ["import", "-", "--apply"], input=exported.stdout,
                            capture_output=True, text=True, env=env, cwd=str(ROOT))
    assert landed.returncode == 0, landed.stderr
    assert _texts(_B) == _texts(_A), "the piped log did not arrive intact"


if __name__ == "__main__":
    raise SystemExit(run_tests(globals()))
