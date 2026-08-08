"""
Recovery from transient database failures — split out of `memory.py` since
it's infrastructure around the cycle, not part of it.

Only TRANSIENT failures are retried. Repeating a write that maybe already
succeeded could duplicate memories or double-apply a reinforcement, so on
corruption, a read-only database, a full disk or a schema error the
`resilient` decorator does NOT retry: it reports instead.
"""

import functools
import sqlite3

from ..support import audit

_TRANSIENT = ("database is locked", "database table is locked", "database is busy",
             "cannot operate on a closed database", "unable to open database file")
_NO_RETRY = ("readonly", "attempt to write a readonly database", "disk i/o error",
            "database disk image is malformed", "disk is full", "no such column",
            "no such table", "file is not a database")


def _is_transient(e: Exception) -> bool:
    """A dropped connection arrives as ProgrammingError, a lock as
    OperationalError: both are transient. Everything else, by message."""
    msg = str(e).lower()
    if any(p in msg for p in _NO_RETRY):
        return False
    return any(p in msg for p in _TRANSIENT)


def resilient(fn):
    """If the database fails with something TRANSIENT (dropped connection,
    lock), WARN, reconnect and RETRY once. If the failure is permanent
    (corruption, read-only, broken schema) it does NOT retry —repeating a
    write could duplicate it— and returns a readable error instead of
    crashing the server: a downed memory shouldn't take the agent using it
    down with it."""
    @functools.wraps(fn)
    def wrapper(self, *a, **kw):
        try:
            return fn(self, *a, **kw)
        except sqlite3.Error as e:
            if not _is_transient(e):
                audit.log("ERROR", f"{fn.__name__}: {e} · non-transient failure, not retrying")
                return {"error": f"memory unavailable: {e}",
                        "retried": False,
                        "suggestion": "run `hipercampo doctor` to diagnose it"}
            audit.log("ERROR", f"{fn.__name__}: {e} · retrying after reconnect")
            try:
                self.store.reconnect()
                return fn(self, *a, **kw)
            except Exception as e2:
                audit.log("ERROR", f"{fn.__name__}: failed after reconnect: {e2}")
                return {"error": f"memory unavailable: {e2}",
                        "retried": True,
                        "suggestion": "run `hipercampo doctor` to diagnose it"}
    return wrapper
