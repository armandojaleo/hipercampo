"""
Shared pytest setup for the whole suite.

WHY THIS FILE EXISTS. The tests are grouped in folders that mirror the package
layers (`core/`, `storage/`, `cycle/`, `support/`, `contracts/`). With pytest's
default import mode, the directory added to `sys.path` is the one holding each
test FILE — so from `tests/core/test_vsa.py` the importable directory is
`tests/core`, not `tests`, and the `from helpers import ...` that every test does
would stop resolving. A conftest at the suite root runs before collection, so
this is the right place to put `tests/` on the path once, for everybody.

It also keeps the repository root importable, so `import hipercampo` picks up the
working tree rather than whatever happens to be installed in the environment.
"""

import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

for ruta in (str(ROOT), str(TESTS)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)
