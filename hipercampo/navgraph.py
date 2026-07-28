"""
Grafo navegable small-world sobre los hipervectores (el índice que SÍ encaja en VSA).

Por qué esto y no un LSH/MIH clásico: en VSA un match bueno está a similitud ~0.72
(≈2800 de 10000 bits difieren) y lo no relacionado a ~0.54. Con "cercano" tan lejos
en Hamming, el hashing por bandas casi no ayuda (medido). Pero un grafo de vecinos SÍ:
se recuerda NAVEGANDO —saltando de vecino en vecino hacia la consulta, como un GPS—
en vez de escaneando todo. La clave, medida:

  - un grafo SOLO de vecinos cercanos NO es navegable: se rompe en islas (recall 0.12).
  - añadir unos pocos ATAJOS débiles de largo alcance lo vuelve navegable (recall ~0.97),
    visitando una fracción de la memoria que ENCOGE al crecer N (13.9%→3.0% de 2k a 16k).
    Es el fenómeno small-world de Watts-Strogatz. Y esos atajos son, además, los mismos
    enlaces débiles que generan ideas: creatividad e índice resultan ser lo mismo.

Insertar tampoco escanea: para colocar un recuerdo nuevo se NAVEGA el grafo existente
para hallar sus vecinos (como HNSW). Coste ~constante (log N), no proporcional a N.

Este módulo es el ALGORITMO puro (adjacencia + búsqueda), sin tocar el store ni el
ciclo de memoria: se integra en fases, cada una medida. Sin dependencias externas.
"""

import heapq
import random

import numpy as np

from .vsa import D, _popcount_rows


def _hamming(a: np.ndarray, b: np.ndarray) -> int:
    """Bits en los que difieren dos hipervectores empaquetados (uint8[1250])."""
    return int(_popcount_rows(np.bitwise_xor(a, b).reshape(1, -1))[0])


class NavGraph:
    """Grafo navegable en memoria. Los nodos son ids de recuerdo; cada uno guarda su
    hipervector y una lista de vecinos (enlaces fuertes k-NN + atajos débiles).

    Parámetros (con valores medidos como razonables; ajustables):
      M         vecinos fuertes por nodo al insertar
      shortcuts atajos débiles de largo alcance por nodo (los que hacen navegable)
      ef        anchura del haz en la búsqueda (más = más recall, más coste)
      max_degree tope de grado por nodo (poda como HNSW, para no degenerar en hubs)
    """

    def __init__(self, M: int = 16, shortcuts: int = 2, ef: int = 48,
                 max_degree: int = 40, seed: int = 0):
        self.M = M
        self.shortcuts = shortcuts
        self.ef = ef
        self.max_degree = max_degree
        self.adj: dict[int, list[int]] = {}
        self.code: dict[int, np.ndarray] = {}
        self.entry: int | None = None          # hub de entrada (nodo muy conectado)
        self._rnd = random.Random(seed)

    def __len__(self) -> int:
        return len(self.code)

    # --- construcción ---------------------------------------------------------
    def add(self, mid: int, hv: np.ndarray) -> None:
        """Inserta un recuerdo NAVEGANDO el grafo para hallar sus vecinos (sin escaneo).
        Enlaza con sus M más cercanos + `shortcuts` atajos aleatorios de largo alcance."""
        if mid in self.code:
            return
        self.code[mid] = hv
        if not self.adj:                        # primer nodo
            self.adj[mid] = []
            self.entry = mid
            return
        self.adj[mid] = []
        _, cercanos = self._buscar(hv, self.ef, excluir=mid)
        for j in cercanos[:self.M]:             # enlaces fuertes, bidireccionales
            self._conectar(mid, j)
        existentes = [x for x in self.code if x != mid]
        for _ in range(self.shortcuts):         # atajos débiles de largo alcance
            self._conectar(mid, self._rnd.choice(existentes))
        # entrada = el nodo más conectado (una autopista por la que entrar barato)
        if self.entry is None or len(self.adj[mid]) > len(self.adj.get(self.entry, [])):
            self.entry = mid

    def _conectar(self, a: int, b: int) -> None:
        if a == b or b in self.adj[a]:
            return
        self.adj[a].append(b)
        self.adj.setdefault(b, []).append(a)
        for n in (a, b):                        # poda de grado
            if len(self.adj[n]) > self.max_degree:
                base = self.code[n]
                ord_ = sorted(self.adj[n], key=lambda x: _hamming(base, self.code[x]))
                self.adj[n] = ord_[:self.max_degree]

    # --- búsqueda -------------------------------------------------------------
    def _buscar(self, qhv: np.ndarray, ef: int, excluir: int | None = None,
                entradas: list[int] | None = None) -> tuple[int, list[int]]:
        """Beam search: parte de las entradas y salta a vecinos más cercanos a q hasta
        que no mejora. Devuelve (nodos_visitados, ids ordenados por cercanía)."""
        if entradas is None:
            entradas = [self.entry] if self.entry is not None else []
        vis: set[int] = set()
        cand: list[tuple[int, int]] = []        # min-heap por distancia (frontera)
        res: list[tuple[int, int]] = []         # max-heap (negado) con los ef mejores
        for e in entradas:
            if e is None or e == excluir or e not in self.code:
                continue
            d = _hamming(qhv, self.code[e])
            vis.add(e)
            heapq.heappush(cand, (d, e))
            heapq.heappush(res, (-d, e))
        while cand:
            d, c = heapq.heappop(cand)
            if res and d > -res[0][0] and len(res) >= ef:
                break                           # nada por explorar mejora a los mejores
            for nb in self.adj.get(c, ()):
                if nb in vis or nb == excluir:
                    continue
                vis.add(nb)
                dn = _hamming(qhv, self.code[nb])
                if len(res) < ef or dn < -res[0][0]:
                    heapq.heappush(cand, (dn, nb))
                    heapq.heappush(res, (-dn, nb))
                    if len(res) > ef:
                        heapq.heappop(res)
        ordenados = [mid for _, mid in sorted((-x[0], x[1]) for x in res)]
        return len(vis), ordenados

    def search(self, qhv: np.ndarray, k: int = 5,
               entradas: list[int] | None = None) -> list[tuple[int, float]]:
        """Los k recuerdos más parecidos a q, NAVEGANDO el grafo. Devuelve (id, similitud)."""
        _, ordenados = self._buscar(qhv, max(self.ef, k), entradas=entradas)
        salida = []
        for mid in ordenados[:k]:
            salida.append((mid, 1.0 - _hamming(qhv, self.code[mid]) / D))
        return salida

    def visitados_en(self, qhv: np.ndarray) -> int:
        """Cuántos nodos toca una búsqueda (para medir la sublinealidad)."""
        vis, _ = self._buscar(qhv, self.ef)
        return vis
