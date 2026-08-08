"""
Server processes: seeing them and restarting them without fighting the OS.

Why this exists. The MCP server is a LONG-LIVED process: the client starts
it once and keeps it alive, so the code it has loaded is whatever was
current at startup. If you upgrade hipercampo, the server keeps serving the
old version until someone kills it, and there's no outward sign: it
responds, it just responds like it used to. Worse, each client declares its
servers in a different place (one in the project's .mcp.json, another in
the user config), so "restarting" from one file only reaches its own and the
rest silently fall behind. And if the client doesn't clean up on reload,
orphaned processes pile up against the same database.

The honest fix is to not guess: list the live server processes with their
start time, and terminate them. No need to start them by hand — the MCP
client spins them back up on its own the next time it uses a tool, already
with the new code.

No dependencies: psutil if it's there, and the OS's own tools if not.
"""

import os
import subprocess
import sys
import time

# How one of ours is recognized on the command line.
_SIGNATURE = ("hipercampo.server", "hipercampo serve")


def _matches(cmdline: str) -> bool:
    return any(f in cmdline for f in _SIGNATURE)


def _via_psutil() -> list[dict] | None:
    try:
        import psutil
    except ImportError:
        return None
    out = []
    for p in psutil.process_iter(["pid", "cmdline", "create_time"]):
        try:
            cmd = " ".join(p.info["cmdline"] or [])
            if not _matches(cmd) or p.info["pid"] == os.getpid():
                continue
            db = ns = None
            try:                                     # might not be allowed: that's fine
                env = p.environ() or {}
                db = env.get("HIPERCAMPO_DB")
                ns = env.get("HIPERCAMPO_NAMESPACE")
            except Exception:
                pass
            out.append({"pid": p.info["pid"], "started_at": p.info["create_time"],
                          "cmd": cmd, "db": db, "namespace": ns})
        except Exception:
            continue                                 # the process may have died mid-look
    return out


def _via_windows() -> list[dict]:
    ps = ("Get-CimInstance Win32_Process -Filter \"Name='python.exe' or "
          "Name='pythonw.exe'\" | ForEach-Object { "
          "'{0}|{1}|{2}' -f $_.ProcessId, "
          "$_.CreationDate.ToString('yyyy-MM-ddTHH:mm:ss'), $_.CommandLine }")
    try:
        output = subprocess.run(["powershell", "-NoProfile", "-NonInteractive",
                                 "-Command", ps], capture_output=True, text=True,
                                timeout=30).stdout
    except Exception:
        return []
    out = []
    for line in output.splitlines():
        parts = line.strip().split("|", 2)
        if len(parts) != 3:
            continue
        pid, started_at, cmd = parts
        if not _matches(cmd) or not pid.isdigit() or int(pid) == os.getpid():
            continue
        try:
            t = time.mktime(time.strptime(started_at, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            t = None
        out.append({"pid": int(pid), "started_at": t, "cmd": cmd.strip(), "db": None})
    return out


def _via_posix() -> list[dict]:
    try:
        output = subprocess.run(["ps", "-eo", "pid=,lstart=,args="],
                                capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return []
    out = []
    for line in output.splitlines():
        line = line.strip()
        chunks = line.split(None, 1)
        if len(chunks) != 2 or not chunks[0].isdigit():
            continue
        pid, rest = int(chunks[0]), chunks[1]
        if not _matches(rest) or pid == os.getpid():
            continue
        t = None
        # lstart takes up 5 fixed fields ("Tue Jul 22 21:14:10 2026") before the command
        fields = rest.split(None, 5)
        if len(fields) == 6:
            try:
                t = time.mktime(time.strptime(" ".join(fields[:5]), "%a %b %d %H:%M:%S %Y"))
                rest = fields[5]
            except ValueError:
                pass
        out.append({"pid": pid, "started_at": t, "cmd": rest, "db": None})
    return out


def list_servers() -> list[dict]:
    """Live server processes, oldest to newest (the oldest is the most
    suspect for carrying stale code)."""
    procs = _via_psutil()
    if procs is None:
        procs = _via_windows() if sys.platform == "win32" else _via_posix()
    return sorted(procs, key=lambda p: (p["started_at"] or 0, p["pid"]))


def terminate(pids: list[int], wait: float | None = None) -> dict[int, str]:
    """Terminates the given processes, politely first. Returns what happened
    to each one. Never raises: one failing can't stop the rest from closing.

    On Windows the polite close almost never works here, and that's not a
    bug: `taskkill` without /F asks for a close via window message, and an
    MCP server over stdio has no window to receive it, so it's ignored.
    That's why the wait there is short before forcing. Forcing is safe for
    the memory: SQLite in WAL mode is crash-safe, and whatever was committed
    stays committed even if the process dies outright.
    """
    if wait is None:
        wait = 1.0 if sys.platform == "win32" else 3.0
    status: dict[int, str] = {}
    for pid in pids:
        try:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/PID", str(pid)],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, 15)                     # SIGTERM
            status[pid] = "terminated"
        except Exception as e:
            status[pid] = f"error: {e}"

    if not wait:
        return status
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:                # give them time to close the DB
        alive = {p["pid"] for p in list_servers()}
        if not (set(pids) & alive):
            return status
        time.sleep(0.25)

    for pid in {p["pid"] for p in list_servers()} & set(pids):
        try:                                         # it resisted: no more politeness
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                               capture_output=True, timeout=15)
            else:
                os.kill(pid, 9)                      # SIGKILL
            status[pid] = "killed (forced)"
        except Exception as e:
            status[pid] = f"error: {e}"
    return status
