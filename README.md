# 🧠 hipercampo

[![CI](https://github.com/armandojaleo/hipercampo/actions/workflows/ci.yml/badge.svg)](https://github.com/armandojaleo/hipercampo/actions/workflows/ci.yml)

🌍 **Español: [README.es.md](README.es.md)** · You are reading the English version.

**A living memory for Claude, built on hypervectors — not embeddings.**

Most LLM memories are the same thing: chunk text, turn it into dense vectors, and
retrieve the closest ones (ANN / top-k). That measures *similarity*, but not
*relevance*, not *importance*, and it never *forgets*. It's a landfill with a search box.

`hipercampo` tries something else. It's an **MCP** server that gives Claude a memory
modeled on the hippocampus, with four ideas integrated into a cycle:

| Idea | What it does | Inspiration |
|------|--------------|-------------|
| **VSA / hypervectors** | Memories as 10,000-bit binary vectors with real algebra (`bind`/`bundle`). It tells *"the dog bites the man"* from its reverse — something a dense embedding blurs. Runs on CPU with popcount, no GPU. | Kanerva (SDM), Plate (HRR) |
| **Surprise-gated writing** | Double veto: it won't store the **redundant** (something similar exists) nor the **predictable** (an internal incremental language model already predicted it, measured in *bits* — compression/MDL). That's where token savings *point* (not yet measured end-to-end). | Hippocampal prediction error; compression-as-intelligence (Hutter) |
| **Consolidation ("sleep")** | An offline process **groups** similar episodes into a semantic memory (structural grouping: fewer nodes, text is joined; with an optional `summarizer` it truly condenses) and archives the originals. | Hippocampus→cortex replay |
| **Active forgetting** | Strength decays with disuse; the weak becomes **dormant** (not deleted, like the human mind) and can later **resurface** via `hc_muse`. High importance protects. | Adaptive forgetting |

> **Engineering honesty.** Surprise combines two signals: *lexical novelty*
> (`1 − max similarity to what's stored`) and real *prediction error*, estimated by
> an in-house incremental language model in bits/token (compression/MDL, no neural
> net, no GPU). The base encoder is **lexical**; for synonyms there's an optional
> semantic hook (below). Everything is swappable without touching the rest.

---

## Install (full guide: [INSTALL.md](INSTALL.md))

**Quick path — from PyPI:**

```bash
pip install hipercampo                # or: pip install "hipercampo[semantic]"
claude mcp add --scope user hipercampo -- python -m hipercampo.server
```

**From source (contributors):**

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo && pip install -e .
python scripts/demo.py                # watch the cycle run
```

Restart Claude Code and you'll have 12 memory tools (`hc_remember`, `hc_recall`,
`hc_muse`, `hc_dream`, `hc_accept_bridge`, `hc_reject_bridge`, `hc_update`, `hc_remember_fact`, `hc_ask_role`,
`hc_consolidate`, `hc_forget`, `hc_stats`). For Docker, Claude Desktop,
`.mcp.json`, verification and troubleshooting → **[INSTALL.md](INSTALL.md)**.

---

## 30-second try (no Claude)

```bash
pip install numpy
python scripts/demo.py
```

You'll see the algebra distinguishing word order and the full cycle
(surprise → recall → sleep → forget) working.

**Real use cases** in [`examples/`](examples/): a personal assistant that remembers
across sessions, a project knowledge base with role queries, and creative
brainstorming where forgotten memories resurface.

---

## Test battery — it does what it says

```bash
python tests/test_vsa.py          # VSA algebra (bind/bundle/order)
python tests/test_memory.py       # the CYCLE: surprise, recall, sleep, forget, persistence
python tests/test_namespaces.py   # context isolation, concurrency, transactions
python tests/test_calibration.py  # adaptive surprise, rollback, empty query, cohesion
python tests/test_properties.py   # invariants over fabricated data (8 rounds)
python scripts/scenarios.py       # narrated story: Claude remembering a user
```

19 suites in total, all green in CI (Python 3.11–3.13). Example invariants checked:
*a duplicate never creates a second memory*, *a needle is retrieved among 25
distractors*, *forgetting never deletes something with importance ≥ 0.8*, *one
context can neither see nor modify another's data*, *a failed transaction leaves no trace*.

## Baseline comparison (Phase 2)

`python scripts/baselines.py [--semantic]` pits hipercampo against the standard
methods on the same corpus (10 facts + 10 confusable distractors). MRR per category
+ **false-recall rate** (unrelated queries that still return something):

| method | keyword | typo | synonym | global | falseRec |
|--------|:---:|:---:|:---:|:---:|:---:|
| BM25 (exact lexical) | 1.00 | 0.77 | 0.33 | 0.70 | 1.00 |
| embeddings + cosine | 0.95 | 0.88 | 0.79 | 0.87 | 0.20 |
| hipercampo (lexical) | 1.00 | 0.91 | 0.51 | 0.81 | **0.20** |
| **hipercampo + semantic** | 1.00 | 0.95 | **0.90** | **0.95** | ~0.20 |

Honest reading:
- **On ranking (MRR), hipercampo+semantic wins** (0.95): it fuses lexical precision
  (keyword/typo) with semantic reach (synonyms). In pure-lexical mode it already
  beats BM25, especially on **typos** thanks to character trigrams.
- **Abstention now works**: a noise-relative (z-score) threshold brings false-recall
  down to **0.20**, on par with embeddings' cosine cutoff (was 1.00).
- The corpus is **small and synthetic**: a signal, not proof at scale. See [ROADMAP.md](ROADMAP.md).

## Scale & latency (measured)

| Memories | full `recall()` (CPU) | Finds the needle? |
|----------|:---:|:---:|
| 2,000 | ~40 ms | yes, rank #1 |
| 10,000 | ~164 ms | yes, rank #1 |

**Vectorized** scan (XOR of the whole matrix + native NumPy 2.0 popcount): ~5× faster
than row-by-row. It's linear (no ANN index): plenty for personal memory (hundreds to
thousands); at ~100k you'd want an index. A known limit, not hidden.

## Tools Claude gains

| Tool | For |
|------|-----|
| `hc_remember(text, importance, confidence)` | Store something (if novel/surprising). `importance` = how much it matters (≥0.8 protects from forgetting); `confidence` = how reliable (weights ranking). |
| `hc_recall(query, k, include_history)` | Retrieve by similarity + spreading activation. Can **abstain** (return `[]`). |
| `hc_muse(query, k)` | **Creative recall**: surfaces *indirect* connections and **dormant** memories that can resurface and tie ideas together. For insight/brainstorming. |
| `hc_dream(max_bridges, dry_run)` | **Creative sleep**: proposes *bridges* between memories sharing a common associate. Hypotheses **don't contaminate memory**: they never propagate until confirmed. |
| `hc_accept_bridge / hc_reject_bridge` | Confirm a dream hypothesis (it becomes a real association) or discard it. |
| `hc_update(target, new_text, memory_id)` | **Update a fact that changed** (safe supersession; the old one stays as history). |
| `hc_consolidate()` | Sleep phase: group episodes into semantic knowledge. |
| `hc_forget(dry_run)` | Active forgetting. `dry_run=True` rehearses without deleting. |
| `hc_remember_fact(subject, predicate, object, …)` | Store a **structured fact** (compositional VSA). If it updates a current fact, the old one isn't deleted — its validity is closed and it becomes **history**. |
| `hc_ask_role(role, …known fields…, days_ago)` | Ask for a field knowing others: *"who bites the man?"* → unbinding. Answers what's **currently true**; `days_ago` asks what was true then. |
| `hc_stats()` | Memory state (includes the DB path). |

Guardrails (env): `HIPERCAMPO_MAX_MEMORIES` caps memories per context (evicts the
lowest-retention, never the protected); `HIPERCAMPO_REDACT_SECRETS=1` masks detected
secrets before storing instead of only warning.

## The four axes of a memory (novelty ≠ importance ≠ reliability ≠ utility)

| Axis | What it measures | Who sets it | Used for |
|------|------------------|-------------|----------|
| **novelty / surprise** | new or predictable? (MDL) | derived | decide whether to **write** |
| **importance** | how much it matters | the caller (`importance`) | **protect** from forgetting |
| **reliability** | how true/credible | the caller (`confidence`) | **ranking** at retrieval |
| **utility** | how much it's actually used | derived (`access_count`) | **protect** from forgetting by use |

Forgetting combines the last three into a transparent *retention*
(`0.4·importance + 0.3·reliability + 0.3·utility`): time only flags candidates, but
**value** decides.

## Compositional memory with roles (the differentiator)

The thing embeddings **can't** do: ask *who did what to whom* and get the right
answer by role. A fact is encoded by binding each value to its ROLE and bundling —
then you recover any field by *unbinding* (`hipercampo/roles.py`):

```python
from hipercampo.roles import ItemMemory, encode_fact, query_role
im = ItemMemory()
fact = encode_fact({"subject": "dog", "predicate": "bites", "object": "man"}, im)
query_role(fact, "subject", im)   # -> [("dog", 0.74)]
query_role(fact, "object",  im)   # -> [("man", 0.76)]
```

`python scripts/roles_demo.py` shows the punchline: *"dog bites man"* and *"man bites
dog"* have the **same values** but the recovered subject/object are **swapped** — a
dense embedding places them at nearly the same point; VSA keeps them distinct.
Measured: correct filler recovered per role with a clear margin (0.74 vs 0.54),
capacity up to 5 roles. Wiring these role-records into the live MCP cycle is next
(see [ROADMAP.md](ROADMAP.md)).

## Contexts, Docker, security

- **Contexts**: namespaces (`HIPERCAMPO_NAMESPACE`) to isolate projects/profiles in
  one DB, or separate files (`HIPERCAMPO_DB`). **Local** isolation, not multi-user
  security — hipercampo is local-first. See [SECURITY.md](SECURITY.md).
- **Docker**: `docker compose build && docker compose run --rm hipercampo`.
- **Security**: retrieved text is **data, not instructions**. Built-in safeguards
  (`hipercampo/safety.py`): `hc_remember` warns on likely **secrets** (plaintext DB),
  `hc_recall` flags memories that look like **injected instructions** as `untrusted`.
  They warn, not block. Details in [SECURITY.md](SECURITY.md).

## Architecture

```
text ──▶ encoder.py ──▶ hypervector (10,000 bits)
                             │
       vsa.py  (bind / bundle / permute / vectorized popcount)
                             │
    memory.py  ── surprise · recall+spreading · sleep · forget · 4 axes
                             │
     store.py  ── SQLite WAL (memories + graph, namespace-isolated, transactional)
                             │
    server.py  ── MCP (stdio) ──▶ Claude
```

## Related work & honest positioning

hipercampo **did not invent** hyperdimensional computing (HDC/VSA dates to the 90s:
Kanerva, Plate), nor is it the first attempt at agent memory (Mem0, Letta, Graphiti,
MemGPT; MnemoCore uses HDC). What's original is **the specific combination**: VSA +
surprise (MDL) + consolidation + forgetting + four axes, exposed as an **MCP** server,
treating memory as a **cycle**. We don't claim to beat embedding-based hybrid memories;
we explore a different paradigm, with its limits measured.

## License & attribution

MIT (see [LICENSE](LICENSE)). Original code; dependencies and ideas credited in
[ATTRIBUTION.md](ATTRIBUTION.md). House rule: **if we use others' work, especially
copyrighted, we say so.**

## Acknowledgments

Built by **Armando Jaleo** with **Claude** (Anthropic), measuring before believing
and telling the truth about the limits. Thanks to Pentti Kanerva and Tony Plate,
whose decades-old ideas are still alive here. And to whoever audits with rigor:
honest criticism made this project better on every pass.

*And yes — congratulations, Spain! 🇪🇸⚽ Some memories deserve `confidence=1.0`.*

> A memory is not a store: it's a cycle that saves, relates, consolidates, and forgets.
> If one day this helps machines remember **with judgment** — and lets the people who
> use them audit it — it will have been worth it. — made with care. 🧠
