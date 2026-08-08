"""
OPTIONAL semantic hook — closes the synonym gap.

The default encoder (encoder.py) is lexical: perfect with shared words,
weak with synonyms ("earnings" vs "revenue"). This module lets you plug in
real semantics WITHOUT betraying the VSA thesis: a dense embedding gets
projected onto a binary hypervector via **signed random projection**
(SimHash / LSH), which approximately preserves cosine similarity as Hamming
distance. That's how semantics "travels" into VSA space and binds with the rest.

  dense embedding (from a model) ──SimHash──▶ binary hypervector ──▶ VSA bundle

ORIGINAL CODE: the SimHash bridge below is ours. The embedding MODELS are
third-party, under their own license; hipercampo does NOT bundle any. The
reference implementation uses sentence-transformers (Apache-2.0), installable
separately with `pip install hipercampo[semantic]`. See docs/ATTRIBUTION.md.
"""

from typing import Callable

import numpy as np

from .vsa import D

_proj_cache: dict[int, np.ndarray] = {}


def _projection(dim: int) -> np.ndarray:
    """Fixed, deterministic random projection matrix (D x dim)."""
    R = _proj_cache.get(dim)
    if R is None:
        rng = np.random.default_rng(42)                 # fixed seed -> reproducible
        R = rng.standard_normal((D, dim)).astype(np.float32)
        _proj_cache[dim] = R
    return R


def embedding_to_hv(vec) -> np.ndarray:
    """Dense vector -> packed binary hypervector, via SimHash (sign of a
    random projection). Preserves similarity: similar vectors -> low Hamming distance."""
    vec = np.asarray(vec, dtype=np.float32).ravel()
    projected = _projection(vec.shape[0]) @ vec
    bits = (projected > 0).astype(np.uint8)
    return np.packbits(bits)


def make_hook(embed_fn: Callable[[str], np.ndarray]) -> Callable[[str], np.ndarray]:
    """Builds a hook from ANY text->dense-vector embedding function (yours,
    your provider's, whatever). Use it with
    encoder.set_semantic_hook(make_hook(my_embed))."""
    return lambda text: embedding_to_hv(embed_fn(text))


def make_sentence_transformer_hook(
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> Callable[[str], np.ndarray]:
    """Reference implementation using sentence-transformers (OPTIONAL
    third-party dependency, Apache-2.0; the model is downloaded separately
    under its own license).

        from hipercampo import encoder, semantic
        encoder.set_semantic_hook(semantic.make_sentence_transformer_hook())
    """
    from sentence_transformers import SentenceTransformer  # lazy, optional import

    model = SentenceTransformer(model_name)

    def embed(text: str) -> np.ndarray:
        return model.encode(text, normalize_embeddings=True)

    return make_hook(embed)
