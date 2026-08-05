"""Escala del grafo navegable integrado (SQLite + VSA + caché + beam).

Ejecuta: python scripts/nav_scale.py 10000 [100000]
Genera grupos VSA conocidos y vecinos locales sin pagar un reindexado O(N²).
Mide precisión de grupo, visitas, latencia y coste frío/caliente del índice.
"""

import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.store import Store  # noqa: E402
from hipercampo.vsa import random_hv  # noqa: E402

DB = "data/_nav_scale.db"
GROUP_SIZE = 100
QUERIES = 30


def clean() -> None:
    for suffix in ("", "-wal", "-shm"):
        Path(DB + suffix).unlink(missing_ok=True)


def seed(store: Store, n: int) -> tuple[list[np.ndarray], float]:
    rng = np.random.default_rng(2026)
    bases: list[np.ndarray] = []
    started = time.perf_counter()
    with store.transaction():
        for cluster_id in range((n + GROUP_SIZE - 1) // GROUP_SIZE):
            base = random_hv(100_000 + cluster_id)
            bases.append(base)
            cluster: list[int] = []
            count = min(GROUP_SIZE, n - cluster_id * GROUP_SIZE)
            for item in range(count):
                hv = base.copy()
                for pos in rng.choice(len(hv), size=4, replace=False):
                    hv[pos] ^= np.uint8(1 << int(rng.integers(0, 8)))
                mid = store.add(
                    f"topic {cluster_id} item {item}", hv, 1.0, 0.5, 0.8
                )
                cluster.append(mid)
            for index, mid in enumerate(cluster):
                for step in (1, 2, 4, 8):
                    other = cluster[(index + step) % len(cluster)]
                    src, dst = sorted((mid, other))
                    store.db.execute(
                        "INSERT OR IGNORE INTO links(src,dst,weight,namespace,type,"
                        "status,created_at) VALUES(?,?,?,?,?,?,?)",
                        (src, dst, 0.99, "bench", "knn", "confirmed", time.time()),
                    )
    store._invalidate_nav()
    return bases, (time.perf_counter() - started) * 1000


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def benchmark(n: int) -> None:
    clean()
    store = Store(DB, namespace="bench")
    bases, seed_ms = seed(store, n)

    tracemalloc.start()
    started = time.perf_counter()
    graph = store.navgraph(shortcuts=2)
    cold_ms = (time.perf_counter() - started) * 1000
    resident, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    started = time.perf_counter()
    same = store.navgraph(shortcuts=2)
    warm_ms = (time.perf_counter() - started) * 1000

    rng = np.random.default_rng(7)
    sample = rng.choice(len(bases), size=min(QUERIES, len(bases)), replace=False)
    print(
        f"N={n:,} | seed={seed_ms / 1000:.2f}s | "
        f"index cold={cold_ms:.1f}ms warm={warm_ms:.3f}ms | "
        f"index resident={resident / 1024 / 1024:.1f}MB "
        f"peak={peak / 1024 / 1024:.1f}MB | same={same is graph}"
    )
    for candidates, ef, entry_count in (
        (12, 12, 0), (16, 16, 0), (16, 32, 0), (16, 48, 0), (16, 48, 1)
    ):
        entries = None
        if entry_count:
            entries = [1 + i * n // entry_count for i in range(entry_count)]
        latencies: list[float] = []
        visits: list[int] = []
        precision: list[float] = []
        for cluster_id in sample:
            started = time.perf_counter()
            found, visited = graph.search_with_stats(
                bases[int(cluster_id)], k=candidates, ef=ef, entradas=entries
            )
            latencies.append((time.perf_counter() - started) * 1000)
            visits.append(visited)
            top = found[:5]
            precision.append(
                sum(1 for mid, _ in top if (mid - 1) // GROUP_SIZE == cluster_id)
                / len(top)
            )
        print(
            f"  candidates={candidates:>2} ef={ef:>2} "
            f"entries={'auto' if entries is None else entry_count} | "
            f"p50={statistics.median(latencies):.3f}ms "
            f"p95={percentile(latencies, 0.95):.3f}ms | "
            f"visited={statistics.mean(visits):.1f} "
            f"({100 * statistics.mean(visits) / n:.3f}%) | "
            f"cluster precision@5={statistics.mean(precision):.3f}"
        )
    store.close()
    clean()


def main() -> None:
    sizes = [int(value) for value in sys.argv[1:]] or [10_000]
    for size in sizes:
        benchmark(size)


if __name__ == "__main__":
    try:
        main()
    finally:
        clean()
