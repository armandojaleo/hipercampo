"""
Registro de decisiones: que hipercampo cuente QUÉ hace y POR QUÉ.

Una memoria que decide sola (guardar o no, olvidar, soñar, callarse) tiene que ser
auditable. Cada decisión relevante se registra:

  - a **stderr**, que es donde el cliente MCP muestra la salida del servidor;
  - y a un **fichero** junto a la base de datos, para poder revisarlo luego
    (`hipercampo log`). Se desactiva con HIPERCAMPO_LOG=0.

Formato legible, una línea por decisión:
    18:42:07 remember  guardado id=12 · novedad=0.42 sorpresa=0.81
    18:42:31 recall    abstención · nada destaca del ruido (n=14)
"""

import os
import sys
import time
import unicodedata
from pathlib import Path

_ENABLED = os.environ.get("HIPERCAMPO_LOG", "1") != "0"
_PATH: Path | None = None


def set_logfile(db_path: str) -> None:
    """El registro vive junto a la base de datos (mismo sitio, fácil de encontrar)."""
    global _PATH
    if not _ENABLED:
        return
    try:
        p = Path(db_path).resolve().parent / "hipercampo.log"
        p.parent.mkdir(parents=True, exist_ok=True)
        _PATH = p
    except Exception:
        _PATH = None


def _a_stderr(linea: str) -> None:
    """Escribe a stderr sin romper ni ensuciar la salida, que es donde el cliente MCP
    lee lo que decimos. Dos destinos distintos y una trampa en medio:

      - TUBERÍA (el caso MCP): Python no ve una consola y cae en la codificación
        local, que en Windows es cp1252; el cliente al otro lado decodifica UTF-8 y
        'abstención' le llega como caracteres rotos. Por eso aquí se escriben bytes
        UTF-8 a mano, sin depender del locale de la máquina.
      - CONSOLA: se respeta su codificación. Si no puede con 'ó' ni con '·', se
        degrada a ASCII legible ('abstencion', '|') en vez de emitir basura.

    El FICHERO de registro guarda siempre el original en UTF-8."""
    buf = getattr(sys.stderr, "buffer", None)
    if buf is not None and not sys.stderr.isatty():
        buf.write((linea + "\n").encode("utf-8", "replace"))
        buf.flush()
        return
    enc = getattr(sys.stderr, "encoding", None) or "utf-8"
    try:
        linea.encode(enc)
    except (UnicodeEncodeError, LookupError):
        plano = unicodedata.normalize("NFKD", linea.replace("·", "|"))
        linea = plano.encode("ascii", "ignore").decode("ascii")
    print(linea, file=sys.stderr, flush=True)


def log(accion: str, detalle: str = "", **campos) -> None:
    """Registra una decisión. Nunca lanza: la observabilidad no puede romper nada."""
    if not _ENABLED:
        return
    try:
        extra = " · ".join(f"{k}={v}" for k, v in campos.items() if v not in (None, ""))
        linea = f"{time.strftime('%H:%M:%S')} {accion:<9} {detalle}"
        if extra:
            linea += f" · {extra}"
        _a_stderr(linea)
        if _PATH is not None:
            with open(_PATH, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {accion:<9} {detalle}"
                        f"{' · ' + extra if extra else ''}\n")
    except Exception:
        pass


def tail(n: int = 20, contiene: str | None = None, solo_hoy: bool = False,
         accion: str | None = None) -> list[str]:
    """Últimas n líneas del registro, con filtros (para `hipercampo log`).

    `contiene`: subcadena a buscar (sin distinguir mayúsculas ni acentos).
    `solo_hoy`: solo lo de hoy. `accion`: solo esa acción (recall, remember…)."""
    if _PATH is None or not _PATH.exists():
        return []
    try:
        lineas = _PATH.read_text(encoding="utf-8", errors="replace").splitlines()
    except Exception:
        return []
    if solo_hoy:
        hoy = time.strftime("%Y-%m-%d")
        lineas = [ln for ln in lineas if ln.startswith(hoy)]
    if accion:
        # la acción es la 3ª columna: "2026-07-23 09:00:37 recall    ..."
        lineas = [ln for ln in lineas if ln[20:].split(" ", 1)[0] == accion]
    if contiene:
        aguja = _plano(contiene)
        lineas = [ln for ln in lineas if aguja in _plano(ln)]
    return lineas[-n:] if n > 0 else lineas


def _plano(t: str) -> str:
    """Minúsculas y sin acentos: buscar 'sueno' debe encontrar 'sueño'."""
    sin = unicodedata.normalize("NFKD", t.lower())
    return "".join(c for c in sin if not unicodedata.combining(c)).replace("ñ", "n")


def acciones() -> list[str]:
    """Qué acciones aparecen en el registro (para la ayuda del comando)."""
    vistas = []
    for ln in tail(0):
        a = ln[20:].split(" ", 1)[0]
        if a and a not in vistas:
            vistas.append(a)
    return sorted(vistas)


def logfile() -> str | None:
    return str(_PATH) if _PATH else None
