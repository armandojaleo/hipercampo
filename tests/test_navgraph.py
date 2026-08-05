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


def test_busqueda_con_metricas_hace_un_solo_recorrido():
    """Observar el coste no debe duplicar el coste que intenta medir."""
    g = NavGraph(seed=0)
    for i in range(20):
        g.add(i, encode_text(f"recuerdo navegable numero {i}"))
    original = g._buscar
    llamadas = 0

    def contar(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        return original(*args, **kwargs)

    g._buscar = contar
    resultados, visitados = g.search_with_stats(encode_text("recuerdo numero 7"), k=5,
                                                 ef=8)
    assert resultados and visitados > 0
    assert llamadas == 1


def test_shortcuts_adaptativos_solo_se_apagan_en_componente_denso():
    codes = {i: encode_text(f"nodo topologico {i}") for i in range(24)}

    densos = set()
    for i in range(12):
        for salto in range(1, 5):
            densos.add(tuple(sorted((i, (i + salto) % 12))))
    denso = NavGraph.desde_enlaces(
        codes={i: codes[i] for i in range(12)},
        edges=sorted(densos),
        shortcuts=2,
        adaptive_shortcuts=True,
    )
    fijo = NavGraph.desde_enlaces(
        codes={i: codes[i] for i in range(12)},
        edges=sorted(densos),
        shortcuts=2,
        adaptive_shortcuts=False,
    )
    assert denso.component_count == 1
    assert denso.mean_base_degree >= 8.0
    assert denso.effective_shortcuts == 0
    assert fijo.effective_shortcuts == 2
    assert fijo.edge_count > denso.edge_count

    cadena = [(i, i + 1) for i in range(11)]
    disperso = NavGraph.desde_enlaces(
        codes={i: codes[i] for i in range(12)},
        edges=cadena,
        shortcuts=2,
        adaptive_shortcuts=True,
    )
    assert disperso.component_count == 1
    assert disperso.mean_base_degree < 8.0
    assert disperso.effective_shortcuts == 2

    islas = [
        (i, j)
        for base in (12, 18)
        for i in range(base, base + 6)
        for j in range(i + 1, base + 6)
    ]
    separado = NavGraph.desde_enlaces(
        codes={i: codes[i] for i in range(12, 24)},
        edges=islas,
        shortcuts=2,
        adaptive_shortcuts=True,
    )
    assert separado.component_count == 2
    assert separado.effective_shortcuts == 2

def test_landmarks_eligen_la_isla_semantica_correcta():
    """Un representante por componente evita depender de atajos aleatorios."""
    bases = [encode_text(f"concepto totalmente distinto {i}") for i in range(10)]
    codes = {}
    edges = []
    for cluster, base in enumerate(bases):
        ids = []
        for item in range(5):
            mid = cluster * 10 + item
            codes[mid] = base.copy()
            ids.append(mid)
        edges.extend((ids[i], ids[i + 1]) for i in range(len(ids) - 1))

    g = NavGraph.desde_enlaces(codes, edges, shortcuts=0)
    found, visited = g.search_with_stats(bases[8], k=5, ef=8)

    assert len(g.entries) == len(bases)
    assert {mid // 10 for mid, _ in found} == {8}
    assert visited >= len(g.entries)

if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
