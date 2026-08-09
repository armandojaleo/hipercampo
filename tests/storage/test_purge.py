"""
PURGA FÍSICA — el reverso consciente del olvido.

`forget()` adormece (reversible, puede resurgir). `purge()` borra DE VERDAD: para un
secreto que nunca debió guardarse, un derecho de supresión, o lo latente muy antiguo.
Lo que se exige aquí:
  - que el texto ya NO esté en el fichero (borrado seguro, no solo desenlazado),
  - que se recupere el espacio (VACUUM),
  - que el criterio sea explícito y no toque nada de otro namespace,
  - que `dry_run` no borre.

Ejecuta:  python -m pytest tests/test_purge.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests  # noqa: E402
from hipercampo.cycle.memory import Hipercampo   # noqa: E402
from hipercampo.storage.store import Store         # noqa: E402

_DB = "data/_test_purge.db"


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


def _texto_en_fichero(fragmento: str) -> bool:
    """¿Quedan bytes de ese texto en el fichero .db? Es la prueba dura del borrado
    seguro: un DELETE normal deja el texto legible en páginas libres hasta un VACUUM."""
    datos = Path(_DB).read_bytes()
    return fragmento.encode("utf-8") in datos


def test_purge_by_ids_really_deletes_from_file():
    _clean()
    hc = Hipercampo(_DB, namespace="p")
    secreto = "TOKEN_SECRETO_hcdemo_no_debio_guardarse_1234567890"
    mid = hc.remember(f"la clave del banco es {secreto}", 0.6)["id"]
    hc.remember("un dato inocente que se queda", 0.6)
    hc.close()

    # antes de purgar, el secreto SÍ está en el fichero
    assert _texto_en_fichero(secreto), "el texto debería estar antes de purgar"

    hc = Hipercampo(_DB, namespace="p")
    r = hc.purge(ids=[mid])
    hc.close()

    assert r["purged"] == 1 and r["ids"] == [mid]
    # y ahora NO: ni como fila, ni como bytes residuales en páginas libres
    assert not _texto_en_fichero(secreto), "el secreto sigue legible en el fichero"

    hc = Hipercampo(_DB, namespace="p")
    quedan = [x["text"] for x in hc.store.all(only_active=False, include_dormant=True)]
    hc.close()
    assert any("inocente" in t for t in quedan), "no debía tocar lo demás"
    assert not any("banco" in t for t in quedan)


def test_dry_run_deletes_nothing():
    _clean()
    hc = Hipercampo(_DB, namespace="p")
    mid = hc.remember("algo que NO se debe borrar en un ensayo", 0.6)["id"]
    r = hc.purge(ids=[mid], dry_run=True)
    vivos = [x["id"] for x in hc.store.all(only_active=False, include_dormant=True)]
    hc.close()
    assert r["dry_run"] and r["purged"] == 0
    assert mid in vivos, "el ensayo no debía borrar"


def test_age_purge_only_touches_old_dormant_memories():
    _clean()
    hc = Hipercampo(_DB, namespace="p")
    viejo = hc.remember("latente viejo que ya no va a resurgir", 0.5)["id"]
    reciente = hc.remember("latente pero recién dormido", 0.5)["id"]
    activo = hc.remember("un recuerdo bien despierto", 0.5)["id"]
    # dormir dos; envejecer el acceso de uno a 100 días atrás
    hc.store.mark_dormant([viejo, reciente])
    import time
    hc.store.db.execute(
        "UPDATE memories SET last_access = ? WHERE id = ?",
        (time.time() - 100 * 86400, viejo))
    hc.store.commit()

    r = hc.purge(older_than_days=30)
    vivos = {x["id"] for x in hc.store.all(only_active=False, include_dormant=True)}
    hc.close()

    assert r["purged"] == 1 and r["ids"] == [viejo]
    assert reciente in vivos, "un latente reciente no se purga por antigüedad"
    assert activo in vivos, "un recuerdo activo nunca se purga por antigüedad"


def test_requires_exactly_one_criterion():
    _clean()
    hc = Hipercampo(_DB, namespace="p")
    hc.remember("da igual", 0.5)
    ni_uno = hc.purge()                       # ni ids ni older_than
    ambos = hc.purge(ids=[1], older_than_days=10)
    hc.close()
    assert "error" in ni_uno and "error" in ambos


def test_purge_does_not_cross_namespace():
    _clean()
    a = Hipercampo(_DB, namespace="alice")
    mid = a.remember("secreto de alice", 0.6)["id"]
    a.close()
    b = Hipercampo(_DB, namespace="bob")
    r = b.purge(ids=[mid])                     # bob no puede purgar lo de alice
    b.close()
    assert r["purged"] == 0

    a = Hipercampo(_DB, namespace="alice")
    sigue = [x["text"] for x in a.store.all(only_active=False, include_dormant=True)]
    a.close()
    assert any("alice" in t for t in sigue), "bob no debía poder purgar a alice"


def test_vacuum_does_not_break_inside_transaction():
    _clean()
    s = Store(_DB, namespace="p")
    try:
        import pytest
        with s.transaction(), pytest.raises(RuntimeError):
            s.vacuum()
    finally:
        s.close()


if __name__ == "__main__":
    try:
        code = run_tests(dict(globals()))
    finally:
        _clean()
    raise SystemExit(code)
