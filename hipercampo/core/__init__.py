"""
CORE — the algebra and the encoding. Pure algorithms, no state or disk.

    vsa        hypervectors: bind, bundle, permute, popcount similarity
    encoder    text -> hypervector (lexical, with an optional semantic hook)
    semantic   the reference hook (sentence-transformers), optional
    atomize    chunk a text into atomic facts before encoding it
    surprise   prediction-error surprise (incremental model, MDL)
    navgraph   small-world navigable graph over the hypervectors

This is the BOTTOM layer: it imports nothing from the other ones. Everything
here is deterministic and can be measured in isolation, which is exactly
what `scripts/benchmark.py` does.
"""
