"""
Backup and restore for hipercampo's memory.

The whole memory is ONE SQLite file. Backing up = copying it. Here we use
SQLite's online backup API to get a CONSISTENT copy even while the server is
using it at that moment.

Usage:
    python -m hipercampo.backup                      # copies to <db>.YYYYMMDD-HHMMSS.bak
    python -m hipercampo.backup my_copy.db           # copies to the path you give
    python -m hipercampo.backup --restore copy.db    # restores from a copy
"""

import os
import sqlite3
import sys
import time

from ..support.config import db_path


def backup(dst: str | None = None, src: str | None = None) -> str:
    src = src or db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"No memory to back up at: {src}")
    if dst is None:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        dst = f"{src}.{stamp}.bak"
    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    con = sqlite3.connect(src)
    out = sqlite3.connect(dst)
    with out:
        con.backup(out)          # consistent copy, even with the server active
    out.close()
    con.close()
    return os.path.abspath(dst)


def restore(src: str, dst: str | None = None) -> str:
    """Restores a copy OVER the current memory.

    Before overwriting anything, saves what was there to
    `<dst>.before-restore`: restoring the wrong copy is an easy mistake to
    make and a very costly one to discover late. And it verifies the copy is
    a readable DB BEFORE touching the original: a good memory doesn't get
    destroyed to put a broken file in its place."""
    dst = dst or db_path()
    if not os.path.exists(src):
        raise FileNotFoundError(f"Copy doesn't exist: {src}")
    con = sqlite3.connect(src)
    try:
        status = con.execute("PRAGMA quick_check").fetchone()[0]
        if status != "ok":
            raise ValueError(f"the copy isn't healthy ({status}): not restoring")
        con.execute("SELECT 1 FROM memories LIMIT 1")     # is it a real memory?
    except sqlite3.DatabaseError as e:
        con.close()
        raise ValueError(f"the copy isn't a valid hipercampo memory: {e}") from e

    os.makedirs(os.path.dirname(os.path.abspath(dst)), exist_ok=True)
    if os.path.exists(dst):
        previous = f"{dst}.before-restore"
        old = sqlite3.connect(dst)
        safeguard = sqlite3.connect(previous)
        try:
            old.backup(safeguard)
        finally:
            safeguard.close()
            old.close()

    out = sqlite3.connect(dst)
    try:
        con.backup(out)
    finally:
        out.close()
        con.close()
    return os.path.abspath(dst)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] == "--restore":
        if len(argv) < 2:
            print("Usage: python -m hipercampo.backup --restore <copy.db>")
            return 1
        print("Memory restored to:", restore(argv[1]))
        return 0
    dst = argv[0] if argv else None
    print("Backup created at:", backup(dst))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
