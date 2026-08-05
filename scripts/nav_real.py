"""
Validación en corpus REAL (no sintético) del grafo navegable.

El benchmark de escala (`nav_scale.py`) usa clústeres sintéticos a similitud ~0.99:
trivialmente separables. Aquí se valida sobre TEXTO real y difuso —docstrings de la
librería estándar de Python, agrupados por módulo (categoría con verdad)—, offline y
reproducible en cualquier máquina. La pregunta honesta: ¿el titular de b12 (navegar
recupera como escanear, tocando poco) aguanta fuera del banco sintético?

Mide, sobre el MISMO camino de producción (store.reindex_navgraph + store.navgraph +
graph.search_with_stats):
  - FIDELIDAD del índice: recall@5 de navegar vs escaneo completo (la verdad),
  - %visitado, latencia y RSS (coste real para robots),
  - precisión de GRUPO@5: navegar y escaneo (calidad semántica; será baja en léxico,
    y ese es justo el cuello de botella conocido de los sinónimos).

Ejecuta:  python scripts/nav_real.py [--check] [--json]
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

from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.store import Store                    # noqa: E402
from hipercampo.vsa import similarity_batch           # noqa: E402

DB = "data/_nav_real.db"
MODULOS = ["email", "http", "json", "math", "random", "os", "xml", "unittest",
           "logging", "sqlite3", "statistics", "argparse", "collections", "asyncio",
           "socket", "decimal", "datetime", "threading", "hashlib", "urllib",
           "html", "csv", "configparser", "tarfile", "zipfile", "ftplib", "smtplib"]

DEFAULT_THRESHOLDS = {
    "min_corpus": 500,
    "min_fidelity": 0.98,
    "max_p95_ms": 30.0,
    "max_visited_ratio": 0.95,
    "max_rss_mb": 256.0,
    "max_group_gap": 0.02,
}


def clean() -> None:
    for suf in ("", "-wal", "-shm"):
        Path(DB + suf).unlink(missing_ok=True)


def cosechar() -> tuple[list[str], list[int], list[str]]:
    """Docstrings reales, etiquetados por módulo. Recorre submódulos para tener volumen."""
    textos, etiqueta, nombres = [], [], []
    vistos: set[str] = set()
    for lbl, raiz in enumerate(MODULOS):
        try:
            mod = importlib.import_module(raiz)
        except Exception:
            continue
        # Solo miembros de primer nivel: importar submódulos por pkgutil puede ejecutar
        # código (p.ej. unittest.__main__ corre tests). Con clases y funciones del módulo
        # basta para tener texto real y volumen suficiente, sin efectos secundarios.
        for _, obj in inspect.getmembers(mod):
            try:
                doc = inspect.getdoc(obj)
                miembros = inspect.getmembers(obj) if inspect.isclass(obj) else []
            except Exception:
                doc, miembros = None, []
            candidatos = [doc] + [inspect.getdoc(o) for _, o in miembros[:40]]
            for d in candidatos:
                if not d or len(d) < 80:
                    continue
                d = " ".join(d.split())[:400]
                if d in vistos:
                    continue
                vistos.add(d)
                textos.append(d)
                etiqueta.append(lbl)
                nombres.append(raiz)
    return textos, etiqueta, nombres


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(q * len(ordered)))]


def current_rss_mb() -> float:
    """Memoria residente actual con stdlib, sin convertir psutil en dependencia."""
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
    """Devuelve regresiones legibles; lista vacía significa que el gate pasa."""
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
            failures.append(f"{name}: {actual:.3f} debe ser {op} {expected:.3f}")
    group_gap = metrics["group_scan"] - metrics["group_nav"]
    if group_gap > limits["max_group_gap"]:
        failures.append(
            f"group_gap: {group_gap:.3f} debe ser <= {limits['max_group_gap']:.3f}"
        )
    return failures


def run_benchmark(query_count: int = 40) -> dict:
    textos, etiquetas, nombres = cosechar()
    n = len(textos)
    if n < 6:
        raise RuntimeError(f"corpus real insuficiente: {n}")
    etiqueta = np.array(etiquetas)
    reparto = {nombre: nombres.count(nombre) for nombre in set(nombres)}

    clean()
    store = Store(DB, namespace="real")
    try:
        started = time.perf_counter()
        codes, ids = [], []
        with store.transaction():
            for txt in textos:
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
        graph = store.navgraph(shortcuts=2)
        index_seconds = time.perf_counter() - started
        _, index_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        rss_mb = current_rss_mb()

        rng = np.random.default_rng(7)
        sample = rng.choice(n, size=min(query_count, n), replace=False)
        fidelidad, grupo_nav, grupo_scan, lat, vis = [], [], [], [], []
        for qi in sample:
            qi = int(qi)
            q, qid, lbl = codes[qi], ids[qi], etiqueta[qi]
            sims = similarity_batch(q, mat)
            orden = [int(p) for p in np.argsort(sims)[::-1] if int(p) != qi][:5]
            scan_ids = {ids[p] for p in orden}
            started = time.perf_counter()
            found, visited = graph.search_with_stats(q, k=6, ef=48)
            lat.append((time.perf_counter() - started) * 1000)
            vis.append(visited)
            nav_ids = [mid for mid, _ in found if mid != qid][:5]
            fidelidad.append(len(set(nav_ids) & scan_ids) / 5.0)
            grupo_nav.append(
                np.mean([etiqueta[id_a_pos[mid]] == lbl
                         for mid in nav_ids if mid in id_a_pos])
                if nav_ids else 0.0
            )
            grupo_scan.append(np.mean([etiqueta[p] == lbl for p in orden]))

        return {
            "corpus": n,
            "modules": len(set(nombres)),
            "queries": len(sample),
            "distribution": dict(
                sorted(reparto.items(), key=lambda item: -item[1])[:8]
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
        f"Corpus REAL: {metrics['corpus']} docstrings de {metrics['modules']} módulos "
        f"(categoría = módulo)"
    )
    print("reparto:", metrics["distribution"], "…")
    print(
        f"sembrado+codificado: {metrics['seed_seconds']:.1f}s · "
        f"índice: {metrics['index_seconds']:.1f}s · "
        f"RSS: {metrics['rss_mb']:.1f}MB · "
        f"pico Python del índice: {metrics['index_peak_mb']:.1f}MB"
    )
    print("\n=== VEREDICTO en corpus REAL ===")
    print(f"fidelidad nav vs escaneo (recall@5): {metrics['fidelity']:.3f}")
    print(
        f"latencia navegable: p50={metrics['p50_ms']:.2f}ms "
        f"p95={metrics['p95_ms']:.2f}ms"
    )
    print(
        f"visitados: {metrics['visited_mean']:.0f} de {metrics['corpus']} "
        f"({100 * metrics['visited_ratio']:.1f}%)"
    )
    print(
        f"precisión de grupo@5 — navegar: {metrics['group_nav']:.3f} · "
        f"escaneo: {metrics['group_scan']:.3f}"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark navegable sobre corpus real")
    parser.add_argument("--check", action="store_true",
                        help="falla si alguna métrica cruza su umbral")
    parser.add_argument("--json", action="store_true",
                        help="emite métricas y veredicto como JSON")
    parser.add_argument("--queries", type=int, default=40,
                        help="número de consultas deterministas (por defecto: 40)")
    args = parser.parse_args(argv)
    if args.queries < 1:
        parser.error("--queries debe ser mayor que cero")

    metrics = run_benchmark(args.queries)
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
                    print(f"FALLO · {failure}")
            else:
                print("OK · todas las métricas conservan su contrato")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
