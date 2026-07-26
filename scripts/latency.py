"""
Latencia y memoria de recall a escala — ejecuta:  python scripts/latency.py [N...]

La pregunta que un embebido/robot hace antes de confiar en hipercampo: ¿cuánto
tarda recordar cuando hay muchos recuerdos, y cuánta RAM cuesta? Sin este número,
"sirve para robots" es una opinión. Aquí está el dato, medido.

Mide, para cada tamaño N:
  - latencia de recall SIN cota (escaneo completo): p50, p95, p99
  - latencia CON cota (max_scan=2000): lo que un robot usaría para acotar tiempo
  - RAM pico de un recall (la matriz N×1250 es el grueso)

MEDIR ANTES DE CREER: la regla de la casa. No hay índice sublineal todavía (eso es
Fase 4), así que el escaneo es lineal; este script enseña dónde empieza a doler y
cuánto lo alivia la cota.
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

from hipercampo.encoder import encode_text            # noqa: E402
from hipercampo.memory import Hipercampo              # noqa: E402

_DB = "data/_latency_bench.db"
_MAX_SCAN = 2000            # cota que un robot pondría: "lo mejor entre los 2000 más vivos"
_CONSULTAS = 40            # recalls por medición (para percentiles estables)


def _limpiar():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _sembrar(n: int) -> Hipercampo:
    """Puebla la BD con n recuerdos distintos, rápido (por el almacén, sin el ciclo
    completo de sorpresa/enlace: aquí medimos recall, no la escritura)."""
    _limpiar()
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


def _medir(hc: Hipercampo, max_scan=None):
    consultas = [f"detalle del servidor numero {i * 137}" for i in range(_CONSULTAS)]
    hc.recall(consultas[0], k=5, max_scan=max_scan)   # calentamiento: la 1ª paga cachés
    tiempos = []
    for q in consultas:
        t0 = time.perf_counter()
        hc.recall(q, k=5, max_scan=max_scan)
        tiempos.append((time.perf_counter() - t0) * 1000)
    return _percentiles(tiempos)


def _ram_pico_mb(hc: Hipercampo):
    gc.collect()
    tracemalloc.start()
    hc.recall("detalle del servidor numero 99", k=5)
    _, pico = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return pico / (1024 * 1024)


def main(tamanos):
    print(f"Latencia de recall (p50/p95/p99, ms) — {_CONSULTAS} consultas por celda")
    print(f"cota = max_scan={_MAX_SCAN}\n")
    cab = f"{'N':>8} | {'completo p50/p95/p99':>24} | {'con cota p50/p95/p99':>24} | RAM/recall"
    print(cab)
    print("-" * 78)
    for n in tamanos:
        hc = _sembrar(n)
        full = _medir(hc, max_scan=None)
        cota = _medir(hc, max_scan=_MAX_SCAN)
        ram = _ram_pico_mb(hc)
        hc.close()
        f = "/".join(f"{x:5.1f}" for x in full)
        c = "/".join(f"{x:5.1f}" for x in cota)
        print(f"{n:>8} | {f:>24} | {c:>24} | {ram:7.1f} MB")
    _limpiar()
    print("\nNota: escaneo lineal (sin índice sublineal aún — Fase 4). La cota mantiene "
          "la latencia plana a cambio de mirar solo los recuerdos más vivos.")


if __name__ == "__main__":
    args = [int(a) for a in sys.argv[1:]] or [1000, 5000, 10000]
    main(args)
