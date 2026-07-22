"""
Tests de la memoria ENTRE PROYECTOS (contextos enlazados, solo lectura).

La garantía: un proyecto puede INSPIRARSE en lo aprendido en otro (recall/muse
ven los enlazados), pero nunca ensuciarlo (toda escritura cae en el propio) ni
ver un proyecto NO enlazado.

Ejecuta:  python tests/test_linked.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar  # noqa: E402
from hipercampo.memory import Hipercampo  # noqa: E402

_DB = "data/_t_linked.db"


def _sembrar():
    """Dos proyectos con saberes distintos + uno que nadie enlaza."""
    limpiar()
    Path(_DB).unlink(missing_ok=True)
    a = Hipercampo(_DB, namespace="player")
    a.remember("IIS rechaza con 400 los segmentos de ruta de mas de 260 caracteres", 0.8)
    a.store.close()
    b = Hipercampo(_DB, namespace="hipercampo")
    b.remember("los hipervectores binarios permiten algebra de roles con XOR", 0.8)
    b.store.close()
    c = Hipercampo(_DB, namespace="secreto")
    c.remember("dato privado del proyecto que nadie ha enlazado", 0.8)
    c.store.close()


def test_sin_enlazar_no_se_ve_nada_ajeno():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo")
    hits = hc.recall("segmentos de ruta IIS 400 caracteres")
    assert not any("IIS" in h["text"] for h in hits), "vio otro proyecto sin enlazar"
    hc.store.close()


def test_enlazado_se_lee_y_se_dice_de_donde_viene():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    hits = hc.recall("segmentos de ruta IIS 400 caracteres")
    assert any("IIS" in h["text"] for h in hits), "no leyó el proyecto enlazado"
    ajeno = next(h for h in hits if "IIS" in h["text"])
    assert ajeno.get("project") == "player", f"sin etiqueta de origen: {ajeno}"
    hc.store.close()


def test_el_no_enlazado_sigue_invisible():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    hits = hc.recall("dato privado del proyecto secreto")
    assert not any("privado" in h["text"] for h in hits), "leyó un proyecto NO enlazado"
    hc.store.close()


def test_leer_no_refuerza_lo_ajeno():
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


def test_remember_siempre_escribe_en_el_propio():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    r = hc.remember("una idea nueva nacida de cruzar los dos proyectos", 0.7)
    assert r["stored"] is True
    ns = hc.store.db.execute("SELECT namespace FROM memories WHERE id=?",
                             (r["id"],)).fetchone()[0]
    assert ns == "hipercampo", f"escribió fuera de su proyecto: {ns}"
    hc.store.close()


def test_update_no_puede_corregir_lo_enlazado():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["player"])
    ajeno = next(r for r in hc.store.all(only_active=True)
                 if r["namespace"] == "player")
    r = hc.update("", "texto que intenta pisar lo del otro proyecto",
                  memory_id=ajeno["id"])
    assert "error" in r and "enlazado" in r["error"], r
    hc.store.close()


def test_consolidar_no_absorbe_texto_ajeno():
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


def test_asterisco_enlaza_todos_los_demas():
    _sembrar()
    hc = Hipercampo(_DB, namespace="hipercampo", linked=["*"])
    assert set(hc.store.linked) == {"player", "secreto"}, hc.store.linked
    hc.store.close()


if __name__ == "__main__":
    limpiar()
    Path(_DB).unlink(missing_ok=True)
    codigo = ejecutar(dict(globals()))
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    sys.exit(codigo)
