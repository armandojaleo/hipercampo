"""
Retrieval on a SHARED-JARGON corpus — the regime a real memory actually lives in.

Why this exists. The other benchmarks describe a corpus but never its REGIME, and
that blind spot hid a real defect for a long time. Spreading activation only means
something on a graph that is neither empty nor complete, and no existing benchmark
sat anywhere near saturation — so none of them could show that propagation changed
the top-5 in 1 of 12 real queries and never surfaced anything plain similarity had
already found.

What actually saturates the graph is NARROWNESS, not scale and not "same project".
Measured on real contexts and reproduced here:

    240 memories, one project, many sub-topics   similarity 0.517, density  2.2%
      8 memories, one project, ONE sub-topic     similarity 0.609, density   75%

A broad project memory stays sparse. A cluster about a single subject links almost
every pair, and there the spread reaches everything and adds noise instead of
signal. Both regimes are measured here, because a score means different things in
each.

So this benchmark does two things the others do not:

  1. It measures a shared-jargon corpus in BOTH regimes: broad (one project, many
     sub-topics) and narrow (one sub-topic), the second reproducing saturation.
  2. It REPORTS the regime it measured in (pairwise baseline, link density,
     isolated nodes) alongside the quality numbers, so a score is never read
     without knowing which world it came from.

Expect harsher numbers than `stress.py`. Shared jargon makes distractors genuinely
confusable: keyword retrieval holds up, paraphrase and synonym collapse. That gap
is the honest state of lexical encoding, not a bug in the benchmark.

    python scripts/jargon_bench.py             # report
    python scripts/jargon_bench.py --check     # blocking gate for CI
    python scripts/jargon_bench.py --json
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.core.vsa import similarity_pairs          # noqa: E402
from hipercampo.cycle.memory import Hipercampo            # noqa: E402

DB = "data/_bench_jargon.db"

# One project, one glossary. Every line could plausibly sit in the same memory, and
# they share words on purpose: "recall", "memory", "context", "the index", "the
# gate". That shared surface is the point — it is what makes the corpus hard.
CASES: list[tuple[str, dict[str, str]]] = [
    ("the recall gate abstains when the best score stays under the floor of 0.19",
     {"keyword": "what floor does the recall gate use to abstain?",
      "paraphrase": "below which value does retrieval stay quiet?",
      "synonym": "when does the memory decide to say nothing?"}),
    ("the index visits about 42% of the nodes on a real corpus of 650 memories",
     {"keyword": "what fraction of nodes does the index visit at 650 memories?",
      "paraphrase": "how much of the graph gets walked on the real corpus?",
      "synonym": "how expensive is navigating instead of scanning everything?"}),
    ("atomizing a long note raises hit@1 from 0.15 to 1.00 at 64 facts per text",
     {"keyword": "what does atomizing do to hit@1 at 64 facts per text?",
      "paraphrase": "how much does splitting a long note help retrieval?",
      "synonym": "why is it better to break a big page into small pieces?"}),
    ("the per-turn context budget is 350 tokens and whole memories are dropped, never cut",
     {"keyword": "what is the per-turn context budget in tokens?",
      "paraphrase": "how many tokens may the memory inject each turn?",
      "synonym": "how much of the window is this allowed to take per message?"}),
    ("the surprise model measures bits per token with an incremental bigram backoff",
     {"keyword": "how does the surprise model measure bits per token?",
      "paraphrase": "what does the model use to score how predictable a note is?",
      "synonym": "how is it decided that something was already expected?"}),
    ("consolidation groups episodes above 0.60 similarity and archives the originals",
     {"keyword": "above what similarity does consolidation group episodes?",
      "paraphrase": "when are two episodes merged into one semantic memory?",
      "synonym": "what makes several notes collapse into a single one?"}),
    ("forgetting halves strength every 14 days and protects importance above 0.8",
     {"keyword": "what is the half-life in days used by forgetting?",
      "paraphrase": "how fast does an unused memory fade?",
      "synonym": "how long before something unused stops coming back?"}),
    ("dreaming proposes bridges only in the similarity band between 0.55 and 0.72",
     {"keyword": "what similarity band does dreaming use for bridges?",
      "paraphrase": "between which values are creative links proposed?",
      "synonym": "how close must two ideas be to suggest a connection?"}),
    ("the viewer reads its panels from CLI JSON, so a renamed key breaks them silently",
     {"keyword": "how does the viewer get the data for its panels?",
      "paraphrase": "where do the numbers shown in the extension come from?",
      "synonym": "what feeds the screens of the editor plugin?"}),
    ("per-project opt-in keys on the directory because a user-scope server has one namespace",
     {"keyword": "what does per-project opt-in key on, and why?",
      "paraphrase": "how does it tell one project from another?",
      "synonym": "what identifies each workspace for switching it on?"}),
]

# Same voice, same glossary, no question attached: these are what a real memory is
# mostly made of, and what a query has to be ranked against.
FILLER = [
    "the release workflow publishes to PyPI through trusted publishing with attestations",
    "the CI matrix covers windows, macos and ubuntu because a local app cannot skip them",
    "the decision log writes one line per decision, next to the database",
    "the store keeps hypervectors packed as blobs and compares them with popcount",
    "namespaces isolate one project from another inside the same database file",
    "linked contexts are read only, so inspiration never writes into someone else's memory",
    "the semantic hook is optional and downloads a model the core never needs",
    "roles bind subject, predicate and object so a fact differs from its inverse",
    "the extension ships compiled javascript and no runtime dependencies",
    "backups use the sqlite online API so a copy stays consistent while writing",
    "purging overwrites released pages instead of leaving the text readable",
    "the token bill is read from the log, so counting never causes a write",
]

# Unrelated to the project, in the same register: the memory must stay quiet.
NEGATIVE_QUERIES = [
    "what time does the bakery on the corner open?",
    "how do you get pomegranate stains out of a shirt?",
    "which train goes to the coast on sunday morning?",
    "what did the neighbour's cat do during the storm?",
    "how long should lentils soak before cooking?",
]


# A NARROW corpus: one project AND one sub-topic. This is the regime that actually
# saturates — measured on a real context of 8 memories about a single subject, where
# 75% of all possible pairs were linked. "Same project" alone does not do it: a broad
# project memory spans many sub-topics and stays sparse (a real 240-memory one sits
# at 2.2%). Narrowness saturates, not scale, which is why both are measured here.
NARROW = [
    "the recall gate abstains when the best score stays under the floor of 0.19",
    "the recall gate uses a z-score against the tail to spot noise",
    "the recall gate was calibrated at 0.19 because 0.28 stops finding paraphrases",
    "the recall gate reports its reason, either nothing relevant or nothing above noise",
    "the recall gate floor for the semantic mode is 0.17 instead of 0.19",
    "the recall gate needs at least 5 tail samples before trusting the z-score",
    "the recall gate is the only thing standing between a query and a false answer",
    "the recall gate keeps false retrieval at 0.17 across three measured scales",
]


def _fresh(corpus: str = "broad") -> tuple[Hipercampo, list[str]]:
    for suffix in ("", "-wal", "-shm"):
        Path(DB + suffix).unlink(missing_ok=True)
    hc = Hipercampo(DB, namespace="jargon")
    facts = NARROW if corpus == "narrow" else [f for f, _ in CASES] + FILLER
    for fact in facts:
        hc.remember(fact, 0.6)
    return hc, facts


def regime(hc: Hipercampo, facts: list[str]) -> dict:
    """The world these numbers come from. Reported so a score is never read
    without knowing whether the graph was empty, healthy or saturated."""
    rows = hc.store.all(only_active=False, include_dormant=True, own_only=True)
    n = len(rows)
    matrix = hc.store.matrix(rows)
    left = [i for i in range(n) for j in range(i + 1, n)]
    right = [j for i in range(n) for j in range(i + 1, n)]
    sims = similarity_pairs(matrix, left, right)
    links = [e for e in hc.store.links_dump() if e["type"] == "lexical"]
    neighbours = hc.store.neighbors_all(ids=[r["id"] for r in rows])
    pairs = n * (n - 1) // 2
    return {"memories": n, "stored": len(facts),
            "pair_similarity_median": round(float(np.median(sims)), 3),
            "link_density": round(len(links) / pairs, 3) if pairs else 0.0,
            "isolated": sum(1 for r in rows if not neighbours.get(r["id"]))}


def quality(hc: Hipercampo, facts: list[str], hops: int) -> dict:
    """MRR and hit@1 per category, plus how often it answers an unrelated query."""
    out: dict[str, float] = {}
    for category in ("keyword", "paraphrase", "synonym"):
        rr = hit1 = 0.0
        for fact, questions in CASES:
            hits = hc.recall(questions[category], k=len(facts), hops=hops,
                             include_history=True)
            texts = [h["text"] for h in hits]
            position = texts.index(fact) if fact in texts else None
            if position == 0:
                hit1 += 1
            rr += 1.0 / (position + 1) if position is not None else 0.0
        out[f"mrr_{category}"] = round(rr / len(CASES), 3)
        out[f"hit1_{category}"] = round(hit1 / len(CASES), 3)
    out["mrr_overall"] = round(
        float(np.mean([out[f"mrr_{c}"] for c in ("keyword", "paraphrase", "synonym")])), 3)
    out["false_retrieval"] = round(
        sum(1 for q in NEGATIVE_QUERIES if hc.recall(q, k=3, hops=hops))
        / len(NEGATIVE_QUERIES), 3)
    return out


def run() -> dict:
    hc, facts = _fresh("broad")
    try:
        report = {"regime": regime(hc, facts),
                  "without_propagation": quality(hc, facts, hops=0),
                  "with_propagation": quality(hc, facts, hops=1)}
    finally:
        hc.close()
        for suffix in ("", "-wal", "-shm"):
            Path(DB + suffix).unlink(missing_ok=True)
    # The narrow corpus is measured for its REGIME only: it has no ground-truth
    # questions, and its whole job is to show what one sub-topic does to the graph.
    hc, facts = _fresh("narrow")
    try:
        report["narrow_regime"] = regime(hc, facts)
    finally:
        hc.close()
        for suffix in ("", "-wal", "-shm"):
            Path(DB + suffix).unlink(missing_ok=True)
    return report


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", action="store_true", help="blocking gate for CI")
    args = ap.parse_args()

    report = run()
    if args.json:
        print(json.dumps(report, indent=2))
        return 0

    n = report["narrow_regime"]
    print(f"narrow corpus (one sub-topic): {n['memories']} memories · pair similarity "
          f"median {n['pair_similarity_median']} · link density {n['link_density']}")
    r = report["regime"]
    print(f"broad  corpus (one project) : {r['memories']} memories · pair similarity median "
          f"{r['pair_similarity_median']} · link density {r['link_density']} · "
          f"{r['isolated']} isolated")
    print(f"\n{'':22}{'keyword':>9}{'paraphrase':>12}{'synonym':>9}"
          f"{'overall':>9}{'falseRet':>10}")
    for label, key in (("without propagation", "without_propagation"),
                       ("with propagation", "with_propagation")):
        q = report[key]
        print(f"  {label:<20}{q['mrr_keyword']:>9.3f}{q['mrr_paraphrase']:>12.3f}"
              f"{q['mrr_synonym']:>9.3f}{q['mrr_overall']:>9.3f}"
              f"{q['false_retrieval']:>10.2f}")

    if not args.check:
        return 0

    problems = []
    # The two regimes are the point of this file, so they are asserted first. If the
    # broad corpus ever saturates, or the narrow one stops saturating, the benchmark
    # has lost the contrast it exists to show and its scores mean something else.
    if not 0.01 <= r["link_density"] <= 0.40:
        problems.append(f"broad corpus density {r['link_density']} outside [0.01, 0.40]: "
                        "it no longer represents a sparse project memory")
    if n["link_density"] < 0.50:
        problems.append(f"narrow corpus density {n['link_density']} below 0.50: "
                        "it no longer reproduces a saturated graph, which is the "
                        "regime this benchmark was built to expose")
    if report["without_propagation"]["mrr_keyword"] < 0.80:
        problems.append("keyword MRR below 0.80 on shared jargon")
    if report["without_propagation"]["false_retrieval"] > 0.40:
        problems.append("answers too many unrelated queries")
    for p in problems:
        print(f"::error::{p}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
