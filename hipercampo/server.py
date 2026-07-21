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

from mcp.server.fastmcp import FastMCP

from .config import db_path
from .memory import Hipercampo

DB_PATH = db_path()
hc = Hipercampo(DB_PATH)
mcp = FastMCP("hipercampo")


@mcp.tool()
def hc_remember(text: str, importance: float = 0.5) -> dict:
    """Guarda un recuerdo. Solo se graba si aporta información novedosa;
    lo redundante refuerza el recuerdo ya existente. importance (0-1) protege
    del olvido: usa >=0.8 para lo que nunca debe perderse."""
    return hc.remember(text, importance)


@mcp.tool()
def hc_recall(query: str, k: int = 5) -> list:
    """Recupera los recuerdos relevantes para 'query'. Combina similitud directa
    con propagación de activación por asociaciones. Recordar refuerza."""
    return hc.recall(query, k)


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
