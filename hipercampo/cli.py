"""
hipercampo CLI — for use from the terminal and, above all, from HOOKS
("synaptic" mode: the memory fires on its own on every turn of the conversation).

    hipercampo serve                 # starts the MCP server (stdio)
    hipercampo assist "text"         # what's needed right now? (for hooks)
    hipercampo recall "query"        # retrieve
    hipercampo remember "text"       # store (respects the surprise veto)
    hipercampo muse "topic"          # inspiration: indirect and dormant connections
    hipercampo sleep                 # consolidate + forget + dream
    hipercampo stats                 # memory status
    hipercampo backup [dest]         # consistent backup
    hipercampo servers               # which MCP servers are alive and since when
    hipercampo restart               # terminate them after an upgrade (client relaunches)
    hipercampo log [-f] [-g text]    # what it decided and why (live with -f)
    hipercampo identity              # what's been learned while working
    hipercampo enable|disable        # turn hipercampo on/off for THIS project
    hipercampo projects              # where it is on
    hipercampo doctor                # diagnosis: path, permissions, version, deps
    hipercampo version

Variables: HIPERCAMPO_DB, HIPERCAMPO_NAMESPACE, HIPERCAMPO_SEMANTIC,
HIPERCAMPO_AUTOSLEEP_EVERY, HIPERCAMPO_MAX_MEMORIES, HIPERCAMPO_REDACT_SECRETS,
HIPERCAMPO_FORCE_ENABLED (bypass the per-project opt-in gate; CI/embedded).
"""

import argparse
import json
import os
import re
import sys
import time
from contextlib import contextmanager
from typing import Any

from .support import audit, budget

try:                                                  # UTF-8 output on Windows
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
except Exception:
    pass


def _ns(args=None) -> str:
    """The context to act on: --namespace if given, otherwise the one from the environment."""
    return (getattr(args, "namespace", None)
            or os.environ.get("HIPERCAMPO_NAMESPACE", "default"))


def _hc():
    from .support.config import db_path
    from .cycle.memory import Hipercampo
    return Hipercampo(db_path(), namespace=_ns())


@contextmanager
def _store(namespace: str):
    """Opens a Store and CLOSES it no matter what.

    Half a dozen commands used to repeat the same `try/finally`, and
    forgetting it leaves a live descriptor —on Windows, it also locks the
    .db. With this, closing no longer depends on remembering to."""
    from .support.config import db_path
    from .storage.store import Store
    s = Store(db_path(), namespace=namespace)
    try:
        yield s
    finally:
        s.close()


def _contexts() -> list[str]:
    """Every context that exists in the file, sorted."""
    with _store("default") as s:
        return sorted({m["namespace"] for m in s.dump(all_namespaces=True)})


def _ids(raw: str) -> list[int]:
    """Turns '3,7,9' into [3, 7, 9]. Raises ValueError if anything isn't an id."""
    return [int(x) for x in raw.split(",") if x.strip()]


def _nav_mode(args) -> bool | str:
    """--nav-auto overrides --nav: 'auto' decides on its own whether to navigate or scan."""
    if getattr(args, "nav_auto", False):
        return "auto"
    return getattr(args, "nav", False)


def _print(obj, plain=False):
    if plain and isinstance(obj, list):
        for h in obj:
            print(f"- {h.get('text', '')}")
    elif plain and isinstance(obj, dict) and "result" in obj:
        print(f"[{obj.get('action')}] {obj.get('why')}")
        for h in obj.get("result") or []:
            print(f"- {h.get('text', '')}")
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_hook(_args) -> int:
    """SYNAPTIC mode: built for Claude Code's UserPromptSubmit hook.

    Reads the hook's JSON from stdin, decides what's needed (assist), and
    returns the context to inject for the turn. If nothing's relevant, it
    injects nothing (stays quiet)."""
    # The hook's JSON is ALWAYS UTF-8. Reading `sys.stdin` as text uses the
    # local encoding (on Windows, cp1252) and turns "¿add it?" into garbled
    # bytes: the memory would end up storing and logging already-broken
    # text. Bytes are read instead.
    try:
        raw = sys.stdin.buffer.read()
    except (AttributeError, ValueError):          # stdin replaced (tests)
        raw = sys.stdin.read()
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", "replace")
    try:
        payload = json.loads(raw)
    except Exception:
        payload = {}

    # OPT-IN gate. The hook is the part that fires on its own, every turn, so it is
    # the part that must never run in a project that did not ask for it. Staying
    # quiet here costs nothing; speaking up in somebody else's project costs them
    # context window and mixes their work into a memory they never chose.
    #
    # The project is the DIRECTORY. Claude Code sends `cwd` in the payload; the
    # fallback exists because the hook is launched inside the project anyway, and
    # guessing wrong should mean "stay quiet", never "write somewhere unexpected".
    from .support import config as _config
    project = payload.get("cwd") or os.getcwd()
    if not _config.project_enabled(project):
        print("{}")
        return 0

    # At session START there's no question to answer: what's needed is to
    # recall who's working, so the session doesn't start from scratch.
    if payload.get("hook_event_name") == "SessionStart":
        try:
            hc = _hc()
            try:
                r = hc.identity()
            finally:
                hc.close()
        except Exception:
            print("{}")
            return 0
        if not r.get("n"):
            print("{}")
            return 0
        # Identity is paid for ONCE per session, so its budget is more
        # generous than a single turn's; but it still has a ceiling, or it
        # would grow unbounded as rules get learned.
        header = "[memory - working identity] learned in past sessions:"
        lines, spent = budget.fit_budget([header] + r["text"].splitlines(),
                                       budget.IDENTITY_BUDGET)
        audit.log("tokens", f"identity {spent['tokens']} tok"
                  + (f" (of {spent['original']})" if spent.get("original") else ""))
        print(json.dumps({
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": "\n".join(lines)},
            "suppressOutput": True}, ensure_ascii=False))
        return 0

    prompt = ""
    for key in ("prompt", "user_prompt", "userPrompt", "message", "input"):
        v = payload.get(key)
        if isinstance(v, str) and v.strip():
            prompt = v.strip()
            break
    # The IDE can slip in its own blocks (<ide_opened_file>, <system-reminder>…):
    # they aren't the user's text, so they shouldn't decide what hipercampo remembers.
    prompt = re.sub(r"<[a-zA-Z_-]+>.*?</[a-zA-Z_-]+>", " ", prompt, flags=re.S).strip()
    if not prompt:
        print("{}")
        return 0
    try:
        hc = _hc()
        try:
            r = hc.assist(prompt)
        finally:
            hc.close()
    except Exception as e:
        print(json.dumps({"systemMessage": f"hipercampo couldn't respond: {e}"}))
        return 0

    action = r.get("action")
    if action in (None, "nothing"):
        print("{}")                      # nothing relevant: don't interrupt
        return 0

    lines = [f"[memory - {action}] {r.get('why', '')}"]
    for h in r.get("result") or []:
        lines.append(f"- {h.get('text', '')}")
    if r.get("suggestion"):
        lines.append(f"(suggestion: {r['suggestion']})")
        if r.get("candidate"):
            lines.append(f"(candidate #{r['candidate']['id']}: {r['candidate']['text']})")

    # BUDGET. With no ceiling, cost grows with the memory: a consolidated
    # memory can take up half a screen and go in whole on every turn. It's
    # trimmed to what's relevant, and the trim is STATED (never a silence).
    lines, spent = budget.fit_budget(lines)

    # If NOTHING fit, what's left is a header and a notice that something's
    # missing: 46 tokens (measured) to contribute not a single fact. Worse
    # than staying quiet, because it costs the same and the model doesn't
    # even know what to ask for. So it stays quiet, which is free.
    # Note: "body" isn't just memories —a save suggestion counts too—, so
    # the header and the notice are dropped and what's left is checked.
    notice = budget._notice(spent.get("omitted", 0), spent.get("budget", 0))
    if not [ln for ln in lines[1:] if ln != notice]:
        audit.log("tokens", "0 tok: nothing fit in the budget, staying quiet",
                  budget=spent.get("budget"), original=spent.get("original"))
        print("{}")
        return 0

    audit.log("tokens", f"injected {spent['tokens']} tok"
              + (f" (of {spent['original']}, budget {spent['budget']})"
                 if spent.get("original") else ""))
    print(json.dumps({
        "hookSpecificOutput": {"hookEventName": "UserPromptSubmit",
                               "additionalContext": "\n".join(lines)},
        "suppressOutput": True}, ensure_ascii=False))
    return 0


def _describe(p: dict) -> str:
    when = (time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(p["started_at"]))
              if p.get("started_at") else "?")
    age = ""
    if p.get("started_at"):
        mins = (time.time() - p["started_at"]) / 60
        age = f" ({mins/60:.1f} h)" if mins >= 90 else f" ({mins:.0f} min)"
    line = f"  pid {p['pid']:<7} started {when}{age}"
    if p.get("db"):
        line += f"\n{'':14}DB {p['db']}"
    return line


def cmd_servers(_args) -> int:
    """Which servers are alive. Useful for a quick glance at whether one's
    been up too long (= stale code) or orphans have piled up."""
    from . import __version__
    from .support.procs import list_servers
    procs = list_servers()
    if not procs:
        print("No hipercampo MCP server is running.")
        print("(the client starts one on its own the first time it uses a tool)")
        return 0
    print(f"hipercampo {__version__} installed - {len(procs)} server(s) running:")
    for p in procs:
        print(_describe(p))
    print("\nThe process loads its code at startup: if you've upgraded hipercampo "
          "since\nthat time, that server is still serving the old version. "
          "`hipercampo restart`\nterminates them and the client spins new ones up on its own.")
    return 0


def cmd_restart(args) -> int:
    """Terminates the servers so the client relaunches them with the current code."""
    from .support.procs import list_servers, terminate
    procs = list_servers()
    if not procs:
        print("No server is running: nothing to restart.")
        print("The client will start a new one (already with the current code) when it's used.")
        return 0
    target = getattr(args, "pids", None)
    if target:                                       # close only the ones requested
        try:
            wanted = {int(x) for x in target.split(",") if x.strip()}
        except ValueError:
            print("--pids must be a comma-separated list of numbers.", file=sys.stderr)
            return 2
        procs = [p for p in procs if p["pid"] in wanted]
        if not procs:
            print("None of those pids are a running hipercampo server.")
            return 0
    print(f"{len(procs)} server(s) running:")
    for p in procs:
        print(_describe(p))
    if args.dry_run:
        print("\n(--dry-run: nothing was touched)")
        return 0

    status = terminate([p["pid"] for p in procs])
    print()
    for pid, outcome in status.items():
        print(f"  pid {pid:<7} {outcome}")
    left = [p for p in list_servers() if p["pid"] in status]
    if left:
        print("\nCOULD NOT close: " + ", ".join(str(p["pid"]) for p in left))
        print("They may belong to another user; close them by hand or restart the client.")
        return 1
    print("\nDone. NO need to start them: the MCP client spins up a new one, with the\n"
          "current code, the next time it uses a hipercampo tool.")
    return 0


def cmd_identity(_args) -> int:
    """What's been learned while working (what survives closing the session)."""
    hc = _hc()
    try:
        r = hc.identity()
        if not r.get("n"):
            print("No working identity has been learned yet.")
            print("It's built with `hc_learn` when something teaches how to work better.")
            return 0
        print(f"# working identity - {r['n']} thing(s) learned\n")
        print(r["text"])
        return 0
    finally:
        hc.close()


def cmd_list(args) -> int:
    """Dumps the memories: JSON for the VS Code viewer, or a readable table."""
    import time as _t

    from .support.config import db_path
    ns = _ns(args)
    with _store(ns) as s:
        rows = s.dump(all_namespaces=args.all_namespaces,
                       include_dormant=args.include_dormant,
                       kind=args.kind, limit=args.limit, order=args.sort)

    if args.json:
        print(json.dumps({"namespace": ns, "all_namespaces": args.all_namespaces,
                          "db": os.path.abspath(db_path()),
                          "count": len(rows), "memories": rows},
                         ensure_ascii=False, default=str))
        return 0

    if not rows:
        print("No memories match this criteria.")
        return 0
    now = _t.time()
    print(f"{len(rows)} memory(ies)"
          + (" - whole file" if args.all_namespaces else f" - context «{ns}»") + "\n")
    for m in rows:
        age_d = (now - m["last_access"]) / 86400
        marks = "".join(c for c, on in (("\U0001f4a4", m["dormant"]),
                                        ("\U0001f4e6", m["consolidated"]),
                                        ("↩", m["superseded"])) if on)
        head = f"#{m['id']} [{m['kind']}]"
        if args.all_namespaces:
            head += f" ⟨{m['namespace']}⟩"
        text = m["text"].replace("\n", " ")
        if len(text) > 100:
            text = text[:97] + "…"
        print(f"{head} {marks}")
        print(f"   {text}")
        print(f"   imp {m['importance']:.2f} - conf {m['confidence']:.2f} - "
              f"strength {m['strength']:.2f} - uses {m['access_count']} - "
              f"seen {age_d:.0f}d ago")
    return 0


def cmd_graph(args) -> int:
    """Dumps the association graph (nodes + edges) as JSON for the viewer's map."""
    from .support.config import db_path, paused
    ns = _ns(args)
    with _store(ns) as s:
        nodes = s.dump(all_namespaces=args.all_namespaces, include_dormant=True)
        edges = s.links_dump(all_namespaces=args.all_namespaces)
    # Only edges whose BOTH ends are among the shown nodes (no dangling ones).
    ids = {n["id"] for n in nodes}
    edges = [e for e in edges if e["src"] in ids and e["dst"] in ids]
    print(json.dumps({"namespace": ns, "all_namespaces": args.all_namespaces,
                      "db": os.path.abspath(db_path()), "paused": paused(args.project),
                      "nodes": nodes, "edges": edges}, ensure_ascii=False, default=str))
    return 0


def cmd_dream(args) -> int:
    """Proposes BRIDGES between memories that share a common associate but
    aren't connected: ideas —hypotheses— the memory suggests. In DRY-RUN:
    just shows them, doesn't persist or contaminate the evidence (that's
    sleep's rule)."""
    cap = max(1, int(getattr(args, "max", 8)))
    if getattr(args, "all_namespaces", False):
        from .support.config import db_path
        from .cycle.memory import Hipercampo
        nss = _contexts()
        bridges: list[dict] = []
        diagnostics: dict[str, dict] = {}
        for ns in nss:
            hc = Hipercampo(db_path(), namespace=ns)
            try:
                dream = hc.dream(max_bridges=cap, dry_run=True)
                diagnostics[ns] = dream.get("diagnostic", {}) if isinstance(dream, dict) else {}
                found = dream.get("bridges", []) if isinstance(dream, dict) else []
                if isinstance(found, list):
                    for b in found:
                        bridges.append({**b, "context": ns})
            finally:
                hc.close()
        bridges.sort(key=lambda b: b.get("similarity", 0), reverse=True)
        d = {"bridges": bridges[:cap], "dry_run": True, "diagnostic": {"contexts": diagnostics}}
    else:
        hc = _hc()
        try:
            d = hc.dream(max_bridges=cap, dry_run=True)
        finally:
            hc.close()
    if getattr(args, "json", False):
        print(json.dumps(d, ensure_ascii=False, default=str))
    else:
        # A separate name: `bridges` above is a list[dict] built for the
        # all-contexts branch, while this one comes out of a dict of `object`.
        found = d.get("bridges", [])
        for b in found if isinstance(found, list) else []:
            print(f"- {b['hypothesis']}")
        if not found:
            print("No new ideas for now (nothing to connect).")
    return 0


def cmd_dormant(args) -> int:
    """Makes memories dormant (or wakes them with --wake) by id. Writes:
    only the own context. It's the viewer's reversible "forget", distinct
    from purging (physical)."""
    ns = _ns(args)
    try:
        ids = _ids(args.ids)
    except ValueError:
        print("--ids must be a comma-separated list of numbers.", file=sys.stderr)
        return 2
    with _store(ns) as s:
        s.set_dormant(ids, dormant=not args.wake)
    key = "awakened" if args.wake else "dormant"
    print(json.dumps({key: ids, "namespace": ns}, ensure_ascii=False))
    return 0


def cmd_projects(args) -> int:
    """Turn hipercampo on or off for a project, and list where it is on.

    The project is the DIRECTORY. That is forced, not chosen: a server registered
    at user scope carries one namespace, so every project without its own
    `.mcp.json` shares it and the namespace cannot tell two projects apart.
    """
    from .support import config
    target = os.path.abspath(getattr(args, "path", None) or os.getcwd())

    if args.cmd in ("enable", "disable"):
        config.set_project_enabled(target, args.cmd == "enable")
        print(json.dumps({"project": target, "enabled": args.cmd == "enable"},
                         ensure_ascii=False))
        return 0

    registry = config.enabled_projects()
    out: dict[str, Any] = {
        "here": target,
        "enabled_here": config.project_enabled(target),
        "opt_in_adopted": registry is not None,
        "projects": registry or [],
    }
    if registry is None:
        # Say it out loud rather than pretending the list is empty. An upgrade must
        # not switch off a working setup in silence.
        out["note"] = ("opt-in is not configured yet, so hipercampo stays on "
                       "wherever it already has memory. The first `hipercampo "
                       "enable`/`disable` adopts opt-in, and from then on any "
                       "project not on the list is off.")
    if getattr(args, "json", False):
        print(json.dumps(out, ensure_ascii=False))
        return 0
    print(f"here:    {out['here']}")
    print(f"enabled: {out['enabled_here']}")
    if out.get("note"):
        print(f"\nnote: {out['note']}")
    elif registry:
        print("\nactive in:")
        for p in registry:
            print(f"  {p}")
    return 0


def cmd_budget(args) -> int:
    """Views or sets the hook's token budget (what the memory injects per
    turn). Persisted next to the .db and honored by the hook on the next
    turn, without restarting anything. The HIPERCAMPO_HOOK_BUDGET variable,
    if set, overrides this."""
    from .support import config
    if getattr(args, "reset", False):
        config.set_hook_budget(None)
    elif args.set is not None:
        config.set_hook_budget(max(0, int(args.set)))
    env = (os.environ.get("HIPERCAMPO_HOOK_BUDGET") or "").strip()
    persisted = config.hook_budget_persisted()
    if env.isdigit():
        effective, source = int(env), "environment"
    elif persisted is not None:
        effective, source = persisted, "saved"
    else:
        effective, source = 350, "default"
    print(json.dumps({"hook_budget": effective, "source": source,
                      "saved": persisted, "default": 350}, ensure_ascii=False))
    return 0


def cmd_facts(args) -> int:
    """Dumps the structured facts (SUBJECT/PREDICATE/OBJECT/TIME/SOURCE) of
    the context — the VSA differentiator, invisible until now. No hv blob.
    With --all-namespaces, aggregates from ALL contexts (each one tagged)."""
    import json as _json
    current_only = getattr(args, "current", False)

    def _facts_of(ns):
        with _store(ns) as s:
            return [{"id": r["id"], "fields": _json.loads(r["fields"]),
                     "source": r["source"], "valid_from": r["valid_from"],
                     "valid_to": r["valid_to"], "current": r["valid_to"] is None,
                     "context": ns}
                    for r in s.all_facts(only_current=current_only)]

    if getattr(args, "all_namespaces", False):
        facts = [h for ns in _contexts() for h in _facts_of(ns)]
        ns = "*"
    else:
        ns = _ns(args)
        facts = _facts_of(ns)
    if getattr(args, "json", False):
        print(_json.dumps({"count": len(facts), "namespace": ns, "facts": facts},
                          ensure_ascii=False, default=str))
    else:
        for h in facts:
            mark = "" if h["current"] else " (closed)"
            fields = " - ".join(f"{k}={v}" for k, v in h["fields"].items())
            print(f"#{h['id']}{mark}  {fields}")
        if not facts:
            print("No structured facts in this context (use hc_remember_fact).")
    return 0


def cmd_reindex(args) -> int:
    """Weaves the neighbor graph (denser map + better recall). With
    --all-namespaces weaves EACH context on its own, without crossing them
    (isolation is respected)."""
    M = max(2, int(args.neighbors))
    if getattr(args, "all_namespaces", False):
        nss = _contexts()
        total = 0
        for ns in nss:
            with _store(ns) as s:
                total += s.reindex_navgraph(M=M)
        print(json.dumps({"links_woven": total, "contexts": nss}, ensure_ascii=False))
        return 0
    ns = _ns(args)
    with _store(ns) as s:
        n = s.reindex_navgraph(M=M)
    print(json.dumps({"links_woven": n, "namespace": ns}, ensure_ascii=False))
    return 0


def cmd_reclassify(args) -> int:
    """Moves OWN memories to another context (owner curation). Writes:
    only the source context; doesn't touch linked or unrelated ones.
    Relocates the links."""
    ns = _ns(args)
    dest = (args.to or "").strip()
    if not dest:
        print("Missing --to (destination context).", file=sys.stderr); return 2
    try:
        ids = _ids(args.ids)
    except ValueError:
        print("--ids must be a comma-separated list of numbers.", file=sys.stderr)
        return 2
    with _store(ns) as s:
        moved = s.reclassify(ids, dest)
    print(json.dumps({"moved": moved, "from": ns, "to": dest}, ensure_ascii=False))
    return 0


def cmd_purge(args) -> int:
    """PHYSICAL, secure deletion. Irreversible: shows what would be deleted
    first (dry run) and asks for confirmation, unless --yes. It's the
    opposite of normal forgetting, which only makes dormant; this removes
    the text from the file and reclaims the space."""
    if (args.ids is None) == (args.older_than is None):   # 0 days is valid, not "missing"
        print("Choose ONE: --ids 3,7,9  or  --older-than DAYS.", file=sys.stderr)
        return 2
    try:
        ids = _ids(args.ids) if args.ids else None
    except ValueError:
        print("--ids must be a comma-separated list of numbers.", file=sys.stderr)
        return 2
    if getattr(args, "namespace", None):
        os.environ["HIPERCAMPO_NAMESPACE"] = args.namespace   # scope to that context
    hc = _hc()
    try:
        dry = hc.purge(older_than_days=args.older_than, ids=ids, dry_run=True)
        if "error" in dry:
            print(dry["error"], file=sys.stderr); return 2
        target = dry["ids"]
        if not target:
            print("Nothing matches that criteria: nothing to purge.")
            return 0
        print(f"{len(target)} memory(ies) will be PHYSICALLY DELETED: "
              f"{', '.join(map(str, target))}")
        print("This is irreversible (not the same as forgetting, which only makes dormant).")
        if not args.yes:
            try:
                if input("Sure? type 'yes' to continue: ").strip().lower() not in (
                        "si", "sí", "s", "yes", "y"):
                    print("Cancelled."); return 0
            except EOFError:
                print("\nNo confirmation (use --yes for non-interactive). Cancelled.")
                return 1
        r = hc.purge(older_than_days=args.older_than, ids=ids, vacuum=not args.no_vacuum)
        _print(r)
        return 0
    finally:
        hc.close()


def cmd_log(args) -> int:
    """What hipercampo has decided: the log, with filters and live tailing."""
    import time as _t

    from .support import audit
    from .support.config import db_path
    audit.set_logfile(db_path())
    path = audit.logfile()
    if getattr(args, "ruta", False):
        print(path or "(log disabled: HIPERCAMPO_LOG=0)")
        return 0
    if not path:
        # Log disabled (HIPERCAMPO_LOG=0). For the viewer this ISN'T an
        # error: it's an empty log, so the Log tab shows it gracefully
        # instead of breaking. For a human, a clear notice.
        if getattr(args, "json", False):
            print(json.dumps({"path": None, "enabled": False, "entries": []},
                             ensure_ascii=False))
            return 0
        print("The log is disabled (HIPERCAMPO_LOG=0).")
        return 1

    action = "ERROR" if args.errores else args.accion

    def read(n):
        return audit.tail(n, contains=args.grep, today_only=args.hoy, action=action)

    if getattr(args, "json", False):        # structured output for the viewer
        entries = [_log_entry(ln) for ln in read(args.n if args.n else 200)]
        print(json.dumps({"path": path, "entries": entries},
                         ensure_ascii=False, default=str))
        return 0

    filters = " - ".join(f for f in (
        f"action={action}" if action else "",
        f"contains «{args.grep}»" if args.grep else "",
        "today only" if args.hoy else "") if f)
    print(f"# {path}{' - ' + filters if filters else ''}")

    lines = read(args.n)
    if not lines:
        print("(nothing matches the filter)" if filters else "(no activity yet)")
        if not args.follow:
            print("\nActions seen in the log: "
                  + (", ".join(audit.actions()) or "none"))
            return 0
    else:
        print("\n".join(lines))

    if not args.follow:
        return 0
    print("\n-- live (Ctrl+C to exit) --", flush=True)
    seen = set(lines)
    try:
        while True:
            _t.sleep(1.0)
            for ln in read(200):
                if ln not in seen:
                    print(ln, flush=True)
                    seen.add(ln)
    except KeyboardInterrupt:
        print("\n-- end --")
    return 0


def _log_entry(ln: str) -> dict:
    """Splits a log line into {ts, action, message} (best-effort).
    Format: 'YYYY-MM-DD HH:MM:SS action    message'."""
    ts = ln[:19]
    rest = ln[20:] if len(ln) > 20 else ""
    parts = rest.split(" ", 1)
    action = parts[0] if parts else ""
    message = parts[1].strip() if len(parts) > 1 else ""
    return {"ts": ts, "action": action, "message": message, "raw": ln}


def cmd_pause(args) -> int:
    """Pauses or resumes the memory ('do not record' mode). While paused, no
    new memories are recorded and existing ones aren't reinforced; READING
    keeps working and nothing is deleted."""
    from .support.config import set_paused
    want = not (args.cmd == "resume" or getattr(args, "off", False))
    path = os.path.abspath(getattr(args, "path", None) or os.getcwd())
    state = set_paused(want, path)
    forced = os.environ.get("HIPERCAMPO_PAUSED", "") not in ("", "0", "false", "False")
    out: dict[str, Any] = {"paused": state, "project": path}
    if forced and not want:
        out["notice"] = ("HIPERCAMPO_PAUSED is set in the environment and overrides "
                           "the switch: it stays paused until that's removed.")
    print(json.dumps(out, ensure_ascii=False))
    return 0


def cmd_tokens(_args) -> int:
    """The token BILL, in JSON: the house's signature trait made visible.
    How much the memory has cost, how much the budget saved, and a time
    series to chart it. Always an ESTIMATE and stated as such (Claude's
    tokenizer isn't public)."""
    from .support import audit, budget
    from .support.config import db_path
    audit.set_logfile(db_path())
    summary = audit.token_cost()
    summary["hook_budget"] = budget.HOOK_BUDGET
    summary["identity_budget"] = budget.IDENTITY_BUDGET
    summary["estimated"] = True
    summary["method"] = budget.method()
    # time series: each injection with its cost (for the viewer's chart)
    series = []
    for e in (_log_entry(ln) for ln in audit.tail(0, action="tokens")):
        m = re.search(r"(\d+) tok", e["message"])
        if m:
            series.append({"ts": e["ts"], "tok": int(m.group(1)),
                          "label": e["message"].split(" ", 1)[0]})
    print(json.dumps({"summary": summary, "series": series[-200:]},
                     ensure_ascii=False, default=str))
    return 0


def cmd_status(_args) -> int:
    """Health status as JSON for the viewer: CLI, database, MCP server and
    log. It's the memory's 'control panel', unadorned: says what's alive."""
    from . import __version__
    from .support import audit
    from .support import config
    from .support.config import db_path, paused
    from .support.procs import list_servers
    path = os.path.abspath(db_path())
    here = os.path.abspath(getattr(_args, "project", None) or os.getcwd())
    out: dict[str, Any] = {"version": __version__, "python": sys.version.split()[0],
                           "paused": paused(here), "db": {"path": path},
                           # Per-project opt-in, for the viewer to show and toggle.
                           # `adopted` is not derivable from `enabled`: not-yet-adopted
                           # also reads as enabled, and the viewer needs to say which,
                           # or an upgraded user cannot tell "on" from "not configured".
                           "project": {"path": here,
                                       "enabled": config.project_enabled(here),
                                       "adopted": config.opt_in_adopted()}}

    try:
        out["db"]["exists"] = os.path.isfile(path)
        out["db"]["size"] = os.path.getsize(path) if os.path.isfile(path) else 0
        folder = os.path.dirname(path) or "."
        out["db"]["writable"] = os.access(folder, os.W_OK)
    except OSError as e:
        out["db"]["error"] = str(e)

    try:
        hc = _hc()
        try:
            health = hc.store.health(full=False)
            out["db"]["schema"] = hc.store.db.execute("PRAGMA user_version").fetchone()[0]
            from .storage import migrations
            out["db"]["schema_expected"] = migrations.SCHEMA_VERSION
            out["db"]["healthy"] = bool(health.get("healthy"))
            out["db"]["integrity"] = health.get("integrity")
            # Count of the WHOLE file (not just the current context), so it
            # matches what the viewer shows ("all contexts").
            everything = hc.store.dump(all_namespaces=True, include_dormant=True)
            by_ctx: dict[str, int] = {}
            for m in everything:
                by_ctx[m["namespace"]] = by_ctx.get(m["namespace"], 0) + 1
            out["stats"] = {
                "total": len(everything),
                "active_episodic": sum(1 for m in everything if m["kind"] == "episodic"
                                          and not m["dormant"] and not m["consolidated"]),
                "semantic": sum(1 for m in everything if m["kind"] == "semantic"),
                "dormant": sum(1 for m in everything if m["dormant"]),
                "archived": sum(1 for m in everything if m["consolidated"]),
                "by_context": by_ctx,
                "tokens": hc.stats().get("tokens"),
            }
        finally:
            hc.close()
    except Exception as e:
        out["db"]["error"] = str(e)

    # MCP server: running or not (the client starts it when a tool is used).
    try:
        from .storage.store import Store
        procs = list_servers()
        for p in procs:                        # is it serving OLD code after an upgrade?
            p["version"] = None
            p["stale"] = False
            if p.get("db") and p.get("namespace"):
                try:
                    s = Store(p["db"], namespace=p["namespace"])
                    try:
                        ver = s.get_meta("server_version")
                        pid = s.get_meta("server_pid")
                    finally:
                        s.close()
                    if ver and str(pid) == str(p["pid"]):
                        p["version"] = ver
                        p["stale"] = ver != __version__
                except Exception:
                    pass
        out["mcp"] = {"running": len(procs), "servers": procs,
                      "installed": __version__}
    except Exception as e:
        out["mcp"] = {"error": str(e)}

    # Log (hooks and decisions): enabled, path and last activity (a sign of life).
    audit.set_logfile(db_path())
    log = audit.logfile()
    reg: dict[str, Any] = {"enabled": bool(log), "path": log}
    if log and os.path.isfile(log):
        reg["last_activity"] = os.path.getmtime(log)
        reg["size"] = os.path.getsize(log)
    out["log"] = reg

    print(json.dumps(out, ensure_ascii=False, default=str))
    return 0


def cmd_doctor(_args) -> int:
    """Quick diagnosis: is everything in place to work?"""
    from . import __version__
    from .support.config import db_path
    path = db_path()
    print(f"hipercampo {__version__}")
    print(f"python     {sys.version.split()[0]}")
    print(f"DB         {os.path.abspath(path)}")
    folder = os.path.dirname(os.path.abspath(path)) or "."
    print(f"folder     {'exists' if os.path.isdir(folder) else 'DOES NOT exist'}"
          f" - {'writable' if os.access(folder, os.W_OK) else 'NO write permission'}")
    print(f"namespace  {os.environ.get('HIPERCAMPO_NAMESPACE', 'default')}")
    for mod, label in (("numpy", "numpy"), ("mcp", "mcp (server)"),
                          ("sentence_transformers", "semantic (optional)")):
        try:
            __import__(mod)
            print(f"dep        {label}: OK")
        except Exception:
            print(f"dep        {label}: not installed")
    try:
        hc = _hc()
        from .storage import migrations
        health = hc.store.health(full=getattr(_args, "full", False))
        print(f"schema     version {hc.store.db.execute('PRAGMA user_version').fetchone()[0]}"
              f" (expected {migrations.SCHEMA_VERSION})")
        print(f"health     {'HEALTHY' if health['healthy'] else 'HAS ISSUES'} - "
              f"{health['check']}={health['integrity']} - "
              f"writable={health['writable']}")
        print("memory     ", json.dumps(hc.stats(), ensure_ascii=False, default=str))
        hc.close()
        return 0
    except Exception as e:
        print(f"ERROR opening the memory: {e}")
        return 1


# Command -> function. `pause` and `resume` are the same command seen from
# its two sides, and cmd_pause tells them apart via `args.cmd`.
_COMMANDS = {
    "doctor": cmd_doctor, "hook": cmd_hook, "identity": cmd_identity,
    "servers": cmd_servers, "restart": cmd_restart, "facts": cmd_facts,
    "reindex": cmd_reindex, "budget": cmd_budget, "reclassify": cmd_reclassify,
    "dream": cmd_dream, "list": cmd_list, "graph": cmd_graph, "status": cmd_status,
    "tokens": cmd_tokens, "pause": cmd_pause, "resume": cmd_pause,
    "dormant": cmd_dormant, "purge": cmd_purge, "log": cmd_log,
    "enable": cmd_projects, "disable": cmd_projects, "projects": cmd_projects,
}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="hipercampo", description="Live memory for agents")
    sub = p.add_subparsers(dest="cmd")
    sub.add_parser("serve", help="start the MCP server (stdio)")
    sub.add_parser("stats", help="memory status")
    sub.add_parser("sleep", help="consolidate + forget + dream")
    dr = sub.add_parser("doctor", help="environment diagnosis")
    dr.add_argument("--full", action="store_true",
                    help="full integrity_check (slower) instead of quick_check")
    sub.add_parser("hook", help="synaptic mode: for Claude Code hooks")
    sub.add_parser("identity", help="what's been learned while working")
    sub.add_parser("servers", help="which MCP servers are running and since when")
    rs = sub.add_parser("restart", help="restart the servers after an upgrade")
    rs.add_argument("--dry-run", action="store_true",
                    help="show what would be closed, without closing anything")
    rs.add_argument("--pids", help="close ONLY these pids (comma-separated); "
                                   "by default, all of them")
    bg = sub.add_parser("budget", help="view or set the hook's token budget")
    bg.add_argument("--set", type=int, help="set the budget (tokens per turn)")
    bg.add_argument("--reset", action="store_true", help="go back to the factory default (350)")
    # Per-project opt-in. hipercampo does not switch itself on in a project nobody
    # asked it to; these are how you say yes (and the viewer calls them).
    for name, help_ in (("enable", "activate hipercampo for this project"),
                        ("disable", "deactivate hipercampo for this project")):
        sp = sub.add_parser(name, help=help_)
        sp.add_argument("path", nargs="?", help="project directory (default: current)")
    pr = sub.add_parser("projects", help="where hipercampo is active")
    pr.add_argument("path", nargs="?", help="project directory (default: current)")
    pr.add_argument("--json", action="store_true", help="JSON output (for the viewer)")
    sub.add_parser("version", help="installed version")
    for name, hlp in (("assist", "what's needed right now (hooks)"),
                          ("recall", "retrieve"), ("muse", "inspiration"),
                          ("remember", "store")):
        sp = sub.add_parser(name, help=hlp)
        sp.add_argument("text", nargs="*", help="text or query")
        sp.add_argument("--plain", action="store_true", help="readable output, not JSON")
        if name in ("assist", "recall"):
            sp.add_argument("--nav", action="store_true",
                            help="use the navigable graph as a candidate generator")
            sp.add_argument("--nav-auto", action="store_true",
                            help="decide automatically whether to navigate or scan")
            sp.add_argument("--max-scan", type=int,
                            help="cap how many memories to scan at most")
        if name == "remember":
            sp.add_argument("--importance", type=float, default=0.5)
            sp.add_argument("--confidence", type=float, default=0.5)
    ft = sub.add_parser("facts", help="view the structured FACTS (roles) of the context")
    ft.add_argument("--json", action="store_true", help="JSON output (for the viewer)")
    ft.add_argument("--current", action="store_true", help="only current ones (not closed)")
    ft.add_argument("--namespace", help="context (defaults to the environment's)")
    ft.add_argument("--all-namespaces", action="store_true",
                    help="facts from ALL contexts (tagged)")
    ri = sub.add_parser("reindex", help="weave the neighbor graph (denser map, better recall)")
    ri.add_argument("--neighbors", type=int, default=12, help="neighbors per memory")
    ri.add_argument("--namespace", help="context (defaults to the environment's)")
    ri.add_argument("--all-namespaces", action="store_true",
                    help="weave EACH context on its own (without crossing them)")
    rc = sub.add_parser("reclassify", help="move OWN memories to another context (curation)")
    rc.add_argument("--ids", required=True, help="comma-separated ids")
    rc.add_argument("--to", required=True, help="destination context")
    rc.add_argument("--namespace", help="source context (defaults to the environment's)")
    dm2 = sub.add_parser("dream", help="propose BRIDGES between distant memories (ideas)")
    dm2.add_argument("--json", action="store_true", help="JSON output (for the viewer)")
    dm2.add_argument("--max", type=int, default=8, help="how many hypotheses at most")
    dm2.add_argument("--all-namespaces", action="store_true",
                     help="ideas from ALL contexts (each on its own)")
    bk = sub.add_parser("backup", help="consistent backup")
    bk.add_argument("dest", nargs="?")
    ls = sub.add_parser("list", help="dump the memories (table or --json for the UI)")
    ls.add_argument("--json", action="store_true", help="JSON output (for the viewer)")
    ls.add_argument("--all-namespaces", "-A", action="store_true",
                    help="the whole file, not just the current context")
    ls.add_argument("--namespace", help="view a specific context (default: the current one)")
    ls.add_argument("--include-dormant", action="store_true",
                    help="include dormant ones (forgotten-but-not-deleted)")
    ls.add_argument("--kind", help="filter by type: episodic, semantic…")
    ls.add_argument("--sort", default="recent",
                    choices=("recent", "importance", "access", "created"),
                    help="ordering (default: most recently accessed)")
    ls.add_argument("--limit", type=int, help="how many at most")
    gr = sub.add_parser("graph", help="dump the graph (nodes + edges) for the viewer")
    gr.add_argument("--all-namespaces", "-A", action="store_true")
    gr.add_argument("--namespace", help="context (default: the current one)")
    gr.add_argument("--include-dormant", action="store_true", default=True)
    gr.add_argument("--project", help="project directory, for the pause check (default: cwd)")
    st = sub.add_parser("status", help="health status as JSON (CLI, DB, MCP, log)")
    st.add_argument("--project", help="project directory, for the pause check (default: cwd)")
    pa = sub.add_parser("pause", help="PAUSE the memory for a project: stop recording ('do not record' mode)")
    pa.add_argument("--off", action="store_true", help="resume instead of pausing")
    pa.add_argument("path", nargs="?", help="project directory (default: cwd)")
    re_ = sub.add_parser("resume", help="resume the memory for a project after a pause")
    re_.add_argument("path", nargs="?", help="project directory (default: cwd)")
    tk = sub.add_parser("tokens", help="token bill as JSON (for the viewer)")
    tk.add_argument("--json", action="store_true", default=True, help=argparse.SUPPRESS)
    dm = sub.add_parser("dormant", help="make memories dormant or wake them by id")
    dm.add_argument("--ids", required=True, help="comma-separated ids")
    dm.add_argument("--wake", action="store_true", help="wake instead of making dormant")
    dm.add_argument("--namespace", help="context (default: the current one)")
    pg = sub.add_parser("purge", help="PHYSICAL, secure deletion (secrets, GDPR, space)")
    pg.add_argument("--ids", help="specific ids to delete, comma-separated")
    pg.add_argument("--older-than", type=float, metavar="DAYS",
                    help="purge DORMANT memories unaccessed for more than N days")
    pg.add_argument("--no-vacuum", action="store_true",
                    help="don't reclaim space (faster; the text still gets overwritten)")
    pg.add_argument("--namespace", help="context (default: the current one)")
    pg.add_argument("--yes", action="store_true", help="don't ask for confirmation")
    lg = sub.add_parser("log", help="what hipercampo has decided lately")
    lg.add_argument("-n", type=int, default=20, help="how many lines (0 = all)")
    lg.add_argument("-f", "--follow", action="store_true",
                    help="keep watching live (Ctrl+C to exit)")
    lg.add_argument("-g", "--grep", metavar="TEXT",
                    help="only lines containing this (ignores accents)")
    lg.add_argument("-a", "--accion", metavar="ACTION",
                    help="only that action: recall, remember, sleep, dream, ERROR…")
    lg.add_argument("--hoy", action="store_true", help="only today's")
    lg.add_argument("--errores", action="store_true", help="shortcut for --accion ERROR")
    lg.add_argument("--ruta", action="store_true", help="only say where the file is")
    lg.add_argument("--json", action="store_true", help="JSON output (for the viewer)")
    args = p.parse_args(argv)

    if args.cmd in (None, "version"):
        from . import __version__
        print(__version__ if args.cmd == "version" else f"hipercampo {__version__}\n")
        if args.cmd is None:
            p.print_help()
        return 0
    # Commands that are self-contained (open whatever they need and close
    # it). Used to be a ladder of twenty `if args.cmd == ...`: a table says
    # the same thing, and adding a command no longer means touching two
    # places and forgetting one.
    if args.cmd in _COMMANDS:
        return _COMMANDS[args.cmd](args)
    if args.cmd == "serve":
        from .server import main as serve
        serve(); return 0
    if args.cmd == "backup":
        from .storage.backup import backup
        print("Backup created at:", backup(args.dest)); return 0

    # And the ones that operate on an open memory, which gets closed no matter what.
    hc = _hc()
    try:
        if args.cmd == "stats":
            _print(hc.stats())
        elif args.cmd == "sleep":
            _print(hc.sleep())
        else:
            text = " ".join(getattr(args, "text", []) or []).strip()
            if not text:
                print("Missing text.", file=sys.stderr); return 2
            if args.cmd == "assist":
                _print(hc.assist(text, max_scan=getattr(args, "max_scan", None),
                                 nav=_nav_mode(args)), plain=args.plain)
            elif args.cmd == "recall":
                _print(hc.recall(text, max_scan=getattr(args, "max_scan", None),
                                 nav=_nav_mode(args)), plain=args.plain)
            elif args.cmd == "muse":
                _print(hc.muse(text), plain=args.plain)
            elif args.cmd == "remember":
                _print(hc.remember(text, args.importance, args.confidence))
        return 0
    finally:
        hc.close()


if __name__ == "__main__":
    raise SystemExit(main())
