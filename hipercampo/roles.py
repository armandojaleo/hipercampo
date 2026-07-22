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
        for row in self.store.all_facts():           # calentar desde lo guardado
            fields = json.loads(row["fields"])
            for v in fields.values():
                self.im.add(v)
            self._ids.append(row["id"])
            self._fields.append(fields)
            self._hvs.append(from_blob(row["hv"]))

    def remember_fact(self, fields: dict) -> dict:
        clean = {r: str(v).strip() for r, v in fields.items()
                 if r in ROLES and str(v).strip()}
        if len(clean) < 2:
            return {"stored": False, "reason": "un hecho necesita al menos 2 campos"}
        hv = encode_fact(clean, self.im)
        fid = self.store.add_fact(json.dumps(clean, ensure_ascii=False), hv)
        self._ids.append(fid); self._fields.append(clean); self._hvs.append(hv)
        return {"stored": True, "id": fid, "fields": clean}

    def ask_role(self, role: str, known: dict, top: int = 1) -> dict:
        """Devuelve el valor del 'role' del hecho que mejor encaja con 'known'."""
        if role not in ROLES:
            return {"error": f"rol desconocido: {role}"}
        known = {r: str(v).strip() for r, v in known.items()
                 if r in ROLES and str(v).strip() and r != role}
        if not known or not self._hvs:
            return {"error": "indica al menos un campo conocido y que haya hechos"}
        # consulta parcial: los campos conocidos, ligados a sus roles
        q = bundle([bind(ROLES[r], self.im.add(v)) for r, v in known.items()])
        sims = similarity_batch(q, stack_hvs([h.tobytes() for h in self._hvs]))
        j = int(np.argmax(sims))
        record, fields = self._hvs[j], self._fields[j]
        respuesta = query_role(record, role, self.im, top=top)
        return {"role": role, "answer": respuesta[0][0] if respuesta else None,
                "confidence": round(respuesta[0][1], 3) if respuesta else 0.0,
                "matched_fact": fields, "match_score": round(float(sims[j]), 3)}
