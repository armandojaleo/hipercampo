"""Handshake MCP contra el servidor recién instalado: initialize, initialized y
 tools/list, leyendo respuesta a respuesta. Escribir las tres líneas de golpe y
cerrar stdin es una carrera: el servidor puede ver el EOF antes de contestar.

El humo usa una BD temporal dentro de ``data/`` para no depender de HOME ni de
permisos del entorno de release, y conserva stderr para diagnosticar fallos reales.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

exe = sys.argv[1] if len(sys.argv) > 1 else sys.executable
smoke_db = Path("data/_mcp_smoke.db")
smoke_db.parent.mkdir(parents=True, exist_ok=True)
for suf in ("", "-wal", "-shm"):
    try:
        Path(str(smoke_db) + suf).unlink(missing_ok=True)
    except PermissionError:
        pass

env = os.environ.copy()
env["HIPERCAMPO_DB"] = str(smoke_db)
env["HIPERCAMPO_LOG"] = "0"
p = subprocess.Popen([exe, "-m", "hipercampo.server"], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                     text=True, bufsize=1, encoding="utf-8", errors="replace",
                     env=env)


def enviar(msg):
    p.stdin.write(json.dumps(msg) + "\n")
    p.stdin.flush()


def esperar(id_esperado):
    for linea in p.stdout:
        try:
            r = json.loads(linea)
        except ValueError:
            continue
        if r.get("id") == id_esperado:
            return r
    err = p.stderr.read() if p.stderr else ""
    raise SystemExit("el servidor cerró sin responder" + (f": {err}" if err else ""))


try:
    enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "ci", "version": "0"}}})
    esperar(1)
    enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
    enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    tools = [t["name"] for t in esperar(2)["result"]["tools"]]
finally:
    try:
        p.stdin.close()
    except Exception:
        pass
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        pass
    for suf in ("", "-wal", "-shm"):
        try:
            Path(str(smoke_db) + suf).unlink(missing_ok=True)
        except PermissionError:
            pass

# Por defecto (HIPERCAMPO_TOOLS=auto) solo se anuncian las de uso DIARIO más la puerta
# `hc_tools`; el resto se activa en caliente.
faltan = {"hc_remember", "hc_recall", "hc_assist", "hc_tools"} - set(tools)
if faltan:
    raise SystemExit(f"faltan herramientas anunciadas por defecto: {sorted(faltan)} · "
                     f"hay {tools}")
print(f"handshake MCP OK · {len(tools)} herramientas anunciadas (+ catálogo en hc_tools)")
