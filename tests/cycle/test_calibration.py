"""
Calibration and consistency guarantees:
- the adaptive "predictable" veto IS reachable with realistic sequences;
- an empty query returns [];
- consolidation is cohesive and does not chain dissimilar items;
- the surprise model does not get ahead of the database after rollback.
Run:  python tests/cycle/test_calibration.py
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from hipercampo.cycle.memory import Hipercampo             # noqa: E402
from hipercampo.core.surprise import SurpriseModel        # noqa: E402

_DB = "data/_test_calib.db"
_cur = None


def fresh():
    global _cur
    if _cur is not None:
        _cur.close()
        _cur = None
    for suf in ("", "-wal", "-shm"):
        try:
            Path(_DB + suf).unlink(missing_ok=True)
        except PermissionError:
            pass
    _cur = Hipercampo(_DB, namespace="c")
    return _cur


# --- the "predictable" veto is REACHABLE through an adaptive threshold ------
def test_predictable_is_reachable():
    m = SurpriseModel()
    # Varied realistic history used to calibrate the quantile.
    frases = [
        "el servidor de produccion fallo por un timeout de red",
        "la reunion trimestral se movio al jueves por la tarde",
        "un meteorito de iridio cruzo la estratosfera boreal",
        "el cliente pidio una factura rectificativa urgente",
        "el gato del vecino trepo al tejado otra vez",
        "se actualizo el certificado ssl del dominio principal",
        "el pipeline de datos consumio mucha memoria anoche",
    ] * 8
    for f in frases:
        m.observe(m.surprise(f)); m.learn(f)
    # Something the model already predicts confidently must be "predictable".
    trillado = "el servidor de produccion fallo por un timeout de red"
    assert m.predictable(m.surprise(trillado)), "highly predictable text must trigger veto"
    # Something genuinely new must NOT be predictable.
    nuevo = "quetzalcoatl bailaba tangos en un submarino de mercurio"
    assert not m.predictable(m.surprise(nuevo)), "new text must not be vetoed"


# --- empty query ------------------------------------------------------------
def test_empty_query_returns_empty():
    hc = fresh()
    hc.remember("un recuerdo cualquiera para el indice", 0.5)
    assert hc.recall("", k=5) == []
    assert hc.recall("   ", k=5) == []


# --- cohesive consolidation -------------------------------------------------
def test_consolidation_does_not_chain_dissimilar_items():
    hc = fresh()
    # A and B are very similar; C shares something with A but not B.
    hc.remember("el despliegue de la version dos fallo por la manana", 0.5)
    hc.remember("el despliegue de la version dos fallo por la tarde", 0.5)
    hc.remember("el despliegue del informe anual quedo aprobado sin cambios", 0.5)
    hc.consolidate()
    # The grouped semantic memory must not mix the annual report with failures.
    sem = [r["text"] for r in hc.store.all(only_active=False) if r["kind"] == "semantic"]
    for s in sem:
        if "fallo" in s:
            assert "informe anual" not in s, "grouped dissimilar items through greedy chaining"


# --- surprise/database consistency after rollback ---------------------------
def test_surprise_does_not_get_ahead_of_database_on_rollback():
    hc = fresh()
    texto = "dato que provocara un fallo simulado en la escritura"
    s_antes = hc.surprise.surprise(texto)
    # Simulate failure inside the write transaction.
    try:
        with hc.store.transaction():
            from hipercampo.core.encoder import encode_text
            hc.store.add(texto, encode_text(texto), 0.5, 0.5)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # Learning happens AFTER commit, so the model must not have learned it.
    s_despues = hc.surprise.surprise(texto)
    assert abs(s_antes - s_despues) < 1e-9, "model learned data rolled back by database"
    assert hc.stats()["total"] == 0


def test_surprise_persistence_is_atomic_with_memory():
    hc = fresh()
    total = hc.surprise.total

    def falla(*_args, **_kwargs):
        raise sqlite3.OperationalError("disk is full")

    hc.store.record_surprise = falla
    result = hc.remember("esta escritura debe revertirse por completo", 0.5)
    assert "error" in result
    assert hc.stats()["total"] == 0
    assert hc.surprise.total == total
    assert hc.store.load_surprise() is None


def test_persistent_surprise_history_is_bounded():
    hc = fresh()
    for i in range(315):
        hc.store.record_surprise([], float(i))
    scores = [row[0] for row in hc.store.db.execute(
        "SELECT score FROM surprise_history WHERE namespace='c' ORDER BY id"
    )]
    assert len(scores) == 300
    assert scores[0] == 15.0 and scores[-1] == 314.0


def test_surprise_persists_rejections_and_isolates_by_namespace():
    hc = fresh()
    frase = "el servidor estable repite exactamente esta secuencia conocida"
    resultados = [hc.remember(frase, 0.5) for _ in range(45)]
    assert any(not r["stored"] for r in resultados), "rejection path was not exercised"
    total = hc.surprise.total
    recent = list(hc.surprise._recent)
    score = hc.surprise.surprise(frase)
    predictable = hc.surprise.predictable(score)
    tokens_db = {row[0] for row in hc.store.db.execute(
        "SELECT token FROM surprise_counts WHERE namespace='c'"
    )}
    assert "servidor" not in tokens_db, "counters must not store literal text"
    hc.close()

    reopened = Hipercampo(_DB, namespace="c")
    assert reopened.surprise.total == total
    assert list(reopened.surprise._recent) == recent
    assert abs(reopened.surprise.surprise(frase) - score) < 1e-12
    assert reopened.surprise.predictable(score) is predictable

    isolated = Hipercampo(_DB, namespace="otro")
    assert isolated.surprise.total == 0
    assert list(isolated.surprise._recent) == []
    isolated.close()
    reopened.close()


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn(); print(f"ok   {name}")
            except AssertionError as e:
                fails += 1; print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1; print(f"ERROR {name}: {e}")
    if _cur is not None:
        _cur.close()
        _cur = None
    for suf in ("", "-wal", "-shm"):
        try:
            Path(_DB + suf).unlink(missing_ok=True)
        except PermissionError:
            pass
    print(f"\n{'OK' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)
