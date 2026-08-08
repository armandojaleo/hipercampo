"""
The navigable small-world graph (`hipercampo/navgraph.py`): the index that fits VSA.
Recall NAVIGATES a neighbor graph instead of scanning everything.

Contract requirements, measured in probes before being frozen here:
  - graph search retrieves almost the same results as a full scan,
  - weak long-range SHORTCUTS make it navigable (without them it forms islands),
  - it visits only a FRACTION of memory, the seed of sublinear behavior,
  - insertion builds by NAVIGATION, without scanning, and small memories work.

Run:  python tests/core/test_navgraph.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean          # noqa: E402
from hipercampo.core.encoder import encode_text      # noqa: E402
from hipercampo.core.navgraph import NavGraph        # noqa: E402
from hipercampo.core.vsa import similarity_batch, stack_hvs   # noqa: E402


def _corpus(topic_count=40, per_topic=20, seed=0):
    """Build STRUCTURED memories with shared topic vocabularies and real neighborhoods."""
    rng = np.random.default_rng(seed)
    vocab = [f"palabra{i}" for i in range(300)]
    suj = ["el sistema", "la maquina", "el modulo", "el proceso", "el nodo",
           "la memoria", "el sensor", "el motor", "la red", "el robot"]
    textos, tema = [], []
    for t in range(topic_count):
        nucleo = list(rng.choice(vocab, size=6, replace=False))
        for _ in range(per_topic):
            k = int(rng.integers(3, 6))
            pal = list(rng.choice(nucleo, size=k, replace=True))
            extra = list(rng.choice(vocab, size=2, replace=False))
            textos.append(f"{suj[t % 10]} {' '.join(pal + extra)}")
            tema.append(t)
    return textos, np.array(tema)


def _codes(textos):
    return stack_hvs([encode_text(t).tobytes() for t in textos])


def _queries(textos, tema, topic_count, seed=7):
    """Build one paraphrase per topic from part of a topic memory as its cue."""
    rng = np.random.default_rng(seed)
    Q, Qt = [], []
    for t in range(topic_count):
        idxs = np.where(tema == t)[0]
        base = textos[int(rng.choice(idxs))].split()
        Q.append(encode_text(" ".join(base[:4])))
        Qt.append(t)
    return Q, Qt


def _recall_and_visits(codes, textos, tema, topic_count, **kw):
    g = NavGraph(seed=0, **kw)
    for i in range(len(codes)):
        g.add(i, codes[i])
    Q, _ = _queries(textos, tema, topic_count)
    rec, vis = 0.0, 0
    for q in Q:
        d = 1.0 - similarity_batch(q, codes)          # menor = más cerca (uso sim)
        verdad = set(int(x) for x in np.argsort(d)[:5])
        top5 = set(mid for mid, _ in g.search(q, k=5))
        rec += len(top5 & verdad) / 5.0
        vis += g.visited_for(q)
    m = len(Q)
    return rec / m, vis / m, len(codes)


def test_is_navigable_without_visiting_everything():
    """Graph navigation nearly matches a scan while touching only a fraction."""
    textos, tema = _corpus()
    codes = _codes(textos)
    recall, visits, n = _recall_and_visits(codes, textos, tema, 40)
    assert recall >= 0.80, f"poor graph navigation: recall@5={recall:.3f}"
    assert visits < 0.7 * n, f"visits nearly everything ({visits:.0f}/{n})"


def test_shortcuts_make_graph_navigable():
    """Long-range shortcuts join islands: the frozen Watts-Strogatz finding."""
    textos, tema = _corpus()
    codes = _codes(textos)
    without, _, _ = _recall_and_visits(codes, textos, tema, 40, shortcuts=0)
    with_shortcuts, _, _ = _recall_and_visits(codes, textos, tema, 40, shortcuts=3)
    assert with_shortcuts >= without
    assert with_shortcuts >= 0.80, f"shortcuts should make it navigable: {with_shortcuts:.3f}"


def test_incremental_insertion_builds_graph():
    """Insertion builds through NAVIGATION without scanning, linking every node."""
    textos, tema = _corpus(topic_count=10, per_topic=10)
    codes = _codes(textos)
    g = NavGraph(seed=0)
    for i in range(len(codes)):
        g.add(i, codes[i])
    assert len(g) == len(codes)
    # No node except, at most, the first remains isolated.
    aislados = [mid for mid in range(len(codes)) if not g.adj.get(mid)]
    assert len(aislados) <= 1, f"isolated nodes: {aislados}"


def test_small_memory_still_works():
    """Search still works with one or two memories through the trivial fallback."""
    g = NavGraph(seed=0)
    hv = encode_text("un unico recuerdo en la memoria")
    g.add(1, hv)
    r = g.search(hv, k=5)
    assert r and r[0][0] == 1 and r[0][1] > 0.99
    g.add(2, encode_text("un segundo recuerdo distinto"))
    assert len(g.search(encode_text("recuerdo"), k=5)) >= 1


def test_search_with_metrics_makes_one_traversal():
    """Observing cost must not double the cost being measured."""
    g = NavGraph(seed=0)
    for i in range(20):
        g.add(i, encode_text(f"recuerdo navegable numero {i}"))
    original = g._search
    llamadas = 0

    def contar(*args, **kwargs):
        nonlocal llamadas
        llamadas += 1
        return original(*args, **kwargs)

    g._search = contar
    resultados, visitados = g.search_with_stats(encode_text("recuerdo numero 7"), k=5,
                                                 ef=8)
    assert resultados and visitados > 0
    assert llamadas == 1


def test_adaptive_shortcuts_only_disable_for_dense_component():
    codes = {i: encode_text(f"nodo topologico {i}") for i in range(24)}

    densos = set()
    for i in range(12):
        for salto in range(1, 5):
            densos.add(tuple(sorted((i, (i + salto) % 12))))
    denso = NavGraph.from_links(
        codes={i: codes[i] for i in range(12)},
        edges=sorted(densos),
        shortcuts=2,
        adaptive_shortcuts=True,
    )
    fijo = NavGraph.from_links(
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
    disperso = NavGraph.from_links(
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
    separado = NavGraph.from_links(
        codes={i: codes[i] for i in range(12, 24)},
        edges=islas,
        shortcuts=2,
        adaptive_shortcuts=True,
    )
    assert separado.component_count == 2
    assert separado.effective_shortcuts == 2

def test_landmarks_choose_correct_semantic_island():
    """One representative per component avoids dependence on random shortcuts."""
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

    g = NavGraph.from_links(codes, edges, shortcuts=0)
    found, visited = g.search_with_stats(bases[8], k=5, ef=8)

    assert len(g.entries) == len(bases)
    assert {mid // 10 for mid, _ in found} == {8}
    assert visited >= len(g.entries)

if __name__ == "__main__":
    clean()
    sys.exit(run_tests(dict(globals())))
