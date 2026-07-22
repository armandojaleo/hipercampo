"""
Sorpresa REAL por error de predicción — el cuarto hilo, ya sin proxy.

Antes medíamos "novedad" = 1 − parecido con lo ya guardado. Eso es redundancia,
no sorpresa. La sorpresa de verdad, como en el hipocampo, es ERROR DE PREDICCIÓN:
cuánto se desvía lo nuevo de lo que el sistema esperaba.

Aquí lo implementamos con **compresión como inteligencia** (Hutter/MDL), sin red
neuronal ni GPU: un modelo de lenguaje incremental (bigramas con backoff) aprende
de TODO lo que ve y estima cuántos *bits* cuesta predecir un texto. Muchos bits =
imprevisible = sorprendente. Pocos bits = ya era predecible = redundante.

  sorpresa(texto) = bits/token medios para codificarlo dado el pasado

Es 100% original, determinista y corre en CPU. Se "calienta" reproduciendo la
memoria GUARDADA al arrancar (ver Hipercampo.__init__).

Limitación honesta: tras reiniciar se reconstruye SOLO desde los recuerdos
guardados; lo que se vio pero se rechazó (por redundante/predecible) no persiste.
Persistir los contadores es un pendiente del roadmap (Fase 1b).
"""

import math
import re
from collections import Counter, defaultdict

_word = re.compile(r"\w+", re.UNICODE)

# Vocabulario "imaginado" para el fallback uniforme: fija la escala de bits de algo
# totalmente nuevo (~log2(V0) bits/token). log2(50000) ≈ 15.6 bits.
_V0 = 50_000
_BITS_FULL = math.log2(_V0)


class SurpriseModel:
    """Modelo de lenguaje online (unigrama + bigrama con backoff interpolado)."""

    def __init__(self):
        self.uni: Counter = Counter()
        self.bi: dict[str, Counter] = defaultdict(Counter)
        self.total = 0
        self.vocab: set[str] = set()

    # Suavizado pequeño sobre un vocabulario "imaginado" _V0: en frío, un token
    # nuevo es muy improbable (~1/_V0 -> muy sorprendente); con la repetición, la
    # probabilidad sube y la sorpresa baja. Ese es el comportamiento que queremos.
    _ALPHA = 0.01

    def _p(self, prev: str | None, tok: str) -> float:
        a, denom = self._ALPHA, self._ALPHA * _V0
        p_uni = (self.uni.get(tok, 0) + a) / (self.total + denom)
        if prev is not None and self.bi.get(prev):
            ctx = self.bi[prev]
            p_bi = (ctx.get(tok, 0) + a) / (sum(ctx.values()) + denom)
            return 0.6 * p_bi + 0.4 * p_uni
        return p_uni

    def bits(self, text: str) -> float:
        """Bits/token medios para predecir 'text' dado lo aprendido (sin aprenderlo)."""
        toks = _word.findall(text.lower())
        if not toks:
            return 0.0
        total_bits = 0.0
        prev = None
        for t in toks:
            total_bits += -math.log2(self._p(prev, t))
            prev = t
        return total_bits / len(toks)

    def surprise(self, text: str) -> float:
        """Sorpresa normalizada en [0,1]: bits/token relativos a algo totalmente nuevo."""
        return min(1.0, self.bits(text) / _BITS_FULL)

    def learn(self, text: str) -> None:
        """Incorpora el texto al modelo: lo que se ve, deja de sorprender."""
        toks = _word.findall(text.lower())
        prev = None
        for t in toks:
            self.uni[t] += 1
            self.total += 1
            self.vocab.add(t)
            if prev is not None:
                self.bi[prev][t] += 1
            prev = t
