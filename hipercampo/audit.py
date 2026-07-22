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
    """Escribe a stderr sin romper ni ensuciar la salida. En Windows la consola suele
    ser cp1252 y no sabe escribir 'ó' ni '·': salían como '?'. Si el destino no puede
    con el texto, se degrada a ASCII legible ('abstención' -> 'abstencion') en vez de
    emitir basura. El FICHERO sigue guardando el original en UTF-8."""
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


def tail(n: int = 20) -> list[str]:
    """Últimas n líneas del registro (para `hipercampo log`)."""
    if _PATH is None or not _PATH.exists():
        return []
    try:
        return _PATH.read_text(encoding="utf-8").splitlines()[-n:]
    except Exception:
        return []


def logfile() -> str | None:
    return str(_PATH) if _PATH else None
