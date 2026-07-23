# Changelog

All notable changes to this project are documented here. Format loosely based on
[Keep a Changelog](https://keepachangelog.com/); versions follow [SemVer](https://semver.org/).

## [Unreleased]

## [0.1.0b1] — 2026-07-23

Primera **beta**: la superficie de la API queda congelada (contrato en
`tests/test_api_contract.py`). Respecto a la última alpha: coste de tokens auditado y
recortado (87k → 26k por sesión), abstención **medida y calibrada** en vez de asumida,
purga física segura, cobertura 69% → 81% con suelo en CI, y CI en los tres sistemas.

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
    `hc_stats`. It is always an **estimate** and says so — see the correction below.

### Fixed
- **The noise was still getting in, through the door next to the one we closed.**
  `VOLUNTEER_MIN_SIM` guarded the "nobody asked" branch, but the "this is a question"
  branch injected with **no similarity bar at all** — and question detection accepted
  the Spanish interrogatives *without their accent*. Unstressed «que» is among the
  most frequent words in the language, so `"espera que termine la sesión"`, `"creo
  que esto está mal"` and `"lo que pasa es que no compila"` all counted as questions.
  Measured in a real session: **2 of 3 turns injected another project's memory with
  nobody having asked anything**. Question detection now has two confidence levels —
  accented or `¿?` is a real question and answers as before; unaccented gets the same
  bar as volunteering, so it still answers when the memory clearly fits and stays
  quiet when the «que» was just passing through. `"espera que termine…"`: 350 → 0 tok.
- **The token budget did not hold.** The "N memories did not fit" notice is appended
  *after* the budget is spent and was never charged against it: a budget of 40 came
  out at 52 real tokens, **30% over**. A budget that overruns is not a budget. The
  notice is now reserved up front, worst case first so the reservation can never fall
  short. Verified across five ceilings: 40→39, 60→58, 120→64, never above.
- **46 tokens to say nothing.** When no memory fit, the hook still injected a header
  plus "1 more did not fit" — costing as much as a useful memory, carrying no data,
  and leaving the model unable to tell what to ask for. It now stays quiet, which is
  free. (A notice only earns its keep next to something.)
- **An unreadable environment variable took the server down.** `int(os.environ…)` at
  import time turned a typo in `.mcp.json` into a `ValueError` traceback and a server
  that would not start — `budget` is imported by both the MCP server and the policy.
  It now warns on stderr and falls back to the factory value.
- **`main()` could start the server twice.** The `try` wrapped `anyio.run(...)`
  entirely — the whole life of the server, not just building the options — so an I/O
  failure mid-session landed in the `except` and called `mcp.run()`, raising a second
  stdio server over already-consumed input. The `try` now covers only the fragile
  preparation; a failure while serving propagates and kills the process, which is
  what the MCP client knows how to handle.

### Changed
- **The abstention threshold was measured, and it had never been a gate.** The
  ROADMAP asked to calibrate `MIN_RECALL_SCORE`; measuring it (new `scripts/calibrate.py`,
  a sweep of 30 in-domain queries + 30 unrelated ones at N=20/100/500) showed that knob
  is **inert** — moving it 0.03→0.08 changes neither MRR (≤0.002) nor false-recall (none).
  The real lever, `ANSWER_MIN_SCORE`, sat at **0.08 — below the 5th percentile of the
  *unrelated* queries (0.100)**: it let the whole negative distribution through, which is
  where false-recall 1.00 came from. The classes do separate at the median (positives
  0.327 vs strangers 0.160), so it is a placement problem, not an impossible one.
  Re-calibrated to **0.19** (lexical) and **0.17** (semantic): false-recall **1.00 → 0.17**
  (lexical, stable across N) and **~0.10** (semantic), while keeping synonym recall alive —
  the thing that separates hipercampo from BM25. This does cost some paraphrase recall
  (the measured price of the compromise, MRR 0.807 → 0.71 lexical); 0.28 would reach
  false-recall 0.00 but kills synonym entirely, so it was not taken. `RECALL_Z` turned out
  inert at scale (identical rows for z=2.0 and z=3.0 at N=500); it still bites on tiny
  memories, where it was put. A length-normalisation of the activation was built and
  **discarded after measuring it**: it seemed to rescue long memories (a fact buried in 60
  filler words is otherwise unrecoverable, 0/10) but, with false-recall held equal, it lost
  on *both* benchmarks at once — the apparent win was just answering more often. The honest
  fix for a long text is to split it into atomic facts, not to rescale; the finding is left
  documented in the code as a measured limit.
- **The token count is never exact, and now says so.** It was declared exact when
  `tiktoken` was installed. It is not: `cl100k_base` is *OpenAI's* tokenizer and what
  is being measured is what it costs **Claude**, whose tokenizer Anthropic does not
  publish — only their API can be exact. With `tiktoken` the estimate improves; it
  does not become exact. `es_estimacion()` now always returns `True`, and a new
  `metodo()` states what the count was made with. Claiming a precision we do not have
  is precisely what this project does not do.
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
- **Physical purge: the deliberate counterpart to forgetting.** `hc_forget` and sleep
  only *dormant* a memory — reversible on purpose, it can resurface. That is memory, not
  erasure, and for a secret that should never have been stored (or a right-to-erasure
  request, or very old dormant clutter) it is not enough. New `hipercampo purge --ids …`
  / `--older-than DAYS` deletes for real: a **secure delete** (SQLite overwrites the freed
  content instead of leaving the text legible in free pages) followed by `VACUUM` to
  return the space to disk. It is irreversible and asks for confirmation first. `hc_unlearn`
  now also secure-deletes the working-identity it removes. `tests/test_purge.py` proves the
  hard part: after a purge the secret's bytes are **gone from the `.db` file**, not just
  unlinked from the table. SECURITY.md corrected — it previously claimed `hc_forget`
  deletes rows; it does not, and conflating the two is exactly the kind of false assurance
  this project avoids.
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
