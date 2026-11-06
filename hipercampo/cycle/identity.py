"""
WORKING IDENTITY memory — the agent's own memory, not the user's.

The rest of hipercampo stores memory **of the world**: facts, projects,
gotchas. This stores the other thing, what's lost every time a session
closes: **what was learned while working**. The rules the user confirmed,
the mistakes not to repeat, the decisions already made and why. Without
this, every session starts from scratch and trips on the same stone again.

It isn't consciousness. It's **continuity of judgment**, which is what
actually separates a tool that gets used from one that grows:

    rule        how work should be done (the user said so, or it was agreed)
    lesson      what went wrong and what was learned (so it isn't repeated)
    decision    what was decided and WHY (so it isn't re-litigated)
    preference  how the user likes to be answered

The Spanish keys these used to have (`regla`, `leccion`, `preferencia`) are still
accepted, because they are written into the stored text of every identity row
created before the rename. See LEGACY_TYPES.

Lives in a reserved context (`__self__`) that:
  - is READABLE from any project (identity doesn't belong to one project),
  - is only written to on purpose (`hc_learn`), never by accident,
  - does NOT fade with time: a lesson learned doesn't expire from disuse.
"""

SELF_NAMESPACE = "__self__"

TYPES = {
    "rule": "how work should be done",
    "lesson": "what went wrong and what was learned",
    "decision": "what was decided and why",
    "preference": "how the user likes to be answered",
}

# The Spanish keys these used to be. They are NOT just an old spelling: they were
# written to disk as a prefix on every identity row (`"leccion: ..."`), so they
# still exist verbatim in the memory of anyone who used hipercampo before this
# rename. Dropping them would not raise anything — it would quietly file every
# stored rule and decision under "lesson" and lose the distinction for good.
#
# So they are accepted on the way IN (nobody's call breaks) and translated on the
# way OUT (old rows keep reading as what they are). New rows are written with the
# English key; the legacy ones are read, never rewritten, because rewriting them
# would need a migration that touches text the user believes is theirs.
LEGACY_TYPES = {
    "regla": "rule",
    "leccion": "lesson",
    "decision": "decision",        # same word in both, kept for clarity
    "preferencia": "preference",
}

# A lesson learned doesn't fade from going unused for a while: it's protected
# from active forgetting like any memory with maximum importance.
IDENTITY_IMPORTANCE = 0.95


def normalise_type(kind: str) -> str | None:
    """The canonical (English) type, accepting the legacy Spanish keys. Returns
    None if it isn't a known type at all."""
    kind = (kind or "").strip()
    if kind in TYPES:
        return kind
    return LEGACY_TYPES.get(kind)


# Measured on the real identity (2026-11-06): the actual rules run 21-52 tok;
# the long ones (150-377) are project episodes. Above this, an index line.
IDENTITY_FULL_MAX = 60


def format_identity(rows: list) -> str:
    """The identity, as text ready to inject at the start of a session.

    ONE line per item, always: the budget trims whole lines, and a
    multi-line item used to be cut mid-way (a stray "1. deployments.json
    — trivial…" closed the injected block). Long items become "#id
    headline …", read in full with hc_recall(ids=[...])."""
    from ..support.budget import estimate_tokens, headline
    if not rows:
        return ""
    by_type: dict[str, list[str]] = {}
    index: list[str] = []
    for r in rows:
        text = r["text"]
        prefix, _, body = text.partition(": ")
        kind = normalise_type(prefix)
        if kind is None:                  # no recognisable prefix: it's a lesson
            kind, body = "lesson", text
        body = " ".join(body.split())
        if estimate_tokens(body) > IDENTITY_FULL_MAX:
            # LAST, so the budget drops index lines before a whole rule.
            index.append(f"#{r['id']} {kind}: {headline(body)}")
            continue
        by_type.setdefault(kind, []).append(body)

    plural = {"rule": "RULES", "preference": "PREFERENCES",
              "decision": "DECISIONS", "lesson": "LESSONS"}
    parts = []
    for kind in ("rule", "preference", "decision", "lesson"):
        if kind in by_type:
            parts.append(f"{plural[kind]} ({TYPES[kind]}):")
            parts += [f"  - {c}" for c in by_type[kind]]
    if index:
        parts.append("LONGER (index only):")
        parts += [f"  - {c}" for c in index]
    return "\n".join(parts)
