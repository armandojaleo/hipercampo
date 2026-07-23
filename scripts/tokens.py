"""
¿Cuántos tokens cuesta hipercampo? Medirlo, no suponerlo.

Una memoria que ocupa media ventana de contexto no ayuda: estorba. Este script
mide las DOS fuentes de coste, que son muy distintas entre sí:

  1. Las descripciones de las herramientas MCP, que viajan en CADA petición de la
     sesión. Es un coste fijo y permanente: ocupa ventana aunque nunca uses la
     memoria. Suele ser el más caro y el más invisible.
  2. La inyección del hook, que se paga solo en los turnos que disparan.

Uso:
    python scripts/tokens.py              # mide con la BD real
    python scripts/tokens.py --json       # salida para comparar antes/después
"""

import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipercampo.budget import es_estimacion, estimate_tokens  # noqa: E402

# Prompts representativos de una sesión real: unos deben disparar la memoria y
# otros NO. Los que no disparan son tan importantes como los que sí: si la
# memoria habla cuando nadie le ha preguntado, el coste es puro desperdicio.
PROMPTS = [
    ("pregunta con contexto", "¿cómo se comparten las listas en el proyecto?", True),
    ("pregunta genérica", "¿qué hago ahora?", False),
    ("afirmación trivial", "mañana compraré pan", False),
    ("orden técnica corta", "arregla el bug del botón", False),
    ("saludo", "buenas", False),
    ("pregunta de arquitectura", "¿qué es VSA y por qué no embeddings?", True),
]


def _hook(prompt: str, env: dict) -> str:
    """Ejecuta el hook como lo ejecuta Claude Code y devuelve lo que inyectaría."""
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", "hook"],
                       input=json.dumps({"prompt": prompt}), capture_output=True,
                       text=True, encoding="utf-8", env=env)
    try:
        d = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return ""
    return d.get("hookSpecificOutput", {}).get("additionalContext", "")


def _tools(env: dict) -> tuple[int, int]:
    """Handshake MCP crudo -> (nº de herramientas, tokens de sus definiciones)."""
    msgs = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "t", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})])
    r = subprocess.run([sys.executable, "-m", "hipercampo.server"], input=msgs,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    for linea in r.stdout.splitlines():
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2:
            tools = d.get("result", {}).get("tools", [])
            return len(tools), estimate_tokens(json.dumps(tools, ensure_ascii=False))
    return 0, 0


def main() -> int:
    env = dict(os.environ, HIPERCAMPO_LOG="0")
    n_tools, t_tools = _tools(env)

    filas, disparos, falsos = [], 0, 0
    for etiqueta, prompt, deberia in PROMPTS:
        ctx = _hook(prompt, env)
        tk = estimate_tokens(ctx)
        if tk:
            disparos += 1
            if not deberia:
                falsos += 1
        filas.append({"caso": etiqueta, "tokens": tk, "esperado": deberia,
                      "desperdicio": bool(tk and not deberia)})

    por_turno = sum(f["tokens"] for f in filas) / len(filas)
    informe = {
        "estimado": es_estimacion(),
        "herramientas": {"n": n_tools, "tokens_por_peticion": t_tools},
        "hook": {"por_turno_medio": round(por_turno),
                 "turnos_que_disparan": f"{disparos}/{len(filas)}",
                 "disparos_indebidos": falsos, "detalle": filas},
        # Sesión típica: 30 turnos. Las herramientas se pagan en cada petición;
        # el hook solo en los turnos que disparan.
        "sesion_30_turnos": {"herramientas": t_tools * 30,
                             "hook": round(por_turno * 30),
                             "total": round(t_tools * 30 + por_turno * 30)},
    }

    if "--json" in sys.argv:
        print(json.dumps(informe, ensure_ascii=False, indent=2))
        return 0

    aviso = " (ESTIMADO por caracteres; instala tiktoken para exactitud)" if es_estimacion() else ""
    print(f"\nCOSTE EN TOKENS DE HIPERCAMPO{aviso}\n" + "=" * 60)
    print(f"\n1. Herramientas MCP: {n_tools} · {t_tools} tokens EN CADA PETICIÓN")
    print("   (coste fijo: ocupa ventana de contexto aunque no uses la memoria)")
    print("\n2. Hook, por turno:")
    for f in filas:
        marca = ("  ← DESPERDICIO" if f["desperdicio"]
                 else ("" if f["tokens"] else "  (se calla, bien)"))
        print(f"   {f['caso']:24} {f['tokens']:5} tok{marca}")
    print(f"\n   media por turno: {round(por_turno)} tok · dispara en {disparos}/{len(filas)}"
          f" · indebidos: {falsos}")
    s = informe["sesion_30_turnos"]
    print(f"\n3. Sesión de 30 turnos: {s['herramientas']} (herramientas) + {s['hook']}"
          f" (hook) = {s['total']} tokens")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
