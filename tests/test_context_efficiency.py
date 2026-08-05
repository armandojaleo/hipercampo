"""Gate de coste contextual y contrato del adaptador LongMemEval."""

import copy
import io
import json
import sys
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import context_efficiency as context  # noqa: E402

_FIXTURE = Path("data/_test_longmemeval.json")
_LOCAL = None


def local_report():
    global _LOCAL
    if _LOCAL is None:
        _LOCAL = context.run_local()
    return _LOCAL


def _write_fixture() -> None:
    data = [
        {
            "question_id": "q1",
            "question_type": "single-session-user",
            "question": "¿Dónde está alojado el servidor de producción?",
            "answer": "Frankfurt",
            "haystack_session_ids": ["evidence", "noise"],
            "haystack_sessions": [
                [{"role": "user", "content":
                  "El servidor de producción está alojado en Frankfurt."}],
                [{"role": "user", "content":
                  "La impresora de pruebas se reinicia los domingos."}],
            ],
            "answer_session_ids": ["evidence"],
        },
        {
            "question_id": "q2_abs",
            "question_type": "single-session-user",
            "question": "¿Qué receta de curry tailandés usamos?",
            "answer": "No hay información",
            "haystack_session_ids": ["office"],
            "haystack_sessions": [[
                {"role": "assistant", "content":
                 "La oficina central está en la calle Serrano de Madrid."}
            ]],
            "answer_session_ids": [],
        },
    ]
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _clean() -> None:
    _FIXTURE.unlink(missing_ok=True)


def test_gate_local_mide_calidad_contexto_y_latencia():
    report = local_report()
    assert context.evaluate_local(report) == []
    assert report["mrr"] >= 0.70
    assert report["abstention_accuracy"] >= 0.70
    assert report["payload_tokens"]["p95"] <= 800
    assert report["answered_payload_tokens"]["p50"] > 0
    assert report["latency_ms"]["p95"] <= 50


def test_gate_detecta_cada_regresion_de_contexto():
    cases = (
        ("mrr", 0.0, "mrr"),
        ("abstention_accuracy", 0.0, "abstention_accuracy"),
        ("selective_precision", 0.0, "selective_precision"),
    )
    for field, value, expected in cases:
        broken = copy.deepcopy(local_report())
        broken[field] = value
        assert any(expected in failure for failure in context.evaluate_local(broken))
    broken = copy.deepcopy(local_report())
    broken["payload_tokens"]["p95"] = 9999
    assert any("payload" in failure for failure in context.evaluate_local(broken))
    broken = copy.deepcopy(local_report())
    broken["latency_ms"]["p95"] = 9999
    assert any("latency" in failure for failure in context.evaluate_local(broken))


def test_adaptador_longmemeval_mide_retrieval_y_abstencion():
    _write_fixture()
    try:
        report = context.run_longmemeval(_FIXTURE, k=1)
    finally:
        _clean()
    assert report["instances"] == 2
    assert report["retrieval_recall_at_k"] == 1.0
    assert report["abstention_accuracy"] == 1.0
    assert report["payload_tokens"]["p95"] > 0


def test_adaptador_rechaza_schema_incompleto():
    _FIXTURE.parent.mkdir(parents=True, exist_ok=True)
    _FIXTURE.write_text('[{"question_id":"rota"}]', encoding="utf-8")
    try:
        try:
            context.load_longmemeval(_FIXTURE)
            raise AssertionError("aceptó una instancia incompleta")
        except ValueError as error:
            assert "incompleta" in str(error)
    finally:
        _clean()


def test_cli_json_local_es_estable():
    measured = local_report()
    original = context.run_local
    context.run_local = lambda: measured
    output = io.StringIO()
    try:
        with redirect_stdout(output):
            code = context.main(["--check", "--json"])
    finally:
        context.run_local = original
    payload = json.loads(output.getvalue())
    assert code == 0
    assert payload["failures"] == []
    assert payload["dataset"] == "local-stress"


if __name__ == "__main__":
    failures = 0
    try:
        for name, fn in sorted(globals().items()):
            if name.startswith("test_"):
                try:
                    fn()
                    print(f"ok   {name}")
                except Exception as error:
                    failures += 1
                    print(f"FAIL {name}: {error}")
    finally:
        _clean()
    raise SystemExit(1 if failures else 0)
