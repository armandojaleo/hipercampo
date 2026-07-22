"""
Servidor MCP de hipercampo.

Expone la memoria como herramientas que Claude puede llamar:

    hc_remember   guarda algo (solo si es novedoso)
    hc_recall     recupera por similitud + propagación de activación
    hc_consolidate corre la fase de 'sueño' (fusiona episodios en semántico)
    hc_forget     poda lo débil y olvidado (con dry_run para ensayar)
    hc_stats      estado de la memoria

Se comunica por stdio (el estándar de MCP), así que funciona igual lanzado en
local (`python -m hipercampo.server`) o dentro de Docker (`docker run -i ...`).
"""

import os
import sys

from mcp.server.fastmcp import FastMCP

from . import encoder
from .config import db_path
from .memory import Hipercampo

# Modo semántico opcional (para sinónimos): HIPERCAMPO_SEMANTIC=1.
# Requiere `pip install "hipercampo[semantic]"`. Si falta, seguimos en léxico.
if os.environ.get("HIPERCAMPO_SEMANTIC") == "1":
    ok = encoder.enable_semantic(os.environ.get("HIPERCAMPO_SEMANTIC_MODEL") or None)
    print("hipercampo: modo semántico " + ("ACTIVO" if ok else
          "NO disponible (instala hipercampo[semantic]); sigo en léxico"),
          file=sys.stderr)

DB_PATH = db_path()
hc = Hipercampo(DB_PATH)
mcp = FastMCP("hipercampo")


@mcp.tool()
def hc_remember(text: str, importance: float = 0.5, confidence: float = 0.5) -> dict:
    """Guarda un recuerdo. Solo se graba si aporta información novedosa o sorprendente.
    Dos ejes independientes (0-1): importance = cuánto IMPORTA (>=0.8 lo protege del
    olvido); confidence = cuán FIABLE/cierto es (pesa en el ranking de recall; baja
    para rumores o datos sin confirmar). Si se parece a algo ya guardado, avisa por
    si deberías usar hc_update."""
    return hc.remember(text, importance, confidence)


@mcp.tool()
def hc_recall(query: str, k: int = 5) -> list:
    """Recupera los recuerdos relevantes para 'query'. Combina similitud directa
    con propagación de activación por asociaciones. Recordar refuerza."""
    return hc.recall(query, k)


@mcp.tool()
def hc_update(target: str, new_text: str, importance: float = 0.7) -> dict:
    """Actualiza un hecho que cambió. Busca el recuerdo que mejor case con 'target'
    (descríbelo con tus palabras), lo marca como superado y guarda 'new_text' como
    la versión vigente. Úsalo cuando algo CONTRADICE o ACTUALIZA lo que ya sabías
    (p. ej. una preferencia que cambió, un dato que se movió). El viejo no se borra:
    queda como historia pero deja de dominar la recuperación."""
    return hc.update(target, new_text, importance)


@mcp.tool()
def hc_consolidate() -> dict:
    """Fase de sueño: agrupa episodios parecidos, los funde en conocimiento
    semántico condensado y archiva los originales. Correr periódicamente."""
    return hc.consolidate()


@mcp.tool()
def hc_forget(dry_run: bool = True) -> dict:
    """Olvido activo: decae la fuerza por desuso y poda lo débil. Con dry_run=True
    solo informa qué se olvidaría, sin borrar. Pon dry_run=False para aplicar."""
    return hc.forget(dry_run)


@mcp.tool()
def hc_stats() -> dict:
    """Estado actual de la memoria (episódicos, semánticos, archivados)."""
    return hc.stats()


def main():
    mcp.run()


if __name__ == "__main__":
    main()
