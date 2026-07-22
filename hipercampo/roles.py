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

import numpy as np

from .encoder import encode_text
from .vsa import bind, bundle, random_hv, similarity

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
