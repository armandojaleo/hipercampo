"""
Tests de la MÁQUINA DE ESTADOS de los enlaces y del mantenimiento observable.

Lo que se protege aquí: la imaginación (hipótesis del sueño) no puede corromper
la evidencia, y el sistema no puede decir que ha dormido si no ha dormido.

Ejecuta:  python tests/test_estados.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar, memoria      # noqa: E402


def _enlace(hc, a, b):
    fila = hc.store.db.execute(
        "SELECT type,status,weight FROM links WHERE (src=? AND dst=?) OR (src=? AND dst=?)",
        (a, b, b, a)).fetchone()
    return (fila["type"], fila["status"], fila["weight"]) if fila else None


# --- precedencia del UPSERT -------------------------------------------------

def test_una_hipotesis_no_degrada_evidencia_confirmada():
    hc = memoria("est_no_degrada")
    hc.store.link(1, 2, 0.9, type="lexical", status="confirmed")
    hc.store.link(1, 2, 0.5, type="dream", status="proposed")
    t, s, _ = _enlace(hc, 1, 2)
    assert (t, s) == ("lexical", "confirmed"), f"la hipótesis pisó la evidencia: {t}/{s}"


def test_una_observacion_real_asciende_una_hipotesis_rechazada():
    hc = memoria("est_asciende")
    hc.store.link(1, 2, 0.4, type="dream", status="rejected")
    hc.store.link(1, 2, 0.9, type="lexical", status="confirmed")
    t, s, _ = _enlace(hc, 1, 2)
    assert (t, s) == ("lexical", "confirmed"), f"lo observado quedó enterrado: {t}/{s}"


def test_lo_rechazado_no_engorda_al_reproponerse():
    hc = memoria("est_no_engorda")
    hc.store.link(1, 2, 0.4, type="dream", status="rejected")
    peso0 = _enlace(hc, 1, 2)[2]
    for _ in range(5):
        hc.store.link(1, 2, 0.4, type="dream", status="proposed")
    t, s, peso = _enlace(hc, 1, 2)
    assert (t, s) == ("dream", "rejected"), f"resucitó lo descartado: {t}/{s}"
    assert peso == peso0, f"lo rechazado se reforzó: {peso0} → {peso}"


def test_confirmar_persiste_frente_a_nuevas_propuestas():
    hc = memoria("est_confirmado_gana")
    hc.store.link(1, 2, 0.5, type="dream", status="proposed")
    hc.store.set_link_status(1, 2, "confirmed")
    hc.store.link(1, 2, 0.5, type="dream", status="proposed")
    t, s, _ = _enlace(hc, 1, 2)
    assert (t, s) == ("dream", "confirmed"), f"se perdió la confirmación: {t}/{s}"


# --- transiciones permitidas ------------------------------------------------

def test_no_se_puede_rechazar_un_enlace_lexico():
    hc = memoria("est_lexico_intocable")
    hc.store.link(1, 2, 0.9, type="lexical", status="confirmed")
    n = hc.store.set_link_status(1, 2, "rejected")
    assert n == 0, "rechazó una asociación observada"
    assert _enlace(hc, 1, 2)[1] == "confirmed"


def test_no_se_re_resuelve_una_hipotesis_ya_resuelta():
    hc = memoria("est_una_vez")
    hc.store.link(1, 2, 0.5, type="dream", status="proposed")
    assert hc.store.set_link_status(1, 2, "confirmed") == 1
    assert hc.store.set_link_status(1, 2, "rejected") == 0, "confirmed → rejected"
    assert _enlace(hc, 1, 2)[1] == "confirmed"


def test_transicion_a_un_estado_inventado_es_error():
    hc = memoria("est_estado_raro")
    hc.store.link(1, 2, 0.5, type="dream", status="proposed")
    try:
        hc.store.set_link_status(1, 2, "maybe")
        raise AssertionError("aceptó un estado que no existe")
    except ValueError:
        pass


def test_aceptar_una_propuesta_inexistente_avisa():
    hc = memoria("est_inexistente")
    hc.remember("un recuerdo cualquiera para tener algo", 0.5)
    r = hc.accept_bridge(1, 999)
    assert "error" in r, f"dio éxito por una hipótesis que no existe: {r}"


# --- salud y mantenimiento --------------------------------------------------

def test_health_prueba_la_escritura_de_verdad():
    hc = memoria("est_health")
    h = hc.health()
    assert h["escribible"] is True and h["sana"] is True, h
    assert h.get("comprobacion") == "quick_check", "por defecto debe ser barato"
    # la prueba de escritura NO deja rastro
    resto = hc.store.db.execute("SELECT value FROM meta WHERE key='_health_probe'").fetchone()
    assert resto is None, "la sonda de escritura dejó basura en meta"
    assert "escrituras_sin_dormir" in h and "wal_bytes" in h, h


def test_health_completo_bajo_demanda():
    hc = memoria("est_health_full")
    h = hc.store.health(full=True)
    assert h.get("comprobacion") == "integrity_check" and h["integridad"] == "ok", h


def test_un_sueno_fallido_no_reinicia_el_contador():
    from hipercampo.memory import AUTOSLEEP_EVERY
    hc = memoria("est_sueno_fallido")
    umbral = AUTOSLEEP_EVERY - 1
    hc.store.set_meta("writes_since_sleep", umbral)

    def sueno_roto(*a, **kw):
        raise RuntimeError("consolidación interrumpida")
    hc.sleep = sueno_roto

    assert hc._autosleep() is None
    n = int(hc.store.get_meta("writes_since_sleep", "0") or 0)
    assert n >= umbral, f"reinició el contador tras fallar: {n}"
    assert "interrumpida" in (hc.store.get_meta("last_sleep_error", "") or "")


def test_un_sueno_correcto_si_reinicia_el_contador():
    hc = memoria("est_sueno_ok")
    hc.store.set_meta("writes_since_sleep", 999)      # forzamos el umbral
    r = hc._autosleep()
    assert r is not None, "debió dormir"
    assert int(hc.store.get_meta("writes_since_sleep", "-1")) == 0
    assert hc.store.get_meta("last_sleep_success", "") not in ("", None)


# --- reintento solo de lo transitorio ---------------------------------------

def test_solo_se_reintenta_lo_transitorio():
    from hipercampo.memory import _es_transitorio
    import sqlite3
    assert _es_transitorio(sqlite3.OperationalError("database is locked"))
    # la conexión caída llega como ProgrammingError: también hay que reintentarla
    assert _es_transitorio(sqlite3.ProgrammingError("Cannot operate on a closed database."))
    assert not _es_transitorio(sqlite3.OperationalError(
        "attempt to write a readonly database"))
    assert not _es_transitorio(sqlite3.DatabaseError("database disk image is malformed"))
    assert not _es_transitorio(sqlite3.OperationalError("no such column: namespace"))


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
