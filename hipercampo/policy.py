"""
Política conversacional: qué hacer en CADA momento de la conversación.

hipercampo deja de esperar órdenes y decide, con sus propias señales, cuál es la
operación de memoria adecuada para el turno actual:

    pregunta sobre el pasado        -> RECORDAR (recall)
    atasco / búsqueda de ideas      -> INSPIRAR (muse)
    afirmación nueva y sorprendente -> GUARDAR (se recomienda; no se escribe solo)
    contradice algo vigente         -> ACTUALIZAR (se recomienda, con el candidato)
    nada relevante                  -> CALLARSE (abstenerse)

Regla de diseño: las LECTURAS (recall/muse) se ejecutan solas —son inocuas—; las
ESCRITURAS solo se RECOMIENDAN, para que nada entre en la memoria sin intención.
Es la misma ética que separa imaginación de evidencia en `dream`.

Heurísticas léxicas bilingües (ES/EN), sin LLM ni dependencias.
"""

import re

from . import audit

# Cuando NADIE ha preguntado, hipercampo solo interviene si la relevancia es alta.
# Soltar una asociación floja sin venir a cuento es ruido, no memoria.
VOLUNTEER_MIN_SCORE = 0.10

# ...pero ese umbral SOLO no basta, y está MEDIDO: "arregla el bug del botón"
# puntuaba 0.167 —más que "¿qué es VSA?" (0.140), que sí es legítima—. Subir el
# listón habría matado los recuerdos buenos antes que el ruido.
#
# Se probaron tres señales sobre los mismos casos, y dos fallaron:
#   · score final:      no separa (el ruido puntúa por encima de aciertos reales)
#   · contraste (z):    tampoco ("gracias, buen trabajo" sacaba z=2.46, el máximo)
#   · activación DIRECTA: sí separa. Legítimas 0.198-0.252 · ruido 0.056-0.154
# La razón es que el score final mezcla propagación, fuerza y fiabilidad —un
# recuerdo muy reforzado puntúa alto aunque la consulta no vaya de él—, mientras
# que la activación directa mide solo una cosa: cuánto se parece ESTO a la
# pregunta. Para decidir si interrumpir, es la única que responde a lo que
# realmente se está preguntando.
#
# El corte (0.18) va a media banda entre el mejor ruido y la peor legítima. Al
# volunteering se le exige más que a una respuesta, y es deliberado: si nadie ha
# preguntado, callarse es gratis y equivocarse cuesta cientos de tokens de la
# ventana del usuario.
VOLUNTEER_MIN_SIM = 0.18

_PREGUNTA = re.compile(
    r"(?i)(^|\s)(qu[eé]|qui[eé]n|cu[aá]ndo|d[oó]nde|c[oó]mo|cu[aá]l|por qu[eé]|"
    r"recuerdas|te acuerdas|sabes si|what|who|when|where|which|why|how|do you (recall|remember))\b")
_INTERROGACION = re.compile(r"[?¿]")

_CREATIVO = re.compile(
    r"(?i)\b(se me ocurre|no s[eé] c[oó]mo|estoy atascad[oa]|alguna idea|ideas para|"
    r"y si|se te ocurre|inspiraci[oó]n|lluvia de ideas|brainstorm|stuck|any ideas|"
    r"what if|inspiration)\b")

_AFIRMACION = re.compile(
    r"(?i)\b(me llamo|soy |prefiero|me gusta|odio|uso |trabajo en|vivo en|mi |"
    r"recuerda que|apunta que|ten en cuenta que|i (am|prefer|use|like|hate)|"
    r"my name is|remember that|note that)\b")


def decide(hc, message: str, k: int = 3) -> dict:
    """Decide y ejecuta lo seguro. Devuelve la acción, el porqué y el resultado."""
    r = _decide(hc, message, k)
    audit.log("assist", f"{r['action']}: {r.get('why','')}")
    return r


def _decide(hc, message: str, k: int = 3) -> dict:
    if not isinstance(message, str) or not message.strip():
        return {"action": "nothing", "why": "mensaje vacío"}
    msg = message.strip()

    # 1) ¿busca ideas / está atascado? -> inspirar
    if _CREATIVO.search(msg):
        ideas = hc.muse(msg, k=k)
        if ideas:
            return {"action": "muse", "why": "parece buscar ideas o estar atascado",
                    "result": ideas}
        # sin nada creativo que ofrecer, se intenta un recuerdo normal

    # 2) ¿pregunta por algo? -> recordar
    if _INTERROGACION.search(msg) or _PREGUNTA.search(msg):
        hits = hc.recall(msg, k=k)
        if hits:
            return {"action": "recall", "why": "es una pregunta y hay memoria relevante",
                    "result": hits}
        return {"action": "nothing", "why": "es una pregunta pero no sé nada relevante",
                "result": []}

    # 3) ¿afirma algo sobre el usuario o el proyecto? -> ¿guardar o actualizar?
    if _AFIRMACION.search(msg):
        prev = hc.recall(msg, k=1)
        sorpresa = hc.surprise.surprise(msg)
        if prev:
            p = prev[0]
            # muy parecido a algo que ya sé: ¿lo actualiza o es redundante?
            return {"action": "update?" if p["score"] >= 0.12 else "remember?",
                    "why": ("se parece a un recuerdo existente: puede actualizarlo"
                            if p["score"] >= 0.12 else
                            "afirma algo nuevo sobre ti o el proyecto"),
                    "candidato": {"id": p["id"], "text": p["text"]},
                    "sugerencia": ("hc_update(memory_id=%d, new_text=...)" % p["id"]
                                   if p["score"] >= 0.12 else "hc_remember(text=...)"),
                    "surprise": round(sorpresa, 3)}
        return {"action": "remember?", "why": "afirma algo nuevo y no tengo nada igual",
                "sugerencia": "hc_remember(text=...)", "surprise": round(sorpresa, 3)}

    # 4) por defecto (nadie ha preguntado): solo hablar si es CLARAMENTE relevante
    # Y encima va del mismo tema. Interrumpir con una asociación fantasma no solo
    # es ruido: son cientos de tokens de la ventana del usuario, gastados en nada.
    hits = [h for h in hc.recall(msg, k=k)
            if h["score"] >= VOLUNTEER_MIN_SCORE
            and h.get("sim", 0.0) >= VOLUNTEER_MIN_SIM]
    if hits:
        return {"action": "recall", "why": "hay memoria claramente relevante",
                "result": hits}
    return {"action": "nothing", "why": "nada relevante que aportar en este turno"}
