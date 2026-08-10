"""
How the LongMemEval subset is chosen, and why it is not `data[:limit]`.

A benchmark subset is a claim about the whole benchmark, and this one was wrong
in a way that looked excellent. LongMemEval ships GROUPED by question_type, with
the abstention instances (`*_abs`) at the end of each group. Taking the first N
therefore sampled one category and zero abstentions: the adapter reported

    recall@5=1.0 · abstention=None

on ten `single-session-user` questions — a perfect score for the easiest sixth of
the benchmark, indistinguishable in the output from a perfect score on all of it.

Nothing could have caught that. No assertion was false; the number was real, the
population was not. So the population is what gets pinned here.

The dataset is 277 MB and is not in the repository, so these tests build a corpus
with the same SHAPE (grouped, `_abs` last) rather than skipping when it is
absent — a test that skips in CI is a test that does not exist.
"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
from helpers import ROOT, run_tests  # noqa: E402

sys.path.insert(0, str(ROOT / "scripts"))
from context_efficiency import load_longmemeval, print_report  # noqa: E402

# Same proportions as the real corpus (500 instances, 6 types, 30 abstentions),
# and crucially the same LAYOUT: sorted by type, `_abs` at the tail of each block.
_SIZES = {"multi-session": 133, "temporal-reasoning": 133, "knowledge-update": 78,
          "single-session-user": 70, "single-session-assistant": 56,
          "single-session-preference": 30}


def _instance(kind, name):
    return {"question_id": name, "question_type": kind, "question": "q?",
            "haystack_session_ids": ["s0"], "answer_session_ids": ["s0"],
            "haystack_sessions": [[{"role": "user", "content": "x"}]]}


def _corpus():
    data = []
    for kind in sorted(_SIZES):
        n = _SIZES[kind]
        abstentions = round(n * 30 / 500)
        for i in range(n - abstentions):
            data.append(_instance(kind, f"{kind}-{i}"))
        for i in range(abstentions):          # at the END of the block, as shipped
            data.append(_instance(kind, f"{kind}-{i}_abs"))
    return data


def _subsample(data, limit):
    """Go through the REAL entry point, not the helper.

    The first version of these tests called `_subsample` directly and passed
    against the very bug they describe: reverting the call site back to
    `data[:limit]` left them green, because they never touched the call site.
    A subset test that does not exercise how the subset is actually taken is
    decoration. So the corpus goes to disk and comes back through
    `load_longmemeval`, exactly as the benchmark loads it."""
    path = Path(tempfile.gettempdir()) / "hc_lme_sampling" / "corpus.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return load_longmemeval(path, limit)


def test_every_question_type_survives_the_subset():
    """The failure that started this: ten instances, one category, reported as
    if it were the benchmark."""
    data = _corpus()
    for n in (12, 30, 60, 120):
        kinds = {i["question_type"] for i in _subsample(data, n)}
        assert kinds == set(_SIZES), (
            f"n={n} sampled {len(kinds)} of {len(_SIZES)} question types: "
            f"missing {sorted(set(_SIZES) - kinds)}")


def test_abstention_questions_are_never_sampled_away():
    """Grouping by question_type alone did NOT fix this, which is the point of a
    separate test: `_abs` sits at the tail of each block, so taking the head of
    every bucket still selected zero abstentions at n=60, and the abstention
    metric silently reported None."""
    data = _corpus()
    for n in (12, 30, 60, 120):
        picked = sum(str(i["question_id"]).endswith("_abs") for i in _subsample(data, n))
        assert picked > 0, f"n={n} sampled no abstention questions at all"


def test_the_subset_keeps_the_corpus_mix():
    """Representation is not enough — round-robin represented every category and
    turned 6% abstention questions into 42% of the sample. Checked where it is
    meaningful: with 12 buckets and a floor of one each, a 12-instance sample
    cannot be proportional, so the guarantee starts once there is room."""
    data = _corpus()
    real = {k: n / len(data) for k, n in _SIZES.items()}
    for n, tolerance in ((60, 0.06), (120, 0.04)):
        sample = _subsample(data, n)
        for kind, share in real.items():
            got = sum(i["question_type"] == kind for i in sample) / len(sample)
            assert abs(got - share) <= tolerance, (
                f"n={n}: {kind} is {got:.1%} of the sample but {share:.1%} of the "
                f"corpus (tolerance {tolerance:.0%})")


def test_a_limit_beyond_the_corpus_returns_all_of_it():
    data = _corpus()
    assert len(_subsample(data, len(data))) == len(data)
    assert len(_subsample(data, len(data) * 10)) == len(data)


def test_the_report_refuses_to_invent_a_missing_number():
    """`print_report` asked for the median with `.get("p50", 0)` while the report
    never carried one, so every run printed a confident `p50=0 tokens` that was
    the default. A missing measurement must raise, not render as zero."""
    report = {"dataset": "LongMemEval", "k": 5, "retrieval_recall_at_k": 0.5,
              "abstention_accuracy": None,
              "payload_tokens": {"mean": 1.0, "p95": 2.0},      # no p50
              "latency_ms": {"p50": 1.0, "p95": 2.0}}
    try:
        print_report(report)
    except KeyError:
        return
    raise AssertionError("a report with no p50 printed a number instead of failing")


if __name__ == "__main__":
    raise SystemExit(run_tests(dict(globals())))
