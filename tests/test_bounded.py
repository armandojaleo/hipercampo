"""
Recall ACOTADO (max_scan) — la cota de tiempo/RAM para embebidos y robots.

Un robot no puede escanear 100k hipervectores en cada paso. `recall(max_scan=N)`
mira solo los N recuerdos más VIVOS (fuerza + recencia) y responde en tiempo
acotado. No es gratis y no se esconde: si la respuesta está fuera de esos N, no se
encuentra; el registro dice cuántos se miraron. Aquí se prueba que la cota:
  - de verdad limita las filas que se traen (RAM/tiempo en origen),
  - conserva lo más vivo (lo reforzado sigue encontrándose bajo una cota estrecha),
  - existe el índice que la hace rápida (sin él medimos que era MÁS lenta),
  - no rompe el recall normal.

Ejecuta:  python tests/test_bounded.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar, memoria    # noqa: E402


def _sembrar_relleno(hc, n):
    """n recuerdos de relleno, distintos entre sí, por el almacén (rápido)."""
    from hipercampo.encoder import encode_text
    with hc.store.transaction():
        for i in range(n):
            t = f"nota de relleno numero {i} sobre un tema cualquiera {i * 7 % 997}"
            hc.store.add(t, encode_text(t), 1.0, 0.5, 0.5)


def test_max_scan_limita_las_filas_que_se_traen():
    hc = memoria("bound_lim")
    _sembrar_relleno(hc, 200)
    todas = hc.store.all(only_active=False)
    acotadas = hc.store.all(only_active=False, limit=50)
    assert len(todas) >= 200
    assert len(acotadas) == 50, "el LIMIT debe acotar en origen, no en Python"
    hc.close()


def test_la_cota_conserva_lo_mas_vivo():
    """Un recuerdo FUERTE (reforzado) se encuentra aunque la cota sea estrecha y haya
    mucho relleno: la cota se queda con lo más vivo, no con lo primero que pilla."""
    from hipercampo.encoder import encode_text
    hc = memoria("bound_vivo")
    _sembrar_relleno(hc, 300)
    diana = "el tesoro esta escondido en la isla del faro"
    tid = hc.store.add(diana, encode_text(diana), 1.0, 0.9, 0.9)
    # lo hacemos el más VIVO: fuerza alta (como si se hubiera reforzado mucho).
    hc.store.db.execute("UPDATE memories SET strength=5.0 WHERE id=?", (tid,))
    hc.store.commit()
    hits = hc.recall("donde esta escondido el tesoro", k=5, max_scan=20)
    assert any("tesoro" in h["text"] for h in hits), \
        "lo más vivo debe sobrevivir a una cota estrecha entre 300 de relleno"
    hc.close()


def test_recall_con_cota_sigue_respondiendo_y_no_revienta():
    hc = memoria("bound_ok")
    _sembrar_relleno(hc, 120)
    hit = hc.recall("nota de relleno numero 50", k=3, max_scan=30)
    assert isinstance(hit, list), "con cota, recall sigue devolviendo una lista"
    hc.close()


def test_cota_ridicula_no_rompe():
    """max_scan=1 (o 0, que se sube a 1) es un caso extremo, no un error."""
    hc = memoria("bound_min")
    _sembrar_relleno(hc, 50)
    assert isinstance(hc.recall("lo que sea", max_scan=1), list)
    assert isinstance(hc.recall("lo que sea", max_scan=0), list)   # 0 -> se acota a 1
    hc.close()


def test_existe_el_indice_que_hace_rapida_la_cota():
    """Sin índice sobre (namespace, strength, last_access) el ORDER BY del LIMIT era
    MÁS lento que escanear todo (medido). El índice es parte del contrato de la cota."""
    hc = memoria("bound_idx")
    idx = {r[0] for r in hc.store.db.execute(
        "SELECT name FROM sqlite_master WHERE type='index'").fetchall()}
    assert "idx_vivos" in idx, f"falta el índice de recuerdos vivos: {idx}"
    hc.close()


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
