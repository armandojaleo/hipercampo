# hipercampo documentation

The repository root keeps only what GitHub recognises by position (README,
LICENSE, CONTRIBUTING, CODE_OF_CONDUCT, SECURITY) plus `AGENTS.md`, which agents
read from there. Everything else lives here.

| Document | What's in it |
|---|---|
| [INSTALL.md](INSTALL.md) · [INSTALL.es.md](INSTALL.es.md) | Full install guide: `.mcp.json`, hooks, verification and troubleshooting |
| [README.es.md](README.es.md) | The README in Spanish (the root one is in English) |
| [ROADMAP.md](ROADMAP.md) | What's done, what's measured, and what's missing |
| [CHANGELOG.md](CHANGELOG.md) | What changed in each version |
| [ATTRIBUTION.md](ATTRIBUTION.md) | Third-party work in use, and under which licence |

## How the code is organised

The package is split into layers, and each one only looks downwards:

| Layer | Modules | What it deals with |
|---|---|---|
| `hipercampo/core/` | `vsa` `encoder` `semantic` `atomize` `surprise` `navgraph` | Hypervector algebra and encoding. Pure, no state, no disk |
| `hipercampo/support/` | `config` `audit` `budget` `safety` `procs` | Cross-cutting: paths, logging, token budget, warnings |
| `hipercampo/storage/` | `store` `backup` | SQLite persistence. Decides *how* to store, never *what* is worth storing |
| `hipercampo/cycle/` | `memory` `roles` `policy` `identity` `tuning` | The memory itself: what's kept, recalled and forgotten |
| `hipercampo/` | `cli` `server` | The two interfaces. They stay at the package root on purpose |

`cli.py` and `server.py` don't move because they are **public paths**: `hipercampo`
is the console script declared in `pyproject.toml`, and `python -m hipercampo.server`
sits in the `.mcp.json` of anyone already using it. Moving them would be an
incompatible change dressed up as tidying.

For the same reason `hipercampo.encoder` and `hipercampo.roles` — documented as
public in INSTALL and the README — still import the same way even though the files
moved. `tests/contracts/test_public_paths.py` holds all of this in place.

The layering isn't decorative: **`core` never touches disk and `storage` doesn't
know what deserves to be remembered.** That's what lets each piece be measured on
its own, and what keeps the core small enough to embed without dragging in the MCP
server — something `tests/contracts/test_core_embebible.py` checks, and which
breaks CI if anyone crosses the line.

## How the tests are organised

The suite mirrors those layers, so a failure points at the layer that broke:

| Folder | Covers |
|---|---|
| `tests/core/` | Algebra, encoding, atomisation, surprise, navigable graph |
| `tests/storage/` | Persistence, migrations, backup, namespaces, purge |
| `tests/cycle/` | The memory cycle: remember, recall, dream, forget, roles, policy |
| `tests/support/` | Logging, budget, safety scanners, processes |
| `tests/contracts/` | The promises made outward: public paths, MCP API, CLI, embeddable core, and the invariants that must not regress |

`tests/conftest.py` puts `tests/` on `sys.path` once, so every test can do
`from helpers import ...` regardless of the folder it sits in. Each file also
keeps a small bootstrap of its own so it can still be run directly
(`python tests/core/test_vsa.py`) via the runner in `helpers.ejecutar`.
