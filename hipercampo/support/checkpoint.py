"""Where a session left off, so the next one starts from there.

A long session is expensive because every turn re-sends the whole history.
The way out is a NEW session, and that is only free if nothing is lost — which
until now depended on someone calling `hc_remember` at the right moment, and
in practice nobody did. So the hook writes this on its own, at PreCompact and
SessionEnd, and SessionStart reads it back.

Extractive, no LLM: what a transcript states for certain (the title Claude
Code gave the session, what was asked, which files changed, what was
committed, the last thing said). Facts are reliable this way; INTENT is not —
half the prompts in a real session are "si". The title and the last assistant
message carry the intent, which is why they are kept.

ONE checkpoint per project, overwritten, never accumulated: it is a bookmark,
not a memory. It lives in a file next to the .db rather than in the memory
store, so it never competes in recall with what was actually learned.
"""

import json
import os
import re
import subprocess
import time

from . import budget, config

# A prompt shorter than this ("si", "ok", "dale") says nothing on its own.
_MIN_PROMPT_CHARS = 15
# Closing tags can carry attributes too: </pasted_content id="717f">.
_TAG = re.compile(r"<([a-zA-Z_-]+)[^>]*>.*?</\1[^>]*>", re.S)
# What was PASTED is often the request itself ("I have this feedback: …"),
# so only its wrapper goes, not its content.
_PASTE = re.compile(r"</?pasted_content[^>]*>")
_EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def _file() -> str:
    return os.path.join(os.path.dirname(os.path.abspath(config.db_path())) or ".",
                        "hipercampo.checkpoints.json")


def _text_of(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content
                        if isinstance(b, dict) and b.get("type") == "text")
    return ""


def _clean(text: str) -> str:
    # The IDE and pasted blocks aren't the user's own words (see cli.cmd_hook).
    return " ".join(_TAG.sub(" ", _PASTE.sub(" ", text)).split())


# Git's own confirmation of a commit: "[main 0beb734] Subject". Parsing the
# COMMAND instead was wrong both ways on a real session: a command that only
# mentioned `git commit` counted as one, and a multi-line -m "…" was missed.
_COMMITTED = re.compile(r"^\[[^\]\s]+(?: \([^)]*\))? [0-9a-f]{7,}\] (.+)$", re.M)
_SHELL_TOOLS = ("Bash", "PowerShell")


def _result_text(block: dict) -> str:
    content = block.get("content")
    return content if isinstance(content, str) else _text_of(content)


def extract(transcript_path: str, cwd: str | None = None) -> dict | None:
    """Reads a Claude Code transcript (.jsonl). None if there is nothing worth
    keeping — an empty session must not overwrite real work with nothing."""
    title, prompts, files, commits, last_said = "", [], [], [], ""
    pending: dict[str, tuple[str, str]] = {}      # tool_use id -> (kind, value)
    failed: set[str] = set()
    try:
        with open(transcript_path, encoding="utf-8") as f:
            for raw in f:
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                kind = row.get("type")
                if kind == "ai-title" and row.get("aiTitle"):
                    title = str(row["aiTitle"])
                    continue
                msg = row.get("message") or {}
                content = msg.get("content")
                if kind == "user" and not row.get("isMeta") \
                        and not row.get("isCompactSummary"):
                    if isinstance(content, list):
                        for b in content:
                            if not (isinstance(b, dict) and b.get("type") == "tool_result"):
                                continue
                            tid = str(b.get("tool_use_id", ""))
                            if b.get("is_error"):
                                failed.add(tid)
                            elif pending.get(tid, ("", ""))[0] == "commit?":
                                m = _COMMITTED.search(_result_text(b))
                                if m:
                                    pending[tid] = ("commit", m.group(1).strip())
                    text = _clean(_text_of(content))
                    if len(text) >= _MIN_PROMPT_CHARS:
                        prompts.append(text)
                elif kind == "assistant" and isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict):
                            continue
                        if b.get("type") == "text" and b.get("text", "").strip():
                            last_said = " ".join(b["text"].split())
                        elif b.get("type") == "tool_use":
                            args = b.get("input") or {}
                            if b.get("name") in _EDIT_TOOLS and args.get("file_path"):
                                pending[str(b.get("id", ""))] = ("file", str(args["file_path"]))
                            elif b.get("name") in _SHELL_TOOLS and \
                                    "git commit" in str(args.get("command", "")):
                                # A candidate only: what git answers decides.
                                pending[str(b.get("id", ""))] = ("commit?", "")
    except OSError:
        return None

    # Only what actually happened: a failed Edit changed nothing.
    for tool_id, (what, value) in pending.items():
        if tool_id in failed:
            continue
        if what == "file":
            value = _relative(value, cwd)
            if value not in files:
                files.append(value)
        elif what == "commit" and value not in commits:
            commits.append(value)

    if not prompts and not files and not commits:
        return None
    return {"title": title, "prompts": prompts, "files": files,
            "commits": commits, "uncommitted": _uncommitted(cwd),
            "last_said": last_said, "at": time.time()}


def _uncommitted(cwd: str | None) -> list[str]:
    """What the session left changed but NOT committed. Measured on a real
    resume: the bookmark said "next: commit what is pending" and the WHY of
    it lived only in that uncommitted diff, which the next session had to go
    and find. The transcript can't say this; git can, as a fact."""
    if not cwd:
        return []
    try:
        out = subprocess.run(["git", "status", "--porcelain"], cwd=cwd,
                             capture_output=True, text=True, timeout=3)
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0:
        return []
    return [ln[3:].strip().strip('"') for ln in out.stdout.splitlines() if len(ln) > 3]


def _relative(path: str, cwd: str | None) -> str:
    if cwd:
        try:
            rel = os.path.relpath(path, cwd)
            if not rel.startswith(".."):
                return rel.replace(os.sep, "/")
        except ValueError:                     # other drive on Windows
            pass
    return path.replace(os.sep, "/")


def _load() -> dict:
    try:
        with open(_file(), encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(project: str, checkpoint: dict, session_id: str = "", reason: str = "") -> None:
    data = _load()
    data[config._normalise(project)] = dict(checkpoint, session_id=session_id,
                                            reason=reason)
    path = _file()
    tmp = f"{path}.{os.getpid()}.tmp"
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)       # two sessions ending at once: last one wins, whole
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass


def load(project: str) -> dict | None:
    return _load().get(config._normalise(project))


def _last_sentences(text: str, max_tokens: int) -> str:
    """The END of a message, whole sentences: that is where the next step or
    the open question usually is, not in the opening line."""
    kept: list[str] = []
    for sentence in reversed(re.split(r"(?<=[.!?])\s+", text)):
        if kept and budget.estimate_tokens(" ".join([sentence] + kept)) > max_tokens:
            break
        kept.insert(0, sentence)
    out = " ".join(kept)
    if budget.estimate_tokens(out) <= max_tokens:
        return out
    return budget.headline(out, max_tokens)


def render(cp: dict, max_tokens: int | None = None) -> list[str]:
    """Lines for SessionStart, shown in reading order but CUT in priority
    order. Measured on a real session: trimming from the bottom dropped
    "last said" — the line that carries the next step — and kept the file
    list. So the least useful lines go first, and the cut is silent: a
    bookmark has no hc_recall behind it to point to."""
    max_tokens = budget.CHECKPOINT_BUDGET if max_tokens is None else max_tokens
    headline = budget.headline
    when = time.strftime("%Y-%m-%d %H:%M", time.localtime(cp.get("at") or 0))
    reason = f", {cp['reason']}" if cp.get("reason") else ""
    # (priority, line): 0 is kept longest.
    items: list[tuple[int, str]] = []
    if cp.get("title"):
        items.append((1, f"  - topic: {cp['title']}"))
    prompts = cp.get("prompts") or []
    if prompts:
        items.append((2, f"  - asked: {headline(prompts[0], 40)}"))
        for p in prompts[1:][-2:]:
            items.append((6, f"  - then: {headline(p, 30)}"))
    files = cp.get("files") or []
    if files:
        more = f" (+{len(files) - 5} more)" if len(files) > 5 else ""
        items.append((4, f"  - changed: {', '.join(files[-5:])}{more}"))
    for c in (cp.get("commits") or [])[-3:]:
        items.append((3, f"  - committed: {c}"))
    pending = cp.get("uncommitted") or []
    if pending:
        more = f" (+{len(pending) - 5} more)" if len(pending) > 5 else ""
        items.append((1, f"  - uncommitted (the diff holds the why): "
                         f"{', '.join(pending[:5])}{more}"))
    if cp.get("last_said"):
        items.append((0, f"  - last said: {_last_sentences(cp['last_said'], 60)}"))

    header = f"[memory - where we left off] last session here ({when}{reason}):"
    cost = budget.estimate_tokens
    while items and max_tokens > 0 and (
            cost(header) + sum(cost(ln) for _, ln in items) > max_tokens):
        items.remove(max(items, key=lambda it: it[0]))
    return [header] + [ln for _, ln in items]
