"""
Shared test utilities. Each file once repeated its own _open/_clean pair (15 of
19 files); the implementation now lives in one place.

    from helpers import memory, clean

    hc = memory("my_test")        # Isolated temporary database; closes the previous one.
    ...
    clean()                      # Close and delete .db, -wal, and -shm.
"""

import os
import sys
from pathlib import Path

# Keep the repository root in ONE place. Tests live in per-layer folders, so
# `parent.parent` inside a test now points to `tests/`, not the root. Importing ROOT
# makes pyproject/docs paths independent of test nesting depth.
ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT))

# Hermeticity: tests must not depend on the runner's environment. A developer with
# HIPERCAMPO_LINKED=* or HIPERCAMPO_PAUSED=1 would see FALSE failures: an isolated
# namespace suddenly sees others, or writes do not persist. CI lacks these variables
# and would pass. Clear them on import; a test that needs one sets it explicitly.
for _v in ("HIPERCAMPO_LINKED", "HIPERCAMPO_PAUSED", "HIPERCAMPO_NAMESPACE", "HIPERCAMPO_DB"):
    os.environ.pop(_v, None)

# Per-project opt-in is OFF for the suite's own sake. The gate asks "was hipercampo
# invited into this directory?", and a test is not a project: without this, whether a
# server-level test passes would depend on whether its scratch database happened to
# hold a memory yet — green or red by accident of ordering. tests/support/test_opt_in.py
# clears this variable itself, because the gate is exactly what it is testing.
os.environ["HIPERCAMPO_FORCE_ENABLED"] = "1"

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

_open_memory: Hipercampo | None = None
_path: str | None = None


def memory(name: str, namespace: str = "test") -> Hipercampo:
    """Open a clean, test-specific temporary database."""
    global _open_memory, _path
    clean()
    _path = f"data/_t_{name}.db"
    for suffix in ("", "-wal", "-shm"):
        try:
            Path(_path + suffix).unlink(missing_ok=True)
        except PermissionError:
            pass          # A remaining Windows lock will make the test fail visibly.
    _open_memory = Hipercampo(_path, namespace=namespace)
    return _open_memory


def clean() -> None:
    """Close the open memory and delete its files (required on Windows)."""
    global _open_memory, _path
    if _open_memory is not None:
        try:
            _open_memory.store.close()
        except Exception:
            pass
        _open_memory = None
    if _path:
        for suffix in ("", "-wal", "-shm"):
            try:
                Path(_path + suffix).unlink(missing_ok=True)
            except PermissionError:
                pass          # Another live Windows handle; retry on the next cleanup.


def run_tests(globs) -> int:
    """Run this module's test_* functions and print a compact summary."""
    fails = 0
    for name, fn in sorted(globs.items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
            except Exception as e:
                fails += 1
                print(f"ERROR {name}: {e}")
            finally:
                clean()
    print(f"\n{'OK' if not fails else f'{fails} FAILED'}")
    return 1 if fails else 0
