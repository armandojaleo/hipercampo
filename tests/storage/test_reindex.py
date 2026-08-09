"""
`reindex_navgraph`: weave the neighbor graph inside the current namespace.

The map starts sparse because only strong lexical matches are linked. Reindex joins
each memory to its actual k-NN neighbors. The contract requires new links and a denser
connected graph, preservation of existing links, no measured recall degradation, and
strict namespace isolation.

Run: python tests/storage/test_reindex.py
"""

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from helpers import run_tests, clean, memory     # noqa: E402
from hipercampo.core.encoder import encode_text          # noqa: E402
from hipercampo.storage.store import Store                   # noqa: E402


def _sembrar(hc, n_temas=15, por=8, seed=0):
    """Seed structured memories with shared topic vocabulary through the store."""
    rng = np.random.default_rng(seed)
    vocab = [f"palabra{i}" for i in range(200)]
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
    return textos, np.array(tema), rng


def _acierto_recall(hc, textos, tema, n_temas, rng):
    """Return the fraction of queries retrieving a memory from the correct topic."""
    ok = 0
    for t in range(n_temas):
        idxs = np.where(tema == t)[0]
        base = textos[int(rng.choice(idxs))].split()
        hits = hc.recall(" ".join(base[:4]), k=5)
        ok += int(any(h["text"].startswith(f"tema {t} ") for h in hits))
    return ok / n_temas


def test_reindex_densifies_without_harming_recall():
    hc = memory("reindex_ok", namespace="proj")
    textos, tema, rng = _sembrar(hc)
    antes_enlaces = len(hc.store.links_dump())
    antes_recall = _acierto_recall(hc, textos, tema, 15, np.random.default_rng(1))

    tejidos = hc.store.reindex_navgraph(M=10)
    despues_enlaces = len(hc.store.links_dump())
    despues_recall = _acierto_recall(hc, textos, tema, 15, np.random.default_rng(1))

    assert tejidos > 0, "reindex debería tejer enlaces nuevos"
    assert despues_enlaces > antes_enlaces, "el grafo debe quedar MÁS denso"
    assert despues_recall >= antes_recall, \
        f"recall no debe empeorar: antes={antes_recall:.2f} despues={despues_recall:.2f}"
    hc.close()


def test_reindex_preserves_existing_links():
    hc = memory("reindex_keep", namespace="proj")
    a = hc.remember("windows rechaza rutas largas con error 400", 0.7)["id"]
    b = hc.remember("los datos largos van por query string, no en el path", 0.7)["id"]
    hc.store.link(a, b, weight=0.9, type="lexical"); hc.store.commit()
    _sembrar(hc, n_temas=6, por=6, seed=2)
    # el enlace lexical original debe seguir siendo lexical tras reindex
    hc.store.reindex_navgraph(M=8)
    tipos = {(min(e["src"], e["dst"]), max(e["src"], e["dst"])): e["type"]
             for e in hc.store.links_dump()}
    assert tipos.get((min(a, b), max(a, b))) == "lexical", "reindex pisó un enlace existente"
    hc.close()


def test_reindex_stays_in_its_namespace():
    hc = memory("reindex_ns", namespace="proj")
    _sembrar(hc, n_temas=5, por=6, seed=3)
    otro = Store(hc.store.path, namespace="otro")
    for i in range(6):
        t = f"otro contexto dato {i}"
        otro.add(t, encode_text(t), 1.0, 0.6, 0.6)
    otro.commit()
    hc.store.reindex_navgraph(M=8)
    # los enlaces tejidos son todos del namespace 'proj'
    ns_enlaces = {e["namespace"] for e in hc.store.links_dump(all_namespaces=True)
                  if e["type"] == "knn"}
    assert ns_enlaces <= {"proj"}, f"tejió fuera de su contexto: {ns_enlaces}"
    otro.close(); hc.close()


def test_densification_does_not_break_dreaming():
    """Regression: densification could connect a pair twice in opposite directions.
    neighbors() then returned a duplicate and dream crashed on a one-item frozenset.
    Neighbors must now be deduplicated by node."""
    hc = memory("reindex_dream", namespace="proj")
    _sembrar(hc, n_temas=8, por=8, seed=9)
    ids = [m["id"] for m in hc.store.all(only_active=False)][:2]
    hc.store.link(ids[0], ids[1], weight=0.9, type="lexical")
    hc.store.link(ids[1], ids[0], weight=0.4, type="knn")     # sentido opuesto, otro peso
    hc.store.commit()
    vecinos = [d for d, _ in hc.store.neighbors(ids[0])]
    assert vecinos.count(ids[1]) == 1, "el vecino no debe salir duplicado"
    hc.store.reindex_navgraph(M=6)
    d = hc.dream(max_bridges=5)                               # antes reventaba aquí
    assert isinstance(d.get("bridges"), list)
    hc.close()


def test_reindex_all_namespaces_weaves_each_namespace():
    """The viewer shows ALL namespaces. --all-namespaces must weave each namespace
    internally without crossing boundaries."""
    import json
    import os
    from hipercampo import cli
    hc = memory("reindex_all", namespace="proj-a")
    _sembrar(hc, n_temas=5, por=6, seed=1)
    db = hc.store.path
    hc.close()
    otro = Store(db, namespace="proj-b")
    for i in range(20):
        t = f"contexto b palabra{i % 5} palabra{(i + 2) % 5} extra{i}"
        otro.add(t, encode_text(t), 1.0, 0.6, 0.6)
    otro.commit(); otro.close()

    os.environ["HIPERCAMPO_DB"] = db
    try:
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["reindex", "--all-namespaces"])
        assert code == 0
        out = json.loads(buf.getvalue())
        assert out["links_woven"] > 0, "debió tejer en los contextos con datos"
        assert {"proj-a", "proj-b"} <= set(out["contexts"])
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)
    # aislamiento: ningún enlace cruza contextos
    s = Store(db, namespace="proj-a")
    cruces = [e for e in s.links_dump(all_namespaces=True) if e["type"] == "knn"
              and e["namespace"] not in ("proj-a", "proj-b")]
    s.close()
    assert not cruces, f"tejió fuera de contexto: {cruces}"


def test_dream_all_namespaces_aggregates_ideas_from_each_namespace():
    """The Ideas tab was empty because dream ran on default. --all-namespaces must
    aggregate labeled bridges from every namespace."""
    import contextlib
    import io
    import json
    import os
    from hipercampo import cli
    hc = memory("dream_all", namespace="ctx-a")
    _sembrar(hc, n_temas=6, por=8, seed=11)
    db = hc.store.path
    hc.store.reindex_navgraph(M=10)
    hc.close()
    otro = Store(db, namespace="ctx-b")
    for i in range(30):
        t = f"ctxb concepto{i % 6} concepto{(i + 1) % 6} nota{i}"
        otro.add(t, encode_text(t), 1.0, 0.6, 0.6)
    otro.commit()
    otro.reindex_navgraph(M=10)
    otro.close()

    os.environ["HIPERCAMPO_DB"] = db
    try:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = cli.main(["dream", "--json", "--max", "10", "--all-namespaces"])
        assert code == 0
        d = json.loads(buf.getvalue())
        ctxs = {b.get("context") for b in d.get("bridges", [])}
        assert d.get("bridges"), "debería proponer ideas de los contextos con datos"
        assert ctxs & {"ctx-a", "ctx-b"}, f"ideas sin contexto reconocible: {ctxs}"
    finally:
        os.environ.pop("HIPERCAMPO_DB", None)


if __name__ == "__main__":
    clean()
    codigo = run_tests(dict(globals()))
    clean()
    sys.exit(codigo)
