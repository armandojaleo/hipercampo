"""
Phase 2 — does hipercampo improve on standard methods? Run:
    python scripts/baselines.py            # BM25 vs lexical hipercampo + ablations
    python scripts/baselines.py --semantic # add embedding cosine and semantic hipercampo

Compare several retrieval methods on the SAME stress-test corpus:
  - BM25            (classic exact lexical method, dependency-free, implemented here)
  - embeddings+cos  (when sentence-transformers is present): strong semantic baseline
  - hipercampo      (lexical VSA, default)
  - hipercampo+sem  (with semantic hook)
  - hipercampo ablations (without propagation or character trigrams)

Metrics: MRR by category (keyword/typo/synonym) plus FALSE RETRIEVAL rate on
negative queries, measuring the ability to ABSTAIN that BM25/cosine lack.
"""

import math
import re
import sys
from collections import Counter
from pathlib import Path


# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.stress import CASES, DISTRACTORS         # noqa: E402
from hipercampo.cycle.memory import Hipercampo               # noqa: E402

_word = re.compile(r"\w+", re.UNICODE)


def tok(s):
    return _word.findall(s.lower())


# NEGATIVE queries should return nothing; they measure abstention.
NEGATIVE_QUERIES = [
    "recetas de cocina tailandesa con leche de coco",
    "resultados de la liga de baloncesto del domingo",
    "cómo plantar tomates en un huerto urbano",
    "historia de la música barroca europea",
    "precio del billete de tren a Sevilla",
]


# --- Minimal dependency-free BM25 -------------------------------------------
class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tok(d) for d in docs]
        self.k1, self.b = k1, b
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(self.N, 1)
        df = Counter()
        for d in self.docs:
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log((self.N - n + 0.5) / (n + 0.5) + 1) for t, n in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, query):
        q = tok(query)
        out = []
        for i, d in enumerate(self.docs):
            s = 0.0
            dl = len(d)
            for t in q:
                if t not in self.idf:
                    continue
                f = self.tf[i][t]
                s += self.idf[t] * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


# --- Evaluation utilities ----------------------------------------------------
def mrr_hit1(rank_fn, cases, category, facts):
    """Evaluate rank_fn(query) and return (MRR, hit1) over ordered fact indexes."""
    rr = hit1 = 0.0
    for fact, questions in cases:
        correct_index = facts.index(fact)
        ranking = rank_fn(questions[category])
        pos = ranking.index(correct_index) if correct_index in ranking else None
        if pos == 0:
            hit1 += 1
        rr += 1.0 / (pos + 1) if pos is not None else 0.0
    n = len(cases)
    return rr / n, hit1 / n


def false_retrieval(returns_anything_fn):
    """Fraction of NEGATIVE queries for which the method returns any
    result (ideally 0, meaning it knows when to abstain)."""
    return (sum(1 for query in NEGATIVE_QUERIES if returns_anything_fn(query))
            / len(NEGATIVE_QUERIES))


def run(semantic=False):
    facts = [h for h, _ in CASES] + DISTRACTORS
    cats = ("keyword", "typo", "synonym")

    methods = {}   # name -> (rank_fn, returns_anything_fn)

    # BM25 ---------------------------------------------------------------
    bm = BM25(facts)
    def bm_rank(q):
        sc = bm.scores(q)
        return sorted(range(len(facts)), key=lambda i: sc[i], reverse=True)
    def bm_hit(q):
        sc = bm.scores(q)
        return max(sc) > 0          # BM25 returns something when terms overlap.
    methods["BM25"] = (bm_rank, bm_hit)

    # embeddings + cosine (optional) ------------------------------------
    if semantic:
        try:
            from sentence_transformers import SentenceTransformer
            model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            E = model.encode(facts, normalize_embeddings=True)
            def cos_rank(q):
                v = model.encode(q, normalize_embeddings=True)
                sc = E @ v
                return sorted(range(len(facts)), key=lambda i: sc[i], reverse=True)
            def cos_hit(q):
                v = model.encode(q, normalize_embeddings=True)
                return float((E @ v).max()) > 0.35   # Typical cosine threshold.
            methods["embeddings+cos"] = (cos_rank, cos_hit)
        except Exception as e:
            print(f"(embeddings unavailable: {e})")

    # hipercampo (several configurations) --------------------------------
    def make_hc(ns, hops=1, semantic_hook=False):
        from hipercampo.core import encoder
        encoder.set_semantic_hook(None)
        if semantic_hook:
            encoder.enable_semantic()
        DB = f"data/_bl_{ns}.db"
        for s in ("", "-wal", "-shm"):
            Path(DB + s).unlink(missing_ok=True)
        hc = Hipercampo(DB, namespace=ns)
        for f in facts:
            hc.remember(f, 0.5)
        id_by_fact = {r["text"]: r["id"] for r in hc.store.all(only_active=False)}
        order_ids = [id_by_fact.get(f) for f in facts]

        def rank(q):
            hits = hc.recall(q, k=len(facts), hops=hops, include_history=True)
            got = [h["id"] for h in hits]
            ranked = [order_ids.index(i) for i in got if i in order_ids]
            remainder = [j for j in range(len(facts)) if j not in ranked]
            return ranked + remainder
        def hit(q):
            return len(hc.recall(q, k=3, hops=hops)) > 0
        return hc, rank, hit

    hc1, r1, h1 = make_hc("full")
    methods["hipercampo"] = (r1, h1)
    hc2, r2, h2 = make_hc("nohop", hops=0)
    methods["hc (no propagation)"] = (r2, h2)
    if semantic:
        hc3, r3, h3 = make_hc("sem", semantic_hook=True)
        methods["hipercampo+sem"] = (r3, h3)

    # Report -------------------------------------------------------------
    print(f"\nCorpus: {len(facts)} facts | negative queries: {len(NEGATIVE_QUERIES)}\n")
    header = (
        f"{'method':22}" + "".join(f"{c:>10}" for c in cats)
        + f"{'overall':>9}{'falseRet':>10}"
    )
    print(header); print("-" * len(header))
    for name, (rank_fn, hit_fn) in methods.items():
        mrrs = [mrr_hit1(rank_fn, CASES, c, facts)[0] for c in cats]
        overall = sum(mrrs) / len(mrrs)
        fr = false_retrieval(hit_fn)
        row = f"{name:22}" + "".join(f"{m:>10.3f}" for m in mrrs) + f"{overall:>9.3f}{fr:>10.2f}"
        print(row)
    print("\n(MRR: higher is better. falseRet: fraction of unrelated queries that"
          " return something; lower is better.)")


if __name__ == "__main__":
    run(semantic="--semantic" in sys.argv)
