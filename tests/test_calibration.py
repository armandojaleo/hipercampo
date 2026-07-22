"""
Tests de las garantías de la ronda de calibración/consistencia:
- el veto por "predecible" ES alcanzable con secuencias realistas (adaptativo);
- consulta vacía -> [];
- consolidación cohesiva (no encadena cosas dispares);
- el modelo de sorpresa no queda por delante de la BD tras un rollback.
Ejecuta:  python tests/test_calibration.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402
from hipercampo.surprise import SurpriseModel        # noqa: E402

_DB = "data/_test_calib.db"
_cur = None


def fresh():
    global _cur
    if _cur is not None:
        _cur.store.close()
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    _cur = Hipercampo(_DB, namespace="c")
    return _cur


# --- el veto "predecible" es ALCANZABLE (umbral adaptativo) -----------------
def test_predecible_es_alcanzable():
    m = SurpriseModel()
    # historial variado y realista para calibrar el cuantil
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
    # algo que el modelo ya predice de sobra debe salir "predecible"
    trillado = "el servidor de produccion fallo por un timeout de red"
    assert m.predictable(m.surprise(trillado)), "lo muy predecible debe activar el veto"
    # algo genuinamente nuevo NO debe ser predecible
    nuevo = "quetzalcoatl bailaba tangos en un submarino de mercurio"
    assert not m.predictable(m.surprise(nuevo)), "lo nuevo no debe vetarse"


# --- consulta vacía ---------------------------------------------------------
def test_consulta_vacia_devuelve_vacio():
    hc = fresh()
    hc.remember("un recuerdo cualquiera para el indice", 0.5)
    assert hc.recall("", k=5) == []
    assert hc.recall("   ", k=5) == []


# --- consolidación cohesiva -------------------------------------------------
def test_consolidacion_no_encadena_dispares():
    hc = fresh()
    # A~B muy parecidos; C comparte algo con A pero no con B
    hc.remember("el despliegue de la version dos fallo por la manana", 0.5)
    hc.remember("el despliegue de la version dos fallo por la tarde", 0.5)
    hc.remember("el despliegue del informe anual quedo aprobado sin cambios", 0.5)
    hc.consolidate()
    # el recuerdo semántico agrupado no debe mezclar el 'informe anual' con los fallos
    sem = [r["text"] for r in hc.store.all(only_active=False) if r["kind"] == "semantic"]
    for s in sem:
        if "fallo" in s:
            assert "informe anual" not in s, "agrupó cosas dispares (cadena voraz)"


# --- consistencia sorpresa/BD tras rollback ---------------------------------
def test_sorpresa_no_se_adelanta_a_la_bd_en_rollback():
    hc = fresh()
    texto = "dato que provocara un fallo simulado en la escritura"
    s_antes = hc.surprise.surprise(texto)
    # simular fallo en plena transacción de escritura
    try:
        with hc.store.transaction():
            from hipercampo.encoder import encode_text
            hc.store.add(texto, encode_text(texto), 0.5, 0.5)
            raise RuntimeError("boom")
    except RuntimeError:
        pass
    # como el aprendizaje va DESPUÉS del commit, el modelo no debió aprenderlo
    s_despues = hc.surprise.surprise(texto)
    assert abs(s_antes - s_despues) < 1e-9, "el modelo aprendió algo que la BD revirtió"
    assert hc.stats()["total"] == 0


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
        _cur.store.close()
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
