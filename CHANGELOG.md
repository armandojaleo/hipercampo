# Changelog

All notable changes to this project are documented here. Format loosely based on
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [0.1.0a1] — 2026-07-22

First public alpha. Local-first, single-user memory for Claude via MCP.

### Added
- **Memory cycle**: surprise-gated writing (double veto: redundant + predictable via
  an in-house incremental LM / MDL, with an *adaptive* threshold), spreading-activation
  recall with **abstention**, sleep **consolidation** (structural, optional summarizer),
  and **active forgetting** driven by a transparent retention value.
- **Four separated axes**: novelty, importance, reliability (`confidence`), utility.
- **Fact updates** (`hc_update`): safe supersession by id or minimum similarity.
- **Compositional roles** (`hc_remember_fact` / `hc_ask_role`): store subject-predicate-
  object facts and query by role via VSA unbinding (distinguishes a fact from its reverse).
- **Contexts**: namespace isolation (reads, id-writes and links), enforced in depth.
- **Reliability**: SQLite WAL + `busy_timeout`, reentrant transactions, input validation.
- **Performance**: vectorized similarity (native popcount) — ~5× faster scans.
- **Safeguards**: secret-detection warnings, injection flagging of recalled memories,
  optional secret **redaction** (`HIPERCAMPO_REDACT_SECRETS`) and per-context memory
  **cap** (`HIPERCAMPO_MAX_MEMORIES`).
- **Optional semantic hook** (SimHash bridge over sentence-transformers).
- Docs (EN/ES), SECURITY, ATTRIBUTION, ROADMAP; 14 test suites + CI (Python 3.11–3.13)
  running tests, benchmarks and a baseline comparison (BM25 / embeddings).

### Added (post-tag, unreleased)
- **Dormant memory & creative recall**: forgetting now *archives* memories as
  `dormant` (not deleted, like the human mind); `hc_muse` performs serendipitous
  recall — favoring indirect associations and resurfacing dormant memories to tie
  ideas together (insight/brainstorming).

### Known limits (declared, not hidden)
- Retrieval is linear (no ANN index): fine for hundreds–thousands of memories.
- Surprise counters are not fully persisted (rebuilt from stored memories on start).
- Benchmarks are small/synthetic — a signal, not proof at scale.
- Local, single-user scope: no auth/encryption/multi-user isolation.

[0.1.0a1]: https://github.com/armandojaleo/hipercampo/releases/tag/v0.1.0-alpha
