"""
El índice de navegación sobre el STORE real (`store.navgraph()`): recordar navegando.

Las sondas probaron el algoritmo en abstracto; aquí se exige sobre datos PERSISTIDOS
de verdad (recuerdos guardados + sus enlaces knn):
  - navegar el índice recupera casi lo mismo que el escaneo completo (la verdad),
  - tocando solo una FRACCIÓN de la memoria (la semilla de la sublinealidad),
  - se monta desde lo ya guardado (los knn del mapa) + atajos internos del índice.

Tambien fija el primer corte de b6 en el camino caliente: `recall(nav=True)`
usa el indice como generador de candidatos, con fallback al escaneo actual.

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


def test_recall_opcional_puede_navegar_el_grafo_del_store():
    """b6: recall(nav=True) usa el grafo persistido como candidato medido,
    manteniendo el recall normal intacto como fallback."""
    hc = memoria("nav_recall", namespace="proj")
    textos, _ = _sembrar(hc, n_temas=12, por=10, seed=41)
    objetivo = textos[37]
    consulta = " ".join(objetivo.split()[:4])
    hc.store.reindex_navgraph(M=10)

    normal = hc.recall(consulta, k=5)
    nav = hc.recall(consulta, k=5, nav=True)

    assert normal, "el recall base debe seguir encontrando senal"
    assert nav, "el recall navegable debe devolver resultados"
    assert (
        any(h["text"] == objetivo for h in nav)
        or {h["id"] for h in nav} & {h["id"] for h in normal}
    )
    assert nav[0].get("recall_mode") == "nav", nav[0]
    assert isinstance(nav[0].get("visited"), int) and nav[0]["visited"] > 0

def test_cli_recall_expone_modo_nav():
    import contextlib
    import io
    import json
    import os
    from hipercampo import cli

    hc = memoria("nav_cli", namespace="proj")
    textos, _ = _sembrar(hc, n_temas=12, por=10, seed=42)
    consulta = " ".join(textos[31].split()[:4])
    db = hc.store.path
    hc.store.reindex_navgraph(M=10)
    hc.close()

    os.environ["HIPERCAMPO_DB"] = db
    os.environ["HIPERCAMPO_NAMESPACE"] = "proj"
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["recall", "--nav", consulta])
        assert code == 0
        hits = json.loads(buf.getvalue())
        assert hits and hits[0].get("recall_mode") == "nav", hits
        assert isinstance(hits[0].get("visited"), int)
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)
        os.environ.pop("HIPERCAMPO_NAMESPACE", None)

def test_recall_auto_navega_si_el_grafo_es_adecuado():
    hc = memoria("nav_auto", namespace="proj")
    textos, _ = _sembrar(hc, n_temas=12, por=10, seed=43)
    consulta = " ".join(textos[44].split()[:4])
    hc.store.reindex_navgraph(M=6)

    hits = hc.recall(consulta, k=5, nav="auto")

    assert hits, "nav auto debe seguir recordando"
    assert hits[0].get("recall_mode") == "nav", hits[0]
    assert isinstance(hits[0].get("visited"), int)

def test_cli_recall_expone_modo_nav_auto():
    import contextlib
    import io
    import json
    import os
    from hipercampo import cli

    hc = memoria("nav_cli_auto", namespace="proj")
    textos, _ = _sembrar(hc, n_temas=12, por=10, seed=44)
    consulta = " ".join(textos[52].split()[:4])
    db = hc.store.path
    hc.store.reindex_navgraph(M=6)
    hc.close()

    os.environ["HIPERCAMPO_DB"] = db
    os.environ["HIPERCAMPO_NAMESPACE"] = "proj"
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["recall", "--nav-auto", consulta])
        assert code == 0
        hits = json.loads(buf.getvalue())
        assert hits and hits[0].get("recall_mode") == "nav", hits
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)
        os.environ.pop("HIPERCAMPO_NAMESPACE", None)

def test_remember_teje_knn_incremental_sin_reindex():
    """b6 escritura: recordar tambien alimenta el mapa navegable sin esperar
    mantenimiento O(N^2). Los enlaces knn no sustituyen evidencia lexical."""
    hc = memoria("nav_write", namespace="proj")
    textos = [
        "sensor solar plaza norte sombra ruta fresca",
        "riego humedad suelo lluvia ahorro agua",
        "farola paso peatones intensidad noche",
        "mercado excedentes comida comedor barrio",
        "nevera comunitaria caducidad temperatura alimento",
        "bicicleta carga ruta corta baja emision",
        "salud soledad actividad voluntaria cuidado",
        "semaforo bus emergencia peatones reglas",
    ]
    for txt in textos:
        r = hc.remember(txt, 0.8, 0.8)
        assert r.get("stored") is True, r

    knn = [e for e in hc.store.links_dump() if e["type"] == "knn"]
    assert knn, "remember debe dejar mapa knn incremental"
    assert len({i for e in knn for i in (e["src"], e["dst"])}) >= 5
    hc.close()


def test_grafo_incremental_sobrevive_al_reinicio():
    """Los KNN son memoria persistente: cerrar el robot no obliga a reindexar."""
    hc = memoria("nav_restart", namespace="robot")
    textos = [f"sensor robot zona {i} temperatura bateria ruta segura" for i in range(12)]
    for texto in textos:
        assert hc.remember(texto, 0.8, 0.8)["stored"]
    db = hc.store.path
    knn_antes = [e for e in hc.store.links_dump() if e["type"] == "knn"]
    assert knn_antes
    hc.close()

    from hipercampo.memory import Hipercampo

    reabierta = Hipercampo(db, namespace="robot")
    knn_despues = [e for e in reabierta.store.links_dump() if e["type"] == "knn"]
    assert len(knn_despues) == len(knn_antes)
    hits = reabierta.recall("sensor robot zona 7 temperatura", k=3, nav=True)
    assert hits and hits[0].get("recall_mode") == "nav"
    assert 0 < hits[0]["visited"] <= len(textos)
    reabierta.close()


def test_grafo_incremental_no_cruza_namespaces():
    """El mapa navegable de un robot/proyecto nunca incorpora recuerdos ajenos."""
    hc_a = memoria("nav_ns", namespace="robot-a")
    for i in range(8):
        assert hc_a.remember(f"robot alfa sensor motor {i} mantenimiento", 0.8, 0.8)["stored"]
    hc_a.close()

    hc_b = memoria("nav_ns", namespace="robot-b")
    for i in range(8):
        assert hc_b.remember(f"robot beta camara rueda {i} navegacion", 0.8, 0.8)["stored"]
    ids_b = {r["id"] for r in hc_b.store.all(own_only=True)}
    knn_b = [e for e in hc_b.store.links_dump() if e["type"] == "knn"]
    assert knn_b
    assert all(e["src"] in ids_b and e["dst"] in ids_b for e in knn_b)
    hc_b.close()


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    limpiar()
    sys.exit(codigo)
