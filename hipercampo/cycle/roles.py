"""
COMPOSITIONAL memory with roles (true VSA) — the differentiator.

A dense embedding places "the dog bites the man" and its inverse almost at
the same point. Not here: we encode a fact by binding each value to its ROLE
with VSA algebra

    record = bundle( bind(SUBJECT, dog), bind(PREDICATE, bites), bind(OBJECT, man) )

and then we can ASK BY ROLE via *unbinding* (bind XOR is its own inverse) +
cleanup against the item memory:

    bind(record, OBJECT) ~= man    ->   "who does it bite?" -> man
    bind(record, SUBJECT) ~= dog   ->   "who bites?"  -> dog

That's a structural query that BM25, SimHash or an embedding don't offer.
Runs on CPU, no GPU, and is 100% original.
"""

import json

import numpy as np

from ..core.encoder import encode_text
from ..core.vsa import bind, bundle, from_blob, random_hv, similarity_batch, stack_hvs

# Role hypervectors, fixed and deterministic (own seeds, reproducible).
ROLES = {
    "subject":   random_hv(70_001),
    "predicate": random_hv(70_002),
    "object":    random_hv(70_003),
    "time":      random_hv(70_004),
    "source":    random_hv(70_005),
}


class ItemMemory:
    """Item memory (cleanup memory): knows the possible values and cleans
    the noisy result of an unbinding towards the nearest known value."""

    def __init__(self):
        self._items: dict[str, np.ndarray] = {}
        self._matrix: np.ndarray | None = None    # stacked cache, invalidated on add
        self._values: list[str] = []

    def add(self, value: str) -> np.ndarray:
        hv = self._items.get(value)
        if hv is None:
            hv = encode_text(value)
            self._items[value] = hv
            self._matrix = None                   # the item vocabulary changed
        return hv

    def _stacked(self) -> tuple[list[str], np.ndarray]:
        """The items as (values, matrix), restacked only if they changed."""
        if self._matrix is None:
            self._values = list(self._items)
            self._matrix = stack_hvs([self._items[v].tobytes() for v in self._values])
        return self._values, self._matrix

    def cleanup(self, approx: np.ndarray, top: int = 1):
        """Returns [(value, similarity)] of the items closest to the noisy
        vector.

        Vectorized comparison against a cached matrix: cleanup is the step
        that turns a noisy unbinding into an answer, and it's called per
        query over the ENTIRE known item vocabulary."""
        values, matrix = self._stacked()
        if not values:
            return []
        sims = similarity_batch(approx, matrix)
        # STABLE order, like the Python `sort` it replaces: when two items
        # are equally similar, the one registered first wins, and that
        # tie-break decides the margin ask_role uses to abstain or not.
        best = np.argsort(-sims, kind="stable")[:max(1, int(top))]
        return [(values[int(i)], float(sims[int(i)])) for i in best]

    def __len__(self):
        return len(self._items)


def encode_fact(fields: dict[str, str], item_memory: ItemMemory | None = None) -> np.ndarray:
    """Encodes a fact {role: value} as a single role-filler hypervector.
    Registers the values in the item memory (so they can be queried later)."""
    parts = []
    for role, value in fields.items():
        if role not in ROLES or not value:
            continue
        fh = item_memory.add(value) if item_memory is not None else encode_text(value)
        parts.append(bind(ROLES[role], fh))
    if not parts:
        return random_hv(0)
    return bundle(parts)


def query_role(record: np.ndarray, role: str, item_memory: ItemMemory, top: int = 1):
    """Asks for a role: unbinding + cleanup. Returns [(value, similarity)]."""
    if role not in ROLES:
        raise ValueError(f"unknown role: {role}")
    approx = bind(record, ROLES[role])       # undoes that role's binding
    return item_memory.cleanup(approx, top=top)


# ask_role abstention thresholds (avoid answering when it isn't known).
ASK_MIN_MATCH = 0.56     # the fact must genuinely fit what's known
ASK_MIN_ANSWER = 0.56    # the unbinding must recover a value clearly
ASK_MIN_MARGIN = 0.06    # and with a margin over the second candidate


class RoleMemory:
    """Memory of structured FACTS, persistent and isolated by namespace.
    Stores facts {role: value} as role-filler hypervectors and answers
    queries by role given other fields ("who BITES the MAN?" -> looks up the
    fact matching {predicate:bites, object:man} and unbinds the subject)."""

    def __init__(self, store):
        self.store = store
        self.im = ItemMemory()
        self._ids: list[int] = []
        self._fields: list[dict] = []
        self._hvs: list[np.ndarray] = []
        self._valid_to: list = []                    # None = current
        self._matrix: np.ndarray | None = None       # cache of stacked _hvs
        for row in self.store.all_facts():           # warm up from what's stored
            fields = json.loads(row["fields"])
            for v in fields.values():
                self.im.add(v)
            self._ids.append(row["id"])
            self._fields.append(fields)
            self._hvs.append(from_blob(row["hv"]))
            self._valid_to.append(row["valid_to"])

    def _contradicts(self, new: dict) -> list[int]:
        """CURRENT facts with the same subject and predicate but a different
        object: not an error, they're the previous version of the truth."""
        s, p, o = new.get("subject"), new.get("predicate"), new.get("object")
        if not (s and p and o):
            return []
        out = []
        for i, f in enumerate(self._fields):
            if self._valid_to[i] is None and f.get("subject") == s \
               and f.get("predicate") == p and f.get("object") != o:
                out.append(i)
        return out

    def remember_fact(self, fields: dict, importance: float = 0.6,
                      confidence: float = 0.6, source: str | None = None) -> dict:
        """Stores a structured fact AND its 'text shadow' in the live
        memory, so it takes part in the full cycle (recall, muse,
        consolidation, forgetting)."""
        clean = {r: str(v).strip() for r, v in fields.items()
                 if r in ROLES and str(v).strip()}
        if len(clean) < 2:
            return {"stored": False, "reason": "a fact needs at least 2 fields"}
        hv = encode_fact(clean, self.im)
        # natural-language text of the fact, in role order (subject predicate object time source)
        text = " ".join(clean[r] for r in ROLES if r in clean)
        # does it update a current fact? (same subject+predicate, different object)
        previous = self._contradicts(clean)
        with self.store.transaction():                       # fact + shadow, atomic
            supersede_id = self._ids[previous[0]] if previous else None
            fid = self.store.add_fact(json.dumps(clean, ensure_ascii=False), hv,
                                      source=source, supersedes=supersede_id)
            mem_id = self.store.add(text, encode_text(text), 1.0, importance,
                                    confidence, fact_id=fid)
            for i in previous:                    # the previous truth is CLOSED, not deleted
                self.store.close_fact(self._ids[i])
                self._valid_to[i] = True         # marked locally: no longer current
        self._ids.append(fid); self._fields.append(clean)
        self._hvs.append(hv); self._valid_to.append(None)
        self._matrix = None                          # one more fact to stack
        res = {"stored": True, "id": fid, "memory_id": mem_id, "text": text,
               "fields": clean}
        if previous:
            res["supersedes"] = [self._ids[i] for i in previous]
            res["note"] = ("the previous version stays as HISTORY (closed validity), "
                           "not deleted: query it with `at`")
        return res

    def _facts_matrix(self) -> np.ndarray:
        """The stacked hypervectors of the facts, rebuilt only if they
        changed. Used to re-copy ALL of them (one `tobytes` per fact) on
        every `ask_role`."""
        if self._matrix is None:
            self._matrix = stack_hvs([h.tobytes() for h in self._hvs])
        return self._matrix

    def ask_role(self, role: str, known: dict, top: int = 1,
                 at: float | None = None) -> dict:
        """Returns the value of 'role' for the fact that best fits 'known'.
        ABSTAINS (answer=None, unknown=True) if no fact genuinely fits, or
        if the unbinding doesn't recover a value clearly and with margin."""
        if role not in ROLES:
            return {"error": f"unknown role: {role}"}
        known = {r: str(v).strip() for r, v in known.items()
                 if r in ROLES and str(v).strip() and r != role}
        if not known or not self._hvs:
            return {"answer": None, "unknown": True,
                    "reason": "provide at least one known field, and have some facts stored"}
        # partial query: known fields bound to their role. Encoded WITHOUT
        # adding anything to the item memory (don't pollute cleanup with
        # unrelated terms).
        q = bundle([bind(ROLES[r], encode_text(v)) for r, v in known.items()])
        sims = similarity_batch(q, self._facts_matrix())
        # VALIDITY: by default only what's true NOW; with `at`, what was true then.
        if at is not None:
            valid = {r["id"] for r in self.store.all_facts(at=at)}
        else:
            valid = {r["id"] for r in self.store.all_facts(only_current=True)}
        forgotten = self.store.dormant_fact_ids()   # its text shadow was forgotten
        sims = np.array([-1.0 if (fid not in valid or fid in forgotten) else s
                         for fid, s in zip(self._ids, sims, strict=False)])
        j = int(np.argmax(sims))
        match = float(sims[j])
        # abstention 1: no fact genuinely fits what's known
        if match < ASK_MIN_MATCH:
            return {"role": role, "answer": None, "unknown": True,
                    "reason": "no fact fits what was given",
                    "match_score": round(match, 3)}
        cand = query_role(self._hvs[j], role, self.im, top=2)
        conf = cand[0][1] if cand else 0.0
        margin = (cand[0][1] - cand[1][1]) if len(cand) > 1 else conf
        # abstention 2: the unbinding doesn't recover a clear value with margin
        if conf < ASK_MIN_ANSWER or margin < ASK_MIN_MARGIN:
            return {"role": role, "answer": None, "unknown": True,
                    "reason": "the role isn't recovered clearly",
                    "match_score": round(match, 3), "confidence": round(conf, 3)}
        return {"role": role, "answer": cand[0][0], "confidence": round(conf, 3),
                "matched_fact": self._fields[j], "match_score": round(match, 3)}
