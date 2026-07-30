"""hipercampo — memoria viva para agentes basada en hipervectores (VSA).

NÚCLEO EMBEBIBLE
----------------
El núcleo (VSA + almacén + el ciclo de memoria) NO depende de `mcp`: eso es solo un
transporte. `import hipercampo` no arrastra `mcp` — así cabe en un sistema embebido o
un robot (SBC con Linux) con solo `numpy`. La frontera está probada en
`tests/test_core_embebible.py`; romperla (meter `import mcp` en un módulo del núcleo)
hace fallar el CI.

    from hipercampo import Hipercampo
    hc = Hipercampo("memoria.db", namespace="robot")
    hc.remember("el pasillo B lleva al almacén", importance=0.7)
    hits = hc.recall("cómo llego al almacén")

API pública del núcleo (el ciclo completo, sin transporte de por medio):
    remember · recall · update · consolidate · forget · purge · sleep · dream ·
    muse · learn · remember_fact · ask_role · identity · unlearn · assist ·
    accept_bridge · reject_bridge · stats · health · close

Transportes (opcionales, encima del núcleo): `hipercampo.server` (MCP, requiere
`mcp`) y `hipercampo.cli` (línea de comandos).
"""

from .memory import Hipercampo

__all__ = ["Hipercampo"]

# Una sola fuente de verdad: la versión instalada (pyproject). Evita que el paquete
# declare una versión distinta de la publicada.
try:                                     # pragma: no cover
    from importlib.metadata import version
    __version__ = version("hipercampo")
except (ImportError, Exception):         # pragma: no cover
    __version__ = "0.0.0+unknown"
