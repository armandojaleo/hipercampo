"""
Fase 2 — ¿aporta hipercampo frente a lo estándar?  Ejecuta:
    python scripts/baselines.py            # BM25 vs hipercampo (léxico) + ablaciones
    python scripts/baselines.py --semantic # añade embeddings+coseno y hipercampo semántico

Compara, sobre el MISMO corpus (banco de estrés), varios métodos de recuperación:
  - BM25            (léxico exacto clásico, sin dependencias, implementado aquí)
  - embeddings+cos  (si hay sentence-transformers): el baseline "fuerte" semántico
  - hipercampo      (léxico VSA, por defecto)
  - hipercampo+sem  (con hook semántico)
  - ablaciones de hipercampo (sin propagación, sin trigramas de carácter)

Métricas: MRR por categoría (keyword/typo/synonym) + tasa de FALSA RECUPERACIÓN
sobre consultas negativas (mide la capacidad de ABSTENERSE, que BM25/coseno no tienen).
"""

import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.stress import CASOS, DISTRACTORES        # noqa: E402
from hipercampo.memory import Hipercampo               # noqa: E402

_word = re.compile(r"\w+", re.UNICODE)


def tok(s):
    return _word.findall(s.lower())


# Consultas NEGATIVAS: no deben devolver nada (miden la abstención).
NEGATIVAS = [
    "recetas de cocina tailandesa con leche de coco",
    "resultados de la liga de baloncesto del domingo",
    "cómo plantar tomates en un huerto urbano",
    "historia de la música barroca europea",
    "precio del billete de tren a Sevilla",
]


# --- BM25 mínimo (sin dependencias) -----------------------------------------
class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = [tok(d) for d in docs]
        self.k1, self.b = k1, b
        self.N = len(self.docs)
        self.avgdl = sum(len(d) for d in self.docs) / max(self.N, 1)
        df = Counter()
        for d in self.docs:
            for t in set(d):
                df[t] += 1
        self.idf = {t: math.log((self.N - n + 0.5) / (n + 0.5) + 1) for t, n in df.items()}
        self.tf = [Counter(d) for d in self.docs]

    def scores(self, query):
        q = tok(query)
        out = []
        for i, d in enumerate(self.docs):
            s = 0.0
            dl = len(d)
            for t in q:
                if t not in self.idf:
                    continue
                f = self.tf[i][t]
                s += self.idf[t] * f * (self.k1 + 1) / (
                    f + self.k1 * (1 - self.b + self.b * dl / self.avgdl))
            out.append(s)
        return out


# --- utilidades de evaluación ------------------------------------------------
def mrr_hit1(rank_fn, casos, categoria, facts):
    """rank_fn(query) -> lista de índices de 'facts' ordenados. Devuelve (MRR, hit1)."""
    rr = hit1 = 0.0
    for hecho, qs in casos:
        idx_correcto = facts.index(hecho)
        orden = rank_fn(qs[categoria])
        pos = orden.index(idx_correcto) if idx_correcto in orden else None
        if pos == 0:
            hit1 += 1
        rr += 1.0 / (pos + 1) if pos is not None else 0.0
    n = len(casos)
    return rr / n, hit1 / n


def falsa_recuperacion(devuelve_algo_fn):
    """Fracción de consultas NEGATIVAS para las que el método devuelve algún
    resultado (idealmente 0: saber abstenerse)."""
    return sum(1 for q in NEGATIVAS if devuelve_algo_fn(q)) / len(NEGATIVAS)


def run(semantic=False):
    facts = [h for h, _ in CASOS] + DISTRACTORES
    cats = ("keyword", "typo", "synonym")

    metodos = {}   # nombre -> (rank_fn, devuelve_algo_fn)

    # BM25 ---------------------------------------------------------------
    bm = BM25(facts)
    def bm_rank(q):
        sc = bm.scores(q)
        return sorted(range(len(facts)), key=lambda i: sc[i], reverse=True)
    def bm_hit(q):
        sc = bm.scores(q)
        return max(sc) > 0          # BM25 "devuelve algo" si hay solape de términos
    metodos["BM25"] = (bm_rank, bm_hit)

    # embeddings + coseno (opcional) ------------------------------------
    if semantic:
        try:
            from sentence_transformers import SentenceTransformer
            import numpy as np
            model = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")
            E = model.encode(facts, normalize_embeddings=True)
            def cos_rank(q):
                v = model.encode(q, normalize_embeddings=True)
                sc = E @ v
                return sorted(range(len(facts)), key=lambda i: sc[i], reverse=True)
            def cos_hit(q):
                v = model.encode(q, normalize_embeddings=True)
                return float((E @ v).max()) > 0.35   # umbral típico de coseno
            metodos["embeddings+cos"] = (cos_rank, cos_hit)
        except Exception as e:
            print(f"(embeddings no disponibles: {e})")

    # hipercampo (varias configuraciones) --------------------------------
    def make_hc(ns, hops=1, semantic_hook=False):
        from hipercampo import encoder
        encoder.set_semantic_hook(None)
        if semantic_hook:
            encoder.enable_semantic()
        DB = f"data/_bl_{ns}.db"
        for s in ("", "-wal", "-shm"):
            Path(DB + s).unlink(missing_ok=True)
        hc = Hipercampo(DB, namespace=ns)
        for f in facts:
            hc.remember(f, 0.5)
        id_by_fact = {r["text"]: r["id"] for r in hc.store.all(only_active=False)}
        order_ids = [id_by_fact.get(f) for f in facts]

        def rank(q):
            hits = hc.recall(q, k=len(facts), hops=hops, include_history=True)
            got = [h["id"] for h in hits]
            ranked = [order_ids.index(i) for i in got if i in order_ids]
            resto = [j for j in range(len(facts)) if j not in ranked]
            return ranked + resto
        def hit(q):
            return len(hc.recall(q, k=3, hops=hops)) > 0
        return hc, rank, hit

    hc1, r1, h1 = make_hc("full")
    metodos["hipercampo"] = (r1, h1)
    hc2, r2, h2 = make_hc("nohop", hops=0)
    metodos["hc (sin propagación)"] = (r2, h2)
    if semantic:
        hc3, r3, h3 = make_hc("sem", semantic_hook=True)
        metodos["hipercampo+sem"] = (r3, h3)

    # informe ------------------------------------------------------------
    print(f"\nCorpus: {len(facts)} hechos | consultas negativas: {len(NEGATIVAS)}\n")
    cab = f"{'método':22}" + "".join(f"{c:>10}" for c in cats) + f"{'global':>9}{'falsaRec':>10}"
    print(cab); print("-" * len(cab))
    for nombre, (rank_fn, hit_fn) in metodos.items():
        mrrs = [mrr_hit1(rank_fn, CASOS, c, facts)[0] for c in cats]
        glob = sum(mrrs) / len(mrrs)
        fr = falsa_recuperacion(hit_fn)
        fila = f"{nombre:22}" + "".join(f"{m:>10.3f}" for m in mrrs) + f"{glob:>9.3f}{fr:>10.2f}"
        print(fila)
    print("\n(MRR: más alto mejor. falsaRec: fracción de consultas ajenas que devuelven algo; más bajo mejor.)")


if __name__ == "__main__":
    run(semantic="--semantic" in sys.argv)
