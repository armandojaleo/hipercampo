# Changelog

All notable changes to this project are documented here. Format loosely based on
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **`hc_health`** — is the memory sound? Checks file integrity (`PRAGMA
  integrity_check`), schema, readability and write permission.
- **Self-recovery**: every public operation is wrapped in `@resiliente`. If SQLite
  fails it **logs the error, reconnects and retries once**; if it still fails it
  returns a readable error (`{"error": ..., "sugerencia": "run hipercampo doctor"}`)
  instead of crashing the MCP server.
- New suite `tests/test_resilience.py` (5 tests) — 20 suites in total.

### Changed
- `tests/helpers.py`: shared `memoria`/`limpiar`/`ejecutar` — 15 of 19 test files
  were duplicating their own open/clean logic.
- `Store.matrix()` replaces four repeated `stack_hvs([...])` call sites.
- `hipercampo hook` now strips IDE-injected blocks (`<ide_opened_file>`,
  `<system-reminder>`) before deciding: they are not the user's words.

## [0.1.0a3] — 2026-07-22

### Added
- **Typed, staged links**: associations now carry `type` (lexical | update |
  consolidation | dream) and `status` (proposed | confirmed | rejected).
- **`hc_dream` proposes, it doesn't assert**: `dry_run=True` by default; hypotheses
  are stored as `proposed` and **never propagate** in recall/muse until confirmed with
  `hc_accept_bridge` (or discarded with `hc_reject_bridge`). Imagination no longer
  contaminates evidence.
- **Creative-zone scoring**: bridges are ranked by `creative_fit` (peak at
  `DREAM_IDEAL`, zero outside the band) × common-path strength × confidence — the most
  dissimilar pair no longer wins by being absurd.
- Structured facts now cast a **textual shadow** into the living memory (`fact_id`),
  so they take part in recall/muse/forgetting; `ask_role` ignores forgotten facts.
- Release pipeline **validates the artifact before publishing**: `twine check`,
  tag/version match, clean-env wheel install, import, and MCP handshake.

### Fixed
- **Critical**: opening a database created by an older version crashed
  (`no such column: namespace`) because indexes were created before the migration.
  Now: tables → migration → indexes. Regression test included.
- `__version__` now comes from installed metadata (no more drift with PyPI).
- `MAX_MEMORIES` counts **physical** rows (dormant included) and prunes dormant
  low-value first; `stats()` reports `total` (current) and `total_fisico` (on disk).

## [0.1.0a2] — 2026-07-22
First release published to PyPI (trusted publishing + attestations). Adds dormant
memory (forgetting archives instead of deleting), `hc_muse` creative recall,
`hc_dream`, compositional role tools (`hc_remember_fact` / `hc_ask_role`) and the
baseline comparison against BM25 / embeddings.

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
- Docs (EN/ES), SECURITY, ATTRIBUTION, ROADMAP; 16 test suites + CI (Python 3.11–3.13)
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
