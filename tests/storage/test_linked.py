"""
Tests de la memoria ENTRE PROYECTOS (contextos enlazados, solo lectura).

La garantía: un proyecto puede INSPIRARSE en lo aprendido en otro (recall/muse
ven los enlazados), pero nunca ensuciarlo (toda escritura cae en el propio) ni
ver un proyecto NO enlazado.

Ejecuta:  python tests/test_linked.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean  # noqa: E402
from hipercampo.cycle.memory import Hipercampo  # noqa: E402

_DB = "data/_t_linked.db"


def _limpiar_db():
    """Borra el .db y sus sidecars WAL. En modo WAL un `-wal` huérfano puede colar
    datos del test anterior al reabrir; en Windows, además, un handle abierto impide
    el borrado (POSIX sí deja borrar un fichero abierto, por eso Linux lo disimula)."""
    for suf in ("", "-wal", "-shm"):
        try:
            Path(_DB + suf).unlink(missing_ok=True)
        except PermissionError:
            pass


def _sembrar():
    """Dos proyectos con saberes distintos + uno que nadie enlaza."""
    clean()
    _limpiar_db()
    a = Hipercampo(_DB, namespace="player")
    a.remember("IIS rechaza con 400 los segmentos de ruta de mas de 260 caracteres", 0.8)
    a.store.close()
    b = Hipercampo(_DB, namespace="hipercampo")
    b.remember("los hipervectores binarios permiten algebra de roles con XOR", 0.8)
    b.store.close()
    c = Hipercampo(_DB, namespace="secreto")
    c.remember("dato privado del proyecto que nadie ha enlazado", 0.8)
    c.store.close()


def test_without_linking_foreign_memory_is_invisible():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo")
    hits = hc.recall("segmentos de ruta IIS 400 caracteres")
    assert not any("IIS" in h["text"] for h in hits), "vio otro proyecto sin enlazar"
    hc.store.close()


def test_linked_memory_is_read_with_source_namespace():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    hits = hc.recall("segmentos de ruta IIS 400 caracteres")
    assert any("IIS" in h["text"] for h in hits), "no leyó el proyecto enlazado"
    ajeno = next(h for h in hits if "IIS" in h["text"])
    assert ajeno.get("project") == "player", f"sin etiqueta de origen: {ajeno}"
    hc.store.close()


def test_unlinked_namespace_remains_invisible():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    hits = hc.recall("dato privado del proyecto secreto")
    assert not any("privado" in h["text"] for h in hits), "leyó un proyecto NO enlazado"
    hc.store.close()


def test_reading_does_not_reinforce_foreign_memory():
    """touch() sobre un recuerdo enlazado no debe cambiarlo: leer no ensucia."""
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    fila = next(r for r in hc.store.all(only_active=True)
                if r["namespace"] == "player")
    antes = (fila["access_count"], fila["strength"])
    hc.recall("segmentos de ruta IIS 400 caracteres")   # lo encuentra y lo usaría
    despues = hc.store.db.execute(
        "SELECT access_count, strength FROM memories WHERE id=?",
        (fila["id"],)).fetchone()
    assert (despues[0], despues[1]) == antes, "leer reforzó un recuerdo ajeno"
    hc.store.close()


def test_remember_always_writes_to_own_namespace():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    r = hc.remember("una idea nueva nacida de cruzar los dos proyectos", 0.7)
    assert r["stored"] is True
    ns = hc.store.db.execute("SELECT namespace FROM memories WHERE id=?",
                             (r["id"],)).fetchone()[0]
    assert ns == "hipercampo", f"escribió fuera de su proyecto: {ns}"
    hc.store.close()


def test_update_cannot_modify_linked_memory():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    ajeno = next(r for r in hc.store.all(only_active=True)
                 if r["namespace"] == "player")
    r = hc.update("", "texto que intenta pisar lo del otro proyecto",
                  memory_id=ajeno["id"])
    assert "error" in r and "linked" in r["error"], r
    hc.store.close()


def test_consolidation_does_not_absorb_foreign_text():
    """El mantenimiento cuida lo propio: un semántico nunca copia texto enlazado."""
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    hc.remember("los hipervectores de diez mil bits toleran mucho ruido", 0.6)
    hc.remember("los hipervectores se comparan con distancia de Hamming", 0.6)
    hc.consolidate()
    for r in hc.store.all(kind="semantic", only_active=False):
        assert "IIS" not in r["text"], "un semántico propio absorbió texto ajeno"
        assert r["namespace"] == "hipercampo"
    hc.store.close()


def test_wildcard_links_all_other_namespaces():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["*"])
    assert set(hc.store.linked) == {"player", "secreto"}, hc.store.linked
    hc.store.close()


if __name__ == "__main__":
    clean()
    _limpiar_db()
    codigo = run_tests(dict(globals()))
    _limpiar_db()
    sys.exit(codigo)
