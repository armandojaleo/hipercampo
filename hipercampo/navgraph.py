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

ADAPTIVE_MIN_MEAN_DEGREE = 8.0
ADAPTIVE_MIN_TWO_HOP_COVERAGE = 0.30
ADAPTIVE_TOPOLOGY_SAMPLES = 8


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
        self.effective_shortcuts = shortcuts
        self.component_count = 0
        self.mean_base_degree = 0.0
        self.two_hop_coverage = 0.0
        self.ef = ef
        self.max_degree = max_degree
        self.adj: dict[int, list[int]] = {}
        self.code: dict[int, np.ndarray] = {}
        self._code_positions: dict[int, int] | None = None
        self._code_matrix: np.ndarray | None = None
        self.entry: int | None = None          # hub de entrada (nodo muy conectado)
        self.entries: list[int] = []           # representantes de islas semánticas
        self._entry_matrix: np.ndarray | None = None
        self._node_positions: dict[int, int] | None = None
        self._neighbor_offsets: np.ndarray | None = None
        self._neighbor_ids: np.ndarray | None = None
        self._rnd = random.Random(seed)

    def __len__(self) -> int:
        return len(self._code_positions) if self._code_positions is not None else len(self.code)

    def _ids(self) -> list[int]:
        if self._code_positions is not None:
            return list(self._code_positions)
        return list(self.code)

    def _has_code(self, mid: int) -> bool:
        if self._code_positions is not None:
            return mid in self._code_positions
        return mid in self.code

    def _code_of(self, mid: int) -> np.ndarray:
        if self._code_positions is None or self._code_matrix is None:
            return self.code[mid]
        return self._code_matrix[self._code_positions[mid]]

    @classmethod
    def desde_enlaces(cls, codes: dict, edges, shortcuts: int = 2, seed: int = 0,
                      compact: bool = False, code_ids: list[int] | None = None,
                      code_matrix: np.ndarray | None = None,
                      adaptive_shortcuts: bool = False, **kw) -> "NavGraph":
        """Construye el índice a partir de enlaces YA existentes (los knn del mapa) +
        atajos de largo alcance efímeros (del índice, no del mapa: no se guardan ni se
        muestran, y no propagan activación — solo hacen navegable el grafo). `codes`
        es {id: hipervector}; `edges` una lista de pares (a, b)."""
        g = cls(shortcuts=shortcuts, seed=seed, **kw)
        if code_matrix is not None:
            ids = list(code_ids or [])
            if code_matrix.shape[0] != len(ids):
                raise ValueError("code_ids y code_matrix no tienen la misma longitud")
            g._code_positions = {mid: pos for pos, mid in enumerate(ids)}
            g._code_matrix = code_matrix
            for mid in ids:
                g.adj[mid] = []
        else:
            for mid, hv in codes.items():
                g.code[mid] = hv
                g.adj.setdefault(mid, [])
            ids = g._ids()
        for a, b in edges:                       # enlaces reales (bidireccionales)
            if g._has_code(a) and g._has_code(b) and b not in g.adj[a]:
                g.adj[a].append(b)
                g.adj.setdefault(b, []).append(a)
        ids = g._ids()
        # Los enlaces reales pueden formar islas semánticas desconectadas. Elegimos
        # un landmark por isla ANTES de añadir atajos efímeros, para seleccionar
        # primero el concepto correcto y navegar después solo su vecindario.
        vistos: set[int] = set()
        for start in ids:
            if start in vistos:
                continue
            componente: list[int] = []
            pila = [start]
            vistos.add(start)
            while pila:
                actual = pila.pop()
                componente.append(actual)
                for vecino in g.adj.get(actual, ()):
                    if vecino not in vistos:
                        vistos.add(vecino)
                        pila.append(vecino)
            g.entries.append(max(componente, key=lambda x: len(g.adj[x])))
        g.component_count = len(g.entries)
        g.mean_base_degree = (
            sum(len(g.adj[mid]) for mid in ids) / len(ids) if ids else 0.0
        )
        if ids:
            sample_count = min(ADAPTIVE_TOPOLOGY_SAMPLES, len(ids))
            sample = [ids[i * len(ids) // sample_count] for i in range(sample_count)]
            coverages = []
            for mid in sample:
                one_hop = set(g.adj[mid])
                two_hops = {
                    neighbor
                    for first in one_hop
                    for neighbor in g.adj.get(first, ())
                }
                coverages.append(len({mid} | one_hop | two_hops) / len(ids))
            g.two_hop_coverage = sum(coverages) / len(coverages)
        # En un componente KNN que ya cubre gran parte del mapa en dos saltos, los
        # atajos aleatorios solo ensanchan la frontera. Si hay comunidades, cadenas
        # o islas, se conserva small-world: ahí sí aporta rutas que faltan.
        if (adaptive_shortcuts and g.component_count == 1
                and g.mean_base_degree >= ADAPTIVE_MIN_MEAN_DEGREE
                and g.two_hop_coverage >= ADAPTIVE_MIN_TWO_HOP_COVERAGE):
            g.effective_shortcuts = 0
        else:
            g.effective_shortcuts = shortcuts
        for mid in ids:                          # atajos small-world (índice interno)
            for _ in range(g.effective_shortcuts):
                r = g._rnd.choice(ids)
                if r != mid and r not in g.adj[mid]:
                    g.adj[mid].append(r)
                    g.adj[r].append(mid)
        if ids:                                  # entrada = el nodo más conectado
            g.entry = max(ids, key=lambda x: len(g.adj[x]))
        g._refresh_entry_matrix()
        if compact:
            g._compact()
        return g

    # --- construcción ---------------------------------------------------------
    def add(self, mid: int, hv: np.ndarray) -> None:
        """Inserta un recuerdo NAVEGANDO el grafo para hallar sus vecinos (sin escaneo).
        Enlaza con sus M más cercanos + `shortcuts` atajos aleatorios de largo alcance."""
        if self._code_positions is not None:
            raise RuntimeError("un índice residente compacto no admite inserción directa")
        if mid in self.code:
            return
        self.code[mid] = hv
        if not self.adj:                        # primer nodo
            self.adj[mid] = []
            self.entry = mid
            self.entries = [mid]
            self._refresh_entry_matrix()
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
        self.entries = [self.entry] if self.entry is not None else []
        self._refresh_entry_matrix()

    def _refresh_entry_matrix(self) -> None:
        """Precalcula landmarks contiguos para comparar conceptos en NumPy."""
        if len(self.entries) < 8:
            self._entry_matrix = None
            return
        self._entry_matrix = np.stack([self._code_of(mid) for mid in self.entries])

    @property
    def is_compact(self) -> bool:
        """El mapa terminado usa arrays contiguos en vez de objetos por arista."""
        return self._neighbor_offsets is not None

    @property
    def edge_count(self) -> int:
        """Número de aristas dirigidas del mapa, sea dinámico o compacto."""
        if self._neighbor_offsets is not None:
            return int(self._neighbor_offsets[-1])
        return sum(len(neighbors) for neighbors in self.adj.values())

    def _compact(self) -> None:
        """Convierte la adyacencia estática a CSR para reducir la RAM residente."""
        ids = self._ids()
        if not ids:
            return
        offsets = np.empty(len(ids) + 1, dtype=np.uint64)
        offsets[0] = 0
        total = 0
        for pos, mid in enumerate(ids, start=1):
            total += len(self.adj.get(mid, ()))
            offsets[pos] = total
        id_dtype = np.uint32 if max(ids) <= np.iinfo(np.uint32).max else np.uint64
        neighbors = np.empty(total, dtype=id_dtype)
        cursor = 0
        for mid in ids:
            actuales = self.adj.pop(mid, ())
            siguiente = cursor + len(actuales)
            neighbors[cursor:siguiente] = actuales
            cursor = siguiente
        self._node_positions = self._code_positions or {
            mid: pos for pos, mid in enumerate(ids)
        }
        self._neighbor_offsets = offsets
        self._neighbor_ids = neighbors

    def _neighbors_of(self, mid: int):
        if self._neighbor_offsets is None or self._neighbor_ids is None:
            return self.adj.get(mid, ())
        assert self._node_positions is not None
        pos = self._node_positions.get(mid)
        if pos is None:
            return ()
        start = int(self._neighbor_offsets[pos])
        end = int(self._neighbor_offsets[pos + 1])
        return self._neighbor_ids[start:end]
    def _conectar(self, a: int, b: int) -> None:
        if a == b or b in self.adj[a]:
            return
        self.adj[a].append(b)
        self.adj.setdefault(b, []).append(a)
        for n in (a, b):                        # poda de grado
            if len(self.adj[n]) > self.max_degree:
                base = self._code_of(n)
                ord_ = sorted(self.adj[n], key=lambda x: _hamming(base, self._code_of(x)))
                self.adj[n] = ord_[:self.max_degree]

    # --- búsqueda -------------------------------------------------------------
    def _buscar(self, qhv: np.ndarray, ef: int, excluir: int | None = None,
                entradas: list[int] | None = None) -> tuple[int, list[int]]:
        """Beam search: parte de las entradas y salta a vecinos más cercanos a q hasta
        que no mejora. Devuelve (nodos_visitados, ids ordenados por cercanía)."""
        vis: set[int] = set()
        cand: list[tuple[int, int]] = []        # min-heap por distancia (frontera)
        res: list[tuple[int, int]] = []         # max-heap (negado) con los ef mejores
        distancias: dict[int, int] = {}
        if entradas is None:
            landmarks = self.entries or (
                [self.entry] if self.entry is not None else []
            )
            # Comparar un representante por componente cuesta C (conceptos), no N
            # (recuerdos). Entramos por las cuatro islas semánticamente más cercanas.
            if self._entry_matrix is not None and len(landmarks) == len(self.entries):
                lote = _popcount_rows(np.bitwise_xor(self._entry_matrix, qhv))
                for e, distancia in zip(self.entries, lote, strict=True):
                    if e != excluir:
                        distancias[e] = int(distancia)
                        vis.add(e)
            else:
                for e in landmarks:
                    if e == excluir or not self._has_code(e):
                        continue
                    distancias[e] = _hamming(qhv, self._code_of(e))
                    vis.add(e)
            entradas = [
                e for e, _ in sorted(distancias.items(), key=lambda item: item[1])[:4]
            ]
        for e in entradas:
            if e is None or e == excluir or not self._has_code(e):
                continue
            d = distancias.get(e)
            if d is None:
                d = _hamming(qhv, self._code_of(e))
            vis.add(e)
            heapq.heappush(cand, (d, e))
            heapq.heappush(res, (-d, e))
        while cand:
            d, c = heapq.heappop(cand)
            if res and d > -res[0][0] and len(res) >= ef:
                break                           # nada por explorar mejora a los mejores
            for raw_nb in self._neighbors_of(c):
                nb = int(raw_nb)
                if nb in vis or nb == excluir:
                    continue
                vis.add(nb)
                dn = _hamming(qhv, self._code_of(nb))
                if len(res) < ef or dn < -res[0][0]:
                    heapq.heappush(cand, (dn, nb))
                    heapq.heappush(res, (-dn, nb))
                    if len(res) > ef:
                        heapq.heappop(res)
        ordenados = [mid for _, mid in sorted((-x[0], x[1]) for x in res)]
        return len(vis), ordenados

    def search_with_stats(self, qhv: np.ndarray, k: int = 5,
                          entradas: list[int] | None = None,
                          ef: int | None = None) -> tuple[list[tuple[int, float]], int]:
        """Busca una sola vez y devuelve (resultados, nodos_visitados).

        ``ef`` permite al consumidor ajustar calidad/coste para su número de
        candidatos sin repetir el recorrido solo para medirlo.
        """
        width = max(k, self.ef if ef is None else max(1, int(ef)))
        visitados, ordenados = self._buscar(qhv, width, entradas=entradas)
        salida = []
        for mid in ordenados[:k]:
            salida.append((mid, 1.0 - _hamming(qhv, self._code_of(mid)) / D))
        return salida, visitados

    def search(self, qhv: np.ndarray, k: int = 5,
               entradas: list[int] | None = None) -> list[tuple[int, float]]:
        """Los k recuerdos más parecidos a q, NAVEGANDO el grafo."""
        return self.search_with_stats(qhv, k=k, entradas=entradas)[0]

    def visitados_en(self, qhv: np.ndarray) -> int:
        """Cuántos nodos toca una búsqueda (para medir la sublinealidad)."""
        vis, _ = self._buscar(qhv, self.ef)
        return vis
