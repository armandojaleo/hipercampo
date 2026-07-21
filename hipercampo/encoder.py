"""
Codificador texto -> hipervector, 100% en CPU, sin red neuronal.

Cada palabra recibe un hipervector aleatorio pero DETERMINISTA (sembrado por el
hash de la palabra), así "perro" siempre es el mismo vector en cualquier máquina.

Un texto se codifica como la superposición (bundle) de:
  - sus unigramas            -> QUÉ palabras aparecen (recuperación léxica)
  - sus bigramas             -> el ORDEN ("perro muerde hombre" != su inverso)
  - trigramas de caracteres  -> robustez morfológica ("logística"~"logístico")
                                y ante erratas, sin coste extra ni dependencias

Limitación honesta y MEDIDA (ver scripts/benchmark.py): esto es memoria
asociativa LÉXICA. Con palabras compartidas recupera perfecto (MRR ~1.0); con
SINÓNIMOS puros ("cobros"~"pagos") sufre. Para cerrar ese hueco existe un HOOK
SEMÁNTICO OPCIONAL (set_semantic_hook): tú enchufas el modelo que prefieras y su
vector se liga al hipervector. Por defecto no se usa ninguno -> cero GPU, cero
dependencias de terceros, todo original.
"""

import hashlib
import os
import re
from typing import Callable, Optional

import numpy as np

from .vsa import D, bind, bundle, permute, random_hv

# Los trigramas de caracteres dan robustez a erratas/morfología. Se pueden apagar
# para medir su aporte (o por velocidad) con HIPERCAMPO_NO_TRIGRAMS=1.
_USE_TRIGRAMS = os.environ.get("HIPERCAMPO_NO_TRIGRAMS") != "1"

_word = re.compile(r"\w+", re.UNICODE)
_cache: dict[str, np.ndarray] = {}

# Gancho semántico opcional: una función texto -> np.ndarray (hipervector empaquetado).
# Si se define, su salida se mezcla en el bundle. Por defecto: None (VSA puro).
_semantic_hook: Optional[Callable[[str], np.ndarray]] = None

# Peso del vector semántico frente a lo léxico. Valor por defecto 0.2: el mejor
# equilibrio MEDIDO (ver scripts/benchmark.py) entre robustez a erratas y sinónimos
# (erratas 0.79 / sinónimos 0.79). Subir para priorizar sinónimos; bajar para erratas.
SEMANTIC_WEIGHT = float(os.environ.get("HIPERCAMPO_SEMANTIC_WEIGHT", "0.2"))


def set_semantic_hook(fn: Optional[Callable[[str], np.ndarray]]) -> None:
    """Enchufa (o quita con None) un codificador semántico externo. La FUNCIÓN y el
    MODELO que uses son tuyos y con su propia licencia: hipercampo no incluye ninguno."""
    global _semantic_hook
    _semantic_hook = fn


def _tokenize(text: str) -> list[str]:
    return _word.findall(text.lower())


def token_hv(token: str) -> np.ndarray:
    """Hipervector determinista de una palabra (cacheado)."""
    hv = _cache.get(token)
    if hv is None:
        seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
        hv = random_hv(seed % (2**32))
        _cache[token] = hv
    return hv


def _char_trigrams(token: str) -> list[np.ndarray]:
    """Hipervectores de los trigramas de caracteres de una palabra (con '#' de borde)."""
    s = f"#{token}#"
    if len(s) < 3:
        return [token_hv(s)]
    return [token_hv("§" + s[i:i + 3]) for i in range(len(s) - 2)]  # §: espacio propio


def encode_text(text: str) -> np.ndarray:
    """Texto -> un único hipervector (unigramas + bigramas + trigramas de char
    + gancho semántico opcional)."""
    tokens = _tokenize(text)
    if not tokens:
        return random_hv(0)

    parts: list[np.ndarray] = [token_hv(t) for t in tokens]          # unigramas
    for a, b in zip(tokens, tokens[1:]):                             # bigramas (orden)
        parts.append(bind(token_hv(a), permute(token_hv(b), 1)))
    if _USE_TRIGRAMS:
        for t in tokens:                                            # subpalabra
            parts.extend(_char_trigrams(t))

    if _semantic_hook is not None:                                  # semántica opcional
        try:
            sem = _semantic_hook(text)
            # El bundle es voto por mayoría: un solo vector semántico quedaría
            # ahogado entre decenas de léxicos. Lo replicamos para que pese ~50%
            # del total y la semántica influya de verdad (peso tuneable).
            peso = max(1, int(len(parts) * SEMANTIC_WEIGHT))
            parts.extend([sem] * peso)
        except Exception:
            pass                                                    # nunca romper por el hook

    return bundle(parts)
