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

import os
import sys
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent

for ruta in (str(ROOT), str(TESTS)):
    if ruta not in sys.path:
        sys.path.insert(0, ruta)

# The per-project opt-in gate asks "was hipercampo invited into this directory?".
# A test run is not a project, so the whole suite answers yes up front.
#
# Without this, whether an unrelated test passes depends on whether its scratch
# database happens to hold a row yet: with no registry, an installation that
# already has memories stays enabled. That is green-or-red by accident of leftover
# files — it passed locally on a machine with old scratch databases and failed on a
# clean CI runner, which is the exact shape of bug this repository keeps hitting.
#
# Set here (pytest) and in the CI workflow (which runs each file standalone, where
# no conftest is loaded). tests/support/test_opt_in.py clears it in the environment
# it builds for its subprocesses, because the gate is what it is testing.
os.environ.setdefault("HIPERCAMPO_FORCE_ENABLED", "1")
