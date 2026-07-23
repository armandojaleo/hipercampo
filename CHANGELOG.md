# Changelog

All notable changes to this project are documented here. Format loosely based on
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

### Added
- **Token budget: hipercampo now knows what it costs you.** Nobody had ever measured
  it. The bill turned out to be the opposite of what was assumed: the hook was the
  cheap part (~244 tok/turn) while the **tool definitions travel in every single
  request** (~2,658 tok) and quietly occupy the context window even when the memory
  is never used. New `scripts/tokens.py` measures both, so the claim is checkable
  rather than asserted.
  - Tool descriptions rewritten short, and **only the six daily tools are announced
    by default**: **2,658 → 807 tok** per request (−70%). The other twelve are not
    gone — new **`hc_tools`** lists them one line each and activates any of them
    **hot**: it registers the tool for real, notifies the client
    (`tools/list_changed`, now correctly declared as a server capability) and runs
    the requested one *in the same call*, so the capability holds even if the client
    ignores the notification. `HIPERCAMPO_TOOLS=all` restores the full announced
    surface. The Python API is unchanged: all 18 functions keep their signatures,
    `hc_tools` is purely additive.
  - New `hipercampo/budget.py`: per-injection budget (`HIPERCAMPO_HOOK_BUDGET`, 350;
    `HIPERCAMPO_IDENTITY_BUDGET`, 500). Memories go in **whole or not at all** —
    the first attempt truncated them, and the very first real injection proved why
    that was wrong: *"Compartir listas: URL …/share?l=<ids> […]"* cut away exactly
    the part that explained why. A halved memory reads as complete and gets answered
    with confidence; an omitted one is visible and recoverable, so what does not fit
    is dropped and the injection **says how many are missing and how to ask for
    them**. Total measured over a 30-turn session: **87k → 26k tokens**.
  - The bill is auditable: `hipercampo log --accion tokens` and a `tokens` field in
    `hc_stats`. It is a character-based **estimate** (~3.7 chars/token) and says so;
    with `tiktoken` installed it becomes exact.

### Fixed
- **It interrupted when nobody had asked.** Measured: "arregla el bug del botón"
  injected 645 tokens of unrelated project context. Two candidate fixes were tested
  and **both failed**: raising the score threshold would have killed legitimate
  recalls first (the noise scored 0.167, above a real question's 0.140), and
  z-contrast was worse still ("gracias, buen trabajo" scored the highest z of all).
  What separates cleanly is the **direct activation** — similarity alone, before
  propagation, strength and confidence are mixed in. `recall` now returns it as
  `sim` on every hit, and volunteering requires clearing a stricter bar than
  answering does: if nobody asked, staying quiet is free and being wrong costs the
  user hundreds of tokens. Waste in the measured session: 1/6 turns → 0/6, average
  244 → 89 tok/turn, with retrieval quality unchanged (MRR 0.807).

### Fixed
- **Accents arrived broken through the hook.** `json.load(sys.stdin)` decodes with
  the locale encoding — cp1252 on Windows — while Claude Code always sends UTF-8,
  so «¿añadelo?» became «Â¿aÃ±adelo?» *and was stored and logged that way*. The hook
  now reads bytes and decodes UTF-8 explicitly.

### Added
- **A much more detailed decision log.** `recall` now records how many memories were
  scanned, the best score, which ids won, which linked projects were consulted and
  the elapsed ms; an abstention records the threshold and the noise it was measured
  against (`mejor=0.061 · umbral=0.118 · ruido=0.043±0.037`); `remember` records what
  it resembled, with what similarity, and how many associations it created.
  A log that says "abstained" without saying *against what* explains nothing.
- **`hipercampo log` grew up**: `-f/--follow` (live), `-g/--grep` (accent- and
  case-insensitive — searching `abstencion` finds `abstención`), `-a/--accion`,
  `--hoy`, `--errores`, `--ruta`, and `-n 0` for everything. With no matches it
  lists which actions exist in the log.

### Added — working identity (the agent's own memory)
- **`hc_learn` / `hc_identity` / `hc_unlearn`.** Until now hipercampo stored memory
  *of the world* — facts, projects, gotchas. It did not store what psychology calls
  procedural and self memory: **what was learned about how to work**. Rules the user
  confirmed, lessons from mistakes, decisions already made and why, preferences.
  All of that died when the session closed, so the next one started from zero and
  tripped over the same stone.
- Lives in a reserved context (`__self__`) that is readable from **every** project
  (identity belongs to the agent, not to a project), is only written on purpose,
  and is **protected from active forgetting** — a lesson learned does not expire
  through disuse. Repeating a rule reinforces it instead of duplicating it: a rule
  repeated is a rule confirmed.
- **`SessionStart` hook**: at the start of a session there is no question to answer,
  so what it injects is *who you are when you work*. Also `hipercampo identity`.
- New suite `tests/test_identity.py` (9) — **29 suites**.

### Fixed
- **The identity leaked in through the linked-contexts door.** With
  `HIPERCAMPO_LINKED="*"` the wildcard enumerated *every* namespace in the file,
  `__self__` included, so working-identity entries surfaced in ordinary `recall`
  mixed with memories of the world. The isolation test only covered the direct
  path, not the linked one. `*` now means "all my projects", never "everything in
  the file", and `__self__` is refused even when named explicitly.
  Caught in production, by the hook, one minute after shipping it.
- `Hipercampo.close()` now closes the identity store too. Without it every hook
  invocation leaked a file handle (and on Windows locked the file).

### Fixed
- **`restore()` could destroy your live memory silently.** It overwrote the
  database with no copy of what it replaced, and without checking the source was
  even a valid memory. Now it verifies the copy first (`quick_check` + readable
  schema) and saves what it is about to overwrite to `<db>.antes-de-restaurar`.
  Restoring the wrong file is an easy mistake and an expensive one to notice late.
- A read-only database **could not be opened at all** (the constructor always wrote
  the schema), and `recall` crashed on one because it reinforces what it retrieves.
  Reinforcement is now best-effort: reading never fails for being unable to write.

### Added
- **Failure simulations** (`tests/test_failures.py`): read-only database, full
  disk at the exact moment of the write, and the process killed mid-write and
  mid-sleep in real subprocesses. Verified: it warns without lying, never
  corrupts, and a killed sleep does not claim to have slept.
- **Coverage gate in CI** (78% floor; currently 81%). New suites for the code that
  had none: `test_backup.py` (6), `test_cli.py` (8, the hook contract),
  `test_audit.py` (6, the decision log) — **28 suites**.

## [0.1.0a5] — 2026-07-22

### Added
- **Cross-project memory (linked contexts, read-only)**: `linked=` /
  `HIPERCAMPO_LINKED` ("proj1,proj2" or `*`). recall/muse/dream also read the
  linked projects and tag foreign results with `"project"`; every write, reinforce,
  update, consolidation and forgetting stays in the own project, and a non-linked
  project remains invisible. New suite `tests/test_linked.py` (8 tests) — 23 suites.

## [0.1.0a4] — 2026-07-22

Hardening release. **No new cognitive features** — this one makes what exists
predictable. Closes the four blockers raised in external review.

### Fixed
- **Link state machine.** The UPSERT only touched `weight`, so a dream hypothesis
  could overwrite the `type`/`status` of confirmed evidence, and `set_link_status`
  could reject *any* link between two memories — including a lexical one. Now a
  strict precedence decides (observed evidence > rejected > confirmed hypothesis >
  proposal): a real observation can **promote** an old rejected hypothesis, but
  re-proposing something already rejected neither resurrects nor reinforces it.
  `set_link_status` only ever moves `dream/proposed → confirmed | rejected`,
  returns the affected row count, and `hc_accept_bridge` / `hc_reject_bridge`
  now **report an error** instead of claiming success for a hypothesis that
  doesn't exist.
- **Retries are no longer blind.** `@resiliente` retried *any* `sqlite3.Error`,
  which could duplicate a write that had actually committed. Only transient
  failures (dropped connection, lock) are retried; corruption, read-only database,
  full disk or a broken schema are reported without retrying (`"reintentado": false`).
- **`hc_health` write check was a false positive.** It tested directory permissions
  (`os.access`), which sees neither a full disk nor a read-only `.db`. It now does a
  **real write** inside a `SAVEPOINT` and rolls it back. Default check is
  `quick_check` (cheap as the memory grows); `integrity_check` on demand via
  `hipercampo doctor --full` or `hc_health(full=True)`.
- **Autosleep could lie.** It reset the write counter and stamped the sleep time
  *before* knowing whether consolidate/forget/dream succeeded, and swallowed errors.
  Now the counter resets **only on success**, and `last_sleep_attempt`,
  `last_sleep_success` and `last_sleep_error` are recorded and surfaced by `hc_health`.
- Backup connection was left open (`with sqlite3.connect(...)` commits, it doesn't
  close) — a real file-handle leak on Windows.

### Added
- **Versioned migrations** (`PRAGMA user_version`, `SCHEMA_VERSION = 5`): five
  explicit, idempotent, transactional steps instead of ad-hoc column sniffing.
  A **backup is taken before touching the schema** (`<db>.bak-v<n>`), and an
  interrupted migration can be resumed — already-applied steps are no-ops.
  Migration 006 rewrites rows predating an `ALTER TABLE ADD COLUMN ... NOT NULL`:
  SQLite serves them the default on read, but the on-disk record lacks the column
  and some versions fail `integrity_check` with "NULL value in memories.confidence".
  Found by CI on Linux — it never reproduced on the development machine.
- `hipercampo doctor` now reports schema version and health.
- New suite `tests/test_estados.py` (13 tests) + 4 migration tests — **21 suites**.
- **CI now runs on Windows and macOS**, not just Linux: hipercampo is a local app.
  That alone caught three bugs that never reproduced on the dev machine.
- **`hipercampo servers` / `hipercampo restart`**: an MCP server is a long-lived
  process that loaded its code at startup, so after an upgrade it keeps serving the
  old version and nothing looks wrong. These list the live servers with their start
  time and terminate them; the MCP client relaunches them on next use, with the new
  code. No dependencies (psutil if present, system tools otherwise).

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
