"""
Decision log: so hipercampo can account for WHAT it does and WHY.

A memory that decides on its own (save or not, forget, dream, stay quiet)
has to be auditable. Every relevant decision gets logged:

  - to **stderr**, which is where the MCP client shows the server's output;
  - and to a **file** next to the database, so it can be reviewed later
    (`hipercampo log`). Disabled with HIPERCAMPO_LOG=0.

Readable format, one line per decision:
    18:42:07 remember  stored id=12 · novelty=0.42 surprise=0.81
    18:42:31 recall    abstention · nothing stands out from the noise (n=14)
"""

import os
import re
import sys
import time
import unicodedata
from pathlib import Path

_ENABLED = os.environ.get("HIPERCAMPO_LOG", "1") != "0"
_PATH: Path | None = None


def set_logfile(db_path: str) -> None:
    """The log lives next to the database (same place, easy to find)."""
    global _PATH
    if not _ENABLED:
        return
    try:
        p = Path(db_path).resolve().parent / "hipercampo.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        _PATH = p
    except Exception:
        _PATH = None


def _to_stderr(line: str) -> None:
    """Writes to stderr without breaking or garbling the output, which is
    where the MCP client reads what we say. Two different targets and a
    trap in the middle:

      - PIPE (the MCP case): Python doesn't see a console and falls back to
        the local encoding, which on Windows is cp1252; the client on the
        other end decodes UTF-8 and 'abstención' arrives as broken
        characters. So here UTF-8 bytes are written by hand, without
        depending on the machine's locale.
      - CONSOLE: its encoding is respected. If it can't handle 'ó' or '·',
        it degrades to readable ASCII ('abstencion', '|') instead of
        emitting garbage.

    The log FILE always keeps the original in UTF-8."""
    buf = getattr(sys.stderr, "buffer", None)
    if buf is not None and not sys.stderr.isatty():
        buf.write((line + "\n").encode("utf-8", "replace"))
        buf.flush()
        return
    enc = getattr(sys.stderr, "encoding", None) or "utf-8"
    try:
        line.encode(enc)
    except (UnicodeEncodeError, LookupError):
        flat = unicodedata.normalize("NFKD", line.replace("·", "|"))
        line = flat.encode("ascii", "ignore").decode("ascii")
    print(line, file=sys.stderr, flush=True)


def _one_line(value) -> str:
    """Collapse anything that would break the one-entry-per-line format.

    The log records fragments of what the user wrote, and a memory containing a
    line break used to split its entry in two: the second half carried no
    timestamp and no action, so `tail` returned it as an entry of its own and the
    viewer rendered it as "?". Newlines, carriage returns and tabs become single
    spaces — the entry stays readable and stays on one line."""
    text = str(value)
    for ch in ("\r\n", "\n", "\r", "\t"):
        text = text.replace(ch, " ")
    return text.strip()


def log(action: str, detail: str = "", **fields) -> None:
    """Logs a decision. Never raises: observability must never break
    anything."""
    if not _ENABLED:
        return
    try:
        extra = " · ".join(f"{k}={_one_line(v)}" for k, v in fields.items()
                           if v not in (None, ""))
        detail = _one_line(detail)
        line = f"{time.strftime('%H:%M:%S')} {action:<9} {detail}"
        if extra:
            line += f" · {extra}"
        _to_stderr(line)
        if _PATH is not None:
            with open(_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {action:<9} {detail}"
                        f"{' · ' + extra if extra else ''}\n")
    except Exception:
        pass


_ENTRY = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \S")


def _is_entry(line: str) -> bool:
    """A real entry starts with 'YYYY-MM-DD HH:MM:SS ' and an action."""
    return bool(_ENTRY.match(line))


def tail(n: int = 20, contains: str | None = None, today_only: bool = False,
         action: str | None = None) -> list[str]:
    """Last n lines of the log, with filters (for `hipercampo log`).

    `contains`: substring to search for (case- and accent-insensitive).
    `today_only`: only today's. `action`: only that action (recall,
    remember...)."""
    if _PATH is None or not _PATH.exists():
        return []
    try:
        lines = _PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    # Drop anything that is not a real entry. Writing now collapses newlines, but a
    # log written before that fix still holds orphaned continuation lines, and they
    # would keep showing up as entries with no action — the "?" rows in the viewer.
    # Reading is where old files get cleaned up, since the log is append-only.
    lines = [ln for ln in lines if _is_entry(ln)]
    if today_only:
        today = time.strftime("%Y-%m-%d")
        lines = [ln for ln in lines if ln.startswith(today)]
    if action:
        # the action is the 3rd column: "2026-07-23 09:00:37 recall    ..."
        lines = [ln for ln in lines if ln[20:].split(" ", 1)[0] == action]
    if contains:
        needle = _flatten(contains)
        lines = [ln for ln in lines if needle in _flatten(ln)]
    return lines[-n:] if n > 0 else lines


def _flatten(t: str) -> str:
    """Lowercase and unaccented: searching 'sueno' should find 'sueño'."""
    stripped = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in stripped if not unicodedata.combining(c)).replace("ñ", "n")


def actions() -> list[str]:
    """Which actions show up in the log (for the command's help text)."""
    seen = []
    for ln in tail(0):
        a = ln[20:].split(" ", 1)[0]
        if a and a not in seen:
            seen.append(a)
    return sorted(seen)


def token_cost() -> dict:
    """How many tokens hipercampo has injected, read straight from the log
    itself.

    If we're going to ask someone to give up part of their context window to
    a memory, the least it can do is show them the bill. This reads from the
    log instead of keeping a counter in the DB on purpose: the log already
    exists, is auditable by hand, and counting shouldn't cause writes on
    every turn.
    """
    import re
    today = time.strftime("%Y-%m-%d")
    total = today_total = turns = saved = 0
    for ln in tail(0, action="tokens"):
        # Search the MESSAGE, never the whole line. Every entry here starts
        # "YYYY-MM-DD HH:MM:SS tokens ", so `(\d+) tok` found "07 tok" — the
        # SECONDS of the clock followed by the action column — before ever
        # reaching the real figure. The bill, which is this project's whole
        # transparency argument, was reporting wall-clock seconds as tokens.
        message = ln[20:].split(" ", 1)[1] if " " in ln[20:] else ""
        m = re.search(r"(\d+) tok", message)
        if not m:
            continue
        n = int(m.group(1))
        total += n
        turns += 1
        if ln.startswith(today):
            today_total += n
        # "(of N)" is what the hook writes today; "(de N)" is what it wrote before
        # the translation. Both are accepted because a real log spans the change,
        # and matching only the new one silently reported zero savings — the whole
        # point of this counter is to show the budget doing its job.
        original = re.search(r"\((?:of|de) (\d+)", ln)      # what was trimmed off
        if original:
            saved += max(0, int(original.group(1)) - n)
    return {"total": total, "today": today_total, "injections": turns,
            "saved_by_budget": saved,
            "avg_per_injection": round(total / turns) if turns else 0}


def logfile() -> str | None:
    return str(_PATH) if _PATH else None
