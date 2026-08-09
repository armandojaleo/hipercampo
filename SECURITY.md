# Security and trust boundaries

hipercampo is a memory store. **Retrieved text is DATA, not instructions.** This
document describes the real risks and how to mitigate them.

## Memory-borne prompt injection

**Risk.** Anyone—or any content—able to write to memory can insert text that tries
to manipulate the model when retrieved, such as *"ignore your instructions and
..."*. Because `hc_recall` returns text that later enters an LLM context, a
malicious memory is an attack vector.

**Mitigations.**

- **Treat retrieved content as untrusted data.** The client must present memories
  as cited information and never execute instructions found inside them. This is
  the MCP host's responsibility, not hipercampo's alone.
- **Control who can write.** `hc_remember` and `hc_update` do not authenticate
  callers. Anyone able to talk to the server can write. Run it locally for one user.
- **Do not store secrets you would not want retrieved.** Memory contents are not
  encrypted; the SQLite database is plaintext.

## Isolation between contexts and projects

hipercampo **does** isolate data by **namespace** within one database. Every memory
has a namespace; all reads and writes—including ID-based operations such as
`delete`, `touch`, and `mark_*`—are scoped to it, and links never cross contexts.
This is **local isolation between contexts** (projects, profiles, or agents), **not**
a security boundary between clients of one server. hipercampo is local-first, with
one process per context. To separate contexts, use either:

- A different `HIPERCAMPO_NAMESPACE` per context with the same `.db`; or
- A different `HIPERCAMPO_DB` per project. See [INSTALL.md](docs/INSTALL.md).

There is no authentication: anyone able to talk to the process can choose its
namespace. Isolation prevents accidental mixing, not a malicious local actor.

## What hipercampo does NOT guarantee yet

- **Encryption** of data at rest.
- **Authentication or per-tool access control.**
- **Truth verification:** it stores what you tell it and does not judge whether it
  is true.

Until encryption exists, physically purge a secret that must truly disappear;
ordinary forgetting is not deletion.

## Actual deletion: forgetting versus purging

Do not confuse two guarantees:

- `hc_forget` (and dreaming) **does not delete**. It makes a memory dormant. The
  memory leaves normal retrieval but remains in the database and may resurface
  through `hc_muse`. This is memory management, not erasure.
- For a secret that should never have been stored, a deletion request, or very old
  dormant data, use **physical purge**: `hipercampo purge --ids …` or
  `--older-than DAYS`. Secure deletion overwrites released SQLite content instead
  of leaving it readable in free pages, then `VACUUM` returns space to disk. It is
  irreversible and requires confirmation. `hc_unlearn` likewise securely deletes
  working-identity data.

## Built-in safeguards (defence in depth)

hipercampo includes two lightweight scanners in `hipercampo/support/safety.py`.
They **warn; they do not block**:

- **Secret warning on write.** `hc_remember` detects common credential patterns
  (Stripe/AWS/GitHub-style keys, JWTs, private keys, `password:`/`api_key=`, and
  long hexadecimal values) and returns `secret_warning` with guidance. Since the
  database is plaintext, this helps prevent accidental secret storage.
- **Injection marker on retrieval.** `hc_recall` marks memories that appear to
  contain instructions—"ignore previous instructions", its Spanish equivalent,
  role markers, and similar patterns—with `untrusted: true`. Clients can then treat
  them as **cited data**, not commands to execute.

These scanners are not infallible; a determined attacker can evade patterns. They
reduce common-case risk and make suspicious content visible. The fundamental
mitigation remains client-side: ALWAYS treat retrieved content as data, never as
instructions.

Optional environment guardrails:

- `HIPERCAMPO_REDACT_SECRETS=1` **redacts** detected secrets before storage instead
  of merely warning. Labels remain; values are masked.
- `HIPERCAMPO_MAX_MEMORIES=N` limits each context to N memories. At the limit it
  prunes the item with the **lowest retention** (importance + confidence + utility)
  and **never** a protected item (importance ≥ 0.8). This bounds growth.

## Is hipercampo safe to install and run?

For someone installing it on their own machine, the attack surface is small **by
design**:

- **Local and offline.** The MCP server communicates with its client over stdio. It
  opens no ports and does not listen on the network, so it is not remotely exposed.
- **It does not execute memory contents.** hipercampo only stores and retrieves
  text. Nothing that comes out of memory is ever evaluated: there is no `eval`,
  `exec`, `os.system` or `pickle` anywhere in the package, and no code path takes a
  stored string anywhere near a shell.
  The one module that spawns processes is `hipercampo/support/procs.py`, which backs
  `hipercampo servers` and `hipercampo restart` — it lists and terminates *hipercampo's
  own* MCP servers. It never touches memory contents: it invokes exactly four fixed
  commands (`ps` and `powershell` to list, `taskkill` and `os.kill` to stop), every
  call passes an argument **list** rather than a shell string (`shell=True` appears
  nowhere in the package), the PowerShell query is a constant with nothing
  interpolated, and the only variable is a PID validated with `.isdigit()` before use.
- **Parameterized SQL.** Every query uses `?` placeholders; SQL strings are not
  assembled from input, preventing SQL injection.
- **Minimal, auditable dependencies:** `numpy` (BSD) and `mcp` (MIT). The semantic
  hook is **optional** and downloads a Hugging Face model when enabled
  (`sentence-transformers`, Apache-2.0). Installing `[semantic]` means accepting
  that additional supply-chain dependency.
- **The repository contains no personal data.** Keys and passwords visible in
  `scripts/` or `tests/` (for example `hcdemo_9f` and `girasol2024`) are fictional
  benchmark fixtures, not real credentials.

Sensible precautions:

- The SQLite database is **unencrypted plaintext**. Do not store secrets you would
  not want kept unencrypted on disk.
- Treat a `.db` from an **unknown source** as untrusted data: its contents may enter
  the model context when retrieved (see prompt injection above).
- Install from the official repository and inspect the code; it is deliberately small.

## Supply chain

Installing a package executes dependency code—and its dependencies' code.
hipercampo treats this as a first-class risk and minimizes it by design. This is
the threat model and the current defences, including what remains unfinished.

### Actual dependency surface

- **Core installation (`pip install hipercampo`): `numpy` + `mcp`.** The VSA/storage
  core itself needs only `numpy`; `import hipercampo` **does not** import `mcp`, as
  enforced by `tests/contracts/test_core_embebible.py`. Embedded users can use the
  core without the server.
- **`mcp` brings its dependency tree** (about 14 transitive packages, including
  `anyio`, `httpx`, `pydantic`, `starlette`, `uvicorn`, `sse-starlette`, `pyjwt`,
  `python-multipart`, and `pywin32`). **Transparency:** hipercampo uses only the
  STDIO server (`mcp.server.fastmcp`, `mcp.server.stdio`). It does not use HTTP
  transport (`uvicorn`/`starlette`), JWT, or multipart. That stack is installed
  because `mcp` requires it, not because hipercampo's code needs it.
- **Optional, opt-in, declared extras:** `[semantic]` (sentence-transformers →
  torch, a large tree users explicitly accept) and `[procs]` (psutil). Neither is
  installed by default.
- **VS Code extension:** development dependencies (`typescript`, `@types/*`, and
  Playwright) are pinned by `package-lock.json`; none ships in the `.vsix`, which
  contains compiled JavaScript only. The viewer has no npm runtime dependencies.
- **`mcp` is bounded** to `>=1.28.1,<2`, preventing an unreviewed new major version
  with API or provenance changes from entering automatically.

### Defences already in place

- **Trusted Publishing (OIDC) plus attestations/PEP 740.** There is no long-lived
  PyPI token to steal. Every release has verifiable provenance identifying the
  workflow and commit that built it. This is the modern defence against package
  impersonation.
- **Minimal dependencies with clear licences** (`numpy` BSD, `mcp` MIT).
- **No dynamic third-party code execution:** the core uses no `eval`, `exec`,
  `pickle`, `subprocess`, or network access.
- **VS Code viewer security model:** it invokes the CLI with `execFile` (argv and
  **no shell**, so query text cannot inject commands); the webview has a strict CSP
  (`default-src 'none'`, scripts allowed only by a **cryptographic nonce**, no
  network); and it escapes all memory content before rendering, preventing stored
  XSS even if an agent stores HTML or JavaScript. It accesses SQLite through the
  CLI. **Workspace Trust:** settings capable of executing code or reading arbitrary
  files (`hipercampo.command`, `hipercampo.dbPath`) are listed under
  `restrictedConfigurations`. An untrusted workspace with hostile
  `.vscode/settings.json` therefore cannot redirect the executable; only user
  configuration applies.

### How to VERIFY a release

```bash
# Download without installing, then inspect hashes/artifacts:
pip download hipercampo --no-deps -d /tmp/hc && ls /tmp/hc
# Reproducible installation with pinned hashes (when using a --hash lock file):
pip install --require-hashes -r requirements.lock
# Provenance: on the PyPI release page, inspect the attestations identifying the
# repository, workflow, and commit that published it. They must point here.
```

### Hardening: current and pending

- 🟢 **Minimal tree** and bounded `mcp` (`<2`).
- 🟢 **Trusted Publishing plus attestations** for releases.
- 🟢 **`pip-audit` blocks CI.** It was informational, with a note to make it blocking
  once the tree was clean. Measured in a clean virtualenv with only the project
  installed: *no known vulnerabilities*. So it blocks now. It will go red the day an
  advisory lands on a transitive of `mcp`, which is the intent. It runs without
  `--strict` on purpose: that flag also fails on dependencies it cannot audit, and
  the project itself is installed in editable mode at a version not yet on PyPI, so
  every version bump would have broken CI until that version was published. A real
  vulnerability still fails the build without it.
- 🟢 **`vsce` pinned** in `vsix.yml` (`@vscode/vsce@3.9.2`), so a compromised newer
  release cannot receive `VSCE_PAT`. The token is also no longer passed as a
  command-line argument: `vsce` reads it from the environment, and argv is readable
  by other processes on the runner.
- 🟢 **GitHub Actions pinned by SHA**, not tag — `checkout`, `setup-python`,
  `setup-node` and `pypa/gh-action-pypi-publish`. Tags are mutable; SHAs are not.
  `release.yml` can publish to PyPI, so its action chain is critical.
- 🟢 **`GITHUB_TOKEN` least privilege.** Every workflow declares `permissions:`
  explicitly (`contents: read`, plus `id-token: write` only where OIDC needs it).
  Without that block the token inherits the repository default, which is often
  read/write.
- 🟢 **CI tooling bounded** (`ruff`, `coverage`, `mypy`, `pytest`) with a floor and a
  major ceiling, so a tool release cannot change what CI checks without a commit.
- ⚪ **Available trade-off: make `mcp` optional.** Moving it to an `[mcp]` extra
  would leave the core with **one dependency** (`numpy`) and remove the unused HTTP
  stack. The cost is changing server installation to `pip install hipercampo[mcp]`.
  This is a product decision recorded for deliberate consideration, not an automatic
  default.

### Policy

- **No dependency is added without justification** against the standard library.
  Every new dependency is permanent attack surface.
- Heavy extras such as models and torch are **opt-in**, never part of the core.
- Every release is published with provenance, never manually using a long-lived token.

## Recommended scope

Use hipercampo **locally for one user** as personal assistant memory. Multi-user use
or sensitive data would require authentication, encryption, and identity isolation,
none of which is implemented today. We state this explicitly to avoid a false sense
of security.
