"""
Navigable-graph validation on a REAL (non-synthetic) corpus.

The scale benchmark (`nav_scale.py`) uses synthetic clusters at ~0.99 similarity,
which are trivially separable. This benchmark uses fuzzy REAL TEXT: Python standard
library docstrings grouped by module (the ground-truth category). It is offline and
reproducible on any machine. The honest question is whether b12's headline claim
(navigation retrieves like a scan while touching little) survives real text.

It measures the SAME production path (store.reindex_navgraph + store.navgraph +
graph.search_with_stats):
  - index FIDELITY: navigation recall@5 versus a full scan (ground truth),
  - percentage visited, latency, and RSS (actual cost for agents),
  - GROUP precision@5 for navigation and scan (semantic quality; it will be low in
    lexical mode, which is precisely the known synonym bottleneck).

Run:  python scripts/nav_real.py [--check] [--json]
"""

import argparse
import ctypes
import importlib
import json
import os
import inspect
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

import numpy as np

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.core.encoder import encode_text          # noqa: E402
from hipercampo.storage.store import Store                    # noqa: E402
from hipercampo.core.vsa import similarity_batch           # noqa: E402

DB = "data/_nav_real.db"
MODULES = ["email", "http", "json", "math", "random", "os", "xml", "unittest",
           "logging", "sqlite3", "statistics", "argparse", "collections", "asyncio",
           "socket", "decimal", "datetime", "threading", "hashlib", "urllib",
           "html", "csv", "configparser", "tarfile", "zipfile", "ftplib", "smtplib"]

DEFAULT_THRESHOLDS = {
    "min_corpus": 500,
    "min_fidelity": 0.98,
    "max_p95_ms": 30.0,
    "max_visited_ratio": 0.55,
    "max_rss_mb": 256.0,
    "max_group_gap": 0.02,
}


def clean() -> None:
    for suf in ("", "-wal", "-shm"):
        Path(DB + suf).unlink(missing_ok=True)


def harvest() -> tuple[list[str], list[int], list[str]]:
    """Collect real docstrings labeled by module, including class members for volume."""
    texts, labels, names = [], [], []
    seen: set[str] = set()
    for label, root in enumerate(MODULES):
        try:
            mod = importlib.import_module(root)
        except Exception:
            continue
        # Only top-level members: importing submodules through pkgutil can execute code
        # (for example unittest.__main__ runs tests). Module classes and functions give
        # enough real text and volume without those side effects.
        for _, obj in inspect.getmembers(mod):
            try:
                doc = inspect.getdoc(obj)
                members = inspect.getmembers(obj) if inspect.isclass(obj) else []
            except Exception:
                doc, members = None, []
            candidates = [doc] + [inspect.getdoc(item) for _, item in members[:40]]
            for d in candidates:
                if not d or len(d) < 80:
                    continue
                d = " ".join(d.split())[:400]
                if d in seen:
                    continue
                seen.add(d)
                texts.append(d)
                labels.append(label)
                names.append(root)
    return texts, labels, names


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def current_rss_mb() -> float:
    """Return current resident memory using stdlib only, without requiring psutil."""
    try:
        statm = Path("/proc/self/statm")
        if statm.exists():
            pages = int(statm.read_text(encoding="ascii").split()[1])
            return pages * os.sysconf("SC_PAGE_SIZE") / 1024 / 1024
        if sys.platform == "win32":
            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            get_process = ctypes.windll.kernel32.GetCurrentProcess
            get_process.restype = ctypes.c_void_p
            get_memory = ctypes.windll.psapi.GetProcessMemoryInfo
            get_memory.argtypes = [
                ctypes.c_void_p,
                ctypes.POINTER(ProcessMemoryCounters),
                ctypes.c_ulong,
            ]
            get_memory.restype = ctypes.c_int
            ok = get_memory(get_process(), ctypes.byref(counters), counters.cb)
            if ok:
                return counters.WorkingSetSize / 1024 / 1024
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
        return usage / divisor
    except (OSError, ValueError, AttributeError, ImportError):
        return float("inf")


def evaluate(metrics: dict, thresholds: dict | None = None) -> list[str]:
    """Return readable regressions; an empty list means the gate passes."""
    limits = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    failures = []
    checks = [
        ("corpus", metrics["corpus"], limits["min_corpus"], ">="),
        ("fidelity", metrics["fidelity"], limits["min_fidelity"], ">="),
        ("p95_ms", metrics["p95_ms"], limits["max_p95_ms"], "<="),
        ("visited_ratio", metrics["visited_ratio"], limits["max_visited_ratio"], "<="),
        ("rss_mb", metrics["rss_mb"], limits["max_rss_mb"], "<="),
    ]
    for name, actual, expected, op in checks:
        failed = actual < expected if op == ">=" else actual > expected
        if failed:
            failures.append(f"{name}: {actual:.3f} must be {op} {expected:.3f}")
    group_gap = metrics["group_scan"] - metrics["group_nav"]
    if group_gap > limits["max_group_gap"]:
        failures.append(
            f"group_gap: {group_gap:.3f} must be <= {limits['max_group_gap']:.3f}"
        )
    return failures


def run_benchmark(query_count: int = 40, candidates: int = 12, ef: int = 12,
                  shortcuts: int = 2,
                  adaptive_shortcuts: bool = True) -> dict:
    texts, labels, names = harvest()
    n = len(texts)
    if n < 6:
        raise RuntimeError(f"insufficient real corpus: {n}")
    label_array = np.array(labels)
    distribution = {name: names.count(name) for name in set(names)}

    clean()
    store = Store(DB, namespace="real")
    try:
        started = time.perf_counter()
        codes, ids = [], []
        with store.transaction():
            for txt in texts:
                hv = encode_text(txt)
                mid = store.add(txt, hv, 1.0, 0.5, 0.6)
                codes.append(hv)
                ids.append(mid)
        seed_seconds = time.perf_counter() - started
        mat = np.frombuffer(
            b"".join(code.tobytes() for code in codes), dtype=np.uint8
        ).reshape(n, 1250)
        id_a_pos = {mid: i for i, mid in enumerate(ids)}

        tracemalloc.start()
        started = time.perf_counter()
        store.reindex_navgraph(M=12)
        graph = store.navgraph(
            shortcuts=shortcuts, adaptive_shortcuts=adaptive_shortcuts
        )
        index_seconds = time.perf_counter() - started
        _, index_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_mb = current_rss_mb()

        rng = np.random.default_rng(7)
        sample = rng.choice(n, size=min(query_count, n), replace=False)
        fidelidad, grupo_nav, grupo_scan, lat, vis = [], [], [], [], []
        for qi in sample:
            qi = int(qi)
            q, qid, lbl = codes[qi], ids[qi], label_array[qi]
            sims = similarity_batch(q, mat)
            orden = [int(p) for p in np.argsort(sims)[::-1] if int(p) != qi][:5]
            scan_ids = {ids[p] for p in orden}
            started = time.perf_counter()
            found, visited = graph.search_with_stats(q, k=candidates, ef=ef)
            lat.append((time.perf_counter() - started) * 1000)
            vis.append(visited)
            nav_ids = [mid for mid, _ in found if mid != qid][:5]
            fidelidad.append(len(set(nav_ids) & scan_ids) / 5.0)
            grupo_nav.append(
                np.mean([label_array[id_a_pos[mid]] == lbl
                         for mid in nav_ids if mid in id_a_pos])
                if nav_ids else 0.0
            )
            grupo_scan.append(np.mean([label_array[p] == lbl for p in orden]))

        return {
            "corpus": n,
            "modules": len(set(names)),
            "queries": len(sample),
            "candidates": candidates,
            "ef": ef,
            "shortcuts": shortcuts,
            "adaptive_shortcuts": adaptive_shortcuts,
            "effective_shortcuts": graph.effective_shortcuts,
            "component_count": graph.component_count,
            "mean_base_degree": graph.mean_base_degree,
            "two_hop_coverage": graph.two_hop_coverage,
            "distribution": dict(
                sorted(distribution.items(), key=lambda item: -item[1])[:8]
            ),
            "seed_seconds": seed_seconds,
            "index_seconds": index_seconds,
            "index_peak_mb": index_peak / 1024 / 1024,
            "rss_mb": rss_mb,
            "fidelity": statistics.mean(fidelidad),
            "p50_ms": statistics.median(lat),
            "p95_ms": percentile(lat, 0.95),
            "visited_mean": statistics.mean(vis),
            "visited_ratio": statistics.mean(vis) / n,
            "group_nav": statistics.mean(grupo_nav),
            "group_scan": statistics.mean(grupo_scan),
        }
    finally:
        store.close()
        clean()


def print_report(metrics: dict) -> None:
    print(
        f"REAL corpus: {metrics['corpus']} docstrings from {metrics['modules']} modules "
        f"(category = module)"
    )
    print("distribution:", metrics["distribution"], "…")
    print(
        f"configuration: candidates={metrics['candidates']} · "
        f"ef={metrics['ef']} · shortcuts={metrics['effective_shortcuts']}/"
        f"{metrics['shortcuts']} · components={metrics['component_count']} · "
        f"degree={metrics['mean_base_degree']:.1f} · "
        f"two-hop coverage={100 * metrics['two_hop_coverage']:.1f}%"
    )
    print(
        f"seed+encode: {metrics['seed_seconds']:.1f}s · "
        f"index: {metrics['index_seconds']:.1f}s · "
        f"RSS: {metrics['rss_mb']:.1f}MB · "
        f"index Python peak: {metrics['index_peak_mb']:.1f}MB"
    )
    print("\n=== VERDICT on REAL corpus ===")
    print(f"navigation vs scan fidelity (recall@5): {metrics['fidelity']:.3f}")
    print(
        f"navigation latency: p50={metrics['p50_ms']:.2f}ms "
        f"p95={metrics['p95_ms']:.2f}ms"
    )
    print(
        f"visited: {metrics['visited_mean']:.0f} of {metrics['corpus']} "
        f"({100 * metrics['visited_ratio']:.1f}%)"
    )
    print(
        f"group precision@5 — navigation: {metrics['group_nav']:.3f} · "
        f"scan: {metrics['group_scan']:.3f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Navigable benchmark on a real corpus")
    parser.add_argument("--check", action="store_true",
                        help="fail if any metric crosses its threshold")
    parser.add_argument("--json", action="store_true",
                        help="emit metrics and verdict as JSON")
    parser.add_argument("--queries", type=int, default=40,
                        help="number of deterministic queries (default: 40)")
    parser.add_argument("--candidates", type=int, default=12,
                        help="navigation candidates (default: 12)")
    parser.add_argument("--ef", type=int, default=12,
                        help="search width (default: 12)")
    parser.add_argument("--shortcuts", type=int, default=2,
                        help="ephemeral shortcuts per node (default: 2)")
    parser.add_argument("--adaptive-shortcuts", action=argparse.BooleanOptionalAction,
                        default=True, help="adapt shortcuts to graph topology")
    args = parser.parse_args(argv)
    if args.queries < 1:
        parser.error("--queries must be greater than zero")
    if args.candidates < 5 or args.ef < 1 or args.shortcuts < 0:
        parser.error("candidates>=5, ef>0, and shortcuts>=0 are required")

    metrics = run_benchmark(
        args.queries, candidates=args.candidates, ef=args.ef,
        shortcuts=args.shortcuts, adaptive_shortcuts=args.adaptive_shortcuts
    )
    failures = evaluate(metrics) if args.check else []
    result = {
        **metrics,
        "gate": {
            "checked": args.check,
            "passed": not failures,
            "failures": failures,
            "thresholds": DEFAULT_THRESHOLDS,
        },
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print_report(metrics)
        if args.check:
            print("\n=== QUALITY GATE ===")
            if failures:
                for failure in failures:
                    print(f"FAIL · {failure}")
            else:
                print("OK · all metrics satisfy their contract")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
