"""
Text -> hypervector encoder, 100% on CPU, no neural network.

Each word gets a random but DETERMINISTIC hypervector (seeded by the word's
hash), so "dog" is always the same vector on any machine.

A text is encoded as the superposition (bundle) of:
  - its unigrams              -> WHICH words appear (lexical retrieval)
  - its bigrams                -> ORDER ("dog bites man" != its reverse)
  - character trigrams         -> morphological robustness ("logistics"~"logistical")
                                and typo tolerance, at no extra cost or dependencies

Honest, MEASURED limitation (see scripts/benchmark.py): this is LEXICAL
associative memory. With shared words it retrieves perfectly (MRR ~1.0);
with pure SYNONYMS ("earnings"~"revenue") it struggles. To close that gap
there's an OPTIONAL SEMANTIC HOOK (set_semantic_hook): you plug in whatever
model you prefer and its vector gets bound to the hypervector. None is used
by default -> zero GPU, zero third-party dependencies, all original.
"""

import hashlib
import os
import re
from typing import Callable, Optional

import numpy as np

from .vsa import bind, bundle, permute, random_hv

# Character trigrams give robustness against typos/morphology. They can be
# turned off to measure their contribution (or for speed) with
# HIPERCAMPO_NO_TRIGRAMS=1.
_USE_TRIGRAMS = os.environ.get("HIPERCAMPO_NO_TRIGRAMS") != "1"

_word = re.compile(r"\w+", re.UNICODE)
_cache: dict[str, np.ndarray] = {}
# Each word's hypervector ALREADY rotated one position, which is how it
# enters the bigram. Rotating costs unpackbits+roll+packbits, and without
# caching it repeated once per bigram of every encoded text (13% of
# encode_text's time, measured).
_shifted: dict[str, np.ndarray] = {}

# Both caches grow with the VOCABULARY, and an MCP server is a long-lived
# process: with no cap, every word and trigram ever seen never gets
# released (~10 KB per entry). On hitting the cap, they're cleared whole.
# Deliberately dumb —not LRU—: recomputing a hypervector is cheap and
# deterministic, so the policy only needs to bound memory, not guess what
# to keep.
_CACHE_MAX = int(os.environ.get("HIPERCAMPO_TOKEN_CACHE", "200000") or 0)

# Optional semantic hook: a text -> np.ndarray (packed hypervector) function.
# If set, its output gets mixed into the bundle. Default: None (pure VSA).
_semantic_hook: Optional[Callable[[str], np.ndarray]] = None

# Weight of the semantic vector against the lexical one. Default 0.15:
# optimum MEASURED in scripts/stress.py (global MRR 0.95; typos 0.95,
# synonyms 0.90). A small weight is enough; too much drowns out the lexical
# cue that disambiguates distractors on the same topic. Tuned on a
# synthetic benchmark: change it for your domain via the env var.
SEMANTIC_WEIGHT = float(os.environ.get("HIPERCAMPO_SEMANTIC_WEIGHT", "0.15"))


def set_semantic_hook(fn: Optional[Callable[[str], np.ndarray]]) -> None:
    """Plugs in (or removes with None) an external semantic encoder. The
    FUNCTION and MODEL you use are yours, under their own license: hipercampo
    doesn't bundle any."""
    global _semantic_hook
    _semantic_hook = fn


def enable_semantic(model_name: str | None = None) -> bool:
    """Turns on the reference semantic hook (sentence-transformers) if
    installed. Returns True if it was enabled, False if the dependency is
    missing (in which case the system keeps working in lexical mode). Lazy
    model loading."""
    global _semantic_hook
    try:
        from . import semantic
        fn = (semantic.make_sentence_transformer_hook(model_name)
              if model_name else semantic.make_sentence_transformer_hook())
        _semantic_hook = fn
        return True
    except Exception:
        return False


def semantic_active() -> bool:
    return _semantic_hook is not None


def _tokenize(text: str) -> list[str]:
    return _word.findall(text.lower())


def token_hv(token: str) -> np.ndarray:
    """A word's deterministic hypervector (cached)."""
    hv = _cache.get(token)
    if hv is None:
        seed = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:16], 16)
        hv = random_hv(seed % (2**32))
        if _CACHE_MAX and len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[token] = hv
    return hv


def _token_hv_shifted(token: str) -> np.ndarray:
    """The word's hypervector rotated one position (its role as 2nd in the bigram)."""
    hv = _shifted.get(token)
    if hv is None:
        hv = permute(token_hv(token), 1)
        if _CACHE_MAX and len(_shifted) >= _CACHE_MAX:
            _shifted.clear()
        _shifted[token] = hv
    return hv


def _char_trigrams(token: str) -> list[np.ndarray]:
    """Hypervectors of a word's character trigrams (with '#' boundary markers)."""
    s = f"#{token}#"
    if len(s) < 3:
        return [token_hv(s)]
    return [token_hv("§" + s[i:i + 3]) for i in range(len(s) - 2)]  # §: its own namespace


def encode_text(text: str) -> np.ndarray:
    """Text -> a single hypervector (unigrams + bigrams + char trigrams +
    optional semantic hook)."""
    tokens = _tokenize(text)
    if not tokens:
        return random_hv(0)

    parts: list[np.ndarray] = [token_hv(t) for t in tokens]          # unigrams
    for a, b in zip(tokens, tokens[1:], strict=False):           # bigrams (order)
        parts.append(bind(token_hv(a), _token_hv_shifted(b)))
    if _USE_TRIGRAMS:
        for t in tokens:                                            # subword
            parts.extend(_char_trigrams(t))

    if _semantic_hook is not None:                                  # optional semantics
        try:
            sem = _semantic_hook(text)
            # The bundle is majority voting: a single semantic vector would
            # be drowned out among dozens of lexical ones. It's replicated
            # so it carries ~50% of the total weight and semantics actually
            # has influence (tunable weight).
            weight = max(1, int(len(parts) * SEMANTIC_WEIGHT))
            parts.extend([sem] * weight)
        except Exception:
            pass                                                    # never break over the hook

    return bundle(parts)
