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

El estado incremental puede restaurarse desde SQLite: incluye también lo visto pero
rechazado, sin guardar el texto literal en los contadores persistentes.
"""

import hashlib
import math
import re
from collections import Counter, defaultdict, deque

_word = re.compile(r"\w+", re.UNICODE)

# Vocabulario "imaginado" para el fallback uniforme: fija la escala de bits de algo
# totalmente nuevo (~log2(V0) bits/token). log2(50000) ≈ 15.6 bits.
_V0 = 50_000
_BITS_FULL = math.log2(_V0)


class SurpriseModel:
    """Modelo de lenguaje online (unigrama + bigrama con backoff interpolado)."""

    # Umbral ADAPTATIVO: en vez de un absoluto fijo (que casi nunca se cruza),
    # "predecible" = estar en el cuantil inferior de la sorpresa reciente. Se calibra
    # solo al dominio. Con poco historial cae a un absoluto de respaldo.
    _HISTORY = 300
    _PREDICTABLE_PERCENTILE = 20      # cuantil inferior que se considera predecible
    _MIN_HISTORY = 40                 # hasta tener esto, usar el absoluto de respaldo
    _ABS_FALLBACK = 0.05

    def __init__(self):
        self.uni: Counter = Counter()
        self.bi: dict[str, Counter] = defaultdict(Counter)
        self.total = 0
        self.vocab: set[str] = set()
        self._recent: deque = deque(maxlen=self._HISTORY)   # sorpresas recientes

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

    @staticmethod
    def tokens(text: str) -> list[str]:
        """Identificadores estables de tokens; no persisten palabras en claro."""
        return [
            hashlib.blake2s(token.encode("utf-8"), digest_size=8).hexdigest()
            for token in _word.findall(text.lower())
        ]

    def bits(self, text: str) -> float:
        """Bits/token medios para predecir 'text' dado lo aprendido (sin aprenderlo)."""
        toks = self.tokens(text)
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

    def observe(self, s: float) -> None:
        """Registra una sorpresa en el historial reciente (para el umbral adaptativo)."""
        self._recent.append(float(s))

    def predictable(self, s: float) -> bool:
        """¿Es 's' predecible? Adaptativo: por debajo del cuantil inferior de la
        sorpresa reciente. Con poco historial, cae a un umbral absoluto de respaldo."""
        if len(self._recent) < self._MIN_HISTORY:
            return s < self._ABS_FALLBACK
        import numpy as np
        umbral = float(np.percentile(list(self._recent), self._PREDICTABLE_PERCENTILE))
        return s <= umbral

    def learn(self, text: str) -> None:
        """Incorpora el texto al modelo: lo que se ve, deja de sorprender."""
        toks = self.tokens(text)
        prev = None
        for t in toks:
            self.uni[t] += 1
            self.total += 1
            self.vocab.add(t)
            if prev is not None:
                self.bi[prev][t] += 1
            prev = t

    def count_rows(self) -> list[tuple[str, str, int]]:
        """Estado compacto listo para persistir: '' identifica unigramas."""
        rows = [("", token, int(count)) for token, count in self.uni.items()]
        rows.extend(
            (previous, token, int(count))
            for previous, context in self.bi.items()
            for token, count in context.items()
        )
        return rows

    def restore(self, rows: list[tuple[str, str, int]],
                recent: list[float]) -> None:
        """Restaura contadores y calibración reciente desde el namespace propio."""
        self.uni.clear()
        self.bi.clear()
        self.total = 0
        self.vocab.clear()
        self._recent.clear()
        for previous, token, count in rows:
            count = int(count)
            if previous:
                self.bi[previous][token] = count
            else:
                self.uni[token] = count
                self.total += count
                self.vocab.add(token)
        self._recent.extend(float(score) for score in recent)
