"""
Salvaguardas de uso (defensa en profundidad, no una barrera infalible).

Dos escáneres ligeros, bilingües (ES/EN), sin dependencias:

  scan_secrets(text)   -> pistas de que el texto contiene un SECRETO (clave, token,
                          contraseña...). La BD es SQLite EN CLARO: conviene avisar
                          antes de guardar algo sensible.
  scan_injection(text) -> pistas de INYECCIÓN vía memoria: instrucciones que
                          intentan manipular al modelo ("ignora las instrucciones
                          anteriores", "you are now...", marcadores de rol...).

Son AVISOS, no bloqueos: hipercampo guarda lo que le pidas, pero marca lo sospechoso
para que el cliente/modelo lo trate con cuidado (el texto recuperado es DATO, no
instrucciones). No garantizan detección perfecta; reducen el riesgo del caso común.
"""

import re

# --- secretos ---------------------------------------------------------------
_SECRET_PATTERNS = [
    (re.compile(r"\b(sk|rk|pk)_(live|test)_[A-Za-z0-9]{6,}\b"), "clave tipo Stripe"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "clave de acceso AWS"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}\b"), "token de GitHub"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\."), "JWT / token bearer"),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"), "clave privada"),
    (re.compile(r"(?i)\b(api[_-]?key|apikey|secret|token|password|contrase[ñn]a|clave)\b"
                r"\s*[:=]\s*\S{6,}"), "credencial etiquetada"),
    (re.compile(r"\b[0-9a-fA-F]{32,}\b"), "cadena hex larga (posible token)"),
]


def scan_secrets(text: str) -> list[str]:
    """Devuelve etiquetas de posibles secretos hallados (vacío si nada)."""
    if not isinstance(text, str):
        return []
    hallados = []
    for rx, etiqueta in _SECRET_PATTERNS:
        if rx.search(text):
            hallados.append(etiqueta)
    return sorted(set(hallados))


def _mask(m: re.Match) -> str:
    """Enmascara conservando algo de contexto: primeros 2 chars + «…›»."""
    s = m.group(0)
    return (s[:2] + "…«redactado»") if len(s) > 4 else "«redactado»"


def redact_secrets(text: str) -> str:
    """Devuelve el texto con los secretos ENMASCARADOS (deja algo de contexto).
    En las credenciales etiquetadas (`password: X`) conserva la etiqueta y enmascara
    solo el valor."""
    if not isinstance(text, str):
        return text
    out = text
    for rx, _ in _SECRET_PATTERNS:
        if "api[_-]?key" in rx.pattern:                 # credencial etiquetada
            out = rx.sub(lambda m: f"{m.group(1)}: «redactado»", out)
        else:
            out = rx.sub(_mask, out)
    return out


# --- inyección vía memoria --------------------------------------------------
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
    """True si el texto parece contener instrucciones para manipular al modelo."""
    if not isinstance(text, str):
        return False
    return any(rx.search(text) for rx in _INJECTION_PATTERNS)
