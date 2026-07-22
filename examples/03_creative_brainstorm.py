"""
Caso de uso 3 · Brainstorming creativo con recuerdos que resurgen.
Ejecuta:  python examples/03_creative_brainstorm.py

La mente no borra: sepulta. Y a veces un recuerdo lejano vuelve y ata una idea
nueva. hc_muse busca conexiones INDIRECTAS e incluye lo latente, diciendo además
POR QUÉ conectó cada cosa (el recuerdo puente).
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

DB = "data/ex_muse.db"


def limpiar():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    limpiar()
    hc = Hipercampo(DB, namespace="creativo")

    recuerdos = [
        ("los hongos micorrízicos conectan árboles bajo tierra y comparten nutrientes", 0.4),
        ("de joven leí sobre redes de telégrafo del siglo XIX", 0.3),
        ("un enjambre de hormigas resuelve rutas sin líder central", 0.4),
        ("estoy diseñando un sistema distribuido sin coordinador único", 0.7),
        ("las neuronas se refuerzan cuando se activan juntas", 0.5),
    ]
    for t, imp in recuerdos:
        hc.remember(t, imp)

    # el tiempo entierra lo poco reforzado
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.45",
                        (time.time() - 120 * 86400,))
    hc.store.commit()
    hc.forget(dry_run=False)
    print(f"El tiempo pasó. Latentes: {hc.stats()['latentes']}\n")

    print("Pensando: «un sistema distribuido sin coordinador, que se auto-organice»")
    print("→ muse trae conexiones inesperadas:\n")
    for idea in hc.muse("un sistema distribuido que se auto-organiza sin líder", k=3):
        marca = " ✨(resurgido de lo latente)" if idea["resurgido"] else ""
        print(f"  • «{idea['text']}»{marca}")
        if idea.get("conectado_por"):
            print(f"      ↳ conectado por: «{idea['conectado_por']}»")

    print("\n  Una lectura olvidada del telégrafo o los hongos del bosque pueden")
    print("  inspirar un diseño de hoy. Eso es incubación creativa.")
    hc.store.close()
    limpiar()


if __name__ == "__main__":
    main()
