"""
Small-world navigable graph over the hypervectors (the index that DOES fit VSA).

Why this and not classic LSH/MIH: in VSA a good match sits at similarity
~0.72 (~2800 of 10000 bits differ) and unrelated content at ~0.54. With
"close" that far apart in Hamming distance, banded hashing barely helps
(measured). But a neighbor graph DOES: memory is recalled by NAVIGATING
—jumping from neighbor to neighbor towards the query, like a GPS— instead
of scanning everything. The key, measured:

  - a graph of ONLY close neighbors is NOT navigable: it breaks into
    islands (recall 0.12).
  - adding a few weak long-range SHORTCUTS makes it navigable (recall
    ~0.97), visiting a fraction of the memory that SHRINKS as N grows
    (13.9%->3.0% from 2k to 16k). It's the Watts-Strogatz small-world
    phenomenon. And those shortcuts happen to be the same weak links that
    generate ideas: creativity and indexing turn out to be the same thing.

Inserting doesn't scan either: placing a new memory NAVIGATES the existing
graph to find its neighbors (like HNSW). Roughly constant cost (log N), not
proportional to N.

This module is the pure ALGORITHM (adjacency + search), and doesn't touch
the store or the memory cycle: it's wired in through phases, each measured.
No external dependencies.
"""

import heapq
import random

import numpy as np

from .vsa import D, _popcount_rows, hamming as _hamming

ADAPTIVE_MIN_MEAN_DEGREE = 8.0
ADAPTIVE_MIN_TWO_HOP_COVERAGE = 0.30
ADAPTIVE_TOPOLOGY_SAMPLES = 8


class NavGraph:
    """Navigable in-memory graph. Nodes are memory ids; each keeps its
    hypervector and a neighbor list (strong k-NN links + weak shortcuts).

    Parameters (with values measured as reasonable; tunable):
      M         strong neighbors per node on insert
      shortcuts weak long-range shortcuts per node (what makes it navigable)
      ef        beam width during search (more = more recall, more cost)
      max_degree per-node degree cap (pruning like HNSW, to avoid degenerating into hubs)
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
        self.entry: int | None = None          # entry hub (a well-connected node)
        self.entries: list[int] = []           # representatives of semantic islands
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
    def from_links(cls, codes: dict, edges, shortcuts: int = 2, seed: int = 0,
                      compact: bool = False, code_ids: list[int] | None = None,
                      code_matrix: np.ndarray | None = None,
                      adaptive_shortcuts: bool = False, **kw) -> "NavGraph":
        """Builds the index from links that ALREADY exist (the map's knn) +
        ephemeral long-range shortcuts (of the index, not the map: they
        aren't stored or shown, and don't propagate activation — they only
        make the graph navigable). `codes` is {id: hypervector}; `edges` a
        list of (a, b) pairs."""
        g = cls(shortcuts=shortcuts, seed=seed, **kw)
        if code_matrix is not None:
            ids = list(code_ids or [])
            if code_matrix.shape[0] != len(ids):
                raise ValueError("code_ids and code_matrix don't have the same length")
            g._code_positions = {mid: pos for pos, mid in enumerate(ids)}
            g._code_matrix = code_matrix
            for mid in ids:
                g.adj[mid] = []
        else:
            for mid, hv in codes.items():
                g.code[mid] = hv
                g.adj.setdefault(mid, [])
            ids = g._ids()
        for a, b in edges:                       # real links (bidirectional)
            if g._has_code(a) and g._has_code(b) and b not in g.adj[a]:
                g.adj[a].append(b)
                g.adj.setdefault(b, []).append(a)
        ids = g._ids()
        # Real links can form disconnected semantic islands. We pick one
        # landmark per island BEFORE adding ephemeral shortcuts, so the
        # right concept is selected first and only its neighborhood gets
        # navigated afterwards.
        seen: set[int] = set()
        for start in ids:
            if start in seen:
                continue
            component: list[int] = []
            stack = [start]
            seen.add(start)
            while stack:
                current = stack.pop()
                component.append(current)
                for neighbor in g.adj.get(current, ()):
                    if neighbor not in seen:
                        seen.add(neighbor)
                        stack.append(neighbor)
            g.entries.append(max(component, key=lambda x: len(g.adj[x])))
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
        # In a KNN component that already covers most of the map within two
        # hops, random shortcuts only widen the frontier. If there are
        # communities, chains or islands, small-world is kept: there they do
        # add missing routes.
        if (adaptive_shortcuts and g.component_count == 1
                and g.mean_base_degree >= ADAPTIVE_MIN_MEAN_DEGREE
                and g.two_hop_coverage >= ADAPTIVE_MIN_TWO_HOP_COVERAGE):
            g.effective_shortcuts = 0
        else:
            g.effective_shortcuts = shortcuts
        for mid in ids:                          # small-world shortcuts (internal index)
            for _ in range(g.effective_shortcuts):
                r = g._rnd.choice(ids)
                if r != mid and r not in g.adj[mid]:
                    g.adj[mid].append(r)
                    g.adj[r].append(mid)
        if ids:                                  # entry = the most connected node
            g.entry = max(ids, key=lambda x: len(g.adj[x]))
        g._refresh_entry_matrix()
        if compact:
            g._compact()
        return g

    # --- building ---------------------------------------------------------
    def add(self, mid: int, hv: np.ndarray) -> None:
        """Inserts a memory by NAVIGATING the graph to find its neighbors
        (no scanning). Links it to its M closest ones + `shortcuts` random
        long-range shortcuts."""
        if self._code_positions is not None:
            raise RuntimeError("a compact resident index doesn't support direct insertion")
        if mid in self.code:
            return
        self.code[mid] = hv
        if not self.adj:                        # first node
            self.adj[mid] = []
            self.entry = mid
            self.entries = [mid]
            self._refresh_entry_matrix()
            return
        self.adj[mid] = []
        _, closest = self._search(hv, self.ef, exclude=mid)
        for j in closest[:self.M]:              # strong, bidirectional links
            self._connect(mid, j)
        existing = [x for x in self.code if x != mid]
        for _ in range(self.shortcuts):         # weak long-range shortcuts
            self._connect(mid, self._rnd.choice(existing))
        # entry = the most connected node (a cheap highway to enter through)
        if self.entry is None or len(self.adj[mid]) > len(self.adj.get(self.entry, [])):
            self.entry = mid
        self.entries = [self.entry] if self.entry is not None else []
        self._refresh_entry_matrix()

    def _refresh_entry_matrix(self) -> None:
        """Precomputes contiguous landmarks to compare concepts in NumPy."""
        if len(self.entries) < 8:
            self._entry_matrix = None
            return
        self._entry_matrix = np.stack([self._code_of(mid) for mid in self.entries])

    @property
    def is_compact(self) -> bool:
        """The finished map uses contiguous arrays instead of per-edge objects."""
        return self._neighbor_offsets is not None

    @property
    def edge_count(self) -> int:
        """Number of directed edges in the map, whether dynamic or compact."""
        if self._neighbor_offsets is not None:
            return int(self._neighbor_offsets[-1])
        return sum(len(neighbors) for neighbors in self.adj.values())

    def _compact(self) -> None:
        """Converts the static adjacency to CSR to reduce resident RAM."""
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
            current = self.adj.pop(mid, ())
            nxt = cursor + len(current)
            neighbors[cursor:nxt] = current
            cursor = nxt
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

    def _connect(self, a: int, b: int) -> None:
        if a == b or b in self.adj[a]:
            return
        self.adj[a].append(b)
        self.adj.setdefault(b, []).append(a)
        for n in (a, b):                        # degree pruning
            if len(self.adj[n]) > self.max_degree:
                base = self._code_of(n)
                ordered = sorted(self.adj[n], key=lambda x: _hamming(base, self._code_of(x)))
                self.adj[n] = ordered[:self.max_degree]

    # --- search -------------------------------------------------------------
    def _search(self, qhv: np.ndarray, ef: int, exclude: int | None = None,
                entries: list[int] | None = None) -> tuple[int, list[int]]:
        """Beam search: starts from the entries and jumps to neighbors
        closer to q until nothing improves. Returns (nodes_visited, ids
        ordered by closeness)."""
        vis: set[int] = set()
        cand: list[tuple[int, int]] = []        # min-heap by distance (frontier)
        res: list[tuple[int, int]] = []         # max-heap (negated) with the best ef
        distances: dict[int, int] = {}
        if entries is None:
            landmarks = self.entries or (
                [self.entry] if self.entry is not None else []
            )
            # Comparing one representative per component costs C (concepts),
            # not N (memories). We enter through the four semantically
            # closest islands.
            if self._entry_matrix is not None and len(landmarks) == len(self.entries):
                batch = _popcount_rows(np.bitwise_xor(self._entry_matrix, qhv))
                for e, distance in zip(self.entries, batch, strict=True):
                    if e != exclude:
                        distances[e] = int(distance)
                        vis.add(e)
            else:
                for e in landmarks:
                    if e == exclude or not self._has_code(e):
                        continue
                    distances[e] = _hamming(qhv, self._code_of(e))
                    vis.add(e)
            entries = [
                e for e, _ in sorted(distances.items(), key=lambda item: item[1])[:4]
            ]
        for e in entries:
            if e is None or e == exclude or not self._has_code(e):
                continue
            d = distances.get(e)
            if d is None:
                d = _hamming(qhv, self._code_of(e))
            vis.add(e)
            heapq.heappush(cand, (d, e))
            heapq.heappush(res, (-d, e))
        while cand:
            d, c = heapq.heappop(cand)
            if res and d > -res[0][0] and len(res) >= ef:
                break                           # nothing left to explore improves the best
            for raw_nb in self._neighbors_of(c):
                nb = int(raw_nb)
                if nb in vis or nb == exclude:
                    continue
                vis.add(nb)
                dn = _hamming(qhv, self._code_of(nb))
                if len(res) < ef or dn < -res[0][0]:
                    heapq.heappush(cand, (dn, nb))
                    heapq.heappush(res, (-dn, nb))
                    if len(res) > ef:
                        heapq.heappop(res)
        ordered = [mid for _, mid in sorted((-x[0], x[1]) for x in res)]
        return len(vis), ordered

    def search_with_stats(self, qhv: np.ndarray, k: int = 5,
                          entries: list[int] | None = None,
                          ef: int | None = None) -> tuple[list[tuple[int, float]], int]:
        """Searches once and returns (results, nodes_visited).

        ``ef`` lets the caller trade off quality/cost for their number of
        candidates without repeating the walk just to measure it.
        """
        width = max(k, self.ef if ef is None else max(1, int(ef)))
        visited, ordered = self._search(qhv, width, entries=entries)
        out = []
        for mid in ordered[:k]:
            out.append((mid, 1.0 - _hamming(qhv, self._code_of(mid)) / D))
        return out, visited

    def search(self, qhv: np.ndarray, k: int = 5,
               entries: list[int] | None = None) -> list[tuple[int, float]]:
        """The k memories most similar to q, NAVIGATING the graph."""
        return self.search_with_stats(qhv, k=k, entries=entries)[0]

    def visited_for(self, qhv: np.ndarray) -> int:
        """How many nodes a search touches (to measure sublinearity)."""
        vis, _ = self._search(qhv, self.ef)
        return vis
