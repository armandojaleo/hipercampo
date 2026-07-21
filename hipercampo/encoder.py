"""
Codificador texto -> hipervector, 100% en CPU, sin red neuronal.

Cada palabra recibe un hipervector aleatorio pero DETERMINISTA (sembrado por el
hash de la palabra), así "perro" siempre es el mismo vector en cualquier máquina.

Un texto se codifica como la superposición (bundle) de:
  - sus unigramas  -> captura QUÉ palabras aparecen (recuperación léxica)
  - sus bigramas   -> captura el ORDEN, así "perro muerde hombre" y
                      "hombre muerde perro" son distinguibles algebraicamente.

Limitación honesta: esto es memoria asociativa LÉXICA, no semántica profunda.
No "entiende" sinónimos por sí sola (sí lo hace un embedding denso). A cambio:
es transparente, componible, reversible y vuela en CPU. Se puede enchufar un
codificador semántico opcional más adelante sin tocar el resto del sistema.
"""

import hashlib
import re

import numpy as np

from .vsa import D, bind, bundle, permute, random_hv

_word = re.compile(r"\w+", re.UNICODE)
_cache: dict[str, np.ndarray] = {}


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


def encode_text(text: str) -> np.ndarray:
    """Texto -> un único hipervector (bundle de unigramas + bigramas)."""
    tokens = _tokenize(text)
    if not tokens:
        return random_hv(0)

    parts: list[np.ndarray] = [token_hv(t) for t in tokens]          # unigramas
    for a, b in zip(tokens, tokens[1:]):                              # bigramas
        parts.append(bind(token_hv(a), permute(token_hv(b), 1)))     # orden-sensible

    return bundle(parts)
