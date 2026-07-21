"""
Backup y restauración de la memoria de hipercampo.

La memoria entera es UN fichero SQLite. Respaldar = copiarlo. Aquí usamos la API
de backup online de SQLite para obtener una copia CONSISTENTE aunque el servidor
esté usándolo en ese momento.

Uso:
    python -m hipercampo.backup                      # copia a <db>.YYYYMMDD-HHMMSS.bak
    python -m hipercampo.backup mi_copia.db          # copia a la ruta que indiques
    python -m hipercampo.backup --restore copia.db   # restaura desde una copia
"""

import os
import sqlite3
import sys
import time

from .config import db_path


def backup(dst: str | None = None, src: str | None = None) -> str:
    src = src or db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"No hay memoria que respaldar en: {src}")
    if dst is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dst = f"{src}.{stamp}.bak"
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    con = sqlite3.connect(src)
    out = sqlite3.connect(dst)
    with out:
        con.backup(out)          # copia consistente, incluso con el server activo
    out.close()
    con.close()
    return os.path.abspath(dst)


def restore(src: str, dst: str | None = None) -> str:
    dst = dst or db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"No existe la copia: {src}")
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    con = sqlite3.connect(src)
    out = sqlite3.connect(dst)
    with out:
        con.backup(out)
    out.close()
    con.close()
    return os.path.abspath(dst)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--restore":
        if len(argv) < 2:
            print("Uso: python -m hipercampo.backup --restore <copia.db>")
            return 1
        print("Restaurada la memoria en:", restore(argv[1]))
        return 0
    dst = argv[0] if argv else None
    print("Copia de seguridad creada en:", backup(dst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
