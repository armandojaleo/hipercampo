"""
Hook semántico OPCIONAL — cierra el hueco de los sinónimos.

El codificador por defecto (encoder.py) es léxico: perfecto con palabras
compartidas, flojo con sinónimos ("cobros" vs "pagos"). Este módulo permite
enchufar semántica de verdad SIN traicionar la tesis VSA: un embedding denso se
proyecta a un hipervector binario mediante **proyección aleatoria con signo**
(SimHash / LSH), que preserva aproximadamente la similitud coseno como distancia
de Hamming. Así la semántica "viaja" al espacio VSA y se liga al resto.

  embedding denso (de un modelo) ──SimHash──▶ hipervector binario ──▶ bundle VSA

CÓDIGO ORIGINAL: el puente SimHash de abajo es nuestro. Los MODELOS de embeddings
son de terceros y con su propia licencia; hipercampo NO incluye ninguno. La
implementación de referencia usa sentence-transformers (Apache-2.0), instalable
aparte con `pip install hipercampo[semantic]`. Ver ATTRIBUTION.md.
"""

from typing import Callable

import numpy as np

from .vsa import D

_proj_cache: dict[int, np.ndarray] = {}


def _projection(dim: int) -> np.ndarray:
    """Matriz de proyección aleatoria fija y determinista (D x dim)."""
    R = _proj_cache.get(dim)
    if R is None:
        rng = np.random.default_rng(42)                 # semilla fija -> reproducible
        R = rng.standard_normal((D, dim)).astype(np.float32)
        _proj_cache[dim] = R
    return R


def embedding_to_hv(vec) -> np.ndarray:
    """Vector denso -> hipervector binario empaquetado, vía SimHash (signo de una
    proyección aleatoria). Preserva similitud: vectores parecidos -> Hamming bajo."""
    vec = np.asarray(vec, dtype=np.float32).ravel()
    projected = _projection(vec.shape[0]) @ vec
    bits = (projected > 0).astype(np.uint8)
    return np.packbits(bits)


def make_hook(embed_fn: Callable[[str], np.ndarray]) -> Callable[[str], np.ndarray]:
    """Construye un hook a partir de CUALQUIER función de embedding texto->vector
    denso (la tuya, la de tu proveedor, la que sea). Úsalo con
    encoder.set_semantic_hook(make_hook(mi_embed))."""
    return lambda text: embedding_to_hv(embed_fn(text))


def make_sentence_transformer_hook(
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
) -> Callable[[str], np.ndarray]:
    """Implementación de referencia con sentence-transformers (dependencia OPCIONAL
    de terceros, Apache-2.0; el modelo se descarga aparte con su licencia).

        from hipercampo import encoder, semantic
        encoder.set_semantic_hook(semantic.make_sentence_transformer_hook())
    """
    from sentence_transformers import SentenceTransformer  # import perezoso, opcional

    model = SentenceTransformer(model_name)

    def embed(text: str) -> np.ndarray:
        return model.encode(text, normalize_embeddings=True)

    return make_hook(embed)
