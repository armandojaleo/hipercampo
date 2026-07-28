"""
El índice de navegación sobre el STORE real (`store.navgraph()`): recordar navegando.

Las sondas probaron el algoritmo en abstracto; aquí se exige sobre datos PERSISTIDOS
de verdad (recuerdos guardados + sus enlaces knn):
  - navegar el índice recupera casi lo mismo que el escaneo completo (la verdad),
  - tocando solo una FRACCIÓN de la memoria (la semilla de la sublinealidad),
  - se monta desde lo ya guardado (los knn del mapa) + atajos internos del índice.

No toca `recall()` todavía (esa cirugía, con su reajuste de abstención, es el paso
siguiente): esto demuestra que el camino de navegación funciona end-to-end.

Ejecuta:  python tests/test_navindex.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar, memoria     # noqa: E402
from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.vsa import similarity_batch          # noqa: E402


def _sembrar(hc, n_temas=40, por=20, seed=0):
    rng = np.random.default_rng(seed)
    vocab = [f"palabra{i}" for i in range(240)]
    textos, tema = [], []
    with hc.store.transaction():
        for t in range(n_temas):
            nucleo = list(rng.choice(vocab, size=5, replace=False))
            for _ in range(por):
                k = int(rng.integers(3, 5))
                pal = list(rng.choice(nucleo, size=k, replace=True))
                extra = list(rng.choice(vocab, size=2, replace=False))
                txt = f"tema {t} {' '.join(pal + extra)}"
                hc.store.add(txt, encode_text(txt), 1.0, 0.6, 0.6)
                textos.append(txt); tema.append(t)
    return textos, np.array(tema)


def test_navegar_recupera_como_escanear():
    hc = memoria("navidx", namespace="proj")
    textos, tema = _sembrar(hc)
    hc.store.reindex_navgraph(M=12)                 # teje los knn (el mapa)
    g = hc.store.navgraph(shortcuts=2)              # monta el índice de navegación

    rows = hc.store.all(only_active=False, own_only=True, include_dormant=True)
    ids = [r["id"] for r in rows]
    mat = hc.store.matrix(rows)

    rng = np.random.default_rng(1)
    recall, visitas, n_q = 0.0, 0, 0
    for t in range(40):
        idxs = np.where(tema == t)[0]
        base = textos[int(rng.choice(idxs))].split()
        q = encode_text(" ".join(base[:4]))
        sims = similarity_batch(q, mat)             # VERDAD por escaneo completo
        verdad = set(int(ids[i]) for i in np.argsort(sims)[::-1][:5])
        nav = set(mid for mid, _ in g.search(q, k=5))
        recall += len(nav & verdad) / 5.0
        visitas += g.visitados_en(q)
        n_q += 1
    recall /= n_q
    visitas /= n_q
    assert recall >= 0.80, f"navegar el store recupera mal: recall@5={recall:.3f}"
    assert visitas < 0.8 * len(ids), \
        f"navegar visita casi todo ({visitas:.0f}/{len(ids)}): no ahorra"
    hc.close()


def test_indice_usa_los_knn_del_mapa():
    """El índice se monta desde los enlaces knn ya guardados, no de la nada."""
    hc = memoria("navidx2", namespace="proj")
    _sembrar(hc, n_temas=8, por=8, seed=5)
    g0 = hc.store.navgraph(shortcuts=0)             # sin knn aún: solo nodos, sin aristas
    aristas0 = sum(len(v) for v in g0.adj.values())
    hc.store.reindex_navgraph(M=10)
    g1 = hc.store.navgraph(shortcuts=0)             # ya con knn
    aristas1 = sum(len(v) for v in g1.adj.values())
    assert aristas1 > aristas0, "el índice debe heredar los knn tejidos"
    hc.close()


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
