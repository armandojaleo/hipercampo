"""Ablaciones aisladas de los mecanismos cognitivos de hipercampo.

Ejecuta ``python scripts/ablations.py --check`` para convertir las relaciones
medidas en una puerta de regresión, o añade ``--json`` para salida de máquina.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo import audit, config, memory  # noqa: E402
from hipercampo.memory import Hipercampo  # noqa: E402
from scripts.calibrate import relleno  # noqa: E402
from scripts.stress import CASOS, DISTRACTORES  # noqa: E402

CATEGORIES = ("keyword", "typo", "synonym")


def _seed(varied_confidence: bool = True) -> Hipercampo:
    hc = Hipercampo(":memory:", namespace="ablation")
    target_confidence = 0.95 if varied_confidence else 0.5
    distractor_confidence = 0.10 if varied_confidence else 0.5
    for fact, _ in CASOS:
        hc.remember(fact, 0.5, target_confidence)
    for distractor in DISTRACTORES:
        hc.remember(distractor, 0.5, distractor_confidence)
    return hc


def _mrr(hc: Hipercampo, hops: int = 0) -> dict[str, float]:
    """MRR sobre idénticas consultas; un resumen que contiene el hecho cuenta."""
    previous_paused = config.paused
    config.paused = lambda: True
    try:
        by_category = {}
        for category in CATEGORIES:
            reciprocal_rank = 0.0
            for fact, queries in CASOS:
                hits = hc.recall(queries[category], k=20, hops=hops)
                position = next(
                    (i for i, hit in enumerate(hits) if fact in hit["text"]), None
                )
                if position is not None:
                    reciprocal_rank += 1.0 / (position + 1)
            by_category[category] = reciprocal_rank / len(CASOS)
        by_category["global"] = sum(by_category.values()) / len(CATEGORIES)
        return by_category
    finally:
        config.paused = previous_paused


def _surprise_ablation() -> dict:
    variants = {}
    anomaly = "un meteorito de iridio cruzó la estratosfera boreal de mercurio"
    for name, disabled in (("full", False), ("without_surprise", True)):
        hc = Hipercampo(":memory:", namespace=name)
        if disabled:
            hc.surprise.predictable = lambda _score: False
        results = [hc.remember(text, 0.5) for text in relleno(100)]
        rare = hc.remember(anomaly, 0.8)
        variants[name] = {
            "routine_stored": sum(bool(result.get("stored")) for result in results),
            "predictable_rejected": sum(
                result.get("reason") == "predecible" for result in results
            ),
            "rare_stored": bool(rare.get("stored")),
        }
        hc.close()
    return variants


def run() -> dict:
    previous_audit = audit._ENABLED
    previous_gate = memory.GATE_ENABLED
    previous_autosleep = memory.AUTOSLEEP_EVERY
    audit._ENABLED = False
    memory.GATE_ENABLED = False
    memory.AUTOSLEEP_EVERY = 0
    try:
        confidence_full = _seed(varied_confidence=True)
        confidence_flat = _seed(varied_confidence=False)
        confidence = {
            "full": _mrr(confidence_full),
            "without_confidence": _mrr(confidence_flat),
        }
        confidence_full.close()
        confidence_flat.close()

        propagation_hc = _seed(varied_confidence=True)
        propagation = {
            "full": _mrr(propagation_hc, hops=1),
            "without_propagation": _mrr(propagation_hc, hops=0),
        }
        propagation_hc.close()

        raw = _seed(varied_confidence=True)
        consolidated = _seed(varied_confidence=True)
        before = len(raw.store.all(only_active=True, own_only=True))
        result = consolidated.consolidate()
        after = sum(
            not row["consolidated"]
            for row in consolidated.store.all(only_active=True, own_only=True)
        )
        consolidation = {
            "full": {
                "mrr": _mrr(consolidated),
                "active_nodes": after,
                **result,
            },
            "without_consolidation": {
                "mrr": _mrr(raw),
                "active_nodes": before,
            },
        }
        raw.close()
        consolidated.close()

        return {
            "surprise": _surprise_ablation(),
            "confidence": confidence,
            "propagation": propagation,
            "consolidation": consolidation,
        }
    finally:
        audit._ENABLED = previous_audit
        memory.GATE_ENABLED = previous_gate
        memory.AUTOSLEEP_EVERY = previous_autosleep


def evaluate(report: dict) -> list[str]:
    failures = []
    surprise = report["surprise"]
    if surprise["full"]["routine_stored"] >= surprise["without_surprise"]["routine_stored"]:
        failures.append("surprise no reduce la corriente predecible")
    if not surprise["full"]["rare_stored"]:
        failures.append("surprise perdió la anomalía rara")
    confidence = report["confidence"]
    if confidence["full"]["global"] < confidence["without_confidence"]["global"] + 0.01:
        failures.append("confidence no aporta al menos 0.01 MRR")
    propagation = report["propagation"]
    propagation_delta = (
        propagation["full"]["global"]
        - propagation["without_propagation"]["global"]
    )
    if abs(propagation_delta) > 0.02:
        failures.append("propagation dejó de ser neutral en el banco actual")
    consolidation = report["consolidation"]
    full_nodes = consolidation["full"]["active_nodes"]
    ablated_nodes = consolidation["without_consolidation"]["active_nodes"]
    if full_nodes >= ablated_nodes:
        failures.append("consolidation no reduce nodos activos")
    full_mrr = consolidation["full"]["mrr"]["global"]
    ablated_mrr = consolidation["without_consolidation"]["mrr"]["global"]
    if full_mrr < ablated_mrr - 0.02:
        failures.append("consolidation degrada MRR más de 0.02")
    return failures


def print_report(report: dict) -> None:
    surprise = report["surprise"]
    print("sorpresa: rutina "
          f"{surprise['without_surprise']['routine_stored']}→"
          f"{surprise['full']['routine_stored']} · "
          f"rechazados={surprise['full']['predictable_rejected']} · "
          f"anomalía={'sí' if surprise['full']['rare_stored'] else 'NO'}")
    for key, label in (("confidence", "confianza"), ("propagation", "propagación")):
        rows = report[key]
        ablated = next(name for name in rows if name != "full")
        print(f"{label}: MRR {rows[ablated]['global']:.3f}→{rows['full']['global']:.3f}")
    consolidation = report["consolidation"]
    print("consolidación: nodos "
          f"{consolidation['without_consolidation']['active_nodes']}→"
          f"{consolidation['full']['active_nodes']} · MRR "
          f"{consolidation['without_consolidation']['mrr']['global']:.3f}→"
          f"{consolidation['full']['mrr']['global']:.3f}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    report = run()
    failures = evaluate(report) if args.check else []
    if args.json:
        print(json.dumps({**report, "failures": failures}, ensure_ascii=False, indent=2))
    else:
        print_report(report)
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
