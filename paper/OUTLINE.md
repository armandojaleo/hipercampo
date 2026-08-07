# Paper outline — Hipercampo

Working container for a preprint / workshop paper. This is the **evidence phase** made
into a document: it says what is *already demonstrated* vs *pending*, so the writing and
the proving are the same work. House rule applies: measure before believing; state limits.

## Working title
*Hipercampo: auditable, local-first cognitive memory for persistent LLM agents built on
hypervectors.*

## Abstract (sketch)
LLM-agent memory is usually "chunk → embed → top-k": it measures similarity, not
relevance or importance, and it never forgets. Hipercampo is a CPU-only, local-first
memory built on **vector-symbolic architectures (VSA)** rather than dense embeddings,
integrating four ideas into a cycle — surprise-gated writing, sleep consolidation, active
forgetting, compositional role queries — over a **navigable small-world graph** that
recalls sublinearly (≈1% of nodes visited at 100k). It separates *what it remembers* from
*what it suspects* (dream hypotheses do not contaminate the graph until confirmed) and is
**observable/auditable** end-to-end (why a memory exists, where it came from, what it
replaced, what it is forgetting). We report reproducible benchmarks and honest limits.

## Contributions
1. VSA memory for agents, CPU-only, no embeddings required; typo/morphology for free.
2. Navigable small-world index with hierarchical VSA landmarks: **sublinear recall at
   100k** (P@5 1.000, p95 ~6.9 ms, ~1.09% visited), safe full-scan fallback.
3. Cognitive cycle: surprise-gated admission, sleep consolidation, active forgetting,
   compositional temporal facts (role-records with validity windows).
4. **Epistemic separation**: dream/bridge hypotheses are typed/staged and do not
   propagate until confirmed.
5. **Auditability/observability** as a first-class property (the VS Code viewer).

## Sections
1. Introduction — the landfill-with-a-search-box problem; contributions.
2. Related work — Mem0, MemGPT/Letta, Zep/Graphiti, RAG, vector DBs; VSA/HDC (Kanerva,
   Plate); hippocampal consolidation/forgetting.
3. System — encoding (10k-bit hypervectors, bind/bundle/permute), surprise gate,
   navigable graph, sleep, forgetting, role-records, dream/bridges, observability.
4. Evaluation — see the evidence table below.
5. Reproducibility — open source, CI (Win/mac/Linux × 3.11–3.13), PyPI, `scripts/*`.
6. Limitations — lexical encoding ceiling on conceptual synonyms (optional semantic hook);
   not yet validated at 1M; longitudinal and real-use A/B pending.
7. Conclusion.

## Evidence: done vs pending
| Claim | Status | Source |
| --- | --- | --- |
| Sublinear navigable recall at 100k (P@5 1.000, ~1.09% visited) | ✅ done | `scripts/nav_scale.py` |
| Navigate == scan fidelity on a real corpus (655 Python docs) | ✅ done | `scripts/nav_real.py` (CI gate) |
| Ablations isolate surprise/confidence/propagation/consolidation | ✅ done | `scripts/ablations.py` (CI gate) |
| Honest false-recall at scale (0.17 lexical / 0.10 semantic at N=500) | ✅ done | `scripts/calibrate.py`, README |
| Baselines: beats BM25 (typos), competitive with embeddings (MRR) | ✅ done | `scripts/baselines.py` |
| **LongMemEval full (500 instances) + head-to-head vs Mem0/Letta/Zep/RAG/reranker** | 🟡 pending | adapter ready (`scripts/context_efficiency.py --longmemeval`) |
| **Longitudinal experiment (100k–1M events / simulated months)** | ⚪ pending | design generator + metrics first |
| **Real-use A/B (~3 months, agent with vs without hipercampo)** | ⚪ pending | dogfooding |

## Longitudinal experiment — metrics to define first (measure before believing)
Events: preference changes, contradictions, expiring facts, repetitive noise, exceptional
events, resurfacing. Metrics: *useful memory / MB*, *useful memory / token*, false recall,
contradiction rate, temporal correctness, forgetting quality, resurfacing quality.

## Venue plan
- **arXiv preprint** now, on the ✅ rows + reproducibility.
- **Workshop** (memory/agents) once the 🟡/⚪ rows land.

## Attribution
Framing sharpened by an external review (ChatGPT, Aug 2026); see ROADMAP "evidence phase".
