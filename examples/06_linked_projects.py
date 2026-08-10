"""
Use case 6 - Two projects, one file: linking reads without ever writing.
Run:  python examples/06_linked_projects.py

All memory lives in one DB; namespaces are drawers inside it. A context can
LINK another's namespace to read it during recall, but every write --
remember, update, forget, consolidate -- always lands in its own drawer.
Linking is a constructor arg (or HIPERCAMPO_LINKED), not a merge.
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

DB = "data/ex_linked.db"


def cleanup():
    # On Windows a just-closed handle can still block deletion for a moment
    # (POSIX allows unlinking an open file; Windows doesn't) -- swallow it,
    # same as tests/storage/test_linked.py does for the same reason.
    for s in ("", "-wal", "-shm"):
        try:
            Path(DB + s).unlink(missing_ok=True)
        except PermissionError:
            pass


def main():
    cleanup()

    print("-- The backend agent works in its own drawer: 'webshop' --")
    backend = Hipercampo(DB, namespace="proj-webshop")
    for text, imp in [
        ("checkout times out above 3 concurrent payment retries", 0.8),
        ("the cart service caches prices for 30s, which surprised a reviewer", 0.6),
    ]:
        backend.remember(text, imp)
        print(f"  webshop remembers: «{text[:56]}»")
    backend.store.close()

    print("\n-- The docs agent works in 'docs', and LINKS 'webshop' read-only --")
    docs = Hipercampo(DB, namespace="docs", linked=["proj-webshop"])
    docs.remember("the README needs a troubleshooting section for checkout", 0.7)

    print("  docs recall('checkout timeout') pulls from both drawers:")
    for hit in docs.recall("checkout timeout", k=3):
        origin = hit.get("project", "docs")
        print(f"    [{origin}] «{hit['text'][:56]}»")

    print("\n-- Writes from 'docs' never touch 'webshop', linked or not --")
    docs.forget(dry_run=False)          # only decays docs' own memories
    docs.store.close()

    backend = Hipercampo(DB, namespace="proj-webshop")
    print(f"  webshop.stats()['active_episodic'] = "
          f"{backend.stats()['active_episodic']}  (untouched by docs' forget)")

    print("\n  What's linked is read, never written: a project that isn't")
    print("  explicitly linked stays invisible, and the reverse link doesn't")
    print("  exist unless 'webshop' also names 'docs' -- linking is one-way.")
    backend.store.close()
    cleanup()


if __name__ == "__main__":
    main()
