"""
Álgebra de hipervectores (VSA / HDC) — el corazón de hipercampo.

No usamos embeddings densos ni GPU. Trabajamos con vectores binarios enormes
(D = 10.000 bits) y tres operaciones que sí tienen "significado algebraico":

    bind(a, b)   -> liga dos conceptos en uno nuevo y reversible   (XOR)
    bundle([..]) -> mete varios en una "bolsa" (superposición)      (voto mayoría)
    permute(a)   -> marca orden / posición                          (rotación de bits)

Comparar dos recuerdos = contar en cuántos bits difieren (distancia de Hamming),
que la CPU resuelve con popcount en nanosegundos. Cero GPU, cero índice ANN.
"""

import numpy as np

D = 10_000                 # dimensionalidad (bits). Alta -> casi-ortogonalidad.
_BYTES = (D + 7) // 8      # 1250 bytes por hipervector empaquetado


def random_hv(seed: int | None = None) -> np.ndarray:
    """Un hipervector aleatorio, empaquetado en bits (uint8[1250])."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=D, dtype=np.uint8)
    return np.packbits(bits)


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Ligar = XOR bit a bit. Reversible: bind(bind(a,b), b) == a."""
    return np.bitwise_xor(a, b)


# Patrón de desempate FIJO y pseudoaleatorio (50/50). Resolver los empates siempre
# a 0 sesgaría la densidad por debajo de 0.5 (con nº par de componentes el bundle
# degeneraba casi en un AND: densidad ~0.25 con 2). Con este desempate, la densidad
# se mantiene en ~0.5 y la similitud base entre bundles no relacionados vuelve a ~0.5.
_TIEBREAK = np.unpackbits(random_hv(0xC0FFEE))[:D].astype(np.int32)


def bundle(hvs: list[np.ndarray]) -> np.ndarray:
    """
    Agrupar = voto por mayoría bit a bit. El resultado se parece a TODOS sus
    componentes a la vez (superposición). Los empates se rompen con un patrón fijo
    pseudoaleatorio 50/50 (no siempre a 0), para no sesgar la densidad.
    """
    if not hvs:
        return random_hv(0)
    if len(hvs) == 1:
        return hvs[0].copy()
    acc = np.zeros(D, dtype=np.int32)
    for h in hvs:
        acc += np.unpackbits(h)[:D].astype(np.int32) * 2 - 1   # 0/1 -> -1/+1
    bits = np.where(acc > 0, 1, np.where(acc < 0, 0, _TIEBREAK)).astype(np.uint8)
    return np.packbits(bits)


def permute(a: np.ndarray, shift: int = 1) -> np.ndarray:
    """Rotar los bits: codifica orden/posición sin colisionar con el original."""
    if shift == 0:
        return a.copy()
    bits = np.unpackbits(a)[:D]
    bits = np.roll(bits, shift)
    return np.packbits(bits)


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    """Número de bits en los que difieren (0 = idénticos, D = opuestos)."""
    return int(np.unpackbits(np.bitwise_xor(a, b)).sum())


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similitud en [0,1]. 1 = idéntico, 0.5 = no relacionado (ortogonal)."""
    return 1.0 - hamming(a, b) / D


# popcount vectorizado: nativo (NumPy>=2.0, en C) o tabla de 256 bytes de respaldo.
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)
_HAS_NATIVE_POPCOUNT = hasattr(np, "bitwise_count")


def _popcount_rows(x: np.ndarray) -> np.ndarray:
    if _HAS_NATIVE_POPCOUNT:
        return np.bitwise_count(x).sum(axis=1)       # C nativo, sin alocar LUT gather
    return _POPCOUNT[x].sum(axis=1)


def similarity_batch(q: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Similitud de 'q' (uint8[1250]) contra CADA fila de 'matrix' (N x 1250), de
    una sola vez. Sustituye el bucle fila-a-fila por operaciones vectorizadas: XOR
    con broadcast + popcount. Escala mucho mejor con N."""
    if matrix.size == 0:
        return np.empty(0, dtype=np.float64)
    dist = _popcount_rows(np.bitwise_xor(matrix, q))  # (N,) distancia de Hamming
    return 1.0 - dist / D


def stack_hvs(blobs) -> np.ndarray:
    """Apila una lista de hipervectores empaquetados en una matriz (N x 1250)."""
    if not blobs:
        return np.empty((0, _BYTES), dtype=np.uint8)
    return np.frombuffer(b"".join(blobs), dtype=np.uint8).reshape(len(blobs), _BYTES)


def to_blob(hv: np.ndarray) -> bytes:
    return hv.tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.uint8).copy()
