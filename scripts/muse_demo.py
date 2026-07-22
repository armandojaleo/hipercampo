"""
Demo del recuerdo INSPIRADOR — ejecuta:  python scripts/muse_demo.py

La mente no borra: sepulta. Y a veces un recuerdo lejano resurge y ata cosas que no
sabías conectadas. Esta demo siembra recuerdos, deja que el olvido adormezca algunos,
y usa `muse` para que resurjan por asociación e inspiren.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402


def main():
    for suf in ("", "-wal", "-shm"):
        Path("data/muse_demo.db" + suf).unlink(missing_ok=True)
    hc = Hipercampo("data/muse_demo.db", namespace="demo")

    print("Sembrando recuerdos (algunos se sepultarán con el tiempo)...\n")
    hc.remember("de niño construía radios de galena con mi abuelo", 0.4)
    hc.remember("las antenas captan ondas que no vemos ni oímos", 0.4)
    hc.remember("el hipocampo consolida recuerdos mientras dormimos", 0.5)
    hc.remember("una radio de galena no necesita pilas: vive de la propia señal", 0.3)
    hc.remember("hoy trabajo en una memoria para IA que olvida como el cerebro", 0.7)

    # el tiempo pasa: lo poco reforzado se adormece
    viejo = time.time() - 90 * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.5",
                        (viejo,))
    hc.store.commit()
    olv = hc.forget(dry_run=False)
    print(f"El tiempo pasó. {olv['olvidados']} recuerdos quedaron LATENTES (no borrados).")
    print("Estado:", hc.stats(), "\n")

    print("Pensando en voz alta: «una memoria que vive de su propia señal»")
    print("→ muse busca conexiones inesperadas (incluye lo latente):\n")
    for idea in hc.muse("una memoria que vive de su propia señal sin pilas", k=3):
        marca = " ✨resurgido" if idea["resurgido"] else ""
        print(f"  • «{idea['text']}»")
        print(f"      via {idea['via']}{marca}")

    print("\n(Un recuerdo sepultado de la infancia puede volver y atar una idea nueva.)")
    hc.store.close()


if __name__ == "__main__":
    main()
