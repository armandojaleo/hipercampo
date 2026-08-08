"""
REAL surprise from prediction error — the fourth thread, no longer a proxy.

We used to measure "novelty" = 1 - similarity to what's already stored.
That's redundancy, not surprise. Real surprise, as in the hippocampus, is
PREDICTION ERROR: how much something new deviates from what the system expected.

Here it's implemented with **compression as intelligence** (Hutter/MDL), no
neural network or GPU: an incremental language model (bigrams with backoff)
learns from EVERYTHING it sees and estimates how many *bits* it costs to
predict a text. Many bits = unpredictable = surprising. Few bits = already
predictable = redundant.

  surprise(text) = average bits/token to encode it given the past

100% original, deterministic, runs on CPU. It "warms up" by replaying the
STORED memory at startup (see Hipercampo.__init__).

The incremental state can be restored from SQLite: it also includes what
was seen but rejected, without storing the literal text in the persistent counters.
"""

import hashlib
import math
import re
from collections import Counter, defaultdict, deque

_word = re.compile(r"\w+", re.UNICODE)

# "Imagined" vocabulary for the uniform fallback: sets the bit scale for
# something entirely new (~log2(V0) bits/token). log2(50000) ~= 15.6 bits.
_V0 = 50_000
_BITS_FULL = math.log2(_V0)


class SurpriseModel:
    """Online language model (unigram + interpolated bigram with backoff)."""

    # ADAPTIVE threshold: instead of a fixed absolute (almost never
    # crossed), "predictable" = being in the lower quantile of recent
    # surprise. Self-calibrates to the domain. With little history, falls
    # back to an absolute value.
    _HISTORY = 300
    _PREDICTABLE_PERCENTILE = 20      # lower quantile considered predictable
    _MIN_HISTORY = 40                 # until reaching this, use the absolute fallback
    _ABS_FALLBACK = 0.05

    def __init__(self):
        self.uni: Counter = Counter()
        self.bi: dict[str, Counter] = defaultdict(Counter)
        self.total = 0
        self.vocab: set[str] = set()
        self._recent: deque = deque(maxlen=self._HISTORY)   # recent surprise scores

    # Small smoothing over an "imagined" _V0 vocabulary: cold, a new token
    # is very unlikely (~1/_V0 -> very surprising); with repetition,
    # probability rises and surprise falls. That's the behavior we want.
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
        """Stable token identifiers; words aren't persisted in the clear."""
        return [
            hashlib.blake2s(token.encode("utf-8"), digest_size=8).hexdigest()
            for token in _word.findall(text.lower())
        ]

    def bits(self, text: str) -> float:
        """Average bits/token to predict 'text' given what's been learned
        (without learning it)."""
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
        """Normalized surprise in [0,1]: bits/token relative to something entirely new."""
        return min(1.0, self.bits(text) / _BITS_FULL)

    def observe(self, s: float) -> None:
        """Records a surprise value in recent history (for the adaptive threshold)."""
        self._recent.append(float(s))

    def predictable(self, s: float) -> bool:
        """Is 's' predictable? Adaptive: below the lower quantile of recent
        surprise. With little history, falls back to an absolute threshold."""
        if len(self._recent) < self._MIN_HISTORY:
            return s < self._ABS_FALLBACK
        import numpy as np
        threshold = float(np.percentile(list(self._recent), self._PREDICTABLE_PERCENTILE))
        return s <= threshold

    def learn(self, text: str) -> None:
        """Folds the text into the model: what's been seen stops being surprising."""
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
        """Compact state ready to persist: '' identifies unigrams."""
        rows = [("", token, int(count)) for token, count in self.uni.items()]
        rows.extend(
            (previous, token, int(count))
            for previous, context in self.bi.items()
            for token, count in context.items()
        )
        return rows

    def restore(self, rows: list[tuple[str, str, int]],
                recent: list[float]) -> None:
        """Restores counters and recent calibration from the own namespace."""
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
