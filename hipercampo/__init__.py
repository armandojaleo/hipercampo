"""hipercampo — live memory for agents, based on hypervectors (VSA).

EMBEDDABLE CORE
---------------
The core (VSA + storage + the memory cycle) does NOT depend on `mcp`: that's
just a transport. `import hipercampo` doesn't pull in `mcp` — so it fits on
an embedded system or a robot (a Linux SBC) with only `numpy`. The boundary
is tested in `tests/test_core_embebible.py`; breaking it (putting `import
mcp` in a core module) fails CI.

    from hipercampo import Hipercampo
    hc = Hipercampo("memory.db", namespace="robot")
    hc.remember("hallway B leads to the storeroom", importance=0.7)
    hits = hc.recall("how do I get to the storeroom")

Public core API (the full cycle, with no transport involved):
    remember · recall · update · consolidate · forget · purge · sleep · dream ·
    muse · learn · remember_fact · ask_role · identity · unlearn · assist ·
    accept_bridge · reject_bridge · stats · health · close

Transports (optional, on top of the core): `hipercampo.server` (MCP, needs
`mcp`) and `hipercampo.cli` (command line).

HOW IT'S ORGANIZED
-------------------
The package is arranged in LAYERS, each looking only downward (no cycles):

    core/      pure algebra and encoding (vsa, encoder, atomize, surprise…)
    support/   cross-cutting: paths, logging, budget, warnings (config, audit…)
    storage/   SQLite persistence (store, backup)
    cycle/     the memory: what's stored, retrieved and forgotten (memory, roles…)
    cli.py     console interface   ── stay at the root on purpose:
    server.py  MCP interface       ── they're public paths (see below)

The lower layers can be measured on their own: `core` never touches disk and
`storage` doesn't know what deserves remembering. That separation is what
lets the core fit on an embedded device, and it's what
`tests/test_core_embebible.py` proves.
"""

import sys

from .cycle.memory import Hipercampo

__all__ = ["Hipercampo"]

# --- import-path compatibility ----------------------------------------------
# `hipercampo.encoder` and `hipercampo.roles` are DOCUMENTED as public
# (INSTALL shows `from hipercampo import encoder; encoder.enable_semantic()`
# and the README shows `from hipercampo.roles import ItemMemory, encode_fact,
# query_role`). Splitting the package into layers would move those paths,
# and breaking the import for anyone already using hipercampo isn't an
# organizational detail: it's a breaking change.
#
# The MODULE itself is aliased in sys.modules, its names aren't re-exported
# one by one. The difference matters: this way `hipercampo.encoder` and
# `hipercampo.core.encoder` are the SAME object, and the semantic hook
# —which is module-level global state— stays a single one. Copying names
# would give two views of the same state, and turning on semantic mode
# through one path wouldn't show up through the other.
# BOTH things are needed, and it's checked in tests/test_rutas_publicas.py:
#   - the sys.modules entry  -> `import hipercampo.encoder` and `from ... import X`
#   - the package attribute  -> `hipercampo.encoder` after `import hipercampo`
# Registering only the first lets the import through but breaks attribute
# access (which is exactly how INSTALL shows it: `from hipercampo import encoder`).
from .cycle import roles                                 # noqa: E402
from .core import encoder                              # noqa: E402

sys.modules.setdefault("hipercampo.encoder", encoder)
sys.modules.setdefault("hipercampo.roles", roles)

# One single source of truth: the installed version (pyproject). Keeps the
# package from declaring a version different from the one published.
try:                                     # pragma: no cover
    from importlib.metadata import version
    __version__ = version("hipercampo")
except (ImportError, Exception):         # pragma: no cover
    __version__ = "0.0.0+unknown"
