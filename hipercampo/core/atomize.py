"""
Text atomizer — chunking into atomic units before encoding.

The why, MEASURED: packing T facts into a single hypervector (bundle) drops
each one's signal by ~1/sqrt(T). A short query looking for ONE fact buried
in a long text barely finds it: at 64 facts per text, monolithic hit@1 ~=
0.15; atomized ~= 1.00 (see scripts/atom_probe.py). The fix isn't more
dimensions: it's splitting the input into atoms —sentences, and clauses
within very long sentences— and encoding each one.

This is LEXICAL segmentation, no dependencies or model: robust rules for
Spanish and English. It doesn't aim for perfect linguistic analysis; it aims
to stop a buried fact from being unrecoverable. An LLM could atomize
better, but it shouldn't be a requirement.
"""

import re

# Sentence end: . ! ? ; … and newlines. Avoids splitting on abbreviations
# and common decimals (not exhaustive: prioritizes not over-splitting).
_ABBREV = {"sr", "sra", "dr", "dra", "st", "sta", "etc", "vs", "ej", "p.ej", "núm",
          "no", "art", "fig", "pág", "cap", "ee.uu", "ee", "uu", "mr", "mrs", "ms",
          "e.g", "i.e", "vol", "col", "op", "cf", "al"}
_END = re.compile(r"([.!?;…]+|\n+)")
# Clauses within a long sentence: connectors and strong separators.
_CLAUSE = re.compile(
    r"\s*(?:,|:|—|–|\bpero\b|\bporque\b|\baunque\b|\bmientras\b|\by luego\b|"
    r"\badem[aá]s\b|\bsin embargo\b|\bhowever\b|\bbecause\b|\balthough\b|\bwhile\b|"
    r"\bbut\b|\band then\b)\s*", re.IGNORECASE)

_MIN_ATOM = 12          # less than this isn't an atom with content, gets dropped
_LONG = 160             # a sentence longer than this gets split into clauses


def _ends_in_abbrev(frag: str) -> bool:
    m = re.search(r"(\w+)\.?$", frag.strip().lower())
    return bool(m and m.group(1) in _ABBREV)


def _by_sentences(text: str) -> list[str]:
    parts, buff = [], ""
    for chunk in _END.split(text):
        if _END.fullmatch(chunk or ""):
            buff += "" if "\n" in chunk else chunk
            if _ends_in_abbrev(buff):          # abbreviation: don't close yet
                buff += " "
                continue
            if buff.strip():
                parts.append(buff.strip())
            buff = ""
        else:
            buff += chunk
    if buff.strip():
        parts.append(buff.strip())
    return parts


def atomize(text: str) -> list[str]:
    """Chunks a text into atoms (sentences; very long ones, into clauses).
    Returns the atoms with content, in order. A short or single-idea text
    is returned whole (a one-element list): atomizing shouldn't fragment
    what's already atomic."""
    if not isinstance(text, str) or not text.strip():
        return []
    sentences = _by_sentences(text) or [text.strip()]
    atoms: list[str] = []
    for o in sentences:
        if len(o) > _LONG:
            chunks = [c.strip() for c in _CLAUSE.split(o) if c and c.strip()]
            for c in chunks:
                if len(c) >= _MIN_ATOM:
                    atoms.append(c)
        elif len(o.strip()) >= _MIN_ATOM or len(sentences) == 1:
            atoms.append(o.strip())
    # Nothing survived the filter (very short text): return the original whole.
    return atoms or [text.strip()]
