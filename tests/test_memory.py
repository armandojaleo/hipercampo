"""
Tests funcionales del CICLO de memoria — comprueban que hipercampo hace de verdad
lo que promete, con escenarios realistas. Ejecuta:  python tests/test_memory.py

Cada test ataca una afirmación concreta del README.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.memory import (                      # noqa: E402
    FORGET_STRENGTH_FLOOR, Hipercampo)
from hipercampo.store import Store                   # noqa: E402
from hipercampo.vsa import similarity                # noqa: E402

_DB = "data/_test_memory.db"


_current: Hipercampo | None = None


def fresh() -> Hipercampo:
    global _current
    if _current is not None:
        _current.store.close()          # liberar el fichero (Windows lo bloquea)
    Path(_DB).unlink(missing_ok=True)
    _current = Hipercampo(_DB)
    return _current


# --- Afirmación: "solo graba lo novedoso; lo redundante refuerza" ----------
def test_sorpresa_no_duplica_lo_conocido():
    hc = fresh()
    r1 = hc.remember("el servidor de producción está en Frankfurt", 0.7)
    assert r1["stored"] is True
    # casi idéntico -> debe reforzar, no duplicar
    r2 = hc.remember("el servidor de producción está en Frankfurt", 0.7)
    assert r2["stored"] is False
    assert "reinforced_id" in r2
    assert hc.stats()["total"] == 1


def test_sorpresa_si_graba_lo_nuevo():
    hc = fresh()
    hc.remember("el servidor de producción está en Frankfurt", 0.7)
    r = hc.remember("el cliente principal es una empresa de logística", 0.7)
    assert r["stored"] is True
    assert hc.stats()["total"] == 2


# --- Afirmación: "recall ordena lo relevante por encima del ruido" ---------
def test_recall_prioriza_lo_relevante():
    hc = fresh()
    hc.remember("la clave de la API de pagos empieza por sk_live", 0.9)
    hc.remember("el equipo hace daily a las nueve de la mañana", 0.4)
    hc.remember("el logo de la empresa es de color naranja", 0.3)
    hits = hc.recall("¿cuál es la clave de la API de pagos?", k=3)
    assert hits, "recall no devolvió nada"
    assert "api" in hits[0]["text"].lower() and "pagos" in hits[0]["text"].lower()


# --- Afirmación: "propagación de activación trae asociados, no solo top-k" -
def test_propagacion_de_activacion():
    hc = fresh()
    # A y B comparten palabras -> quedan asociados en el grafo al escribirse.
    hc.remember("el proyecto orion usa una base de datos postgres", 0.6)
    b = hc.remember("el proyecto orion usa una base de datos replicada", 0.6)
    assert b["stored"]
    # La consulta apunta claramente a A; B es asociado, no el match directo.
    hits = hc.recall("háblame del proyecto orion y su base de datos", k=5, hops=1)
    textos = " || ".join(h["text"] for h in hits)
    assert "postgres" in textos and "replicada" in textos, \
        "la propagación debería traer ambos episodios asociados"


# --- Afirmación: "consolidación funde episodios en conocimiento semántico" -
def test_consolidacion_fusiona_y_archiva():
    hc = fresh()
    for extra in ("por la mañana", "según el log", "otra vez hoy"):
        hc.remember(f"el despliegue de la versión dos falló {extra}", 0.5)
    antes = hc.stats()
    assert antes["episodicos_activos"] >= 2
    res = hc.consolidate()
    assert res["clusters_fusionados"] >= 1
    despues = hc.stats()
    assert despues["semanticos"] >= 1
    assert despues["archivados"] >= 2
    assert despues["episodicos_activos"] < antes["episodicos_activos"]


def test_lo_consolidado_sigue_siendo_recuperable():
    hc = fresh()
    for extra in ("ayer", "esta mañana", "de nuevo"):
        hc.remember(f"el usuario reportó un error de login {extra}", 0.5)
    hc.consolidate()
    hits = hc.recall("problemas de login del usuario", k=3)
    assert any("login" in h["text"].lower() for h in hits)
    assert any(h["kind"] == "semantic" for h in hits)


# --- Afirmación: "olvido activo poda lo débil; la importancia protege" -----
def _envejecer(hc, dias):
    """Simula el paso del tiempo retrasando last_access de todo."""
    viejo = time.time() - dias * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ?", (viejo,))
    hc.store.commit()


def test_olvido_poda_lo_debil_y_viejo():
    hc = fresh()
    hc.remember("nota trivial: la máquina de café está a la izquierda", 0.2)
    _envejecer(hc, 90)
    res = hc.forget(dry_run=False)
    assert res["olvidados"] == 1
    assert hc.stats()["total"] == 0


def test_importancia_protege_del_olvido():
    hc = fresh()
    hc.remember("dato crítico: el backup se restaura con el comando restore-all", 0.9)
    hc.remember("dato trivial: hoy llovió un poco", 0.2)
    _envejecer(hc, 120)
    hc.forget(dry_run=False)
    restantes = [r["text"] for r in hc.store.all(only_active=False)]
    assert any("crítico" in t for t in restantes), "lo importante NO debe olvidarse"
    assert not any("trivial" in t for t in restantes), "lo trivial SÍ debe olvidarse"


def test_recordar_protege_del_olvido():
    hc = fresh()
    hc.remember("el pipeline de datos corre cada noche a las tres", 0.4)
    _envejecer(hc, 40)
    # recordarlo varias veces lo refuerza y actualiza last_access
    for _ in range(4):
        hc.recall("¿cuándo corre el pipeline de datos?", k=1)
    res = hc.forget(dry_run=False)
    assert res["olvidados"] == 0, "un recuerdo usado a menudo no debería olvidarse"


# --- Afirmación: "la memoria persiste (SQLite portátil)" -------------------
def test_persistencia_entre_reinicios():
    global _current
    hc = fresh()
    hc.remember("la contraseña del wifi de la oficina es girasol2024", 0.8)
    hc.store.close()
    # "reiniciar": abrir de cero apuntando al mismo fichero
    hc2 = Hipercampo(_DB)
    _current = hc2                       # que el cleanup final lo cierre
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
        _current.store.close()
    Path(_DB).unlink(missing_ok=True)
    print(f"\n{'TODOS PASARON' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
