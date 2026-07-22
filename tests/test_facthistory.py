"""
Tests de HECHOS CON HISTORIA: una contradicción no destruye, cierra la vigencia.
"En 2025 el servidor estaba en Frankfurt; en 2026, en Dublín" no es un conflicto:
es memoria con tiempo. Ejecuta:  python tests/test_facthistory.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_fhist.db"
_cur = None


def _open(ns="h"):
    global _cur
    if _cur is not None:
        _cur.store.close()
    _clean()
    _cur = Hipercampo(_DB, namespace=ns)
    return _cur


def _clean():
    global _cur
    if _cur is not None:
        _cur.store.close(); _cur = None
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def test_un_hecho_nuevo_cierra_al_anterior_sin_borrarlo():
    hc = _open()
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Frankfurt"})
    r = hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                          "object": "Dublin"})
    assert r.get("supersedes"), "debería reconocer que actualiza al anterior"
    # ambos siguen existiendo: uno vigente, otro cerrado (historia)
    todos = hc.store.all_facts()
    vigentes = hc.store.all_facts(only_current=True)
    assert len(todos) == 2, "no debe borrar la versión anterior"
    assert len(vigentes) == 1, "solo uno puede estar vigente"
    _clean()


def test_pregunta_devuelve_lo_vigente():
    hc = _open()
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Frankfurt"})
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Dublin"})
    r = hc.ask_role("object", {"subject": "servidor", "predicate": "ubicado_en"})
    assert r["answer"] == "Dublin", f"debe responder lo vigente: {r}"
    _clean()


def test_se_puede_preguntar_por_el_pasado():
    hc = _open()
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Frankfurt"})
    # el primero fue cierto desde hace tiempo: lo retrasamos para simular historia
    hc.store.db.execute("UPDATE facts SET valid_from = ? WHERE id = 1",
                        (time.time() - 400 * 86400,))
    hc.store.commit()
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Dublin"})
    pasado = time.time() - 200 * 86400          # cuando aún era Frankfurt
    r = hc.ask_role("object", {"subject": "servidor", "predicate": "ubicado_en"},
                    at=pasado)
    assert r["answer"] == "Frankfurt", f"en el pasado era Frankfurt: {r}"
    _clean()


def test_hechos_distintos_no_se_cierran_entre_si():
    hc = _open()
    hc.remember_fact({"subject": "servidor", "predicate": "ubicado_en",
                      "object": "Frankfurt"})
    hc.remember_fact({"subject": "backup", "predicate": "ubicado_en",
                      "object": "Dublin"})
    assert len(hc.store.all_facts(only_current=True)) == 2, \
        "hechos de sujetos distintos conviven"
    _clean()


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
    _clean()
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    sys.exit(1 if fails else 0)
