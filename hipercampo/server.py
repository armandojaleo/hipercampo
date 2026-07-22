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
# Namespace = contexto/perfil/workspace. Aísla los recuerdos por proyecto o perfil
# dentro de la MISMA máquina (local-first; no es una frontera de seguridad entre
# clientes de un servidor). Se elige por entorno: un proceso por contexto.
NAMESPACE = os.environ.get("HIPERCAMPO_NAMESPACE", "default")
hc = Hipercampo(DB_PATH, namespace=NAMESPACE)
mcp = FastMCP("hipercampo")


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


@mcp.tool()
def hc_remember(text: str, importance: float = 0.5, confidence: float = 0.5) -> dict:
    """Guarda un recuerdo. Solo se graba si aporta información novedosa o sorprendente.
    Dos ejes independientes (0-1): importance = cuánto IMPORTA (>=0.8 lo protege del
    olvido); confidence = cuán FIABLE/cierto es (pesa en el ranking de recall; baja
    para rumores o datos sin confirmar). Si se parece a algo ya guardado, avisa por
    si deberías usar hc_update."""
    return hc.remember(text, _clip01(importance), _clip01(confidence))


@mcp.tool()
def hc_recall(query: str, k: int = 5, include_history: bool = False) -> list:
    """Recupera los recuerdos relevantes para 'query'. Combina similitud directa con
    propagación de activación. Puede devolver [] si nada es relevante (sabe abstenerse).
    include_history=True incluye recuerdos ya consolidados o superados (la historia)."""
    k = min(50, max(1, int(k)))
    return hc.recall(query, k, include_history=include_history)


@mcp.tool()
def hc_update(target: str = "", new_text: str = "", importance: float = 0.7,
              memory_id: int | None = None, confidence: float = 0.75) -> dict:
    """Actualiza un hecho que cambió. Indica el recuerdo a reemplazar por 'memory_id'
    (exacto, lo más seguro) o por 'target' (se busca el que mejor case). Si no hay un
    match fiable, NO pisa nada: guarda 'new_text' como recuerdo nuevo y lo avisa.
    Úsalo cuando algo CONTRADICE o ACTUALIZA lo que ya sabías. El viejo no se borra:
    queda como historia, demovido."""
    return hc.update(target, new_text, _clip01(importance), memory_id, _clip01(confidence))


@mcp.tool()
def hc_remember_fact(subject: str = "", predicate: str = "", object: str = "",
                     time: str = "", source: str = "") -> dict:
    """Guarda un HECHO estructurado (memoria composicional VSA). Rellena los campos
    que apliquen (al menos 2): subject/predicate/object y opcionalmente time/source.
    Luego podrás preguntar por un campo conociendo otros con hc_ask_role
    ("¿quién MUERDE al HOMBRE?"). Distingue estructura que un embedding difumina."""
    return hc.remember_fact({"subject": subject, "predicate": predicate,
                             "object": object, "time": time, "source": source})


@mcp.tool()
def hc_ask_role(role: str, subject: str = "", predicate: str = "", object: str = "",
                time: str = "", source: str = "") -> dict:
    """Pregunta por un CAMPO de un hecho conociendo otros. 'role' es el campo que
    quieres (subject/predicate/object/time/source); rellena los que SÍ sabes. Ej.:
    role='subject', predicate='muerde', object='hombre' -> '¿quién muerde al hombre?'."""
    return hc.ask_role(role, {"subject": subject, "predicate": predicate,
                              "object": object, "time": time, "source": source})


@mcp.tool()
def hc_consolidate() -> dict:
    """Fase de sueño: AGRUPA episodios parecidos en un recuerdo semántico y archiva
    los originales (reduce nodos activos; el texto se une, no se resume). Correr
    periódicamente."""
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
