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
SUPERSEDE_HINT_SIMILARITY = 0.72 # por encima -> avisamos de posible actualización
SUPERSEDED_RECALL_PENALTY = 0.2  # cuánto se demueve un recuerdo superado al recuperar
MIN_RECALL_SCORE = 0.03          # por debajo -> irrelevante; recall se abstiene
REINFORCE_MIN_SCORE = 0.10       # solo se refuerza lo claramente relevante (no roce)
UPDATE_MIN_SIMILARITY = 0.60     # hc_update no reemplaza si no hay match así de bueno
LINK_SIMILARITY = 0.58           # crear asociación entre recuerdos así de parecidos
CONSOLIDATE_SIMILARITY = 0.60    # fundir episodios así de parecidos
DECAY_HALF_LIFE_DAYS = 14.0      # a qué ritmo se desvanece lo no reforzado
FORGET_STRENGTH_FLOOR = 0.15     # por debajo de esto y sin uso -> candidato a poda
RETENTION_FLOOR = 0.40           # valor (4 ejes) mínimo para NO olvidar
UTILITY_CAP = 5                  # nº de usos que ya cuenta como "utilidad plena"


class Hipercampo:
    def __init__(self, path="data/hipercampo.db", namespace="default"):
        self.store = Store(path, namespace=namespace)
        # Modelo de sorpresa: se "calienta" reproduciendo la memoria existente,
        # así lo ya guardado no vuelve a considerarse sorprendente tras un reinicio.
        self.surprise = SurpriseModel()
        for row in self.store.all(only_active=False):
            self.surprise.learn(row["text"])

    # --- los cuatro ejes, separados ------------------------------------
    @staticmethod
    def utility(row) -> float:
        """Utilidad: cuánto se ha USADO de verdad (0..1). Derivada, no declarada."""
        return min(row["access_count"], UTILITY_CAP) / UTILITY_CAP

    def retention(self, row) -> float:
        """Cuánto MERECE conservarse, combinando ejes DISTINTOS y transparentes:
        importancia (cuánto importa) + fiabilidad (cuán cierto) + utilidad (cuánto
        se usa). No mezcla la fuerza/decaimiento (eso es el tiempo, no el valor)."""
        return (0.4 * row["importance"] + 0.3 * row["confidence"]
                + 0.3 * self.utility(row))

    # 1 -------------------------------------------------------------------
    def remember(self, text: str, importance: float = 0.5,
                 confidence: float = 0.5) -> dict:
        """Graba un episodio salvo doble veto: NO lo guarda si es redundante (ya hay
        algo casi igual) NI si es predecible (el modelo de sorpresa ya lo esperaba)."""
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

        mem_id = self.store.add(text, hv, max(novelty, surprise), importance, confidence)

        # Tejer asociaciones con lo parecido (grafo para la propagación).
        for row in actives:
            s = similarity(hv, self.store.hv_of(row))
            if s >= LINK_SIMILARITY:
                self.store.link(mem_id, row["id"], weight=s)

        result = {"stored": True, "id": mem_id, "novelty": round(novelty, 3),
                  "surprise": round(surprise, 3), "importance": importance}

        # Aviso de posible actualización/contradicción: si esto se parece mucho a un
        # recuerdo existente, quizá lo ACTUALICE. No decidimos nosotros (haría falta
        # entender el significado): se lo señalamos al LLM para que use hc_update.
        if best_id is not None and best_sim >= SUPERSEDE_HINT_SIMILARITY:
            old = self.store.get(best_id)
            result["similar_to"] = {"id": best_id, "text": old["text"],
                                    "similarity": round(best_sim, 3)}
            result["hint"] = ("Se parece a un recuerdo existente. Si lo ACTUALIZA o "
                              "CONTRADICE (un hecho que cambió), usa hc_update para "
                              "reemplazarlo en vez de acumular contradicciones.")
        return result

    def update(self, target: str, new_text: str, importance: float = 0.7,
               memory_id: int | None = None) -> dict:
        """Reemplaza un hecho que cambió. Localiza el recuerdo a superar por
        'memory_id' (exacto) o por el que mejor case con 'target'. Si NO hay un
        match suficientemente bueno (< UPDATE_MIN_SIMILARITY) NO reemplaza nada:
        guarda 'new_text' como recuerdo nuevo y lo avisa, para no pisar un recuerdo
        ajeno por error. El superado no se borra: queda como historia, demovido."""
        best, best_sim = None, 0.0
        if memory_id is not None:
            best = self.store.get(memory_id)
            best_sim = 1.0 if best is not None else 0.0
        else:
            thv = encode_text(target)
            for r in self.store.all(only_active=False):
                if r["superseded"]:
                    continue
                s = similarity(thv, self.store.hv_of(r))
                if s > best_sim:
                    best_sim, best = s, r

        new_hv = encode_text(new_text)
        self.surprise.learn(new_text)
        new_id = self.store.add(new_text, new_hv, 1.0, importance, confidence=0.75)
        for r in self.store.all(only_active=True):
            if r["id"] != new_id:
                s = similarity(new_hv, self.store.hv_of(r))
                if s >= LINK_SIMILARITY:
                    self.store.link(new_id, r["id"], weight=s)

        # Solo superamos si el match es fiable; si no, no pisamos a nadie.
        if best is not None and best_sim >= UPDATE_MIN_SIMILARITY:
            self.store.mark_superseded([best["id"]])
            self.store.link(new_id, best["id"], weight=1.0)   # cadena de historia
            return {"updated": True, "new_id": new_id, "superseded_id": best["id"],
                    "replaced_text": best["text"], "match_similarity": round(best_sim, 3)}
        return {"updated": False, "reason": "sin match fiable que reemplazar",
                "new_id": new_id, "best_similarity": round(best_sim, 3),
                "hint": "Guardado como recuerdo nuevo. Si querías reemplazar uno "
                        "concreto, vuelve a llamar con memory_id."}

    # 2 -------------------------------------------------------------------
    def recall(self, query: str, k: int = 5, hops: int = 1,
               include_history: bool = False) -> list[dict]:
        """
        Recupera por similitud (semillas) + propagación de activación (asociados).
        Puede devolver LISTA VACÍA si nada supera el umbral mínimo de relevancia
        (saber decir "no tengo nada" evita reforzar falsos positivos por ruido).
        Por defecto NO devuelve historia (episodios ya consolidados ni superados);
        pon include_history=True para verla. Solo refuerza lo realmente devuelto.
        """
        qhv = encode_text(query)
        rows = self.store.all(only_active=False)
        if not include_history:                      # nada de archivados ni superados
            rows = [r for r in rows if not r["consolidated"] and not r["superseded"]]
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
            score *= (0.6 + 0.4 * r["confidence"])    # la FIABILIDAD pesa en el ranking
            if r["superseded"]:                       # lo reemplazado no debe dominar
                score *= SUPERSEDED_RECALL_PENALTY
            scored.append((score, act, r))
        scored.sort(key=lambda t: t[0], reverse=True)

        # ABSTENCIÓN: solo lo que supera el umbral mínimo de relevancia. Así una
        # consulta sin relación real devuelve [] en vez de ruido, y no reforzamos
        # falsos positivos (que si no, ganarían utilidad y se auto-protegerían).
        top = [(s, a, r) for s, a, r in scored[:k] if s >= MIN_RECALL_SCORE]
        # Reforzar SOLO lo claramente relevante (no un match por roce incidental),
        # para no darle utilidad a falsos positivos que luego se auto-protegerían.
        self.store.touch([r["id"] for s, _, r in top if s >= REINFORCE_MIN_SCORE])

        return [
            {"id": r["id"], "text": r["text"], "kind": r["kind"],
             "score": round(score, 3), "activation": round(act, 3),
             "strength": round(r["strength"], 2),
             "confidence": round(r["confidence"], 2),
             "utility": round(self.utility(r), 2)}
            for score, act, r in top
        ]

    # 3 -------------------------------------------------------------------
    def consolidate(self, summarizer=None) -> dict:
        """
        Fase de 'sueño': AGRUPA episodios muy parecidos en un recuerdo semántico
        (superposición de sus hipervectores) y archiva los originales. Reduce el nº
        de nodos activos y su hipervector condensa la estructura.

        Honestidad: por defecto es agrupación ESTRUCTURAL; el texto se une, NO se
        resume (no reduce tokens por sí solo). Pasa `summarizer(list[str])->str`
        (p. ej. una llamada a un LLM) para condensar el texto de verdad.
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
            textos = [g["text"] for g in group]
            if summarizer is not None:                    # condensación real (LLM)
                cuerpo = summarizer(textos)
                etiqueta = f"[resumen x{len(group)}]\n{cuerpo}"
            else:                                         # agrupación estructural
                etiqueta = "[agrupado x{}]\n· {}".format(len(group), "\n· ".join(textos))
            importance = max(g["importance"] for g in group)
            # confianza = media (una sola fuente muy fiable no debe inflar al grupo)
            confidence = float(np.mean([g["confidence"] for g in group]))
            novelty = float(np.mean([g["novelty"] for g in group]))
            sem_id = self.store.add(etiqueta, hv, novelty, importance,
                                    confidence, kind="semantic")
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
        Olvido activo con CUATRO EJES. El tiempo (decaimiento) solo marca
        CANDIDATOS; quien decide es la RETENCIÓN (importancia + fiabilidad +
        utilidad). Así no se olvida algo poco consultado pero importante o fiable,
        ni algo trivial solo porque se usó una vez. La importancia alta protege.
        """
        now = time.time()
        half = DECAY_HALF_LIFE_DAYS * 86400
        to_prune: list[int] = []

        for r in self.store.all(only_active=False):
            # El conocimiento semántico perdura MÁS (decae x5 más lento), pero no es
            # inmortal: una consolidación mala u obsoleta también puede podarse.
            vida = half * (5.0 if r["kind"] == "semantic" else 1.0)
            age = now - r["last_access"]
            decayed = r["strength"] * (0.5 ** (age / vida))
            protected = r["importance"] >= 0.8
            candidato = decayed < FORGET_STRENGTH_FLOOR    # el tiempo lo marca
            poco_valioso = self.retention(r) < RETENTION_FLOOR   # los ejes deciden
            if candidato and poco_valioso and not protected:
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
