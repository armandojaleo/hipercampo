"""
El grafo navegable small-world (`hipercampo/navgraph.py`): el índice que SÍ encaja
en VSA. Se recuerda NAVEGANDO un grafo de vecinos, no escaneando todo.

Lo que se exige (medido antes en sondas, aquí congelado como contrato):
  - navegable: buscar por el grafo recupera casi lo mismo que el escaneo completo,
  - los ATAJOS débiles de largo alcance son lo que lo hace navegable (sin ellos, islas),
  - visita solo una FRACCIÓN de la memoria (no todo — la semilla de la sublinealidad),
  - se construye NAVEGANDO al insertar (sin escaneo), y no revienta con memoria pequeña.

Ejecuta:  python tests/test_navgraph.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar          # noqa: E402
from hipercampo.encoder import encode_text      # noqa: E402
from hipercampo.navgraph import NavGraph        # noqa: E402
from hipercampo.vsa import similarity_batch, stack_hvs   # noqa: E402


def _corpus(n_temas=40, por_tema=20, seed=0):
    """Recuerdos con ESTRUCTURA: temas con vocabulario propio compartido (vecindarios
    reales), como una memoria de verdad y no ruido uniforme."""
    rng = np.random.default_rng(seed)
    vocab = [f"palabra{i}" for i in range(300)]
    suj = ["el sistema", "la maquina", "el modulo", "el proceso", "el nodo",
           "la memoria", "el sensor", "el motor", "la red", "el robot"]
    textos, tema = [], []
    for t in range(n_temas):
        nucleo = list(rng.choice(vocab, size=6, replace=False))
        for _ in range(por_tema):
            k = int(rng.integers(3, 6))
            pal = list(rng.choice(nucleo, size=k, replace=True))
            extra = list(rng.choice(vocab, size=2, replace=False))
            textos.append(f"{suj[t % 10]} {' '.join(pal + extra)}")
            tema.append(t)
    return textos, np.array(tema)


def _codes(textos):
    return stack_hvs([encode_text(t).tobytes() for t in textos])


def _consultas(textos, tema, n_temas, seed=7):
    """Una paráfrasis por tema: un trozo de un recuerdo del tema (la 'pista')."""
    rng = np.random.default_rng(seed)
    Q, Qt = [], []
    for t in range(n_temas):
        idxs = np.where(tema == t)[0]
        base = textos[int(rng.choice(idxs))].split()
        Q.append(encode_text(" ".join(base[:4])))
        Qt.append(t)
    return Q, Qt


def _recall_y_visitas(codes, textos, tema, n_temas, **kw):
    g = NavGraph(seed=0, **kw)
    for i in range(len(codes)):
        g.add(i, codes[i])
    Q, _ = _consultas(textos, tema, n_temas)
    rec, vis = 0.0, 0
    for q in Q:
        d = 1.0 - similarity_batch(q, codes)          # menor = más cerca (uso sim)
        verdad = set(int(x) for x in np.argsort(d)[:5])
        top5 = set(mid for mid, _ in g.search(q, k=5))
        rec += len(top5 & verdad) / 5.0
        vis += g.visitados_en(q)
    m = len(Q)
    return rec / m, vis / m, len(codes)


def test_es_navegable_y_no_visita_todo():
    """Navegar el grafo recupera casi lo mismo que el escaneo, tocando una fracción."""
    textos, tema = _corpus()
    codes = _codes(textos)
    recall, visitas, n = _recall_y_visitas(codes, textos, tema, 40)
    assert recall >= 0.80, f"grafo poco navegable: recall@5={recall:.3f}"
    assert visitas < 0.7 * n, f"visita casi todo ({visitas:.0f}/{n}): no ahorra"


def test_los_atajos_hacen_navegable():
    """Sin atajos de largo alcance el grafo se rompe en islas. Con ellos, navega.
    Es el corazón del hallazgo (small-world de Watts-Strogatz), congelado."""
    textos, tema = _corpus()
    codes = _codes(textos)
    sin, _, _ = _recall_y_visitas(codes, textos, tema, 40, shortcuts=0)
    con, _, _ = _recall_y_visitas(codes, textos, tema, 40, shortcuts=3)
    assert con >= sin, f"los atajos deberían ayudar o igualar: con={con:.3f} sin={sin:.3f}"
    assert con >= 0.80, f"con atajos debería ser navegable: {con:.3f}"


def test_insercion_incremental_construye_grafo():
    """Se construye NAVEGANDO al insertar (sin escaneo). Cada nodo queda enlazado."""
    textos, tema = _corpus(n_temas=10, por_tema=10)
    codes = _codes(textos)
    g = NavGraph(seed=0)
    for i in range(len(codes)):
        g.add(i, codes[i])
    assert len(g) == len(codes)
    # ningún nodo (salvo a lo sumo el primero) queda aislado
    aislados = [mid for mid in range(len(codes)) if not g.adj.get(mid)]
    assert len(aislados) <= 1, f"nodos aislados: {aislados}"


def test_memoria_pequena_no_revienta():
    """Con uno o dos recuerdos, buscar sigue funcionando (respaldo trivial)."""
    g = NavGraph(seed=0)
    hv = encode_text("un unico recuerdo en la memoria")
    g.add(1, hv)
    r = g.search(hv, k=5)
    assert r and r[0][0] == 1 and r[0][1] > 0.99
    g.add(2, encode_text("un segundo recuerdo distinto"))
    assert len(g.search(encode_text("recuerdo"), k=5)) >= 1


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
