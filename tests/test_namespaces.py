"""
Tests de aislamiento de contextos (namespaces), concurrencia, defensa en
profundidad, transacciones atómicas y validación de entradas.
Ejecuta:  python tests/test_namespaces.py
"""

import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402
from hipercampo.store import Store                   # noqa: E402

_DB = "data/_test_ns.db"


def _clean():
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)


# --- aislamiento -------------------------------------------------------------
def test_un_contexto_no_ve_lo_de_otro():
    _clean()
    alice = Hipercampo(_DB, namespace="alice")
    bob = Hipercampo(_DB, namespace="bob")
    alice.remember("el secreto de alice es el número 42", 0.8)
    bob.remember("a bob le gusta el senderismo", 0.5)
    ha = alice.recall("cuál es el secreto", k=5)
    assert any("alice" in h["text"] for h in ha)
    assert not any("bob" in h["text"] for h in ha), "¡fuga entre contextos!"
    assert alice.stats()["total"] == 1 and bob.stats()["total"] == 1
    alice.store.close(); bob.store.close(); _clean()


def test_get_no_cruza_namespace():
    _clean()
    alice = Hipercampo(_DB, namespace="alice")
    bob = Hipercampo(_DB, namespace="bob")
    mid = alice.remember("dato privado de alice", 0.7)["id"]
    assert bob.store.get(mid) is None
    assert alice.store.get(mid) is not None
    alice.store.close(); bob.store.close(); _clean()


# --- defensa en profundidad: escrituras por id no cruzan namespace ----------
def test_delete_y_touch_no_cruzan_namespace():
    _clean()
    alice = Hipercampo(_DB, namespace="alice")
    bob = Store(_DB, namespace="bob")
    mid = alice.remember("recuerdo de alice a proteger", 0.5)["id"]
    # bob intenta borrar y tocar un id de alice: no debe tener efecto
    bob.delete([mid])
    bob.touch([mid])
    bob.reinforce(mid)
    bob.mark_superseded([mid])
    r = alice.store.get(mid)
    assert r is not None, "bob no debería poder borrar un recuerdo de alice"
    assert r["access_count"] == 0 and r["superseded"] == 0, "bob no debió modificarlo"
    alice.store.close(); bob.close(); _clean()


# --- concurrencia ------------------------------------------------------------
def test_escrituras_concurrentes_no_corrompen():
    _clean()

    def escribir(ns, n):
        hc = Hipercampo(_DB, namespace=ns)
        for i in range(n):
            hc.remember(f"{ns} recuerdo distinto numero {i} zeta", 0.5)
        hc.store.close()

    hilos = [threading.Thread(target=escribir, args=(f"t{t}", 10)) for t in range(4)]
    for h in hilos:
        h.start()
    for h in hilos:
        h.join()
    for t in range(4):
        hc = Hipercampo(_DB, namespace=f"t{t}")
        assert hc.stats()["total"] == 10, f"t{t} deberia tener 10"
        hc.store.close()
    _clean()


# --- transacción atómica -----------------------------------------------------
def test_transaccion_revierte_en_error():
    _clean()
    hc = Hipercampo(_DB, namespace="x")
    hc.remember("base", 0.5)
    antes = hc.stats()["total"]
    try:
        with hc.store.transaction():
            from hipercampo.encoder import encode_text
            hc.store.add("a medias", encode_text("a medias"), 0.5, 0.5)
            raise RuntimeError("fallo simulado a mitad")
    except RuntimeError:
        pass
    assert hc.stats()["total"] == antes, "una transacción fallida no debe dejar rastro"
    hc.store.close(); _clean()


# --- validación de entradas --------------------------------------------------
def test_validacion_rechaza_texto_vacio():
    _clean()
    hc = Hipercampo(_DB, namespace="x")
    for malo in ("", "   ", None):
        try:
            hc.remember(malo, 0.5)
            assert False, f"debería rechazar texto inválido: {malo!r}"
        except (ValueError, TypeError):
            pass
    hc.store.close(); _clean()


def test_validacion_acota_importance_y_confidence():
    _clean()
    hc = Hipercampo(_DB, namespace="x")
    r = hc.remember("dato con valores fuera de rango", importance=20, confidence=-3)
    row = hc.store.get(r["id"])
    assert 0.0 <= row["importance"] <= 1.0 and 0.0 <= row["confidence"] <= 1.0
    hc.store.close(); _clean()


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
