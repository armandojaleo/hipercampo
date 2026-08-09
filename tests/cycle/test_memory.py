"""
Functional memory CYCLE tests verify hipercampo's claims with realistic scenarios.
Run: python tests/cycle/test_memory.py

Each test targets one concrete README claim.
"""

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from hipercampo.cycle.memory import (                      # noqa: E402
    Hipercampo)

_DB = f"data/_test_memory_{os.getpid()}.db"


_current: Hipercampo | None = None


def fresh() -> Hipercampo:
    global _current
    if _current is not None:
        _current.close()
        _current = None
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    _current = Hipercampo(_DB)
    return _current


# --- Claim: "store only novelty; redundant input reinforces" ----------------
def test_surprise_does_not_duplicate_known_memory():
    hc = fresh()
    r1 = hc.remember("el servidor de producción está en Frankfurt", 0.7)
    assert r1["stored"] is True
    # An identical fact should reinforce rather than duplicate.
    r2 = hc.remember("el servidor de producción está en Frankfurt", 0.7)
    assert r2["stored"] is False
    assert "reinforced_id" in r2
    assert hc.stats()["total"] == 1


def test_surprise_stores_new_memory():
    hc = fresh()
    hc.remember("el servidor de producción está en Frankfurt", 0.7)
    r = hc.remember("el cliente principal es una empresa de logística", 0.7)
    assert r["stored"] is True
    assert hc.stats()["total"] == 2


# --- Claim: "recall ranks relevant memories above noise" -------------------
def test_recall_prioritizes_relevant_memory():
    hc = fresh()
    hc.remember("la clave de la API de pagos empieza por hcdemo", 0.9)
    hc.remember("el equipo hace daily a las nueve de la mañana", 0.4)
    hc.remember("el logo de la empresa es de color naranja", 0.3)
    hits = hc.recall("¿cuál es la clave de la API de pagos?", k=3)
    assert hits, "recall returned nothing"
    assert "api" in hits[0]["text"].lower() and "pagos" in hits[0]["text"].lower()
    componentes = hits[0]["score_components"]
    assert set(componentes) == {
        "activation", "strength_factor", "confidence_factor", "superseded_factor"
    }
    assert all(isinstance(v, float) for v in componentes.values())


# --- Claim: "activation propagation retrieves associates, not just top-k" ---
def test_activation_propagation():
    hc = fresh()
    # A and B share words, so writing associates them in the graph.
    hc.remember("el proyecto orion usa una base de datos postgres", 0.6)
    b = hc.remember("el proyecto orion usa una base de datos replicada", 0.6)
    assert b["stored"]
    # The query clearly targets A; B is an associate, not a direct match.
    hits = hc.recall("háblame del proyecto orion y su base de datos", k=5, hops=1)
    textos = " || ".join(h["text"] for h in hits)
    assert "postgres" in textos and "replicada" in textos, \
        "propagation should retrieve both associated episodes"


# --- Claim: "consolidation merges episodes into semantic knowledge" --------
def test_consolidation_merges_and_archives():
    hc = fresh()
    for extra in ("por la mañana", "según el log", "otra vez hoy"):
        hc.remember(f"el despliegue de la versión dos falló {extra}", 0.5)
    antes = hc.stats()
    assert antes["active_episodic"] >= 2
    res = hc.consolidate()
    assert res["clusters_merged"] >= 1
    despues = hc.stats()
    assert despues["semantic"] >= 1
    assert despues["archived"] >= 2
    assert despues["active_episodic"] < antes["active_episodic"]


def test_consolidated_memory_remains_retrievable():
    hc = fresh()
    for extra in ("ayer", "esta mañana", "de nuevo"):
        hc.remember(f"el usuario reportó un error de login {extra}", 0.5)
    hc.consolidate()
    hits = hc.recall("problemas de login del usuario", k=3)
    assert any("login" in h["text"].lower() for h in hits)
    assert any(h["kind"] == "semantic" for h in hits)


# --- Claim: "active forgetting prunes weakness; importance protects" --------
def _age(hc, days):
    """Simulate time passing by moving every last_access timestamp backward."""
    old_timestamp = time.time() - days * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ?", (old_timestamp,))
    hc.store.commit()


def test_forgetting_prunes_weak_old_memory():
    hc = fresh()
    hc.remember("nota trivial: la máquina de café está a la izquierda", 0.2)
    _age(hc, 90)
    res = hc.forget(dry_run=False)
    assert res["forgotten"] == 1
    assert hc.stats()["total"] == 0


def test_importance_protects_from_forgetting():
    hc = fresh()
    hc.remember("dato crítico: el backup se restaura con el comando restore-all", 0.9)
    hc.remember("dato trivial: hoy llovió un poco", 0.2)
    _age(hc, 120)
    hc.forget(dry_run=False)
    restantes = [r["text"] for r in hc.store.all(only_active=False)]
    assert any("crítico" in t for t in restantes), "important memory must NOT be forgotten"
    assert not any("trivial" in t for t in restantes), "trivial memory SHOULD be forgotten"


def test_recall_protects_from_forgetting():
    hc = fresh()
    hc.remember("el pipeline de datos corre cada noche a las tres", 0.4)
    _age(hc, 40)
    # Recalling several times reinforces it and updates last_access.
    for _ in range(4):
        hc.recall("¿cuándo corre el pipeline de datos?", k=1)
    res = hc.forget(dry_run=False)
    assert res["forgotten"] == 0, "frequently used memory should not be forgotten"


# --- Claim: "memory persists through portable SQLite" ----------------------
def test_persistence_across_restarts():
    global _current
    hc = fresh()
    hc.remember("la contraseña del wifi de la oficina es girasol2024", 0.8)
    hc.store.close()
    # Simulate restart by opening from scratch against the same file.
    hc2 = Hipercampo(_DB)
    _current = hc2                       # Let final cleanup close it.
    hits = hc2.recall("contraseña del wifi de la oficina", k=1)
    assert hits and "girasol2024" in hits[0]["text"]


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
    if _current is not None:
        _current.close()
        _current = None
    Path(_DB).unlink(missing_ok=True)
    print(f"\n{'ALL PASSED' if not fails else f'{fails} FAILED'}")
    sys.exit(1 if fails else 0)
