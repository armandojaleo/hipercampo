"""
Recall latency and memory at scale — run: python scripts/latency.py [N...]

The question an embedded system or robot asks before trusting hipercampo: how long
does recall take with many memories, and how much RAM does it cost? Without this
number, "works for robots" is an opinion. This script measures it.

For each N, measure full-scan p50/p95/p99 latency, bounded `max_scan=2000` latency,
and peak recall RAM (dominated by the N×1250 matrix).

MEASURE BEFORE BELIEVING: the house rule. This historical benchmark predates the
sublinear index; it shows where linear scanning hurts and how much a bound helps.
"""

import gc
import sys
import time
import tracemalloc
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.core.encoder import encode_text            # noqa: E402
from hipercampo.cycle.memory import Hipercampo              # noqa: E402

_DB = "data/_latency_bench.db"
_MAX_SCAN = 2000            # Robot-style bound: best among the 2,000 liveliest.
_QUERIES = 40               # Recalls per measurement for stable percentiles.


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _seed(n: int) -> Hipercampo:
    """Seed n distinct memories through storage; this measures recall, not writes."""
    _clean()
    hc = Hipercampo(_DB, namespace="bench")
    temas = ["servidor", "cliente", "despliegue", "reunión", "clave", "error",
             "ruta", "base de datos", "red", "certificado", "cola", "caché"]
    with hc.store.transaction():
        for i in range(n):
            t = temas[i % len(temas)]
            texto = f"el {t} numero {i} tiene el detalle particular {i * 7 % 9973}"
            hc.store.add(texto, encode_text(texto), 1.0, 0.5, 0.5)
    return hc


def _percentiles(muestras_ms):
    s = sorted(muestras_ms)

    def p(q):
        return s[min(len(s) - 1, int(q * len(s)))]
    return p(0.50), p(0.95), p(0.99)


def _measure(hc: Hipercampo, max_scan=None):
    queries = [f"detalle del servidor numero {i * 137}" for i in range(_QUERIES)]
    hc.recall(queries[0], k=5, max_scan=max_scan)   # Warm-up pays cache costs.
    timings = []
    for q in queries:
        t0 = time.perf_counter()
        hc.recall(q, k=5, max_scan=max_scan)
        timings.append((time.perf_counter() - t0) * 1000)
    return _percentiles(timings)


def _peak_ram_mb(hc: Hipercampo):
    gc.collect()
    tracemalloc.start()
    hc.recall("detalle del servidor numero 99", k=5)
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return peak / (1024 * 1024)


def main(sizes):
    print(f"Recall latency (p50/p95/p99, ms) — {_QUERIES} queries per cell")
    print(f"bound = max_scan={_MAX_SCAN}\n")
    header = f"{'N':>8} | {'full p50/p95/p99':>24} | {'bounded p50/p95/p99':>24} | RAM/recall"
    print(header)
    print("-" * 78)
    for n in sizes:
        hc = _seed(n)
        full = _measure(hc, max_scan=None)
        bounded = _measure(hc, max_scan=_MAX_SCAN)
        ram = _peak_ram_mb(hc)
        hc.close()
        f = "/".join(f"{x:5.1f}" for x in full)
        c = "/".join(f"{x:5.1f}" for x in bounded)
        print(f"{n:>8} | {f:>24} | {c:>24} | {ram:7.1f} MB")
    _clean()
    print("\nNote: this linear-scan benchmark predates the sublinear index. The bound "
          "keeps latency flat by examining only the liveliest memories.")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]] or [1000, 5000, 10000]
    main(args)
