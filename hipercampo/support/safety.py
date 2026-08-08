"""
Usage safeguards (defense in depth, not a foolproof barrier).

Two lightweight, bilingual (ES/EN) scanners, no dependencies:

  scan_secrets(text)   -> hints that the text contains a SECRET (key, token,
                          password...). The DB is SQLite in PLAIN TEXT: worth
                          warning before storing something sensitive.
  scan_injection(text) -> hints of INJECTION via memory: instructions
                          trying to manipulate the model ("ignore previous
                          instructions", "you are now...", role markers...).

These are WARNINGS, not blocks: hipercampo stores whatever you ask it to,
but flags what's suspicious so the client/model treats it carefully
(retrieved text is DATA, not instructions). They don't guarantee perfect
detection; they reduce the risk in the common case.
"""

import re

# --- secrets ------------------------------------------------------------
_SECRET_PATTERNS = [
    (re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]{6,}\b"), "Stripe-style key"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "GitHub token"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT / bearer token"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "private key"),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|password|contrase[ñn]a|clave)\b"
                r"\s*[:=]\s*\S{6,}"), "labeled credential"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "long hex string (possible token)"),
]


def scan_secrets(text: str) -> list[str]:
    """Returns labels for possible secrets found (empty if none)."""
    if not isinstance(text, str):
        return []
    found = []
    for rx, label in _SECRET_PATTERNS:
        if rx.search(text):
            found.append(label)
    return sorted(set(found))


def _mask(m: re.Match) -> str:
    """Masks while keeping some context: first 2 chars + «…redacted»."""
    s = m.group(0)
    return (s[:2] + "…«redacted»") if len(s) > 4 else "«redacted»"


def redact_secrets(text: str) -> str:
    """Returns the text with secrets MASKED (keeps some context). For
    labeled credentials (`password: X`) keeps the label and masks only the
    value."""
    if not isinstance(text, str):
        return text
    out = text
    for rx, _ in _SECRET_PATTERNS:
        if "api[_-]?key" in rx.pattern:                 # labeled credential
            out = rx.sub(lambda m: f"{m.group(1)}: «redacted»", out)
        else:
            out = rx.sub(_mask, out)
    return out


# --- injection via memory ------------------------------------------------
_INJECTION_PATTERNS = [
    re.compile(r"(?i)\b(ignore|disregard|forget)\s+(all\s+|the\s+)?(previous|prior|above)"
               r"\s+(instructions?|prompts?|rules?)"),
    re.compile(r"(?i)\b(ignora|olvida|descarta)\s+(todas?\s+)?(las\s+)?"
               r"(instrucciones|reglas|órdenes)\s+(anteriores|previas)"),
    re.compile(r"(?i)\byou\s+are\s+now\b|\bnow\s+you\s+are\b"),
    re.compile(r"(?i)\b(eres|ahora\s+eres|actúa\s+como|compórtate\s+como)\b"),
    re.compile(r"(?i)\b(system\s+prompt|developer\s+message|jailbreak|prompt\s+injection)\b"),
    re.compile(r"(?im)^\s*(system|assistant|usuario|user)\s*:"),
    re.compile(r"(?i)\b(reveal|show|print)\s+(your\s+)?(system\s+prompt|instructions)\b"),
]


def scan_injection(text: str) -> bool:
    """True if the text looks like it contains instructions to manipulate
    the model."""
    if not isinstance(text, str):
        return False
    return any(rx.search(text) for rx in _INJECTION_PATTERNS)
