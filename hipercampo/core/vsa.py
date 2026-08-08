"""
Hypervector algebra (VSA / HDC) — hipercampo's core.

No dense embeddings, no GPU. We work with huge binary vectors
(D = 10,000 bits) and three operations that genuinely have "algebraic meaning":

    bind(a, b)   -> ties two concepts into a new, reversible one   (XOR)
    bundle([..]) -> puts several into a "bag" (superposition)      (majority vote)
    permute(a)   -> marks order / position                          (bit rotation)

Comparing two memories = counting how many bits they differ in (Hamming
distance), which the CPU solves with popcount in nanoseconds. Zero GPU,
zero ANN index.
"""

import numpy as np

D = 10_000                 # dimensionality (bits). High -> near-orthogonality.
_BYTES = (D + 7) // 8      # 1250 bytes per packed hypervector


def random_hv(seed: int | None = None) -> np.ndarray:
    """A random hypervector, bit-packed (uint8[1250])."""
    rng = np.random.default_rng(seed)
    bits = rng.integers(0, 2, size=D, dtype=np.uint8)
    return np.packbits(bits)


def bind(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Bind = bitwise XOR. Reversible: bind(bind(a,b), b) == a."""
    return np.bitwise_xor(a, b)


# FIXED, pseudorandom (50/50) tie-break pattern. Always resolving ties to 0
# would bias density below 0.5 (with an even number of components the bundle
# degenerated almost into an AND: density ~0.25 with 2). With this
# tie-break, density stays around ~0.5 and the base similarity between
# unrelated bundles goes back to ~0.5.
_TIEBREAK = np.unpackbits(random_hv(0xC0FFEE))[:D].astype(np.int32)


# How many hypervectors get unpacked at once in `bundle`. Each takes up D
# bytes unpacked (10 KB), so 64 is 640 KB: the batch and its sum fit in
# L2 cache. The 64/128/256/512 sweep was measured and the smallest wins
# clearly (1.67 s vs 2.18 s for 200 texts): locality governs here, not the
# number of NumPy calls. It also caps the RAM for a very long text.
_BUNDLE_CHUNK = 64


def bundle(hvs: list[np.ndarray]) -> np.ndarray:
    """
    Bundle = bitwise majority vote. The result resembles ALL of its
    components at once (superposition). Ties are broken with a fixed,
    pseudorandom 50/50 pattern (not always to 0), so density isn't biased.

    The vote is counted VECTORIZED in batches: stacking and
    `unpackbits(axis=1)` does in C what used to be a Python loop with an
    `astype` per component. Encoding an average text goes from ~26 ms to
    ~6 ms (measured), and this is the HOTTEST path in the system —every
    write and every query pass through here—.
    """
    if not hvs:
        return random_hv(0)
    if len(hvs) == 1:
        return hvs[0].copy()
    # We count ONES (not +-1): so the accumulator is a sum of bits and a
    # tie is exactly 2*ones == n. Equivalent to the old vote, without the
    # intermediate step.
    ones = np.zeros(D, dtype=np.int32)
    for start in range(0, len(hvs), _BUNDLE_CHUNK):
        batch = hvs[start:start + _BUNDLE_CHUNK]
        # uint8 per batch: with 64 rows the max is 64, so a 16-bit
        # accumulator is plenty and faster than a 32-bit one. The total is int32.
        mat = np.stack(batch)
        ones += np.unpackbits(mat, axis=1)[:, :D].sum(axis=0, dtype=np.uint16)
    n = len(hvs)
    double = ones * 2
    bits = np.where(double > n, 1, np.where(double < n, 0, _TIEBREAK)).astype(np.uint8)
    return np.packbits(bits)


def permute(a: np.ndarray, shift: int = 1) -> np.ndarray:
    """Rotate the bits: encodes order/position without colliding with the original."""
    if shift == 0:
        return a.copy()
    bits = np.unpackbits(a)[:D]
    bits = np.roll(bits, shift)
    return np.packbits(bits)


# vectorized popcount: native (NumPy>=2.0, in C) or a 256-byte lookup table fallback.
_POPCOUNT = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)
_HAS_NATIVE_POPCOUNT = hasattr(np, "bitwise_count")


# Count bits 16 at a time instead of byte by byte: half as many elements to
# walk and sum, for the SAME total (a popcount doesn't depend on how the
# bits are grouped or the byte order within the word). Measured over
# 1500x1250: 1.38 s -> 0.79 s, and it's the primitive every comparison in
# the system goes through. Only used if bytes-per-vector is even and the row
# is contiguous; if D ever stops satisfying that, it falls back to the usual
# path instead of breaking.
_WIDE_VIEW = _BYTES % 2 == 0


def _wide(x: np.ndarray) -> np.ndarray:
    """The same memory viewed as 16-bit words, if possible."""
    if _WIDE_VIEW and x.flags["C_CONTIGUOUS"]:
        return x.view(np.uint16)
    return x


def _popcount_rows(x: np.ndarray) -> np.ndarray:
    if _HAS_NATIVE_POPCOUNT:                         # native C, no LUT gather allocation
        return np.bitwise_count(_wide(x)).sum(axis=1, dtype=np.uint32)
    return _POPCOUNT[x].sum(axis=1)


def _popcount(x: np.ndarray) -> int:
    """Bits set to 1 in a packed hypervector, without unpacking it."""
    if _HAS_NATIVE_POPCOUNT:
        return int(np.bitwise_count(_wide(x)).sum(dtype=np.uint32))
    return int(_POPCOUNT[x].sum())


def hamming(a: np.ndarray, b: np.ndarray) -> int:
    """Number of bits that differ (0 = identical, D = opposite).

    Via popcount over the packed bytes: `unpackbits` used to allocate and
    walk a D-byte array per comparison, and this function lives inside the
    O(N^2) loops of sleep, consolidation and role cleanup."""
    return _popcount(np.bitwise_xor(a, b))


def similarity(a: np.ndarray, b: np.ndarray) -> float:
    """Similarity in [0,1]. 1 = identical, 0.5 = unrelated (orthogonal)."""
    return 1.0 - hamming(a, b) / D


def similarity_batch(q: np.ndarray, matrix: np.ndarray) -> np.ndarray:
    """Similarity of 'q' (uint8[1250]) against EVERY row of 'matrix' (N x
    1250), in one go. Replaces the row-by-row loop with vectorized
    operations: broadcast XOR + popcount. Scales much better with N."""
    if matrix.size == 0:
        return np.empty(0, dtype=np.float64)
    dist = _popcount_rows(np.bitwise_xor(matrix, q))  # (N,) Hamming distance
    return 1.0 - dist / D


def similarity_pairs(matrix: np.ndarray, ia, ib) -> np.ndarray:
    """Similarity of MANY pairs (matrix[ia[i]], matrix[ib[i]]) at once.

    `similarity_batch` compares one against everything; this compares a
    list of specific pairs, which is what dream needs when scoring open
    wedges (tens of thousands of loose pairs, not one row against the whole
    corpus). Chunked so two full copies of the matrix aren't materialized
    when there are very many pairs."""
    ia = np.asarray(ia, dtype=np.intp)
    ib = np.asarray(ib, dtype=np.intp)
    if ia.size == 0:
        return np.empty(0, dtype=np.float64)
    out = np.empty(ia.size, dtype=np.float64)
    step = 8192                              # ~10 MB per batch at D = 10,000 bits
    for start in range(0, ia.size, step):
        end = start + step
        dist = _popcount_rows(np.bitwise_xor(matrix[ia[start:end]],
                                             matrix[ib[start:end]]))
        out[start:end] = 1.0 - dist / D
    return out


def stack_hvs(blobs) -> np.ndarray:
    """Stacks a list of packed hypervectors into a matrix (N x 1250)."""
    if not blobs:
        return np.empty((0, _BYTES), dtype=np.uint8)
    return np.frombuffer(b"".join(blobs), dtype=np.uint8).reshape(len(blobs), _BYTES)


def to_blob(hv: np.ndarray) -> bytes:
    return hv.tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.uint8).copy()
