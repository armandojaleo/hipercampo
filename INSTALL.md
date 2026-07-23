# hipercampo · Installation guide

🌍 **Español: [INSTALL.es.md](INSTALL.es.md)** · You are reading the English version.

From zero to "Claude has memory" in a few minutes. Pick **one** of the two paths
(A: local Python — the simplest way to start; B: Docker — more portable).

Requirements: **Python 3.11+** (path A) or **Docker** (path B). Windows, macOS or Linux.

---

## The map: how memory is organised

Before configuring anything, the mental model. All memory lives in **a single
SQLite file**. Inside it, *namespaces* are separate drawers. Here is an example
with two imaginary projects, `webshop` and `blog`:

```
                 A SINGLE FILE:  ~/.hipercampo/hipercampo.db
                 ────────────────────────────────────────────
                   (namespaces are drawers inside it)

   ┌─ __self__ ─────────────┐        ┌─ personal ─────────────┐
   │ the agent's working    │        │ who you are:           │
   │ identity: rules,       │        │ role, preferences,     │
   │ decisions, lessons     │        │ how you like to work   │
   └────────────────────────┘        └────────────────────────┘
     read at every session             "personal" server, global

   ┌─ proj-webshop ─────────┐        ┌─ proj-blog ────────────┐
   │ the shop's technical   │        │ the blog's technical   │
   │ side: stack, deploys,  │        │ side: stack, deploys,  │
   │ gotchas, decisions     │        │ gotchas, decisions     │
   └────────────────────────┘        └────────────────────────┘
        ▲                                 ▲
        │ "project" server                │ "project" server
        │ (the shop's .mcp.json)          │ (the blog's .mcp.json)
     ~/code/webshop                    ~/code/blog


   WHO SEES WHOM   (with HIPERCAMPO_LINKED="*")
   ───────────────────────────────────────────
    working on webshop:   ══> WRITES to  proj-webshop  ← and only there
                          ──> reads      personal, __self__, proj-blog

    working on blog:      ══> WRITES to  proj-blog
                          ──> reads      personal, __self__, proj-webshop

   ══> WRITE arrow: only one, into your own drawer
   ──> READ arrow: towards linked drawers, and it never comes back
```

**The asymmetry is the guarantee**: what is linked is **read, never touched**.
Storing, reinforcing, updating, consolidating and forgetting operate on your own
project alone. A project that is not linked is simply invisible.

> ⚠️ **The `default` drawer.** If you store memories before setting
> `HIPERCAMPO_NAMESPACE`, they land in a drawer called `default`. It is not an
> error — it works — but it is a drawer with no owner: every project reads it and
> none feels it is theirs. If that happened to you, split its contents into the
> drawers they belong to (see *Moving memories between drawers*, below).

---

## Step 0 · Get the code

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
```

---

## Path A · Install from PyPI (recommended)

```bash
pip install hipercampo                 # or: pip install "hipercampo[semantic]"
```

### From source (contributors)

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo && pip install -e .
```

### A.2 Check that it works (without Claude yet)

```bash
python scripts/demo.py        # see the whole cycle: surprise, recall, dream, forgetting
python -m pytest -q           # or: python tests/test_memory.py
```

### A.3 Start the MCP server by hand (optional, to see it alive)

```bash
python -m hipercampo.server
```

It sits waiting on stdio (that is normal for MCP). Stop it with Ctrl+C. You do not
need to launch it yourself: Claude starts it automatically once connected (next step).

---

## Path B · Docker

```bash
docker compose build
```

Memory is stored in the `hipercampo_data` volume. For a manual test:

```bash
docker compose run --rm hipercampo   # starts the server (stdio); Ctrl+C to exit
```

---

## Final step · Connect to Claude

### Claude Code (CLI / VSCode extension)

**Option 1 — with the command** (from the project folder):

```bash
# Path A (Python):
claude mcp add hipercampo -- python -m hipercampo.server

# Path B (Docker):
claude mcp add hipercampo -- docker run --rm -i -v hipercampo_data:/data hipercampo:latest
```

**Option 2 — by hand**: create an `.mcp.json` file at the project root:

```json
{
  "mcpServers": {
    "hipercampo": {
      "command": "python",
      "args": ["-m", "hipercampo.server"],
      "env": { "HIPERCAMPO_DB": "./data/hipercampo.db" }
    }
  }
}
```

Restart Claude Code. You should see 18 tools: `hc_remember`, `hc_recall`,
`hc_muse`, `hc_dream`, `hc_accept_bridge`, `hc_reject_bridge`, `hc_update`,
`hc_remember_fact`, `hc_ask_role`, `hc_consolidate`, `hc_forget`, `hc_stats`.

### Memory shared across ALL projects (global)

The `.mcp.json` above enables hipercampo **in that project only**. Since the
database already lives at a global path (`~/.hipercampo/hipercampo.db`), the data
is shared anyway; the only "per project" part is the server registration.

To have the tools available in **any** project, register the server at **user**
scope:

```bash
claude mcp add --scope user hipercampo -- python -m hipercampo.server
```

Or by hand, add a root-level `mcpServers` block to `~/.claude.json` (Claude Code)
— same shape as `.mcp.json`, but in the user's global file. Use absolute paths for
the Python executable and for `HIPERCAMPO_DB`. Restart Claude Code.

> You can have both (global + the repo's `.mcp.json`): if they point to the same
> DB and command, it is harmless. The repo's `.mcp.json` is useful for whoever
> clones the project.

### Isolating contexts: namespaces (recommended) or separate files

Two ways to keep one project's memory out of another's (local-first, both valid):

**Option A — namespaces (a single DB).** Add `HIPERCAMPO_NAMESPACE` to each
server's `env`. Every memory carries its context and **nothing crosses over**
(reads, writes by id and links — all scoped):

```json
"env": {
  "HIPERCAMPO_DB": "C:/Users/you/.hipercampo/hipercampo.db",
  "HIPERCAMPO_NAMESPACE": "proj-webshop"
}
```

**Option B — separate files.** One `HIPERCAMPO_DB` per project (below). This is
**local isolation between contexts**, not a multi-user security boundary (see
[SECURITY.md](SECURITY.md)).

### Hybrid: personal memory + per-project memory

Two servers with a **different DB** (or the same file and a different namespace),
so one project's technical detail does not mix with another's while Claude still
knows you:

**1) Personal (global, `~/.claude.json`)** — a `personal` server with its own DB:

```json
"mcpServers": {
  "personal": {
    "command": "C:/Python313/python.exe",
    "args": ["-m", "hipercampo.server"],
    "env": { "HIPERCAMPO_DB": "C:/Users/you/.hipercampo/personal.db" }
  }
}
```

**2) Per project (`.mcp.json` at each project's root)** — a `project` server with
its own DB per project:

```json
{
  "mcpServers": {
    "project": {
      "command": "C:/Python313/python.exe",
      "args": ["-m", "hipercampo.server"],
      "env": { "HIPERCAMPO_DB": "C:/Users/you/.hipercampo/proj-NAME.db" }
    }
  }
}
```

Change `proj-NAME.db` per project (`proj-webshop.db`, `proj-blog.db`...). Claude
will see two sets of tools (`personal` and `project`) and will pick where to store
each thing. To copy your current memory into the personal one: `python -m
hipercampo.backup C:/Users/you/.hipercampo/personal.db` (with `HIPERCAMPO_DB`
pointing at the old one).

### Claude Desktop

Edit the configuration file:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "hipercampo": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-v", "hipercampo_data:/data",
               "hipercampo:latest"]
    }
  }
}
```

(Or with Python: `"command": "python"`, `"args": ["-m", "hipercampo.server"]`, and
`"env": {"HIPERCAMPO_DB": "C:/path/to/hipercampo.db"}`.)

Restart Claude Desktop.

---

## Check that Claude really has memory

In a conversation with Claude, ask it:

> «Store in your memory that I prefer direct answers» → it will use `hc_remember`.
> Later: «what do you remember about how I like to be spoken to?» → `hc_recall`.

You can also verify the server without Claude, with a raw MCP handshake:

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
'{"jsonrpc":"2.0","method":"notifications/initialized"}' \
'{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python -m hipercampo.server
```

It must list the 18 `hc_*` tools.

---

## SYNAPTIC mode (memory firing on its own, every turn)

By default memory is *pull*: Claude decides when to call it. With a Claude Code
**hook** it can fire **on every message you send**, like a synapse.

hipercampo decides for itself what is called for (`hipercampo assist`): recall if
you ask, inspire if you are stuck, suggest storing/updating if you state something
new, or **stay quiet** if nothing is relevant. It never writes on its own.

In `~/.claude/settings.json` (global) or `.claude/settings.json` (per project):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "hipercampo hook",
            "timeout": 15,
            "statusMessage": "consulting memory..."
          }
        ]
      }
    ]
  }
}
```

`hipercampo hook` reads the hook's JSON from **stdin**, decides what is called for
and returns the context to inject (`hookSpecificOutput.additionalContext`). If
nothing is relevant it returns `{}`: **it does not get in the way**. Try it by hand
first:

```bash
echo '{"prompt":"where is the server hosted?"}' | hipercampo hook
echo '{"prompt":"tomorrow I will buy bread"}' | hipercampo hook   # -> {} : stays quiet
```

After editing it, open `/hooks` once (this reloads the configuration) or restart
Claude Code. If you would rather not use hooks, the **`hc_assist`** tool does the
same thing when Claude calls it at the start of a turn.

### Seeing what it is doing (transparency)

Every decision is logged — to stderr (visible in the MCP server logs) and to a
file next to the database:

```bash
hipercampo log -n 20     # what it decided lately, and why
hipercampo doctor        # DB path, permissions, version, dependencies
```

```
20:47:05 remember  stored id=1 · novelty=1.0 · surprise=1.0
20:47:06 remember  skipped: redundant · novelty=0.0 · surprise=0.57
20:47:07 recall    abstained: nothing stands out from the noise · n=14
20:47:07 assist    nothing: nothing relevant to add this turn
```

Turn it off with `HIPERCAMPO_LOG=0`.

### What it costs in tokens (and how to cut it)

A memory that eats your context window is not helping: it is in the way.
hipercampo spends in two very different places, and it pays to know which is which:

```bash
python scripts/tokens.py       # the bill, measured on your own machine
```

| Source | Cost | When you pay it |
|---|---:|---|
| Announced tools (7, by default) | ~810 tok | on **every** request |
| …with `HIPERCAMPO_TOOLS=all` (all 18) | ~2,070 tok | on every request |
| Working identity (at startup) | ≤500 tok | once per session |
| Hook injection | ≤350 tok | only on turns that fire |

The expensive part is **not** the memory: it is the tool descriptions, which
travel in every request even if you never use it. So only the six daily ones are
announced up front (`hc_remember`, `hc_recall`, `hc_update`, `hc_learn`,
`hc_assist`, `hc_stats`), plus `hc_tools`.

**Nothing is lost.** The other twelve are one call away:

```
hc_tools()                                     -> lists them, one line each
hc_tools(name="hc_dream", args={"max_bridges": 3})   -> activates AND runs it
```

Once activated they are registered for real and the server notifies the client
(`tools/list_changed`), so from then on they are called like any other tool. They
also run in that same call on purpose: if a client ignores the notification, the
capability must stay reachable anyway.

Prefer all 18 announced from the start? `"HIPERCAMPO_TOOLS": "all"`.

Injection budgets are tuned with `HIPERCAMPO_HOOK_BUDGET` (350 by default, `0`
disables it) and `HIPERCAMPO_IDENTITY_BUDGET` (500). Memories go in **whole or not
at all**: one cut in half looks like information and isn't, so whatever does not
fit is omitted and hipercampo **says how many are missing** and how to ask for them.

For the running total: `hipercampo log --accion tokens`, or the `tokens` field of
`hc_stats`. Honest caveat: the count is a character-based **estimate** (~3.7 per
token); install `tiktoken` if you want exactness.

### Is the memory healthy?

```bash
hipercampo doctor          # environment: path, permissions, dependencies, state
```

or the **`hc_health`** tool from the chat: it checks file integrity, schema, reads
and write permission. If the database fails mid-operation, hipercampo **warns in
the log, reconnects and retries once**; if it still cannot, it returns a readable
error instead of taking the MCP server down.

### Memory across projects (linked contexts)

Each project keeps its own isolated memory, but you can **link** others read-only
so they can feed you ideas:

```jsonc
// the project's .mcp.json
"env": { "HIPERCAMPO_NAMESPACE": "proj-webshop",
         "HIPERCAMPO_LINKED": "proj-blog,proj-docs" }   // or "*" = all of them
```

`hc_recall`/`hc_muse` responses mark anything foreign with `"project": "..."`.
The asymmetry is the guarantee: what is linked is **read, never touched** —
storing, reinforcing, updating, consolidating and forgetting operate on your own
project alone, and a project that is not linked stays invisible.

### Autonomous sleep

Every **50 writes** (`HIPERCAMPO_AUTOSLEEP_EVERY`, `0` disables it) hipercampo
**maintains itself**: it consolidates, lets what no longer matters go dormant, and
proposes bridges. Like a brain that sleeps without being told. You can also ask
for it: `hipercampo sleep` or the `hc_sleep` tool.

## Controlling and backing up the memory

All of hipercampo's memory is **a single SQLite file**. Easy to inspect, move,
copy or delete.

### Where is it?

By default:

- **Local (Windows)**: `C:\Users\<you>\.hipercampo\hipercampo.db`
- **Local (macOS/Linux)**: `~/.hipercampo/hipercampo.db`
- **Docker**: inside the `hipercampo_data` volume (`/data/hipercampo.db`)

You can change it with the **`HIPERCAMPO_DB`** variable (in your MCP config's
`env`, or when launching the server). And you can ask Claude: the `hc_stats` tool
returns a `db` field with the absolute path.

### Controlling its use from Claude

The 18 tools give you full control, without touching code:

| You want to… | Ask Claude (uses the tool) |
|----------|-------------------------------|
| See how much it remembers and where | `hc_stats` |
| Store something specific | `hc_remember` (with high `importance` so it is not forgotten) |
| Recall something | `hc_recall` |
| Update a fact that changed | `hc_update` |
| Condense (sleep phase) | `hc_consolidate` |
| Prune the old/trivial | `hc_forget` (use `dry_run=true` to preview what would go) |
| Start from scratch | stop the server and delete the `.db` file |

The thresholds (when something counts as "novel", "predictable", when it is
forgotten) are at the top of [`hipercampo/memory.py`](hipercampo/memory.py) —
commented and adjustable.

### Moving memories between drawers

If you started without namespaces and everything landed in `default`, or you want
a project's technical memory to live in its own drawer, you split it with SQL.
**Back up first** — this touches live memory:

```bash
python -m hipercampo.backup            # back up, always the first move
```

```sql
-- See what you have and where:
SELECT namespace, count(*) FROM memories GROUP BY 1;
SELECT id, namespace, substr(text,1,80) FROM memories WHERE namespace='default';

-- Move specific memories into their project (ids 3, 13, 14 as an example):
UPDATE memories SET namespace='proj-webshop' WHERE id IN (3,13,14);
UPDATE links    SET namespace='proj-webshop' WHERE src IN (3,13,14) AND dst IN (3,13,14);

-- Links left straddling two drawers are noise: delete them.
DELETE FROM links
 WHERE (src IN (3,13,14)) != (dst IN (3,13,14));
```

Two warnings learned the hard way: **move the links along with the memories** (or
the graph is left limping), and **compare the full text before deleting a
duplicate**, not just its beginning. When you are done, check no orphans are left:

```sql
SELECT src, dst FROM links
 WHERE src NOT IN (SELECT id FROM memories) OR dst NOT IN (SELECT id FROM memories);
```

### Backup and restore

```bash
# Backup (consistent, even with the server running):
python -m hipercampo.backup                       # -> <db>.YYYYMMDD-HHMMSS.bak
python -m hipercampo.backup C:\copies\hc.db        # -> to the path you choose

# Restore from a copy:
python -m hipercampo.backup --restore C:\copies\hc.db
```

Or simply **copy the `.db` file** with the server stopped; that is just as valid.
On Docker: `docker run --rm -v hipercampo_data:/data -v "%cd%":/backup alpine \
cp /data/hipercampo.db /backup/`.

---

## Optional semantics (for synonyms)

By default hipercampo is lexical (CPU, no GPU). If you want it to catch synonyms:

```bash
pip install -e ".[semantic]"     # brings sentence-transformers (Apache-2.0)
```

And enable it on the server with an environment variable (in your MCP config's `env`):

```json
"env": {
  "HIPERCAMPO_DB": "C:/Users/you/.hipercampo/hipercampo.db",
  "HIPERCAMPO_SEMANTIC": "1"
}
```

(Or in code: `from hipercampo import encoder; encoder.enable_semantic()`.)

It raises global retrieval MRR from **0.77 to 0.95** on the stress bench
(`python scripts/stress.py --semantic`). The first run downloads the model. See
[ATTRIBUTION.md](ATTRIBUTION.md) for the model's licences.

---

## Common problems

| Symptom | Cause / fix |
|---|---|
| `No module named hipercampo` | You did not run `pip install -e .` in the project folder. |
| Claude does not see the tools | Restart the client after editing the config; check the path/command is right. |
| The `hipercampo` command does not exist | Use `python -m hipercampo.server` (the console script may not be on your PATH). |
| Docker: "cannot access stdin" | `-i` is missing from `docker run` (MCP speaks over stdin). |
| Memory "gets lost" | On Docker, check you are mounting the `hipercampo_data` volume. |
