"""
Caso de uso 4 (largo) · Una noche de incubación: sorpresa, sueño, poda y EUREKA.
Ejecuta:  python examples/04_the_long_night.py

Sigue a una investigadora durante semanas: acumula recuerdos (trabajo + vida),
DUERME (consolida), el tiempo PODA lo trivial a estado latente, SUEÑA (teje puentes
entre ideas lejanas) y, al final, `muse` ata un recuerdo sepultado con el problema
actual: la eureka. Todo emerge de la mecánica, no está guionizado.
"""

import sys
import time
from pathlib import Path


# Salida UTF-8 aunque se redirija (en Windows, cp1252 rompe con «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

DB = "data/ex_long.db"


def limpiar():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def titulo(t):
    print("\n" + "═" * 66 + f"\n  {t}\n" + "═" * 66)


def main():
    limpiar()
    hc = Hipercampo(DB, namespace="investigadora")

    titulo("SEMANA 1-3 · Acumula recuerdos (trabajo y vida)")
    recuerdos = [
        # el problema y su entorno técnico (se irán reforzando/asociando)
        ("intento que muchos sensores acuerden una hora común sin reloj central", 0.7),
        ("los sensores solo hablan con sus vecinos más cercanos de la red", 0.6),
        ("un reloj central sería un punto único de fallo que quiero evitar", 0.6),
        ("cada sensor ajusta su hora mirando la de sus vecinos poco a poco", 0.6),
        # vida y lecturas tangenciales (poco reforzadas: se sepultarán)
        ("de niña veía las luciérnagas del jardín parpadear todas a la vez", 0.3),
        ("leí que las luciérnagas se sincronizan sin ninguna que dirija", 0.35),
        ("el café de la esquina cambió su mezcla de tueste este mes", 0.2),
        ("mi abuela contaba historias de pescadores al anochecer", 0.2),
        ("el corazón late gracias a células que se acompasan entre vecinas", 0.4),
    ]
    for t, imp in recuerdos:
        r = hc.remember(t, imp)
        print(f"  {'· recordado' if r['stored'] else '· (ya lo sabía)'}: {t[:52]}")

    titulo("FIN DE SEMANA · Duerme: consolida lo repetido")
    print("  ", hc.consolidate())

    titulo("PASAN LAS SEMANAS · El tiempo poda lo trivial (a latente)")
    hc.store.db.execute("UPDATE memories SET last_access = ? WHERE importance < 0.45",
                        (time.time() - 120 * 86400,))
    hc.store.commit()
    print("  olvido:", hc.forget(dry_run=False))
    print("  estado:", {k: hc.stats()[k] for k in ("episodicos_activos", "latentes")})

    titulo("DE MADRUGADA · Sueña: PROPONE puentes entre ideas lejanas")
    sueno = hc.dream(max_bridges=3, dry_run=False)   # registra como hipótesis
    for b in sueno.get("bridges", []):
        print(f"  hipótesis: {b['hypothesis']}")
    if not sueno.get("bridges"):
        print("  (esta noche no surgieron puentes nuevos)")
    print("\n  Nota: son HIPÓTESIS. No influyen en la memoria hasta confirmarlas")
    print("  con hc_accept_bridge — lo especulativo no contamina lo observado.")

    titulo("A LA MAÑANA SIGUIENTE · Sigue atascada. Piensa en voz alta:")
    print("  «necesito que la red se ponga de acuerdo sola, sin nadie al mando»\n")
    print("  → muse busca inspiración (incluye lo sepultado):\n")
    ideas = hc.muse("que la red se sincronice sola sin nadie al mando", k=4)
    for idea in ideas:
        marca = " ✨ RESURGIÓ de la infancia/lecturas" if idea["resurgido"] else ""
        print(f"  • «{idea['text']}»{marca}")
        if idea.get("conectado_por"):
            print(f"      ↳ por: «{idea['conectado_por'][:55]}»")

    eureka = next((i for i in ideas if i["resurgido"]), None)
    titulo("EUREKA")
    if eureka:
        print(f"  Un recuerdo sepultado resurgió y ató el problema con una analogía:")
        print(f"    «{eureka['text']}»")
        print("  → Y si los sensores se sincronizan COMO LAS LUCIÉRNAGAS: sin líder,")
        print("    solo mirando a los vecinos y ajustándose... ¡ahí está la solución!")
    else:
        print("  (Esta vez no resurgió nada; la incubación no siempre da fruto —")
        print("   como en la mente real. Vuelve a intentarlo otra noche.)")
    hc.store.close()
    limpiar()


if __name__ == "__main__":
    main()
