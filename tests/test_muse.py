"""
Tests del olvido que NO borra (latente) y del recuerdo inspirador (muse).
Ejecuta:  python tests/test_muse.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_DB = "data/_test_muse.db"
_cur = None


def _open(ns="m"):
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


def _envejecer(hc, dias):
    hc.store.db.execute("UPDATE memories SET last_access = ?", (time.time() - dias * 86400,))
    hc.store.commit()


# --- el olvido ADORMECE, no borra -------------------------------------------
def test_olvidar_no_borra_sino_adormece():
    hc = _open()
    mid = hc.remember("una idea trivial que quedará latente con el tiempo", 0.2)["id"]
    _envejecer(hc, 90)
    hc.forget(dry_run=False)
    # fuera de la memoria viva...
    assert hc.stats()["total"] == 0
    assert hc.stats()["latentes"] >= 1
    # ...pero el recuerdo SIGUE existiendo (latente), no se borró
    assert hc.store.get(mid) is not None
    assert hc.store.get(mid)["dormant"] == 1
    _clean()


def test_recall_normal_no_ve_los_latentes():
    hc = _open()
    hc.remember("nota latente sobre mariposas azules del amazonas", 0.2)
    _envejecer(hc, 90)
    hc.forget(dry_run=False)
    assert hc.recall("mariposas azules del amazonas", k=5) == []
    _clean()


# --- muse trae conexiones indirectas y resucita lo latente ------------------
def test_muse_resucita_un_recuerdo_latente():
    hc = _open()
    # dos recuerdos asociados por vocabulario compartido
    hc.remember("el río amazonas alberga mariposas azules enormes", 0.6)
    viejo = hc.remember("las mariposas azules inspiraron un cuadro famoso", 0.2)["id"]
    # adormecemos solo el segundo (simulamos que el tiempo lo sepultó)
    hc.store.mark_dormant([viejo])
    # muse sobre el primero debería tirar del hilo asociativo y despertar al segundo
    ideas = hc.muse("mariposas azules del amazonas", k=3)
    resucito = hc.store.get(viejo)["dormant"] == 0
    assert resucito or any(h.get("resurgido") for h in ideas), \
        f"muse debería resucitar el recuerdo latente asociado: {ideas}"
    _clean()


def test_muse_consulta_vacia():
    hc = _open()
    hc.remember("algo cualquiera", 0.5)
    assert hc.muse("", k=3) == []
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
