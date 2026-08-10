"""Context quality per token and a LongMemEval retrieval adapter.

Local mode is offline and blocking::

    python scripts/context_efficiency.py --check

A previously downloaded official dataset can be evaluated without extra dependencies::

    python scripts/context_efficiency.py --longmemeval data/longmemeval_s_cleaned.json

Here LongMemEval measures evidence-session *retrieval*, not an LLM's final answer.
Keeping the layers separate avoids attributing generator quality to the index.
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.support import audit, config  # noqa: E402
from hipercampo.cycle import memory
from hipercampo.support.budget import is_estimate, estimate_tokens, method  # noqa: E402
from hipercampo.cycle.memory import Hipercampo  # noqa: E402
from scripts.calibrate import NEGATIVE_QUERIES  # noqa: E402
from scripts.stress import CASES, DISTRACTORS  # noqa: E402

CATEGORIES = ("keyword", "typo", "synonym")
LOCAL_THRESHOLDS = {
    "min_mrr": 0.70,
    "min_abstention": 0.70,
    "min_selective_precision": 0.70,
    "max_payload_p95_tokens": 800,
    "max_latency_p95_ms": 50.0,
}


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    if not ordered:
        return 0.0
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def payload_tokens(hits: list[dict]) -> int:
    """Return the full result cost crossing MCP, including metadata."""
    return estimate_tokens(json.dumps(hits, ensure_ascii=False, separators=(",", ":")))


def _seed_local() -> Hipercampo:
    hc = Hipercampo(":memory:", namespace="context-benchmark")
    for fact, _ in CASES:
        hc.remember(fact, 0.5, 0.95)
    for distractor in DISTRACTORS:
        hc.remember(distractor, 0.5, 0.10)
    return hc


def _measure_query(hc: Hipercampo, question: str, k: int = 5) -> tuple[list[dict], float, int]:
    started = time.perf_counter()
    hits = hc.recall(question, k=k)
    latency_ms = (time.perf_counter() - started) * 1000
    return hits, latency_ms, payload_tokens(hits)


def run_local() -> dict:
    previous_audit = audit._ENABLED
    previous_gate = memory.GATE_ENABLED
    previous_autosleep = memory.AUTOSLEEP_EVERY
    previous_paused = config.paused
    audit._ENABLED = False
    memory.GATE_ENABLED = True
    memory.AUTOSLEEP_EVERY = 0
    try:
        hc = _seed_local()
        config.paused = lambda: True  # Measure reads without reinforcement between queries.
        reciprocal_rank = 0.0
        hit1 = 0
        answered_positive = 0
        latencies: list[float] = []
        tokens: list[float] = []
        answered_tokens: list[float] = []
        for fact, questions in CASES:
            for category in CATEGORIES:
                hits, latency, cost = _measure_query(hc, questions[category])
                latencies.append(latency)
                tokens.append(float(cost))
                if hits:
                    answered_tokens.append(float(cost))
                    answered_positive += 1
                position = next(
                    (i for i, hit in enumerate(hits) if fact in hit["text"]), None
                )
                if position == 0:
                    hit1 += 1
                if position is not None:
                    reciprocal_rank += 1.0 / (position + 1)

        false_answers = 0
        for question in NEGATIVE_QUERIES:
            hits, latency, cost = _measure_query(hc, question)
            latencies.append(latency)
            tokens.append(float(cost))
            false_answers += bool(hits)
            if hits:
                answered_tokens.append(float(cost))
        hc.close()

        positive_count = len(CASES) * len(CATEGORIES)
        negative_count = len(NEGATIVE_QUERIES)
        answered = answered_positive + false_answers
        return {
            "dataset": "local-stress",
            "positive_queries": positive_count,
            "negative_queries": negative_count,
            "hit_at_1": hit1 / positive_count,
            "mrr": reciprocal_rank / positive_count,
            "positive_coverage": answered_positive / positive_count,
            "abstention_accuracy": 1.0 - false_answers / negative_count,
            "selective_precision": hit1 / answered if answered else 1.0,
            "payload_tokens": {
                "mean": statistics.mean(tokens),
                "p50": statistics.median(tokens),
                "p95": percentile(tokens, 0.95),
                "total": sum(tokens),
                "estimated": is_estimate(),
                "method": method(),
            },
            "answered_payload_tokens": {
                "mean": statistics.mean(answered_tokens) if answered_tokens else 0.0,
                "p50": statistics.median(answered_tokens) if answered_tokens else 0.0,
                "p95": percentile(answered_tokens, 0.95),
            },
            "latency_ms": {
                "p50": statistics.median(latencies),
                "p95": percentile(latencies, 0.95),
            },
        }
    finally:
        audit._ENABLED = previous_audit
        memory.GATE_ENABLED = previous_gate
        memory.AUTOSLEEP_EVERY = previous_autosleep
        config.paused = previous_paused


def evaluate_local(report: dict, thresholds: dict | None = None) -> list[str]:
    limits = {**LOCAL_THRESHOLDS, **(thresholds or {})}
    checks = (
        ("mrr", report["mrr"], limits["min_mrr"], ">="),
        ("abstention_accuracy", report["abstention_accuracy"],
         limits["min_abstention"], ">="),
        ("selective_precision", report["selective_precision"],
         limits["min_selective_precision"], ">="),
        ("payload_p95_tokens", report["payload_tokens"]["p95"],
         limits["max_payload_p95_tokens"], "<="),
        ("latency_p95_ms", report["latency_ms"]["p95"],
         limits["max_latency_p95_ms"], "<="),
    )
    return [
        f"{name}: {value:.3f} must be {operator} {limit:.3f}"
        for name, value, limit, operator in checks
        if (operator == ">=" and value < limit) or (operator == "<=" and value > limit)
    ]


def _subsample(data: list[dict], limit: int) -> list[dict]:
    """A subset that keeps the mix of question types, NEVER the first N.

    `data[:limit]` looks like an innocent way to run a cheap subset, and it is a
    trap here: LongMemEval ships grouped by question_type, so the first 10
    instances are ten `single-session-user` questions and not one abstention
    case. Measured that way the adapter reported a flawless recall@5 = 1.0 with
    `abstention=None` — a perfect score for the easiest sixth of the benchmark,
    presented as if it were the benchmark.

    So the subset is stratified: each type contributes in proportion, and every
    type present in the corpus survives if the budget allows it. Deterministic,
    no seed, so two runs of the same size are comparable.
    """
    if limit >= len(data):
        return list(data)
    # Stratify by type AND by abstention. Grouping on question_type alone is not
    # enough: the `_abs` instances sit at the END of each type's block, so taking
    # the head of every bucket still selected zero of them at n=60 — the same
    # bias one level down, and it silences the abstention metric entirely.
    groups: dict[str, list[dict]] = {}
    for instance in data:
        kind = str(instance.get("question_type", "unknown"))
        abstains = str(instance.get("question_id", "")).endswith("_abs")
        groups.setdefault(f"{kind}{'/abs' if abstains else ''}", []).append(instance)
    # Proportional (largest remainder), with a floor of one per bucket. Plain
    # round-robin was the first attempt and it overshot in the other direction:
    # equal weight per bucket turned 6% abstention questions into 42% of the
    # sample. Proportional keeps the corpus mix; the floor keeps a small category
    # from being rounded out of existence.
    order = sorted(groups)
    total = len(data)
    floor_each = 1 if limit >= len(order) else 0
    quotas: dict[str, int] = {}
    remainders: list[tuple[float, str]] = []
    for name in order:
        exact = limit * len(groups[name]) / total
        quotas[name] = max(floor_each, min(int(exact), len(groups[name])))
        remainders.append((exact - int(exact), name))
    # Hand out (or claw back) the slots left over by the flooring above.
    spare = limit - sum(quotas.values())
    for _, name in sorted(remainders, reverse=True):
        if spare == 0:
            break
        if spare > 0 and quotas[name] < len(groups[name]):
            quotas[name] += 1
            spare -= 1
        elif spare < 0 and quotas[name] > floor_each:
            quotas[name] -= 1
            spare += 1
    selected: list[dict] = []
    for name in order:
        selected.extend(groups[name][:quotas[name]])
    return selected[:limit]


def load_longmemeval(path: str | Path, limit: int | None = None) -> list[dict]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("LongMemEval must be a JSON list of instances")
    required = {
        "question_id", "question", "haystack_session_ids",
        "haystack_sessions", "answer_session_ids",
    }
    selected = _subsample(data, limit) if limit is not None else data
    for index, instance in enumerate(selected):
        if not isinstance(instance, dict) or not required <= set(instance):
            missing = required - set(instance) if isinstance(instance, dict) else required
            raise ValueError(f"incomplete LongMemEval instance {index}: {sorted(missing)}")
        if len(instance["haystack_session_ids"]) != len(instance["haystack_sessions"]):
            raise ValueError(f"LongMemEval instance {index}: IDs and sessions do not match")
    return selected


def _session_text(session: list[dict]) -> str:
    return "\n".join(
        f"{turn.get('role', 'unknown')}: {turn.get('content', '')}"
        for turn in session
    )


def _map_session(hc: Hipercampo, result: dict, session_id, mapping: dict[int, object]) -> None:
    source_id = result.get("id") or result.get("reinforced_id")
    if not source_id:
        return
    mapping[int(source_id)] = session_id
    rows = hc.store.db.execute(
        "SELECT src,dst FROM links WHERE namespace=? AND type='atom' "
        "AND (src=? OR dst=?)", (hc.store.namespace, source_id, source_id),
    )
    for src, dst in rows:
        mapping[int(dst if src == source_id else src)] = session_id


def run_longmemeval(path: str | Path, limit: int | None = None,
                    k: int = 5) -> dict:
    instances = load_longmemeval(path, limit)
    # Progress on stderr, so stdout stays a clean report. This run takes HOURS —
    # about 50 sessions and half a megabyte of text are ingested per instance —
    # and it used to print nothing until the end. A three-hour job with no signal
    # cannot be told apart from a hung one: the first attempt was left running
    # blind, and "how far along is it" had no answer other than guessing from CPU
    # time. Anything this slow has to say where it is.
    started = time.perf_counter()

    def _progress(done: int) -> None:
        elapsed = time.perf_counter() - started
        rate = elapsed / done
        # ASCII only. The first version separated the fields with "·" and the
        # Windows console printed "Â·": stderr there is not UTF-8 unless someone
        # sets PYTHONIOENCODING, and progress output is exactly the thing nobody
        # sets it for. A status line has no business needing an encoding.
        print(f"  [{done:>4}/{len(instances)}] {elapsed / 60:6.1f} min elapsed | "
              f"{rate:5.1f} s/instance | ~{rate * (len(instances) - done) / 60:6.1f} min left",
              file=sys.stderr, flush=True)

    recalls = []
    abstentions = []
    latencies = []
    tokens = []
    answered_tokens = []
    previous_audit = audit._ENABLED
    previous_autosleep = memory.AUTOSLEEP_EVERY
    previous_paused = config.paused
    audit._ENABLED = False
    memory.AUTOSLEEP_EVERY = 0
    try:
        for index, instance in enumerate(instances):
            hc = Hipercampo(":memory:", namespace=f"longmemeval-{index}")
            memory_to_session: dict[int, object] = {}
            for session_id, session in zip(
                    instance["haystack_session_ids"],
                    instance["haystack_sessions"], strict=True):
                result = hc.remember(_session_text(session), 0.5, 0.7)
                _map_session(hc, result, session_id, memory_to_session)
            config.paused = lambda: True
            hits, latency, cost = _measure_query(hc, instance["question"], k=min(100, k * 4))
            ranked_sessions = list(dict.fromkeys(
                memory_to_session[hit["id"]]
                for hit in hits if hit["id"] in memory_to_session
            ))[:k]
            is_abstention = str(instance["question_id"]).endswith("_abs")
            if is_abstention:
                abstentions.append(not ranked_sessions)
            else:
                expected = set(instance["answer_session_ids"])
                recalls.append(bool(expected & set(ranked_sessions)))
            latencies.append(latency)
            tokens.append(float(cost))
            if hits:
                answered_tokens.append(float(cost))
            hc.close()
            config.paused = previous_paused
            _progress(index + 1)
        return {
            "dataset": "LongMemEval",
            "instances": len(instances),
            "retrieval_recall_at_k": statistics.mean(recalls) if recalls else None,
            "abstention_accuracy": statistics.mean(abstentions) if abstentions else None,
            "k": k,
            "payload_tokens": {
                "mean": statistics.mean(tokens) if tokens else 0.0,
                # p50 was missing while the report asked for it with
                # `.get("p50", 0)`, so every LongMemEval run printed a confident
                # "p50=0 tokens" that was the default, not a measurement.
                "p50": statistics.median(tokens) if tokens else 0.0,
                "p95": percentile(tokens, 0.95),
                "estimated": is_estimate(),
                "method": method(),
            },
            "answered_payload_tokens": {
                "mean": statistics.mean(answered_tokens) if answered_tokens else 0.0,
                "p50": statistics.median(answered_tokens) if answered_tokens else 0.0,
                "p95": percentile(answered_tokens, 0.95),
            },
            "latency_ms": {
                "p50": statistics.median(latencies) if latencies else 0.0,
                "p95": percentile(latencies, 0.95),
            },
        }
    finally:
        audit._ENABLED = previous_audit
        memory.AUTOSLEEP_EVERY = previous_autosleep
        config.paused = previous_paused


def print_report(report: dict) -> None:
    print(f"dataset: {report['dataset']}")
    if report["dataset"] == "local-stress":
        print(f"hit@1={report['hit_at_1']:.3f} · MRR={report['mrr']:.3f} · "
              f"abstention={report['abstention_accuracy']:.3f} · "
              f"selective precision={report['selective_precision']:.3f}")
    else:
        print(f"recall@{report['k']}={report['retrieval_recall_at_k']} · "
              f"abstention={report['abstention_accuracy']}")
    # No `.get` default here: a missing key must explode, not print a plausible
    # zero. That is how "p50=0 tokens" survived unnoticed in every run.
    print(f"context: p50={report['payload_tokens']['p50']:.0f} "
          f"p95={report['payload_tokens']['p95']:.0f} tokens · "
          f"latency p50={report['latency_ms']['p50']:.2f}ms "
          f"p95={report['latency_ms']['p95']:.2f}ms")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--longmemeval", type=Path)
    parser.add_argument("--limit", type=int)
    parser.add_argument("-k", type=int, default=5)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be greater than zero")
    if not 1 <= args.k <= 25:
        parser.error("-k must be between 1 and 25")
    report = (
        run_longmemeval(args.longmemeval, args.limit, args.k)
        if args.longmemeval else run_local()
    )
    failures = evaluate_local(report) if args.check and not args.longmemeval else []
    if args.json:
        print(json.dumps({**report, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        print_report(report)
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
