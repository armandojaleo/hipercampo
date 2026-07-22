"""
Los procesos servidor: verlos y reiniciarlos sin pelearse con el sistema.

Por qué existe esto. El servidor MCP es un proceso LARGO: el cliente lo arranca una
vez y lo mantiene vivo, así que el código que tiene cargado es el del arranque. Si
actualizas hipercampo, el servidor sigue sirviendo la versión antigua hasta que
alguien lo mata, y desde fuera no se nota: responde, simplemente responde como antes.
Peor aún, cada cliente declara sus servidores en un sitio distinto (uno en el
.mcp.json del proyecto, otro en la config de usuario), así que "reiniciar" desde un
fichero solo alcanza a los suyos y los demás se quedan atrás sin avisar. Y si el
cliente no limpia al recargar, se acumulan procesos huérfanos contra la misma base.

La solución honesta es no adivinar: se listan los procesos servidor vivos con su hora
de arranque, y se terminan. No hace falta arrancarlos a mano — el cliente MCP los
vuelve a levantar solo la próxima vez que use una herramienta, ya con el código nuevo.

Sin dependencias: psutil si está, y si no, las herramientas del propio sistema.
"""

import os
import subprocess
import sys
import time

# Cómo se reconoce a uno de los nuestros en la línea de comandos.
_FIRMA = ("hipercampo.server", "hipercampo serve")


def _coincide(cmdline: str) -> bool:
    return any(f in cmdline for f in _FIRMA)


def _via_psutil() -> list[dict] | None:
    try:
        import psutil
    except ImportError:
        return None
    fuera = []
    for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if not _coincide(cmd) or p.info["pid"] == os.getpid():
                continue
            db = None
            try:                                     # puede no dejarnos: no pasa nada
                db = (p.environ() or {}).get("HIPERCAMPO_DB")
            except Exception:
                pass
            fuera.append({"pid": p.info["pid"], "arranque": p.info["create_time"],
                          "cmd": cmd, "db": db})
        except Exception:
            continue                                 # el proceso pudo morir al mirarlo
    return fuera


def _via_windows() -> list[dict]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
          "Name='pythonw.exe'\" | ForEach-Object { "
          "'{0}|{1}|{2}' -f $_.ProcessId, "
          "$_.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss'), $_.CommandLine }")
    try:
        salida = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                                 "-Command", ps], capture_output=True, text=True,
                                timeout=30).stdout
    except Exception:
        return []
    fuera = []
    for linea in salida.splitlines():
        partes = linea.strip().split("|", 2)
        if len(partes) != 3:
            continue
        pid, arranque, cmd = partes
        if not _coincide(cmd) or not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            t = time.mktime(time.strptime(arranque, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            t = None
        fuera.append({"pid": int(pid), "arranque": t, "cmd": cmd.strip(), "db": None})
    return fuera


def _via_posix() -> list[dict]:
    try:
        salida = subprocess.run(["ps", "-eo", "pid=,lstart=,args="],
                                capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    fuera = []
    for linea in salida.splitlines():
        linea = linea.strip()
        trozos = linea.split(None, 1)
        if len(trozos) != 2 or not trozos[0].isdigit():
            continue
        pid, resto = int(trozos[0]), trozos[1]
        if not _coincide(resto) or pid == os.getpid():
            continue
        t = None
        # lstart ocupa 5 campos fijos ("Tue Jul 22 21:14:10 2026") antes del comando
        campos = resto.split(None, 5)
        if len(campos) == 6:
            try:
                t = time.mktime(time.strptime(" ".join(campos[:5]), "%a %b %d %H:%M:%S %Y"))
                resto = campos[5]
            except ValueError:
                pass
        fuera.append({"pid": pid, "arranque": t, "cmd": resto, "db": None})
    return fuera


def listar() -> list[dict]:
    """Procesos servidor vivos, del más antiguo al más nuevo (el más viejo es el
    más sospechoso de arrastrar código caducado)."""
    procesos = _via_psutil()
    if procesos is None:
        procesos = _via_windows() if sys.platform == "win32" else _via_posix()
    return sorted(procesos, key=lambda p: (p["arranque"] or 0, p["pid"]))


def terminar(pids: list[int], espera: float | None = None) -> dict[int, str]:
    """Termina los procesos indicados, con buenos modales primero. Devuelve qué pasó
    con cada uno. Nunca lanza: que falle uno no puede impedir cerrar el resto.

    En Windows el cierre amable casi nunca funciona aquí y no es un fallo: `taskkill`
    sin /F pide el cierre por mensaje de ventana, y un servidor MCP por stdio no tiene
    ventana que lo reciba, así que lo ignora. Por eso allí se espera poco antes de
    forzar. Forzar es seguro para la memoria: SQLite en modo WAL es a prueba de
    caídas, y lo confirmado sigue confirmado aunque el proceso muera de golpe.
    """
    if espera is None:
        espera = 1.0 if sys.platform == "win32" else 3.0
    estado: dict[int, str] = {}
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid)],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, 15)                     # SIGTERM
            estado[pid] = "terminado"
        except Exception as e:
            estado[pid] = f"error: {e}"

    if not espera:
        return estado
    limite = time.monotonic() + espera
    while time.monotonic() < limite:                 # darles tiempo a cerrar la BD
        vivos = {p["pid"] for p in listar()}
        if not (set(pids) & vivos):
            return estado
        time.sleep(0.25)

    for pid in {p["pid"] for p in listar()} & set(pids):
        try:                                         # se resistió: sin miramientos
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, 9)                      # SIGKILL
            estado[pid] = "cerrado (forzado)"
        except Exception as e:
            estado[pid] = f"error: {e}"
    return estado
