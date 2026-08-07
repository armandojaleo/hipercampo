# Hipercampo: auditable, local-first cognitive memory for persistent LLM agents

*Working draft. Numbers are reproducible from the cited scripts; pending items are marked.
House rule: measure before believing, and state the limits.*

## Abstract
Most memory for LLM agents is "chunk → embed → top-k": it ranks by similarity, ignores
importance and recency, and never forgets. We present **Hipercampo**, a CPU-only,
local-first memory built on **vector-symbolic architectures (VSA)** instead of dense
embeddings. Four ideas run as a cycle — *surprise-gated writing, sleep consolidation,
active forgetting, and compositional role queries* — over a **navigable small-world
graph** that recalls sublinearly (≈1% of nodes visited at 100k memories). Hipercampo
separates *what it remembers* from *what it suspects* (dream-generated hypotheses do not
enter the graph until confirmed) and is **auditable** end to end. On a longitudinal
simulation of months of agent memory, temporal validity eliminates stale answers
(contradiction rate 0.00 vs 0.71 for a store-everything baseline) while active forgetting
keeps the working set lean and still resurfaces forgotten memories on cue. We release the
code, benchmarks, and honest limits.

## 1. Introduction
An agent that works for months needs a memory that does more than search. It must know
what is *currently* true versus what *was* true, drop noise without losing rare signal,
and let a human audit *why* it remembers something. Vector databases answer "what is
similar?", not "what is relevant, current, and trustworthy?". Hipercampo is an MCP server
that gives agents a hippocampus-inspired memory addressing these needs on commodity CPUs,
with no embeddings required. **Contributions:** (1) a VSA memory for agents; (2) a
navigable small-world index with hierarchical VSA landmarks, sublinear at 100k; (3) a
cognitive cycle (surprise gate, consolidation, forgetting, temporal role-records); (4)
epistemic separation of confirmed knowledge from hypotheses; (5) auditability as a
first-class property.

## 2. Related work
Agent-memory systems (Mem0, MemGPT/Letta, Zep/Graphiti), retrieval-augmented generation,
and vector databases; vector-symbolic / hyperdimensional computing (Kanerva's sparse
distributed memory, Plate's holographic reduced representations); hippocampal models of
consolidation and forgetting. *(To expand with a head-to-head comparison — Section 4.4.)*

## 3. System
Text is encoded into 10,000-bit hypervectors (bind/bundle/permute). A **surprise gate**
admits only observations that are novel enough relative to a persistent, per-namespace
model. Recall **navigates** a small-world graph (beam search from VSA landmarks) rather
than scanning, with a safe full-scan fallback. **Sleep** consolidates similar episodes;
**active forgetting** makes low-retention memories dormant (not deleted) so they can
resurface. **Role-records** encode `subject⊗predicate⊗object⊗time⊗source` with temporal
validity: a new fact closes the previous truth (history, not overwrite). **Dream** proposes
bridges between distant memories; these are typed and staged and do **not** propagate until
confirmed. A read-only VS Code viewer exposes all of this (graph, timeline, facts, ideas,
token cost, decisions), making the memory observable.

## 4. Evaluation

### 4.1 Navigable recall at scale (`scripts/nav_scale.py`, `scripts/nav_real.py`)
On a reproducible structured benchmark at **100,000 memories**: group precision@5 = 1.000,
p50 6.07 ms, p95 6.94 ms, **1.094%** of nodes visited; resident index 141.5 MB, cold build
7.46 s, warm reuse 0.073 ms. On a **real corpus** (Python stdlib docstrings), navigate-vs-
scan fidelity is 1.000 (navigation returns the same top-5 as a full scan), a CI gate. The
lexical group precision (~0.50) is bounded by the *encoding*, not by navigation — see 4.5.

### 4.2 Ablations (`scripts/ablations.py`, CI-gated)
Surprise stores 46/100 routine observations while retaining the rare anomaly; confidence
raises MRR 0.783→0.820; propagation is neutral (0.820→0.820, so no false credit);
consolidation cuts active nodes 20→11 while raising content MRR 0.820→0.860. CI fails if
these relationships invert.

### 4.3 Longitudinal dynamics (`scripts/longitudinal.py`)
We simulate months of agent memory with a controllable clock: entities whose attribute
changes over time (preference changes, contradictions, expiring facts), routine noise, rare
high-value events, and planted memories that are cued again later. We compare Hipercampo
against a naive "store-everything + top-k recall" baseline against ground truth. At a modest
scale (1,844 events, 120 entities, 6 simulated months, seed 1):

| metric (what it measures) | Hipercampo | naive |
| --- | ---: | ---: |
| contradiction rate — answering a truth that has been superseded | **0.000** | 0.708 |
| current-value correctness — knows what is true *now* | **1.000** | 0.292 |
| temporal correctness — what was true at a past time *t* | **0.733** | n/a |
| noise forgotten / valuable kept | 0.844 / 1.000 | 0.000 / 1.000 |
| resurfacing — a forgotten memory returns on its cue (`muse`) | **1.000** | n/a |
| awake ratio — fraction of memory kept lean (signal, not clutter) | 0.50 | 1.00 |
| total on-disk footprint | ~41 MB | ~81 MB |

Temporal validity **eliminates contradictions** (0.00 vs 0.71): a vector store that keeps
every version cannot tell the current value from a stale one. Active forgetting sheds most
noise while protecting 100% of high-value memories, and forgotten memories still resurface
on a strong cue — forgetting keeps the set lean without losing the ability to recover.

*(A larger run — hundreds of entities, thousands of events, 12 months — is pending to show
the metrics hold with more history; see the repo for the current number.)*

### 4.4 Head-to-head on a standard benchmark — PENDING
A LongMemEval adapter exists and separates evidence-session recall from LLM answer quality
(`scripts/context_efficiency.py --longmemeval`). Publishing the full 500 official instances
with comparisons to Mem0, Letta/MemGPT, Zep/Graphiti, RAG, and embeddings+reranker is the
main open item.

### 4.5 Limits, stated plainly
Pure-lexical encoding nails keyword and typo queries (hit@1 = 1.000 via character
trigrams) but conceptual **synonyms** are its ceiling (~0.20 lexical); an optional semantic
hook recovers them (0.75) at the cost of a model download — the core stays embedding-free
by design. False-recall on fully-novel queries is not a differentiator (both abstain);
the interesting near-miss variant is future work. Temporal correctness < 1.0 reflects VSA
cross-entity confusion among historically-valid facts, a real limit. Footprint is reported
as total bytes and awake-ratio; "bytes per useful memory" was dropped as misleading because
forgetting makes memories dormant, not deleted.

## 5. Reproducibility
Open source (MIT core), CI on Windows/macOS/Linux × Python 3.11–3.13 with ruff, mypy,
coverage, and blocking benchmarks; installable from PyPI; every number above regenerates
from a named script.

## 6. Conclusion
Hipercampo is a step toward memory that an agent can rely on over time and a human can
audit: it knows what is current, forgets noise without losing signal, and never confuses a
hypothesis with a fact. The remaining work is evidence at scale — standard-benchmark
comparisons and a longitudinal study — not more mechanism.

---
*Attribution: framing sharpened by an external review (ChatGPT, Aug 2026); see ROADMAP.*
