"""
Token budget: keeping the memory from eating the context window.

hipercampo injects text on every turn (the hook) and exposes tools whose
descriptions travel on EVERY request. Both cost tokens the user pays for
and, worse, take up context window no longer available for the real work.
A memory that gets in the way isn't a help.

House rule: measure before believing. There's no tokenizer here (we didn't
want a 2 MB dependency just to count), so it's ESTIMATED by character count.
It's an honest approximation, not an exact measurement:

    Spanish/English prose ~ 3.7 characters per token

The typical error is around +-15%, enough to decide what to trim and to warn
about it, not enough to bill by. Anyone who wants exactness can install
`tiktoken` and hipercampo will use it automatically.
"""

import os

# Characters per token (estimate for ES/EN prose). Adjustable in case
# someone works in a language where the ratio is very different.
CHARS_PER_TOKEN = 3.7

def _int_env(variable: str, default: int) -> int:
    """Reads an integer from the environment without being able to crash
    startup.

    This is evaluated at IMPORT time, and budget is imported by both the MCP
    server and the policy: an `int("abc")` here shouldn't degrade anything,
    it would prevent startup with a ValueError. A typo in .mcp.json can't be
    allowed to leave anyone without a memory, so an unreadable value is
    reported on stderr and the factory default is used instead."""
    raw = (os.environ.get(variable) or "").strip()
    if not raw:
        return default
    try:
        return max(0, int(raw))
    except ValueError:
        import sys
        print(f"hipercampo: {variable}={raw!r} is not a number; "
              f"using {default}", file=sys.stderr)
        return default


# Budget per hook injection. 350 tokens is roughly half a screen of text:
# enough for 2-3 useful memories, little enough to not be a nuisance. 0 = no
# limit (not recommended: cost grows with the memory, with no ceiling).
# Precedence: environment variable HIPERCAMPO_HOOK_BUDGET > persisted value
# (set by the viewer) > factory default of 350. Evaluated at import time,
# and the hook is a short-lived process spawned fresh every turn, so a
# change from the viewer takes effect the following turn.
def _default_budget() -> int:
    from . import config
    persisted = config.hook_budget_persisted()
    return persisted if persisted is not None else 350


HOOK_BUDGET = _int_env("HIPERCAMPO_HOOK_BUDGET", _default_budget())

# Working identity is paid for ONCE at session start, not on every turn: it
# can afford to be more generous. Still has a ceiling, because the number of
# learned rules only ever grows.
IDENTITY_BUDGET = _int_env("HIPERCAMPO_IDENTITY_BUDGET", 500)

_tokenizer = None
_tried = False


def _real_tokenizer():
    """Real tokenizer if installed; None if not. Tried ONCE."""
    global _tokenizer, _tried
    if _tried:
        return _tokenizer
    _tried = True
    try:                                          # optional, never required
        import tiktoken
        _tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tokenizer = None
    return _tokenizer


def estimate_tokens(text: str) -> int:
    """Tokens in a text: exact if a tokenizer is available, estimated if not."""
    if not text:
        return 0
    enc = _real_tokenizer()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass
    return max(1, round(len(text) / CHARS_PER_TOKEN))


def is_estimate() -> bool:
    """Is the count approximate? It's ALWAYS approximate, which is why this
    always returns True.

    It used to return False when a tokenizer was available, treating the
    count as exact. It isn't: `tiktoken`/cl100k_base is OpenAI's models'
    tokenizer, and hipercampo measures what it costs CLAUDE. Anthropic
    doesn't publish theirs; the exact figure only comes from their API (a
    counting endpoint, or the response's `usage`). With tiktoken the
    estimate is noticeably better than counting characters, but better
    isn't exact, and calling it exact would be precisely what this project
    doesn't do.
    """
    return True


def method() -> str:
    """How the count was made, so it can be stated without overclaiming."""
    return ("approximated with tiktoken/cl100k_base (OpenAI's tokenizer; "
            "Claude doesn't publish its own)" if _real_tokenizer() is not None
            else f"estimated at {CHARS_PER_TOKEN} characters per token")


def truncate(text: str, max_tokens: int) -> str:
    """Trims a text to a maximum number of tokens, marking the cut.

    Cuts at a WORD boundary, not mid-word: a text cut off abruptly reads as
    corrupted and can change the meaning of the last sentence.

    NOT used on memory text —there "whole or nothing" applies, see
    `fit_budget`—. This is for labels and queries in the log, where
    shortening is harmless because nobody reasons from them.
    """
    if max_tokens <= 0 or estimate_tokens(text) <= max_tokens:
        return text
    limit = int(max_tokens * CHARS_PER_TOKEN)
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:                       # don't leave a tiny stub
        cut = cut[:space]
    return cut.rstrip(" .,;:—-") + " […]"


def _notice(omitted: int, budget: int) -> str:
    """What gets said when something doesn't fit. Kept separate because its
    own cost has to be RESERVED before the budget gets divided up (see
    `fit_budget`)."""
    return (f"({omitted} more memory(ies) don't fit in the {budget}-token "
            f"budget; ask for them with hc_recall if you need them)")


def fit_budget(lines: list[str], budget: int | None = None) -> tuple[list[str], dict]:
    """Fits a list of lines (the first is the header) to a budget.

    WHOLE OR NOTHING. A memory cut in half is worse than a missing memory:
    it looks like information and isn't. The real case that proved it was

        "Compartir listas: URL m.armandojaleo.com/share?l=<ids en base64url> […]"

    where the cut ate exactly the part explaining WHY. Whoever reads it
    doesn't know the important part is missing, so they answer confidently
    about a mutilated fact. A memory that doesn't fit is OMITTED and the
    count of how many is stated: that's verifiable and can be requested with
    `hc_recall`, a stub can't.

    Strategy: the header always goes in (it's cheap and says what this is
    about); then the memories in relevance order, as long as they fit
    WHOLE. If one doesn't fit, it's skipped and the next ones are still
    tried: a short one further down might fit where a long one didn't.

    Returns (fitted lines, report), so the real cost can be logged and the
    user can audit it with `hipercampo log --accion tokens`.
    """
    budget = HOOK_BUDGET if budget is None else budget
    original = sum(estimate_tokens(x) for x in lines)
    if budget <= 0 or original <= budget:
        return lines, {"tokens": original, "budget": budget,
                        "omitted": 0}

    # The omission NOTICE also costs tokens, and it's appended at the end: if
    # it isn't reserved beforehand, the budget gets broken right when it's
    # being enforced (measured: budget of 40 -> 52 actual, 30% over). The
    # worst case is reserved —all lines omitted, which gives the longest
    # number— so the reserve is never too small at the end.
    reserve = estimate_tokens(_notice(max(1, len(lines) - 1), budget))
    cap = max(0, budget - reserve)

    output, spent, omitted = [], 0, 0
    for i, line in enumerate(lines):
        cost = estimate_tokens(line)
        if i == 0:                                # the header always goes in: it's
            output.append(line)                   # cheap, says what this is about, and
            spent += cost                         # without it nothing else makes sense
            continue
        if spent + cost <= cap:
            output.append(line)
            spent += cost
        else:
            omitted += 1                          # whole or nothing

    if omitted:                                   # the omission is STATED, and stated
        # with how to get what's missing: so the model can decide if it
        # needs it instead of believing it already has everything.
        output.append(_notice(omitted, budget))
    return output, {"tokens": sum(estimate_tokens(x) for x in output),
                    "budget": budget, "original": original,
                    "omitted": omitted}
