"""
Memoria COMPOSICIONAL con roles (VSA de verdad) — el diferenciador.

Un embedding denso mete "el perro muerde al hombre" y su inverso casi en el mismo
punto. Aquí no: codificamos un hecho ligando cada valor a su ROL con el álgebra VSA

    record = bundle( bind(SUJETO, perro), bind(PREDICADO, muerde), bind(OBJETO, hombre) )

y luego podemos PREGUNTAR POR ROL mediante *unbinding* (el bind XOR es su propia
inversa) + limpieza contra la memoria de ítems:

    bind(record, OBJETO) ≈ hombre   →   "¿a quién muerde?" -> hombre
    bind(record, SUJETO) ≈ perro    →   "¿quién muerde?"  -> perro

Eso es una consulta estructural que BM25, SimHash o un embedding no ofrecen. Corre
en CPU, sin GPU, y es 100% original.
"""

import json

import numpy as np

from .encoder import encode_text
from .vsa import bind, bundle, from_blob, random_hv, similarity, similarity_batch, stack_hvs

# Hipervectores de rol, fijos y deterministas (semillas propias, reproducibles).
ROLES = {
    "subject":   random_hv(70_001),
    "predicate": random_hv(70_002),
    "object":    random_hv(70_003),
    "time":      random_hv(70_004),
    "source":    random_hv(70_005),
}


class ItemMemory:
    """Memoria de ítems (cleanup memory): conoce los valores posibles y limpia el
    resultado ruidoso de un unbinding hacia el valor conocido más cercano."""

    def __init__(self):
        self._items: dict[str, np.ndarray] = {}

    def add(self, value: str) -> np.ndarray:
        hv = self._items.get(value)
        if hv is None:
            hv = encode_text(value)
            self._items[value] = hv
        return hv

    def cleanup(self, approx: np.ndarray, top: int = 1):
        """Devuelve [(valor, similitud)] de los ítems más cercanos al vector ruidoso."""
        scored = [(v, similarity(approx, hv)) for v, hv in self._items.items()]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top]

    def __len__(self):
        return len(self._items)


def encode_fact(fields: dict[str, str], item_memory: ItemMemory | None = None) -> np.ndarray:
    """Codifica un hecho {rol: valor} como un único hipervector role-filler.
    Registra los valores en la memoria de ítems (para poder consultarlos luego)."""
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
    """Pregunta por un rol: unbinding + limpieza. Devuelve [(valor, similitud)]."""
    if role not in ROLES:
        raise ValueError(f"rol desconocido: {role}")
    approx = bind(record, ROLES[role])       # deshace el ligado de ese rol
    return item_memory.cleanup(approx, top=top)


# Umbrales de abstención de ask_role (evitar responder cuando no se sabe).
ASK_MIN_MATCH = 0.56     # el hecho debe encajar de verdad con lo conocido
ASK_MIN_ANSWER = 0.56    # el unbinding debe recuperar un valor con claridad
ASK_MIN_MARGIN = 0.06    # y con margen sobre el segundo candidato


class RoleMemory:
    """Memoria de HECHOS estructurados, persistente y aislada por namespace. Guarda
    hechos {rol: valor} como hipervectores role-filler y responde consultas por rol
    conociendo otros campos ("¿quién MUERDE al HOMBRE?" -> se busca el hecho que
    encaja con {predicate:muerde, object:hombre} y se des-liga el sujeto)."""

    def __init__(self, store):
        self.store = store
        self.im = ItemMemory()
        self._ids: list[int] = []
        self._fields: list[dict] = []
        self._hvs: list[np.ndarray] = []
        self._valid_to: list = []                    # None = vigente
        for row in self.store.all_facts():           # calentar desde lo guardado
            fields = json.loads(row["fields"])
            for v in fields.values():
                self.im.add(v)
            self._ids.append(row["id"])
            self._fields.append(fields)
            self._hvs.append(from_blob(row["hv"]))
            self._valid_to.append(row["valid_to"])

    def _contradice(self, nuevo: dict) -> list[int]:
        """Hechos VIGENTES con el mismo sujeto y predicado pero distinto objeto: no
        son un error, son la versión anterior de la verdad."""
        s, p, o = nuevo.get("subject"), nuevo.get("predicate"), nuevo.get("object")
        if not (s and p and o):
            return []
        fuera = []
        for i, f in enumerate(self._fields):
            if self._valid_to[i] is None and f.get("subject") == s \
               and f.get("predicate") == p and f.get("object") != o:
                fuera.append(i)
        return fuera

    def remember_fact(self, fields: dict, importance: float = 0.6,
                      confidence: float = 0.6, source: str | None = None) -> dict:
        """Guarda un hecho estructurado Y su 'sombra textual' en la memoria viva, para
        que participe del ciclo completo (recall, muse, consolidación, olvido)."""
        clean = {r: str(v).strip() for r, v in fields.items()
                 if r in ROLES and str(v).strip()}
        if len(clean) < 2:
            return {"stored": False, "reason": "un hecho necesita al menos 2 campos"}
        hv = encode_fact(clean, self.im)
        # texto natural del hecho, en orden de rol (sujeto predicado objeto tiempo fuente)
        texto = " ".join(clean[r] for r in ROLES if r in clean)
        # ¿actualiza a un hecho vigente? (mismo sujeto+predicado, otro objeto)
        previos = self._contradice(clean)
        with self.store.transaction():                       # hecho + sombra, atómico
            supersede_id = self._ids[previos[0]] if previos else None
            fid = self.store.add_fact(json.dumps(clean, ensure_ascii=False), hv,
                                      source=source, supersedes=supersede_id)
            mem_id = self.store.add(texto, encode_text(texto), 1.0, importance,
                                    confidence, fact_id=fid)
            for i in previos:                    # la verdad anterior se CIERRA, no se borra
                self.store.close_fact(self._ids[i])
                self._valid_to[i] = True         # marcado local: ya no vigente
        self._ids.append(fid); self._fields.append(clean)
        self._hvs.append(hv); self._valid_to.append(None)
        res = {"stored": True, "id": fid, "memory_id": mem_id, "text": texto,
               "fields": clean}
        if previos:
            res["supersedes"] = [self._ids[i] for i in previos]
            res["nota"] = ("la versión anterior queda como HISTORIA (vigencia cerrada), "
                           "no se borra: puedes consultarla con `at`")
        return res

    def ask_role(self, role: str, known: dict, top: int = 1,
                 at: float | None = None) -> dict:
        """Devuelve el valor del 'role' del hecho que mejor encaja con 'known'. Se
        ABSTIENE (answer=None, unknown=True) si no hay un hecho que encaje de verdad o
        si el unbinding no recupera un valor con claridad y margen."""
        if role not in ROLES:
            return {"error": f"rol desconocido: {role}"}
        known = {r: str(v).strip() for r, v in known.items()
                 if r in ROLES and str(v).strip() and r != role}
        if not known or not self._hvs:
            return {"answer": None, "unknown": True,
                    "reason": "indica al menos un campo conocido y que haya hechos"}
        # consulta parcial: campos conocidos ligados a su rol. Se codifican SIN añadir
        # nada a la memoria de ítems (no contaminar el cleanup con términos ajenos).
        q = bundle([bind(ROLES[r], encode_text(v)) for r, v in known.items()])
        sims = similarity_batch(q, stack_hvs([h.tobytes() for h in self._hvs]))
        # VIGENCIA: por defecto solo lo cierto AHORA; con `at`, lo cierto entonces.
        if at is not None:
            validos = {r["id"] for r in self.store.all_facts(at=at)}
        else:
            validos = {r["id"] for r in self.store.all_facts(only_current=True)}
        olvidados = self.store.dormant_fact_ids()   # su sombra textual se olvidó
        sims = np.array([-1.0 if (fid not in validos or fid in olvidados) else s
                         for fid, s in zip(self._ids, sims)])
        j = int(np.argmax(sims))
        match = float(sims[j])
        # abstención 1: ningún hecho encaja de verdad con lo conocido
        if match < ASK_MIN_MATCH:
            return {"role": role, "answer": None, "unknown": True,
                    "reason": "ningún hecho encaja con lo indicado",
                    "match_score": round(match, 3)}
        cand = query_role(self._hvs[j], role, self.im, top=2)
        conf = cand[0][1] if cand else 0.0
        margen = (cand[0][1] - cand[1][1]) if len(cand) > 1 else conf
        # abstención 2: el unbinding no recupera un valor claro y con margen
        if conf < ASK_MIN_ANSWER or margen < ASK_MIN_MARGIN:
            return {"role": role, "answer": None, "unknown": True,
                    "reason": "el rol no se recupera con claridad",
                    "match_score": round(match, 3), "confidence": round(conf, 3)}
        return {"role": role, "answer": cand[0][0], "confidence": round(conf, 3),
                "matched_fact": self._fields[j], "match_score": round(match, 3)}
