"""
INSPIRATIONAL recall demo — run: python scripts/muse_demo.py

The mind does not erase: it buries. Sometimes a distant memory resurfaces and links
things you did not know were connected. This demo seeds memories, lets forgetting
make some dormant, and uses `muse` to resurface them by association and inspire.
"""

import sys
import time
from pathlib import Path


# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402


def main():
    for suf in ("", "-wal", "-shm"):
        Path("data/muse_demo.db" + suf).unlink(missing_ok=True)
    hc = Hipercampo("data/muse_demo.db", namespace="demo")

    print("Seeding memories (some will become buried over time)...\n")
    hc.remember("de niño construía radios de galena con mi abuelo", 0.4)
    hc.remember("las antenas captan ondas que no vemos ni oímos", 0.4)
    hc.remember("el hipocampo consolida recuerdos mientras dormimos", 0.5)
    hc.remember("una radio de galena no necesita pilas: vive de la propia señal", 0.3)
    hc.remember("hoy trabajo en una memoria para IA que olvida como el cerebro", 0.7)

    # Time passes: weakly reinforced memories become dormant.
    old = time.time() - 90 * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.5",
                        (old,))
    hc.store.commit()
    result = hc.forget(dry_run=False)
    forgotten = result.get("forgotten", result.get("olvidados", 0))
    print(f"Time passed. {forgotten} memories became DORMANT (not deleted).")
    print("Status:", hc.stats(), "\n")

    print("Thinking aloud: «a memory powered by its own signal»")
    print("→ muse searches for unexpected connections, including dormant ones:\n")
    for idea in hc.muse("una memoria que vive de su propia señal sin pilas", k=3):
        marker = " ✨resurfaced" if idea["resurfaced"] else ""
        print(f"  • «{idea['text']}»")
        print(f"      via {idea['via']}{marker}")

    print("\n(A buried childhood memory can return and connect a new idea.)")
    hc.store.close()


if __name__ == "__main__":
    main()
