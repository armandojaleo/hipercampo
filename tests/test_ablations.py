"""Contrato y evidencia del banco de ablaciones cognitivas."""

import copy
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import ablations  # noqa: E402

_REPORT = None


def report():
    global _REPORT
    if _REPORT is None:
        _REPORT = ablations.run()
    return _REPORT


def test_ablaciones_miden_aporte_y_limites_reales():
    measured = report()
    assert ablations.evaluate(measured) == []
    surprise = measured["surprise"]
    assert surprise["full"]["routine_stored"] < surprise["without_surprise"]["routine_stored"]
    assert surprise["full"]["rare_stored"] is True
    confidence = measured["confidence"]
    assert confidence["full"]["global"] > confidence["without_confidence"]["global"]
    propagation = measured["propagation"]
    assert abs(propagation["full"]["global"]
               - propagation["without_propagation"]["global"]) <= 0.02
    consolidation = measured["consolidation"]
    assert consolidation["full"]["active_nodes"] < 20
    assert consolidation["full"]["mrr"]["global"] >= 0.80


def test_gate_detecta_una_regresion_por_mecanismo():
    mutations = []
    broken = copy.deepcopy(report())
    broken["surprise"]["full"]["routine_stored"] = 100
    mutations.append((broken, "surprise"))
    broken = copy.deepcopy(report())
    broken["confidence"]["full"]["global"] = 0.0
    mutations.append((broken, "confidence"))
    broken = copy.deepcopy(report())
    broken["propagation"]["full"]["global"] = 0.0
    mutations.append((broken, "propagation"))
    broken = copy.deepcopy(report())
    broken["consolidation"]["full"]["active_nodes"] = 20
    mutations.append((broken, "consolidation"))
    for candidate, expected in mutations:
        assert any(expected in failure for failure in ablations.evaluate(candidate))


def test_cli_json_expone_resultado_y_fallos():
    measured = report()
    original = ablations.run
    ablations.run = lambda: measured
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = ablations.main(["--check", "--json"])
    finally:
        ablations.run = original
    payload = json.loads(output.getvalue())
    assert code == 0
    assert payload["failures"] == []
    assert set(payload) == {
        "surprise", "confidence", "propagation", "consolidation", "failures"
    }


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok   {name}")
            except Exception as exc:
                failures += 1
                print(f"FAIL {name}: {exc}")
    raise SystemExit(1 if failures else 0)
