"""
Servidor MCP de hipercampo.

Expone la memoria como herramientas que Claude puede llamar. Se comunica por
stdio (el estándar de MCP), así que funciona igual lanzado en local
(`python -m hipercampo.server`) o dentro de Docker (`docker run -i ...`).

COSTE: las descripciones de las herramientas viajan en CADA petición de la
sesión. No es un detalle estético: ocupan ventana de contexto aunque nunca uses
la memoria. Por eso se escriben CORTAS —lo justo para que Claude elija bien— y
por eso, por defecto, solo se ANUNCIAN las seis de uso diario: las demás se
activan en caliente con `hc_tools` cuando de verdad hacen falta.
Mídelo con `python scripts/tokens.py` antes de alargar una descripción.
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

# Superficie expuesta. El coste fijo de anunciar 18 herramientas se paga en CADA
# petición, se usen o no. Por defecto ("auto") solo se anuncian las de uso diario,
# con la descripción mínima que basta para elegir bien; las demás no desaparecen:
# se activan EN CALIENTE con `hc_tools`, que las registra y avisa al cliente
# (notificación MCP tools/list_changed).
#
# Recortar la descripción no es lo mismo que recortar un recuerdo: aquí no se
# pierde información que nadie pueda recuperar —la herramienta sigue ahí, con su
# ficha completa a un `hc_tools` de distancia—, mientras que un recuerdo cortado
# se lee como completo y engaña. Por eso comprimir aquí sí, y ahí no.
CORE = {"hc_remember", "hc_recall", "hc_update", "hc_learn", "hc_assist", "hc_stats"}
MODO = (os.environ.get("HIPERCAMPO_TOOLS") or "auto").strip().lower()
TODAS = MODO in ("all", "todas", "full", "completo")

# Catálogo de lo que NO se anuncia de entrada: nombre -> (función, para qué sirve).
# El resumen es de una línea a propósito: se paga solo cuando alguien pregunta.
_CATALOGO: dict[str, tuple] = {}


def tool(fn):
    """Anuncia la herramienta si es del núcleo (o si se pidieron todas); si no, la
    deja en el catálogo, lista para activarse a petición."""
    if TODAS or fn.__name__ in CORE:
        return mcp.tool()(fn)
    resumen = (fn.__doc__ or "").strip().split("\n")[0]
    _CATALOGO[fn.__name__] = (fn, resumen)
    return fn


def _clip01(x: float) -> float:
    return min(1.0, max(0.0, float(x)))


@tool
def hc_remember(text: str, importance: float = 0.5, confidence: float = 0.5) -> dict:
    """Guarda algo. Solo graba lo novedoso. importance>=0.8 protege del olvido;
    confidence pesa en el ranking."""
    return hc.remember(text, _clip01(importance), _clip01(confidence))


@tool
def hc_recall(query: str, k: int = 5, include_history: bool = False) -> list:
    """Recupera lo relevante. Devuelve [] si no sabe nada (sabe abstenerse)."""
    k = min(50, max(1, int(k)))
    return hc.recall(query, k, include_history=include_history)


@tool
def hc_update(target: str = "", new_text: str = "", importance: float = 0.7,
              memory_id: int | None = None, confidence: float = 0.75) -> dict:
    """Actualiza un hecho que cambió. Identifícalo por memory_id (mejor) o target.
    El viejo no se borra: queda como historia."""
    return hc.update(target, new_text, _clip01(importance), memory_id, _clip01(confidence))


@tool
def hc_remember_fact(subject: str = "", predicate: str = "", object: str = "",
                     time: str = "", source: str = "") -> dict:
    """Guarda un HECHO estructurado (VSA composicional). Rellena al menos 2 campos.
    Si actualiza uno vigente (mismo sujeto y predicado), el anterior se cierra y
    queda como historia."""
    return hc.remember_fact({"subject": subject, "predicate": predicate,
                             "object": object, "time": time, "source": source},
                            source=source or None)


@tool
def hc_ask_role(role: str, subject: str = "", predicate: str = "", object: str = "",
                time: str = "", source: str = "", days_ago: float = 0.0) -> dict:
    """Pregunta un CAMPO de un hecho sabiendo otros. 'role' es el que quieres;
    rellena los que sabes. Ej.: role='subject', predicate='muerde', object='hombre'.
    Responde lo vigente; days_ago>0 pregunta qué era cierto entonces. Se abstiene
    si no lo sabe."""
    import time as _t
    at = (_t.time() - days_ago * 86400) if days_ago else None
    return hc.ask_role(role, {"subject": subject, "predicate": predicate,
                              "object": object, "time": time, "source": source}, at=at)


@tool
def hc_muse(query: str, k: int = 3) -> list:
    """Recuerdo INSPIRADOR: conexiones indirectas y recuerdos latentes que pueden
    resurgir. Para brainstorming y analogías, no para buscar un dato (eso es
    hc_recall)."""
    return hc.muse(query, k)


@tool
def hc_dream(max_bridges: int = 5, dry_run: bool = True) -> dict:
    """Propone PUENTES entre recuerdos con un asociado común. Por defecto solo
    propone: las hipótesis no contaminan la memoria. Con dry_run=False quedan como
    enlaces 'proposed' que aún no propagan; confírmalos con hc_accept_bridge."""
    return hc.dream(max_bridges, dry_run)


@tool
def hc_accept_bridge(a_id: int, b_id: int) -> dict:
    """Confirma un puente propuesto: pasa a asociación real y ya propaga."""
    return hc.accept_bridge(int(a_id), int(b_id))


@tool
def hc_reject_bridge(a_id: int, b_id: int) -> dict:
    """Descarta un puente propuesto: no se repetirá ni propagará."""
    return hc.reject_bridge(int(a_id), int(b_id))


@tool
def hc_assist(message: str, k: int = 3) -> dict:
    """¿Qué toca en este turno? Decide solo: recordar, inspirar, sugerir guardar o
    callarse. Solo lee; escribir lo recomienda."""
    return hc.assist(message, k)


@tool
def hc_sleep() -> dict:
    """Ciclo de sueño completo: consolida, adormece y propone puentes. Se hace solo
    cada N escrituras; esto es para pedirlo."""
    return hc.sleep()


@tool
def hc_consolidate() -> dict:
    """Agrupa episodios parecidos en un recuerdo semántico y archiva los originales."""
    return hc.consolidate()


@tool
def hc_forget(dry_run: bool = True) -> dict:
    """Olvido activo: decae por desuso y poda lo débil. dry_run=True solo informa."""
    return hc.forget(dry_run)


@tool
def hc_learn(text: str, tipo: str = "leccion") -> dict:
    """Aprender cómo TRABAJAR (no sobre el mundo): úsalo cuando te corrijan, cuando
    un error enseñe algo o al cerrar una decisión. tipo: regla|leccion|decision|
    preferencia. No caduca."""
    return hc.learn(text, tipo)


@tool
def hc_identity(k: int = 40) -> dict:
    """QUIÉN SOY TRABAJANDO: reglas, lecciones y decisiones de sesiones anteriores.
    Léelo al empezar para no repetir errores. Se comparte entre proyectos."""
    return hc.identity(k)


@tool
def hc_unlearn(memory_id: int) -> dict:
    """Desaprender una regla que dejó de valer. Se borra de verdad."""
    return hc.unlearn(int(memory_id))


@tool
def hc_health(full: bool = False) -> dict:
    """¿Está sana la memoria? Integridad, esquema, lectura y escritura real.
    full=True hace un integrity_check completo (más lento)."""
    return hc.health(full)


@tool
def hc_stats() -> dict:
    """Estado de la memoria: cuánto recuerda, dónde y qué tokens ha gastado."""
    return hc.stats()


# --- puerta a lo que no se anuncia de entrada -------------------------------

_ACTIVADAS: set[str] = set()


@mcp.tool()
async def hc_tools(name: str = "", args: dict | None = None) -> dict:
    """Herramientas avanzadas, bajo demanda. Sin argumentos, lista las que hay
    (sueño, puentes, hechos por roles, consolidar, salud, identidad…). Con 'name'
    la activa y la EJECUTA con 'args' en la misma llamada."""
    if not name:
        return {"disponibles": {n: r for n, (_, r) in _CATALOGO.items()},
                "como": "hc_tools(name='hc_dream', args={'max_bridges': 3})",
                "activas_ya": sorted(_ACTIVADAS)}

    if name not in _CATALOGO:
        return {"error": f"no existe o ya está activa: {name}",
                "disponibles": sorted(_CATALOGO)}

    fn, _ = _CATALOGO[name]
    if name not in _ACTIVADAS:
        # Se registra de verdad, para que a partir de ahora el cliente la vea como
        # una herramienta más y pueda llamarla sin pasar por aquí.
        mcp.add_tool(fn)
        _ACTIVADAS.add(name)
        try:
            ctx = mcp.get_context()
            await ctx.session.send_tool_list_changed()
        except Exception as e:                    # cliente que no soporta la
            print(f"hipercampo: sin aviso de tools/list_changed ({e})",
                  file=sys.stderr)                # notificación: no es fatal

    # Y se ejecuta ya. Es deliberado: si el cliente ignora la notificación y no
    # refresca su lista, la herramienta seguiría siendo inalcanzable. Ejecutándola
    # aquí, la capacidad está garantizada aunque el aviso no llegue.
    try:
        salida = fn(**(args or {}))
    except TypeError as e:
        return {"error": f"argumentos inválidos para {name}: {e}"}
    return {"activada": name, "resultado": salida}


async def _run_stdio_avisando():
    """Igual que mcp.run(), pero declarando que la lista de herramientas PUEDE
    cambiar. FastMCP lo anuncia como `listChanged: false` por defecto, y un cliente
    que lee eso tiene todo el derecho a ignorar el aviso y quedarse con la lista
    vieja: la activación en caliente no llegaría a verse nunca."""
    from mcp.server.lowlevel.server import NotificationOptions
    from mcp.server.stdio import stdio_server

    srv = mcp._mcp_server
    opciones = srv.create_initialization_options(
        NotificationOptions(tools_changed=True))
    async with stdio_server() as (lectura, escritura):
        await srv.run(lectura, escritura, opciones)


def main():
    # Con todas las herramientas anunciadas no hay nada que activar, así que se usa
    # el camino estándar. Y si la librería cambia por dentro, se cae con gracia al
    # comportamiento de siempre: perder el aviso es un incordio, no arrancar es un fallo.
    if not TODAS:
        try:
            import anyio
            anyio.run(_run_stdio_avisando)
            return
        except Exception as e:
            print(f"hipercampo: sin capacidad tools/list_changed ({e}); "
                  "sigo en modo estándar", file=sys.stderr)
    mcp.run()


if __name__ == "__main__":
    main()
