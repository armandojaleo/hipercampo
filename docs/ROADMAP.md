# Roadmap to production (local-first)

**Goal: the best local memory for an agent.** Each user hosts hipercampo on their
own machine, with their own memory file. There is no central or multi-user server:
that would add unnecessary cost and infrastructure. Local-first means private by
design, free to operate, and no third-party data to hold in trust.

The following are therefore **deliberately out of scope**: authentication, managed
encryption, shared Postgres, network transport, and multi-user hosting. A SaaS built
on top would be another project; this core stays local and simple.

Status: 🟢 done · 🟡 in progress · ⚪ pending

## Current state — v0.1.0b14 (9 August 2026)

Beta b14 is published on PyPI after green multi-platform CI and benchmarks. It
carries the layered package, the finished English migration, per-project opt-in,
and a round of fixes described in the changelog.

Two of those fixes are worth repeating here, because they say something about the
gates rather than the features:

- **CI passed three commits while running zero tests.** `tests/test_*.py` does not
  descend into subdirectories, and the suite had been grouped into folders. The
  multi-platform matrix — the thing this project relies on most — was reporting
  green having executed nothing. Discovery is now recursive, and finding zero tests
  is an explicit failure.
- **The token bill was reporting clock seconds instead of tokens** (5304 against a
  real 65451). The figure this project uses to argue for itself was wrong by 12x,
  with a green suite throughout, and it surfaced because a human said a number
  looked odd.

The lesson is written into `AGENTS.md`: a regression test only counts once it has
been seen RED against the old code, and the checker needs checking too.

- ✅ **Multi-platform CI:** full suites on Windows, macOS, and Ubuntu with Python
  3.11–3.13.
- ✅ **Quality gates:** Ruff, Mypy, and coverage in CI; benchmarks block regressions.
- ✅ **Working MCP:** compatible dependency, release smoke test, and budget-bounded tools.
- ✅ **Navigable memory:** graph/index navigation with a safe scan fallback;
  `nav=auto` and `max_scan` are exposed over MCP.
- ✅ **Windows reliability:** SQLite closure, migrations, and helper processes covered in CI.
- ✅ **Publishing:** `v0.1.0b13` released through Trusted Publishing with attestations
  and an independent installation smoke test from PyPI.
- 🟡 **Semantic quality:** the synthetic benchmark identifies synonyms as the next
  bottleneck (overall lexical score ~0.742).

### Next stretch

1. ✅ Explainable retrieval (`score_components`) in core/MCP and a visible extension
   tooltip, protected by a contract test.
2. ✅ A persistent, incremental, hierarchical navigable graph isolated by namespace.
   On 100,000 structured memories: group precision@5 = 1.000, p50 = 6.07 ms,
   p95 = 6.94 ms, 1.094% visited, 141.5 MB resident index, and 0.073 ms reuse.
   `scripts/nav_scale.py` reproduces this.

   **Also validated on a REAL corpus** (`scripts/nav_real.py`: fuzzy English stdlib
   docstrings, offline): **navigation-versus-scan fidelity is 1.000**—navigation
   returns exactly the same top five as a scan on real text, not just synthetic data.
   With 12/12 and topology-aware shortcuts it visits **42.6%** at N≈650, down from
   81.3% with the old 48/48 configuration; the gate requires less than 55%. It
   preserves small-world shortcuts on community or disconnected graphs. At 10,000
   memories it keeps precision@5 = 1.000 while visiting 1.751% (p95 ~2.2 ms).
   **Lexical group precision is ~0.50** for both navigation and scanning: navigation
   does not degrade quality; the ceiling comes from lexical encoding and points to
   the synonym bottleneck below.
3. ✅ Multi-agent integration: Claude and Codex share the MCP server and project
   namespace, with safe handshake instructions, configuration, and a tested contract.
4. ✅ Surprise continuity across processes: incremental state is namespace-isolated,
   persistent, bounded, and atomic; a rejected observation is no longer lost on restart.
5. 🟡 The real stdlib corpus is now an automatic gate for fidelity, latency, memory,
   and navigation cost; standard external datasets are still missing.
6. 🟡 Stable extension namespace selection and UX: EN/ES localization, icon,
   manifest, and CI contract are done. **Viewer redesign (v0.9.15):** constellation
   map (cognitive-state color, glow, neighbor hover, focus-only labels, N-hop
   **neighborhood mode**), separate browse/filter and agent-operation modes, a
   divergence-proof simulation tested on the real graph with zero NaNs, list sorting
   and kind filtering, per-recall token cost, and Status/Tokens fixes. **Screenshots**
   and **manual VSIX validation in both languages** remain before calling it stable.

## The next leap: from ADDING to PROVING (evidence phase)

An external review (ChatGPT, August 2026) agrees with the direction and sharpens it.
hipercampo already has **enough cognitive concepts**: VSA, surprise, semantics,
navigable graph, dreaming, forgetting, temporal facts, muse, dream bridges, and
observability. The risk is **not too few ideas, but so many that it becomes hard to
prove which one creates the advantage**. This makes `scripts/ablations.py` one of
the repository's most important files. The next leap is not another feature, but:

> **An agent with hipercampo remembers better over months while using less memory
> and context—demonstrated independently and reproducibly.**

Three demonstrations, ordered by effort and value:

1. 🟡 **Complete LongMemEval, not just the adapter — now blocked on more than access.**
   Run and publish all 500 official instances reproducibly against **Mem0,
   Letta/MemGPT, Zep/Graphiti, classic RAG, and embeddings + reranker**. Separate
   evidence-session recall from LLM answer quality, as the runner already does. Data/
   network access is still one blocker, but no longer the only one: publishing
   against the full set now first needs the abstention collapse below understood —
   without it, the number would ship with the confounder in it.

   **Measured on a stratified 60-instance subset (dense haystacks, ~48 sessions
   each), 2026-08-11: abstention collapses to 0.000 (0/7), against 0.833 on our own
   `stress.py` benchmark.** Recall@5 stays healthy at 0.830 (chance ~0.10), so this
   is not a retrieval failure — it is specific to abstention. Probed at k=1/3/5/20 on
   the same 7 questions: k is always returned exactly, at every level, so it is not
   an artifact of requesting k=20. Working hypothesis, not yet confirmed: the gate
   abstains by comparing similarity against the tail's noise (z-score), and in a
   large, homogeneous corpus there is no tail to stand out against — everything looks
   a little similar, so nothing drops below the threshold. If so, this does not get
   fixed by moving the threshold. None of our other benchmarks can see this because
   they all use small corpora. Reproduce with `python scripts/context_efficiency.py
   --longmemeval data/longmemeval_s_cleaned.json --limit 60` (dataset not in the
   repo, 277 MB, `data/` is gitignored; ~195s CPU per instance).
2. ⚪ **Longitudinal experiment (the definitive one).** Simulate 100k–1M events over
   months: preference changes, contradictions, expiring facts, repetitive noise,
   exceptional events, and resurfacing memories. Metrics: useful memory/MB, useful
   memory/token, false recall, contradiction rate, temporal correctness, forgetting
   quality, and resurfacing quality. Build the **generator and metrics first**, then
   produce the number.
3. ⚪ **Long-running real-world A/B.** Use Claude or Codex with hipercampo on a real
   project for about three months and compare it with the same agent without memory.
   This is the most persuasive and slowest test; ordinary dogfooding starts it.

**Positioning**, once evidence exists: move from *"experimental cognitive memory for
AI agents"* to **"Auditable cognitive memory infrastructure for persistent AI
agents"**—four words: **persistent · local · adaptive · auditable**. Observable
memory—what it remembers, why, where it came from, what it forgot, and what it
associated—is a differentiator a vector database does not answer elegantly and may
matter more than two extra Recall@10 points.

**Discipline:** pause large new cognitive concepts. Converge and **prove** rather
than expand. Product features (visible value, actionable Ideas) belong on branches;
new concepts stay in the backlog until evidence calls for them.

## The road to a “panacea”: honest triage of external criticism

External reviews (July 2026) proposed five leaps. They do not have equal value:

1. **Sublinear index beyond 100k memories — YES.** Linear scanning was a measured
   limit (~164 ms at 10k). The local-first answer need not be generic HNSW: binary
   Hamming vectors can use **multi-index hashing**, splitting the hypervector into
   bands for exact-band prefiltering and exact reranking. It is simple and adds no
   dependency. ⚪ Phase 4.
2. **Native synonyms without embeddings (lexical random indexing) — MEASURED AND
   REJECTED.** A prototype on a real 354k-word corpus produced marginal signal:
   mean synonym cosine 0.095 versus random 0.052, with only **1 of 8** pairs above
   the noise p95. Learning synonyms from co-occurrence requires word2vec-scale data;
   a personal memory does not have it, and even this 350k-word technical corpus did
   not separate them. The honest synonym path is the OPTIONAL semantic hook
   (`[semantic]`), not a partial word2vec reimplementation. Lexical encoding handles
   typos/morphology for free (trigrams, hit@1 = 1.0); a semantic model handles pure
   synonyms.
3. **Learn retention weights (lightweight RL) — PARTLY.** Learn from observed utility,
   already represented by `access_count`; do not use an unexplained network to decide
   what to forget. Transparent, auditable retention is a feature. Use **measured
   tuning**, not a black box.
4. **Dynamic vector sizes — NOT NOW.** The measured five roles are sufficient for
   atomic facts. A whole contract should be split into facts rather than encoded in
   a larger vector. High cost, doubtful benefit.
5. **Multi-tenant cloud / homomorphic encryption — NO in this repository.** This is
   out of scope by design. The honest path would be a funded **spin-off**. The local
   MIT core remains unchanged.

Cross-project memory (read linked, write local) is complete: see Phase 1.

## Phase 1 — Reliability and isolation foundations

- 🟢 **Cross-project memory (read-only linked contexts):** `linked=` /
  `HIPERCAMPO_LINKED` accepts `project1,project2` or `*`. Recall, muse, and dream
  read linked projects and label their origin (`project`); every write, reinforcement,
  forgetting, and consolidation remains local. Unlinked contexts stay invisible.
  Covered by `tests/storage/test_linked.py`.
- 🟢 **Namespace/context isolation:** every operation sees only its context,
  including ID-based reads and writes (`delete`, `touch`, `mark_*`), and links never
  cross contexts. Covered by `tests/storage/test_namespaces.py`.
- 🟢 **Basic concurrency:** SQLite WAL plus `busy_timeout` permits reads during writes
  without corruption.
- 🟢 **Atomic transactions** for compound operations such as update and consolidate;
  failure rolls the whole operation back through `store.transaction()`.
- 🟢 **Core input validation:** non-empty text and maximum length; bounded
  `importance`, `confidence`, `k`, and `hops`; sanitized namespace.
- 🟢 Versioned migrations (`PRAGMA user_version`, seven idempotent, resumable steps
  with a prior backup), covered by `tests/storage/test_migration.py`.
- 🟢 **Physical purge / secure deletion**, distinct from reversible forgetting:
  `hipercampo purge --ids …` / `--older-than DAYS` for secrets, deletion rights, or
  very old dormant data. SQLite overwrites freed content and `VACUUM` reclaims space;
  confirmation is mandatory. `hc_unlearn` also deletes securely. The purge tests
  verify that text is absent from the raw `.db` bytes.

## Phase 1b — Calibrating surprise

- 🟢 **Adaptive threshold:** “predictable” means the lower quantile of recent surprise,
  with an absolute fallback for short histories. A calibration test proves realistic
  sequences can reach the veto.
- 🟢 Learn **after** commit so rollback cannot leave the model ahead of the database;
  reinforce only true redundancy, not a weak match rejected as predictable.
- 🟢 **Per-namespace persistent surprise:** unigram/bigram counts and the adaptive
  300-observation window survive restarts, including seen-but-rejected input. Tokens
  persist as hashes, not literal text; learning and memory share one transaction.
  Migration v7 tests continuity, isolation, rollback, and bounded growth.
- 🟢 Calibrated **abstention** by measuring false retrieval as N grows
  (`scripts/calibrate.py`). `MIN_RECALL_SCORE` was **inert**: changing it affected
  neither MRR nor false recall. The real control, `ANSWER_MIN_SCORE`, sat **below**
  the 5th percentile of unrelated queries and filtered nothing. Recalibration from
  **0.08→0.19** lexical and **0.05→0.17** semantic reduced false recall from
  **1.00→0.17** lexical (stable at N=20/100/500) and to **~0.10** semantic while
  retaining synonym hits. `RECALL_Z` was inert at scale. Length normalization was
  measured and **rejected** because it lost on both benchmarks at matched false
  recall; chunking remains the documented answer.

## Phase 2 — Credibility: prove quality

- 🟢 **Baselines** (`scripts/baselines.py`): BM25 and embedding cosine versus
  hipercampo. Measured result: semantic hipercampo wins overall MRR (0.95 versus
  embedding 0.87); lexical hipercampo already beats BM25 on typos (0.95 versus
  0.77). A misplaced abstention threshold once caused false recall 1.00; calibration
  reduced it to 0.17–0.20, comparable to embeddings.
- 🟢 **Isolated, blocking ablations** (`scripts/ablations.py --check`): surprise
  reduces a predictable stream from 100 to 46 memories while keeping the anomaly;
  confidence raises MRR 0.783→0.820; propagation is neutral here (0.820→0.820), so
  no false improvement is claimed; consolidation cuts active nodes 20→11 and raises
  content MRR 0.820→0.860. CI fails if these relationships reverse or consolidation
  degrades more than 0.02.
- 🟡 **Standard datasets:** the official LongMemEval JSON retrieval adapter is ready
  and tested (`scripts/context_efficiency.py --longmemeval …`), including evidence-
  session recall and abstention. Running and publishing all 500 official instances
  remains; MemoryAgentBench also remains.
- 🟢 **Blocking context efficiency** (`scripts/context_efficiency.py --check`): 30
  positive plus 30 unrelated queries measure MRR, coverage, selective precision,
  abstention, estimated MCP payload, and latency. Lexical state: MRR 0.744,
  abstention 0.833, selective precision 0.786, p95 401 tokens, p95 6.2 ms.

## Phase 3 — Performance at scale

- 🟢 **Vectorized scan:** XOR the whole matrix and use native NumPy 2.0 popcount,
  with a lookup-table fallback. About 5× faster (10k: 224→47 ms); full recall at 2k
  is ~40 ms and at 10k ~164 ms.
- 🟢 **Hierarchical navigable index at 100k:** landmarks per semantic island,
  vectorized VSA selection, and local beam search. On the reproducible structured
  benchmark (30 queries): group precision@5 **1.000**, p50 **6.07 ms**, p95
  **6.94 ms**, **1.094%** visited. A positional VSA matrix, streaming load, and CSR
  adjacency reduced construction from 14.6 to **7.46 s**, peak memory from 558.8 to
  **189.7 MB**, and resident memory to **141.5 MB**; reuse takes 0.073 ms. External
  validation remains open.

## Phase 4 — Local context isolation (NOT a multi-user server)

Authentication, encryption, Postgres, and networking remain out of scope because
each user runs locally. The useful work separates contexts on one machine:

- 🟢 **Complete namespaces:** isolate projects/profiles in one database across all
  operations and links. Implemented and tested.
- 🟢 **Per-project opt-in (b14).** hipercampo starts switched OFF and is turned on per
  project, from `hipercampo enable|disable|projects` or the viewer's banner. In a
  project that never opted in, the hook stays silent and the tools decline with an
  explanation instead of reading or writing.

  The unit is the **directory**, not the namespace, and that was forced rather than
  chosen: a server registered at user scope carries one `HIPERCAMPO_NAMESPACE`, so
  every project without its own `.mcp.json` shares it — the namespace cannot tell two
  projects apart, the path can. An installation that already holds memories keeps
  working untouched until the first `enable`/`disable`, so an upgrade never switches
  someone off in silence.
- ⚪ Client-level hardening against memory-borne injection; see [SECURITY.md](../SECURITY.md).

## Phase 5 — The real VSA differentiator

- 🟢 **Compositional memory with roles** (`hipercampo/cycle/roles.py`):
  `SUBJECT⊗ · PREDICATE⊗ · OBJECT⊗ · TIME⊗ · SOURCE⊗`, queried through unbinding
  (“who bit whom?”). It retrieves the correct role value with a clear margin
  (0.74 versus 0.54), supports up to five roles, and distinguishes a fact from its
  inverse. See `tests/cycle/test_roles.py` and `scripts/roles_demo.py`.
- 🟢 **Role records integrated into the cycle:** `remember_fact` / `ask_role` in the
  core and `hc_remember_fact` / `hc_ask_role` over MCP, persisted in `facts` and
  namespace-isolated. Cleanup item memory rebuilds from stored facts on open, needing
  no extra persistent state. Each fact stores a textual shadow that participates in
  recall/muse/consolidation/forgetting and has **temporal validity**. A new fact with
  the same subject + predicate and a different object CLOSES the previous truth
  without deleting it—history rather than overwrite.
- ✅ **Visible facts:** `hipercampo facts [--json]` and the viewer's **Facts** tab expose
  role records and temporal history.
- ⚪ Consolidation with a **real summary** (LLM summarizer hook already exists),
  conflict detection, provenance, and `valid_from` / `valid_to`.
- ⚪ Typed directed relations: `supports`, `contradicts`, `updates`, `caused_by`.

## Phase 6 — Release and operations

- 🟢 GitHub Actions suites and benchmarks on Python 3.11–3.13.
- ✅ Ruff, Mypy, coverage, webview compilation, and syntax smoke gates in CI.
- ✅ **Explainable retrieval:** `score_components` exposes direct similarity,
  association boost, confidence factor, and superseded penalty.
- 🟢 v0.1.0-alpha published on **PyPI** through Trusted Publishing and attestations.
- 🟡 **Observability.** The decision log is structured and machine-readable
  (`hipercampo log --json`: timestamp, action, message), the token bill is exposed
  with a time series (`hipercampo tokens`), and `hipercampo status` reports database
  health, running servers, and per-context counts. What is missing is *metrics* in
  the operational sense — nothing aggregates over time or alerts. Marked ⚪ until
  b14 even though most of it already existed, which is its own small lesson about
  taking a roadmap's word for the state of things.

## The viewer is where the net does not reach

Not a phase — a measured risk that had no entry here, written down because three
bugs shipped through it in one week.

| | production | test | ratio |
|---|---|---|---|
| Python core | 5728 lines | 5765 | **1.01** |
| Viewer (`viewer.js` + `src/*.ts`) | 1957 lines | 113 | **0.06** |

*(non-blank lines, measured 2026-08-10; re-measure before quoting)*

Sixteen times less test per line than the core, on the surface a user actually
looks at. The bugs were not exotic. All three were the same shape — the CLI emits
JSON in Python, the viewer reads it in JavaScript, and **a renamed key breaks the
panel silently**: no test on either side sees it, the value just renders empty.

- `s.metodo` against an emitted `method` — the "how tokens were counted" note went
  blank after the English migration.
- `PROJECT.enabled` against an emitted `enabled_here` — the opt-in banner would have
  claimed every project was off, forever. Caught before shipping.
- Log rows rendering as `?` — an unescaped newline split entries in two.
- **Pause was global, not per-project (found 2026-08-13).** Pausing recording in one
  project's viewer silently paused every other project sharing the same DB.
  `config.paused()`/`set_paused()` used a single flag file next to the shared
  database with no directory scoping — unlike `enable`/`disable`, which already
  keyed itself by directory for exactly this reason. Compounding it, `extension.ts`
  called `pause`/`resume`/`graph`/`status` without passing the workspace path, the
  same `execFile`-without-`cwd` trap noted below, just not yet closed off for this
  command. Fixed: `paused(path)`/`set_paused(on, path)` now use a per-directory
  registry (`hipercampo.paused_projects`, same pattern as `hipercampo.projects`),
  the CLI takes `--project`/positional `path` on `pause`, `resume`, `graph`, and
  `status`, and the extension passes `projectPath()` explicitly on all four calls.
  Verified with two projects sharing one DB: pausing one no longer touches the other.

What exists now: `tests/contracts/test_viewer_json.py` binds the field names the
viewer reads against what the CLI emits, for all six payloads (`status`, `tokens`,
`projects`, `log`, `graph`, `facts`), and three Playwright end-to-end tests gate
viewer releases.

- 🟢 **The extension host (`src/*.ts`) has a first contract test (2026-08-13),
  `editor/tests/extension.test.js`, wired into `npm test`/CI.** It mocks `vscode`
  and `execFile`, drives the sidebar provider exactly as VS Code would, and asserts
  that `pause`, `resume`, `graph`, `status`, and `enable` all carry the project path
  explicitly — the exact contract whose absence caused the bug above. Confirmed RED
  against the pre-fix `extension.ts` before being merged, per house rule. It covers
  one contract, not the whole file: `Panel`, `chooseDatabase`, `editLinked`, `mutate`,
  `reclassify`, and error paths remain unexercised.

What is still missing:

- ⚪ **Behaviour, not just field names.** The contract tests prove the keys line up;
  they say nothing about whether the panel *renders* correctly. That is the
  Playwright side, and three tests is thin for 1806 lines.
- ⚪ **Most of the extension host is still untested.** The new contract test closes
  the specific path-passing trap; `Panel`/`chooseDatabase`/`editLinked` and the
  remaining `onMessage` branches (`mutate`, `reclassify`, `backup`, `kill-server`,
  `set-budget`, `reindex`) have no coverage yet.

## Phase 7 — Engineering maturity and the path to embedded use

The core works; it now needs production discipline and suitability for Linux SBCs
and robots (Raspberry Pi, Jetson, ROS2). This is reliability, structure, and release
engineering rather than research. Small betas each carry one measurable promise.

- 🟢 **`0.1.0b2` — Core separation.** Only `server.py` imports `mcp` (plus the lazy
  `serve` subcommand). `import hipercampo` does not bring in `mcp`, enforced by
  `test_core_embebible.py`; the public core API is documented in `__init__.py`.
- 🟢 **`0.1.0b3` — CI safety net.** Ruff, Mypy, and coverage became gates. Mypy is
  configured to catch unchecked `None` and incompatible assignments without drowning
  NumPy/JSON code in `--strict` noise. Coverage floors at 78% against a measured 79%.
  The CI matrix previously enumerated tests and omitted four files on Windows/macOS;
  glob discovery now covers all of them.
- 🟢 **`0.1.0b4` — Language and viewer improvements (extension v0.6.0).** Viewer i18n
  follows VS Code's language through a webview dictionary, `package.nls`, and
  `vscode.env.language`. The viewer starts in English on English VS Code. The Ideas
  tab exposes dry-run dream bridges without contaminating memory; Status can open
  the log, identify each MCP server and its database, create backups, and open a new
  GitHub issue.
- 🟢 **`0.1.0b5` — Reliability under stress.** `max_scan=N` bounds recall time/RAM by
  examining only the N liveliest memories (strength and recency), while logging the
  count and whether it was bounded. The naive bound was measured **slower** because
  unindexed `ORDER BY` cost more than a full scan. Adding `idx_vivos` made it real:
  at 10k, bounded p50 ~35 ms versus ~200 ms full (5–6×) and flat with N. Corrupt,
  locked, and full databases already have resilience/failure coverage. b6 exposed
  `max_scan` over MCP so agents and robots can bound CPU/RAM without the Python API.
- 🟢 **`0.1.0b6` — Brain-like navigable graph (FLAGSHIP).** The measured limit was
  scanning itself: at 100k, ~1.8 s and 542 MB. Navigation follows a neighbor graph
  like GPS, recalling through connections rather than examining everything.
  Measurements before integration showed:
  - A neighbor-only graph breaks into islands and is not navigable (recall 0.12).
    Weak long-range shortcuts make it navigable (recall **0.97–1.0**), a Watts–
    Strogatz small world. The same shortcuts create dream ideas: **creativity and
    indexing are the same structure**.
  - **Actually sublinear:** the percentage visited shrinks with N, from 13.9% to
    **3.0%** between 2k and 16k (~log N). Extrapolated to one million memories:
    roughly 1,000 nodes (~0.1%).
  - **Insertion does not scan either:** graph navigation places each memory in about
    293 visits, approximately constant, HNSW-style; graph recall remains 1.0.

  Integration keeps KNN neighbors incrementally, navigates with a beam, exposes
  `visited`/`recall_mode`, retains scan fallback, survives restarts, and never crosses
  namespaces. Retrieval returns results and visit stats in one pass; the resident
  index invalidates on local or external changes. A hierarchical layer identifies
  semantic islands, compares vectorized VSA landmarks, and searches locally from the
  four nearest. At 100k structured memories: group precision@5 **1.000** (formerly
  **0.400** with one entry), p50 **6.07 ms**, p95 **6.94 ms**, **1.094%** visited.
  Streaming, one VSA matrix, and CSR cut cold construction **14.6→7.46 s**, peak
  **558.8→189.7 MB**, resident memory to **141.5 MB**, and reuse to 0.073 ms. The
  trade-off versus the previous CSR version is +0.83 s startup for -15.7 MB resident.
  `scripts/nav_scale.py` reproduces it. Next: batched binary loading and external-
  corpus recall@5 ≥ 0.9 without hiding fallback.
- 🟡 **`0.2.0b1` — Serious extension.** Settings, complete i18n, real-browser release
  tests and UX refined through real use are in place. Marketplace publisher and
  `VSCE_PAT` still require one-time owner-side confirmation before the first tag.
- ⚪ **Real SBC benchmark (League A).** Measure latency, RAM, and power at
  1k/10k/100k memories on Pi/Jetson. Without this, “works for robots” is empty. This
  gates `1.0`.

**Out of scope here:** a C/Rust core for Linux-free microcontrollers (League B).
VSA algebra is popcount + XOR and could fit in a few KB, but that is a spin-off,
recorded rather than added to this repository.

## Ideas (living backlog)

Ideas stay here and evolve. This is a repository, not a promise. A mature idea moves
into a phase together with its measurement.

- ✅ **Facts in the viewer:** `hipercampo facts [--json]` and the extension's **Facts**
  tab already expose structured role facts visually.
- ✅ **Ambient activity footer (2026-08-13).** The viewer's footer shows a short,
  non-intrusive phrase for what the memory is doing right now — "recalling…",
  "saving a memory…", "dreaming…" — sourced from the decision log, never a popup.
  A found dream bridge gets its own phrase and is clickable to jump to Ideas; a
  turn with real token savings gets "saved N tokens off the context…". No
  ambient noise for uninteresting entries (e.g. a `tokens` log line with no
  savings produces nothing). Covered by `editor/tests/e2e/activity.spec.js`,
  confirmed RED before the footer existed.
- ✅ **Supply chain:** `vsce` is pinned exactly in `vsix.yml`, GitHub Actions are pinned
  by SHA, and Playwright gates the webview before `VSCE_PAT` reaches the publish step.
  See [SECURITY.md](../SECURITY.md).
- **Open decision: optional `mcp`** (`[mcp]`) for a one-dependency (`numpy`) core.
  It reduces attack surface but changes server installation.
- **Synonyms:** random indexing was measured ineffective at this scale. The path is
  the optional semantic hook unless a compact, free lexical resource appears.
- **Real-summary consolidation**, typed `supports` / `contradicts` / `updates`
  relations, and external standard datasets such as LongMemEval.

### Long-term technical direction

Large ideas filtered through the house rule—local-first, CPU-conscious, measure
before believing. Each enters a phase only with its measurement:

1. **Atomization — 🟢 DONE.** Addresses the main long-text limit, 1/√T dilution.
   `remember()` splits text into dependency-free atoms and links each to its source.
   A buried fact in 64 ideas improves from **hit@1 0.15 monolithic to 1.00 atomized**;
   end-to-end a short cue retrieves the exact atom. Disable with
   `HIPERCAMPO_NO_ATOMIZE=1`.

   **MULTICHANNEL encoding — MEASURED and NOT justified for text retrieval.** A
   prototype compared content/place/time channels with one bundle, including
   aspect queries: both achieved Recall@1 1.000, even when content mentioned other
   places. Dilution lowers absolute similarity but not ranking, and encoder bigrams
   already distinguish a place field from a loose direction word. Per-channel HVs
   would be a major redesign for zero measured text gain. Multimodal sensors may
   justify it in a robotics spin-off, not this core.
2. **External multilingual benchmarks** (LongMemEval, LoCoMo, MuSiQue, BEIR) to move
   claims beyond the project's own benchmark.
3. **Meta-memory: admission by UTILITY + surprise.** Use explicit features and a
   conservative, auditable online regression/contextual bandit, never a black box.
   Hard constraints for secrets and protected memories remain policy, not learning.
4. **CALIBRATED abstention** using conformal/isotonic calibration on an independent
   set, providing a selective-risk guarantee rather than hand-tuned thresholds.
5. **Provenance-aware consolidation and claim-level contradictions**, never treating
   an LLM summary as automatically true, plus incremental microclustering to remove
   O(N²).
6. **Profile-configurable dimensionality** (fewer bits for edge RAM) and MIH as an
   alternate index for a micro profile.
7. **Refactor around `Protocol` interfaces** (Encoder/Index/Store/AdmissionPolicy/...)
   for experimentation without breakage; Rust kernels through PyO3 **only after profiling**.

The guiding vision is not “another vector database”, but **temporal, explainable,
frugal memory that keeps working without cloud infrastructure**. Multi-tenant SaaS
or production-scale robotics would be a funded **spin-off**; this core remains
**MIT and local-first**.

---

**House rule:** every phase closes with a *measurement*, not an opinion. No strong
claim without a test or benchmark behind it. See [ATTRIBUTION.md](ATTRIBUTION.md)
and [SECURITY.md](../SECURITY.md).
