"""
El ciclo de memoria de hipercampo — los cuatro hilos, integrados:

  1. ESCRITURA POR SORPRESA   remember() solo graba lo que NO era predecible
                              a partir de lo ya guardado. Lo redundante refuerza
                              el recuerdo existente en vez de duplicar.
  2. RECUERDO POR PROPAGACIÓN recall() no hace solo top-k: enciende los nodos más
                              parecidos y la activación se propaga por asociaciones
                              (spreading activation).
  3. CONSOLIDACIÓN ("sueño")  consolidate() agrupa episodios parecidos, los funde
                              en conocimiento semántico condensado y los archiva.
  4. OLVIDO ACTIVO            forget() deja decaer la fuerza con el tiempo y poda
                              lo débil, poco usado y poco importante.

Nota honesta sobre "sorpresa": sin acceso a la pérdida del LLM usamos un proxy
por NOVEDAD = 1 - (máxima similitud con lo ya sabido). Es una aproximación
defendible; el gancho para una sorpresa real (error de predicción) queda abierto.
"""

import os
import time

import numpy as np

from .encoder import encode_text
from .store import Store
from .surprise import SurpriseModel
from .vsa import bundle, similarity

# --- parámetros de criterio (aquí es donde manda el juicio humano) -------
NOVELTY_WRITE_THRESHOLD = 0.06   # por debajo -> ya lo tenemos, no dupliques
SURPRISE_WRITE_THRESHOLD = 0.05  # por debajo -> el modelo ya lo predecía, trivial
LINK_SIMILARITY = 0.58           # crear asociación entre recuerdos así de parecidos
CONSOLIDATE_SIMILARITY = 0.60    # fundir episodios así de parecidos
DECAY_HALF_LIFE_DAYS = 14.0      # a qué ritmo se desvanece lo no reforzado
FORGET_STRENGTH_FLOOR = 0.15     # por debajo de esto y sin uso -> se poda


class Hipercampo:
    def __init__(self, path="data/hipercampo.db"):
        self.store = Store(path)
        # Modelo de sorpresa: se "calienta" reproduciendo la memoria existente,
        # así lo ya guardado no vuelve a considerarse sorprendente tras un reinicio.
        self.surprise = SurpriseModel()
        for row in self.store.all(only_active=False):
            self.surprise.learn(row["text"])

    # 1 -------------------------------------------------------------------
    def remember(self, text: str, importance: float = 0.5) -> dict:
        """Graba un episodio si es novedoso O sorprendente (error de predicción)."""
        hv = encode_text(text)
        actives = self.store.all(only_active=True)

        best_id, best_sim = None, 0.0
        for row in actives:
            s = similarity(hv, self.store.hv_of(row))
            if s > best_sim:
                best_sim, best_id = s, row["id"]

        novelty = 1.0 - best_sim                      # ¿hay algo parecido ya?
        surprise = self.surprise.surprise(text)       # ¿era predecible? (bits, MDL)
        self.surprise.learn(text)                     # lo visto deja de sorprender

        # DOBLE VETO (la tesis del ahorro de tokens): saltamos lo que NO aporta,
        # sea porque ya lo tenemos (redundante) o porque el modelo ya lo predecía
        # (conocimiento trivial). Solo guardamos lo novedoso Y sorprendente.
        redundante = best_id is not None and novelty < NOVELTY_WRITE_THRESHOLD
        predecible = surprise < SURPRISE_WRITE_THRESHOLD
        if redundante or predecible:
            if best_id is not None:
                self.store.reinforce(best_id)
            return {"stored": False,
                    "reason": "redundante" if redundante else "predecible",
                    "novelty": round(novelty, 3), "surprise": round(surprise, 3),
                    "reinforced_id": best_id}

        mem_id = self.store.add(text, hv, max(novelty, surprise), importance)

        # Tejer asociaciones con lo parecido (grafo para la propagación).
        for row in actives:
            s = similarity(hv, self.store.hv_of(row))
            if s >= LINK_SIMILARITY:
                self.store.link(mem_id, row["id"], weight=s)

        return {"stored": True, "id": mem_id, "novelty": round(novelty, 3),
                "surprise": round(surprise, 3), "importance": importance}

    # 2 -------------------------------------------------------------------
    def recall(self, query: str, k: int = 5, hops: int = 1) -> list[dict]:
        """
        Recupera por similitud (semillas) + propagación de activación (asociados).
        Refuerza lo recuperado: recordar algo lo hace más difícil de olvidar.
        """
        qhv = encode_text(query)
        rows = self.store.all(only_active=False)
        if not rows:
            return []

        # activación inicial = similitud con la consulta, AFILADA.
        # En VSA lo no-relacionado vive en ~0.5, así que reescalamos
        # 0.5 -> 0 y 1.0 -> 1 para que el ranking tenga contraste real.
        activation: dict[int, float] = {}
        by_id = {r["id"]: r for r in rows}
        for r in rows:
            sim = similarity(qhv, self.store.hv_of(r))
            activation[r["id"]] = max(0.0, 2.0 * (sim - 0.5))

        # propagación: la chispa salta a los vecinos, atenuada
        seeds = sorted(activation, key=activation.get, reverse=True)[:k]
        frontier = list(seeds)
        for _ in range(hops):
            nxt = []
            for mid in frontier:
                for dst, w in self.store.neighbors(mid):
                    if dst in activation:
                        spread = activation[mid] * w * 0.5
                        if spread > activation[dst]:
                            activation[dst] = spread
                            nxt.append(dst)
            frontier = nxt

        # puntuación final combina activación con fuerza del recuerdo
        scored = []
        for mid, act in activation.items():
            r = by_id[mid]
            score = act * (0.7 + 0.3 * min(r["strength"], 3.0) / 3.0)
            scored.append((score, act, r))
        scored.sort(key=lambda t: t[0], reverse=True)

        top = scored[:k]
        self.store.touch([r["id"] for _, _, r in top])   # reforzar lo usado

        return [
            {"id": r["id"], "text": r["text"], "kind": r["kind"],
             "score": round(score, 3), "activation": round(act, 3),
             "strength": round(r["strength"], 2)}
            for score, act, r in top
        ]

    # 3 -------------------------------------------------------------------
    def consolidate(self) -> dict:
        """
        Fase de 'sueño': agrupa episodios muy parecidos, los funde en un recuerdo
        semántico (superposición de sus hipervectores + texto unido) y archiva los
        originales. Así el conocimiento se condensa y deja de ocupar contexto.
        """
        eps = [r for r in self.store.all(kind="episodic", only_active=True)]
        used: set[int] = set()
        clusters: list[list] = []

        for r in eps:
            if r["id"] in used:
                continue
            group = [r]
            used.add(r["id"])
            for other in eps:
                if other["id"] in used:
                    continue
                if similarity(self.store.hv_of(r), self.store.hv_of(other)) >= CONSOLIDATE_SIMILARITY:
                    group.append(other)
                    used.add(other["id"])
            if len(group) >= 2:
                clusters.append(group)

        made = 0
        archived = 0
        for group in clusters:
            hv = bundle([self.store.hv_of(g) for g in group])
            text = "· " + "\n· ".join(g["text"] for g in group)
            importance = max(g["importance"] for g in group)
            novelty = float(np.mean([g["novelty"] for g in group]))
            sem_id = self.store.add(
                f"[consolidado x{len(group)}]\n{text}", hv, novelty, importance,
                kind="semantic",
            )
            self.store.mark_consolidated([g["id"] for g in group])
            for g in group:                      # heredar asociaciones
                for dst, w in self.store.neighbors(g["id"]):
                    self.store.link(sem_id, dst, w)
            made += 1
            archived += len(group)

        return {"clusters_fusionados": made, "episodios_archivados": archived}

    # 4 -------------------------------------------------------------------
    def forget(self, dry_run: bool = False) -> dict:
        """
        Olvido activo: la fuerza decae exponencialmente con el tiempo sin uso.
        Lo que cae por debajo del suelo (y no es importante ni consolidado)
        se poda. La importancia alta protege del olvido.
        """
        now = time.time()
        half = DECAY_HALF_LIFE_DAYS * 86400
        to_prune: list[int] = []

        for r in self.store.all(only_active=False):
            if r["kind"] == "semantic":
                continue                                   # el conocimiento perdura
            age = now - r["last_access"]
            decayed = r["strength"] * (0.5 ** (age / half))
            protected = r["importance"] >= 0.8
            if decayed < FORGET_STRENGTH_FLOOR and not protected:
                to_prune.append(r["id"])
            elif not dry_run:
                self.store.set_strength(r["id"], decayed)

        if not dry_run and to_prune:
            self.store.delete(to_prune)
        self.store.commit()
        return {"olvidados": len(to_prune), "ids": to_prune, "dry_run": dry_run}

    # utilidades ----------------------------------------------------------
    def stats(self) -> dict:
        rows = self.store.all(only_active=False)
        ep = [r for r in rows if r["kind"] == "episodic" and not r["consolidated"]]
        sem = [r for r in rows if r["kind"] == "semantic"]
        arch = [r for r in rows if r["consolidated"]]
        return {"episodicos_activos": len(ep), "semanticos": len(sem),
                "archivados": len(arch), "total": len(rows),
                "db": os.path.abspath(self.store.path)}
