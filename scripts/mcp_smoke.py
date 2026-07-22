"""Handshake MCP contra el servidor recién instalado: initialize, initialized y
tools/list, leyendo respuesta a respuesta. Escribir las tres líneas de golpe y
cerrar stdin es una carrera: el servidor puede ver el EOF antes de contestar."""
import json
import subprocess
import sys

exe = sys.argv[1] if len(sys.argv) > 1 else sys.executable
p = subprocess.Popen([exe, "-m", "hipercampo.server"], stdin=subprocess.PIPE,
                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                     text=True, bufsize=1, encoding="utf-8", errors="replace")


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
    raise SystemExit("el servidor cerró sin responder")


enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                   "clientInfo": {"name": "ci", "version": "0"}}})
esperar(1)
enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
tools = [t["name"] for t in esperar(2)["result"]["tools"]]
p.stdin.close(); p.terminate()

faltan = {"hc_remember", "hc_recall", "hc_assist", "hc_health"} - set(tools)
if faltan:
    raise SystemExit(f"faltan herramientas: {sorted(faltan)} · hay {tools}")
print(f"handshake MCP OK · {len(tools)} herramientas")
