"""
Conversational policy: what to do at EACH point in the conversation.

hipercampo stops waiting for orders and decides, from its own signals, which
memory operation fits the current turn:

    question about the past       -> RECALL (recall)
    stuck / looking for ideas     -> INSPIRE (muse)
    new, surprising statement     -> SAVE (recommended; never written on its own)
    contradicts something current -> UPDATE (recommended, with the candidate)
    nothing relevant              -> STAY QUIET (abstain)

Design rule: READS (recall/muse) run on their own —they're harmless—;
WRITES are only RECOMMENDED, so nothing enters the memory without intent.
It's the same ethic that separates imagination from evidence in `dream`.

Bilingual (ES/EN) lexical heuristics, no LLM or dependencies.
"""

import re

from ..support import audit

# When NOBODY has asked, hipercampo only speaks up if relevance is high.
# Volunteering a loose association out of nowhere is noise, not memory.
VOLUNTEER_MIN_SCORE = 0.10

# ...but that threshold alone isn't enough, and it's MEASURED: "fix the
# button bug" scored 0.167 —more than "what is VSA?" (0.140), which IS
# legitimate—. Raising the bar would have killed good memories before the
# noise.
#
# Three signals were tried on the same cases, and two failed:
#   - final score:      doesn't separate (noise scores above real hits)
#   - contrast (z):      doesn't either ("thanks, good work" got z=2.46, the max)
#   - DIRECT activation:  does separate. Legitimate 0.198-0.252 · noise 0.056-0.154
# The reason is that the final score mixes propagation, strength and
# confidence —a heavily reinforced memory scores high even if the query
# isn't about it—, while direct activation measures just one thing: how much
# THIS resembles the query. To decide whether to interrupt, it's the only
# one that answers what's actually being asked.
#
# The cutoff (0.18) sits at the midpoint between the worst noise and the
# weakest legitimate case. Volunteering is held to a higher bar than
# answering, and that's deliberate: if nobody asked, staying quiet is free
# and getting it wrong costs hundreds of tokens of the user's window.
VOLUNTEER_MIN_SIM = 0.18

# Detecting a question has TWO levels of certainty, and the difference
# matters because the "question" branch injects context without requiring
# high relevance.
#
# The old regex accepted interrogatives WITHOUT their accent mark, and in
# Spanish that's catastrophic: unstressed "que" is one of the most frequent
# words in the language, so "espera que termine la sesión", "creo que esto
# está mal" or "haz lo que te digo" got classified as questions and fired a
# context injection of hundreds of tokens. Measured on a real session: 2 of
# 3 turns injected memory from another project when nobody had asked
# anything.
#
#   CLEAR      -> carries the diacritic accent or is unambiguous ("recuerdas",
#                 "do you remember"). The user really did ask: answered with
#                 the normal bar.
#   UNCERTAIN  -> the same word without the accent, which may be an
#                 unstressed relative pronoun. It might be a question and it
#                 might not, so it's held to the same bar as speaking up
#                 unprompted (VOLUNTEER_MIN_SIM): if it hits, it still
#                 answers, and if it was a stray "que", it stays quiet.
#
# The ? ¿ marks override everything: with them, it's always CLEAR.
_CLEAR_QUESTION = re.compile(
    r"(?i)(^|\s)(qué|quién|cuándo|dónde|cómo|cuál|por qué|"
    r"recuerdas|te acuerdas|sabes si|do you (recall|remember))\b")
_UNCERTAIN_QUESTION = re.compile(
    r"(?i)(^|\s)(que|quien|cuando|donde|como|cual|por que|"
    r"what|who|when|where|which|why|how)\b")
_QUESTION_MARK = re.compile(r"[?¿]")


def _is_question(msg: str) -> str | None:
    """'clear' | 'uncertain' | None — how confident we are this is a question."""
    if _QUESTION_MARK.search(msg) or _CLEAR_QUESTION.search(msg):
        return "clear"
    return "uncertain" if _UNCERTAIN_QUESTION.search(msg) else None

_CREATIVE = re.compile(
    r"(?i)\b(se me ocurre|no s[eé] c[oó]mo|estoy atascad[oa]|alguna idea|ideas para|"
    r"y si|se te ocurre|inspiraci[oó]n|lluvia de ideas|brainstorm|stuck|any ideas|"
    r"what if|inspiration)\b")

_STATEMENT = re.compile(
    r"(?i)\b(me llamo|soy |prefiero|me gusta|odio|uso |trabajo en|vivo en|mi |"
    r"recuerda que|apunta que|ten en cuenta que|i (am|prefer|use|like|hate)|"
    r"my name is|remember that|note that)\b")


def decide(hc, message: str, k: int = 3, max_scan: int | None = None,
           nav: bool | str = False) -> dict:
    """Decides and runs whatever's safe. Returns the action, the why, and
    the result."""
    r = _decide(hc, message, k, max_scan=max_scan, nav=nav)
    audit.log("assist", f"{r['action']}: {r.get('why','')}")
    return r


def _decide(hc, message: str, k: int = 3, max_scan: int | None = None,
            nav: bool | str = False) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"action": "nothing", "why": "empty message"}
    msg = message.strip()

    # 1) looking for ideas / stuck? -> inspire
    if _CREATIVE.search(msg):
        ideas = hc.muse(msg, k=k)
        if ideas:
            return {"action": "muse", "why": "seems to be looking for ideas or stuck",
                    "result": ideas}
        # nothing creative to offer, fall through to a normal recall

    # 2) asking about something? -> recall
    certainty = _is_question(msg)
    if certainty:
        hits = hc.recall(msg, k=k, max_scan=max_scan, nav=nav)
        if certainty == "uncertain":              # might not be a question:
            hits = [h for h in hits              # held to the speak-up bar
                    if h.get("sim", 0.0) >= VOLUNTEER_MIN_SIM]   # even unprompted
        if hits:
            return {"action": "recall",
                    "why": ("it's a question and there's relevant memory" if certainty == "clear"
                            else "might be a question and the memory clearly fits"),
                    "result": hits}
        return {"action": "nothing",
                "why": ("it's a question but nothing relevant is known" if certainty == "clear"
                        else "not clearly a question and nothing fits well enough"),
                "result": []}

    # 3) states something about the user or the project? -> save or update?
    if _STATEMENT.search(msg):
        prev = hc.recall(msg, k=1, max_scan=max_scan, nav=nav)
        surprise = hc.surprise.surprise(msg)
        if prev:
            p = prev[0]
            # closely resembles something already known: update it or is it redundant?
            return {"action": "update?" if p["score"] >= 0.12 else "remember?",
                    "why": ("resembles an existing memory: could update it"
                            if p["score"] >= 0.12 else
                            "states something new about you or the project"),
                    "candidate": {"id": p["id"], "text": p["text"]},
                    "suggestion": ("hc_update(memory_id=%d, new_text=...)" % p["id"]
                                   if p["score"] >= 0.12 else "hc_remember(text=...)"),
                    "surprise": round(surprise, 3)}
        return {"action": "remember?", "why": "states something new and there's nothing like it",
                "suggestion": "hc_remember(text=...)", "surprise": round(surprise, 3)}

    # 4) default (nobody asked): only speak up if CLEARLY relevant
    # AND on the same topic besides. Interrupting with a ghost association
    # isn't just noise: it's hundreds of tokens of the user's window, spent
    # on nothing.
    hits = [h for h in hc.recall(msg, k=k, max_scan=max_scan, nav=nav)
            if h["score"] >= VOLUNTEER_MIN_SCORE
            and h.get("sim", 0.0) >= VOLUNTEER_MIN_SIM]
    if hits:
        return {"action": "recall", "why": "there's clearly relevant memory",
                "result": hits}
    return {"action": "nothing", "why": "nothing relevant to add this turn"}
