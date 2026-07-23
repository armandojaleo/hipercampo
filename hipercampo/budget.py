"""
Presupuesto de tokens: que la memoria no se coma la ventana de contexto.

hipercampo inyecta texto en cada turno (el hook) y expone herramientas cuyas
descripciones viajan en CADA petición. Ambas cosas cuestan tokens que el usuario
paga y, peor, ocupan ventana de contexto que ya no está disponible para el
trabajo real. Una memoria que estorba no es una ayuda.

Regla de la casa: medir antes de creer. Aquí no hay tokenizador (no queremos una
dependencia de 2 MB para contar), así que se ESTIMA por caracteres. Es una
aproximación honesta, no una medida exacta:

    español/inglés en prosa ~ 3.7 caracteres por token

El error típico es de un ±15%, suficiente para decidir qué recortar y para
avisar, insuficiente para facturar. Quien quiera exactitud puede instalar
`tiktoken` y hipercampo lo usará automáticamente.
"""

import os

# Caracteres por token (estimación para prosa ES/EN). Ajustable por si alguien
# trabaja en un idioma donde la proporción es muy distinta.
CHARS_PER_TOKEN = 3.7

def _entero(variable: str, por_defecto: int) -> int:
    """Lee un entero del entorno sin poder tumbar el arranque.

    Esto se evalúa al IMPORTAR, y budget lo importan el servidor MCP y la política:
    un `int("abc")` aquí no degrada nada, impide arrancar con un ValueError. Un
    typo en .mcp.json no puede dejar sin memoria a nadie, así que un valor
    ilegible se avisa por stderr y se sigue con el de fábrica."""
    crudo = (os.environ.get(variable) or "").strip()
    if not crudo:
        return por_defecto
    try:
        return max(0, int(crudo))
    except ValueError:
        import sys
        print(f"hipercampo: {variable}={crudo!r} no es un número; "
              f"uso {por_defecto}", file=sys.stderr)
        return por_defecto


# Presupuesto por inyección del hook. 350 tokens es aproximadamente media pantalla
# de texto: suficiente para 2-3 recuerdos útiles, poco para molestar. 0 = sin límite
# (no recomendado: el coste crece con la memoria, sin techo).
HOOK_BUDGET = _entero("HIPERCAMPO_HOOK_BUDGET", 350)

# La identidad de trabajo se paga UNA vez al arrancar la sesión, no en cada turno:
# puede permitirse ser más generosa. Aun así tiene techo, porque el número de
# reglas aprendidas solo crece.
IDENTITY_BUDGET = _entero("HIPERCAMPO_IDENTITY_BUDGET", 500)

_tokenizador = None
_intentado = False


def _real():
    """Tokenizador real si está instalado; None si no. Se intenta UNA vez."""
    global _tokenizador, _intentado
    if _intentado:
        return _tokenizador
    _intentado = True
    try:                                          # opcional, nunca obligatorio
        import tiktoken
        _tokenizador = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _tokenizador = None
    return _tokenizador


def estimate_tokens(texto: str) -> int:
    """Tokens de un texto: exactos si hay tokenizador, estimados si no."""
    if not texto:
        return 0
    enc = _real()
    if enc is not None:
        try:
            return len(enc.encode(texto))
        except Exception:
            pass
    return max(1, round(len(texto) / CHARS_PER_TOKEN))


def es_estimacion() -> bool:
    """¿La cuenta es aproximada? SIEMPRE lo es, y por eso devuelve True siempre.

    Antes devolvía False cuando había tokenizador, dando por exacta la cuenta. No
    lo es: `tiktoken`/cl100k_base es el tokenizador de los modelos de OpenAI, y
    hipercampo mide lo que le cuesta a CLAUDE. Anthropic no publica el suyo; lo
    exacto solo lo da su API (endpoint de conteo, o el `usage` de la respuesta).
    Con tiktoken la estimación es bastante mejor que contar caracteres, pero mejor
    no es exacto, y decirlo exacto sería justo lo que este proyecto no hace.
    """
    return True


def metodo() -> str:
    """Con qué se ha contado, para poder declararlo sin exagerar."""
    return ("aproximado con tiktoken/cl100k_base (tokenizador de OpenAI; "
            "Claude no publica el suyo)" if _real() is not None
            else f"estimado a {CHARS_PER_TOKEN} caracteres por token")


def truncar(texto: str, max_tokens: int) -> str:
    """Recorta un texto a un máximo de tokens, marcando el corte.

    Corta por PALABRA, no a mitad de una: un texto cortado en seco se lee como
    corrupto y puede cambiar el sentido de la última frase.

    NO se usa con el texto de los recuerdos —ahí rige "enteros o ninguno", ver
    `ajustar`—. Sirve para etiquetas y consultas en el registro, donde acortar es
    inofensivo porque nadie razona a partir de ellas.
    """
    if max_tokens <= 0 or estimate_tokens(texto) <= max_tokens:
        return texto
    limite = int(max_tokens * CHARS_PER_TOKEN)
    corte = texto[:limite]
    espacio = corte.rfind(" ")
    if espacio > limite * 0.6:                    # no dejar un muñón diminuto
        corte = corte[:espacio]
    return corte.rstrip(" .,;:—-") + " […]"


def _aviso(omitidas: int, presupuesto: int) -> str:
    """Lo que se dice cuando algo no cabe. Aparte, porque su coste hay que
    RESERVARLO antes de repartir el presupuesto (ver `ajustar`)."""
    return (f"({omitidas} recuerdo(s) más no caben en el presupuesto de "
            f"{presupuesto} tokens; pídelos con hc_recall si hacen falta)")


def ajustar(lineas: list[str], presupuesto: int = None) -> tuple[list[str], dict]:
    """Ajusta una lista de líneas (la primera es la cabecera) a un presupuesto.

    ENTEROS O NINGUNO. Un recuerdo cortado por la mitad es peor que un recuerdo
    ausente: parece información y no lo es. El caso real que lo demostró fue

        "Compartir listas: URL m.armandojaleo.com/share?l=<ids en base64url> […]"

    donde el corte se comió justo la parte que explicaba POR QUÉ. Quien lo lee no
    sabe que le falta lo importante, así que responde con confianza sobre un dato
    mutilado. Un recuerdo que no cabe se OMITE y se dice cuántos faltan: eso es
    verificable y se puede pedir con `hc_recall`, un muñón no.

    Estrategia: la cabecera siempre entra (es barata y dice de qué va); después,
    los recuerdos por orden de relevancia mientras quepan ENTEROS. Si uno no cabe,
    se salta y se sigue probando con los siguientes: uno corto que venía detrás
    puede caber donde no cabía el largo.

    Devuelve (líneas ajustadas, informe), para poder registrar el coste real y
    que el usuario lo audite con `hipercampo log --accion tokens`.
    """
    presupuesto = HOOK_BUDGET if presupuesto is None else presupuesto
    original = sum(estimate_tokens(x) for x in lineas)
    if presupuesto <= 0 or original <= presupuesto:
        return lineas, {"tokens": original, "presupuesto": presupuesto,
                        "omitidas": 0}

    # El AVISO de omisión también cuesta tokens, y se añade al final: si no se
    # reserva antes, el presupuesto se incumple justo cuando se está aplicando
    # (medido: 40 de presupuesto -> 52 reales, un 30% de más). Se reserva el peor
    # caso —todas las líneas omitidas, que da el número más largo— para que la
    # reserva nunca se quede corta al final.
    reserva = estimate_tokens(_aviso(max(1, len(lineas) - 1), presupuesto))
    tope = max(0, presupuesto - reserva)

    salida, gastado, omitidas = [], 0, 0
    for i, linea in enumerate(lineas):
        coste = estimate_tokens(linea)
        if i == 0:                                # la cabecera siempre: es barata,
            salida.append(linea)                  # dice de qué va, y sin ella lo
            gastado += coste                      # demás no se entiende
            continue
        if gastado + coste <= tope:
            salida.append(linea)
            gastado += coste
        else:
            omitidas += 1                         # entero o nada

    if omitidas:                                  # la omisión se DICE, y se dice
        # cómo recuperar lo que falta: así el modelo puede decidir si lo necesita
        # en vez de creer que ya lo tiene todo.
        salida.append(_aviso(omitidas, presupuesto))
    return salida, {"tokens": sum(estimate_tokens(x) for x in salida),
                    "presupuesto": presupuesto, "original": original,
                    "omitidas": omitidas}
