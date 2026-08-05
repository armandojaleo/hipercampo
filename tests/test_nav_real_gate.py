"""
Contrato del quality gate sobre corpus real.

No ejecuta el corpus completo (eso vive en el job benchmarks de CI); prueba que cada
regresión cruza el umbral correcto y produce un diagnóstico accionable.

Ejecuta: python tests/test_nav_real_gate.py
"""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar                         # noqa: E402
from scripts import nav_real  # noqa: E402
from scripts.nav_real import current_rss_mb, evaluate, percentile  # noqa: E402


BASE = {
    "corpus": 655,
    "fidelity": 1.0,
    "p95_ms": 9.0,
    "visited_ratio": 0.43,
    "rss_mb": 60.0,
    "group_nav": 0.50,
    "group_scan": 0.50,
}


def test_gate_acepta_linea_base():
    assert evaluate(BASE) == []


def test_gate_detecta_cada_regresion():
    casos = [
        ("corpus", {"corpus": 499}),
        ("fidelity", {"fidelity": 0.97}),
        ("p95_ms", {"p95_ms": 31.0}),
        ("visited_ratio", {"visited_ratio": 0.56}),
        ("rss_mb", {"rss_mb": 257.0}),
        ("group_gap", {"group_nav": 0.40, "group_scan": 0.50}),
    ]
    for metrica, cambio in casos:
        fallos = evaluate({**BASE, **cambio})
        assert any(fallo.startswith(f"{metrica}:") for fallo in fallos), (
            metrica, fallos
        )


def test_umbrales_se_pueden_endurecer_sin_cambiar_el_runner():
    fallos = evaluate(BASE, {"max_p95_ms": 8.0, "max_rss_mb": 59.0})
    assert {fallo.split(":")[0] for fallo in fallos} == {"p95_ms", "rss_mb"}


def test_cli_cablea_el_presupuesto_sin_ejecutar_el_corpus():
    llamadas = []
    real = nav_real.run_benchmark

    def simulado(queries, candidates, ef, shortcuts, adaptive_shortcuts):
        llamadas.append((queries, candidates, ef, shortcuts, adaptive_shortcuts))
        return dict(BASE)

    nav_real.run_benchmark = simulado
    try:
        code = nav_real.main([
            "--check", "--json", "--queries", "7",
            "--candidates", "9", "--ef", "8", "--shortcuts", "1",
            "--no-adaptive-shortcuts",
        ])
    finally:
        nav_real.run_benchmark = real
    assert code == 0
    assert llamadas == [(7, 9, 8, 1, False)]

def test_percentil_es_determinista():
    assert percentile([9.0, 1.0, 5.0, 3.0], 0.5) == 5.0
    assert percentile([9.0, 1.0, 5.0, 3.0], 0.95) == 9.0


def test_rss_disponible_en_la_plataforma():
    rss = current_rss_mb()
    assert math.isfinite(rss) and rss > 0, rss


if __name__ == "__main__":
    raise SystemExit(ejecutar(dict(globals())))
