"""
Casos de uso REALES, narrados — ejecuta:  python scripts/scenarios.py

Cuenta la historia de un asistente (Claude) que usa hipercampo como memoria a lo
largo de varias "sesiones" con un usuario. No es un test con asserts: es una
demostración legible de que el sistema aporta algo útil de verdad.
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


def linea(c="─"):
    print(c * 64)


def sesion(titulo):
    print()
    linea("═")
    print(f"  {titulo}")
    linea("═")


def main():
    Path("data/scenarios.db").unlink(missing_ok=True)
    hc = Hipercampo("data/scenarios.db")

    # ---- Sesión 1: el usuario se presenta -------------------------------
    sesion("SESIÓN 1 · El usuario cuenta cosas de sí mismo")
    hechos = [
        ("me llamo Armando y soy desarrollador", 0.9),
        ("prefiero respuestas honestas y directas sin rodeos", 0.9),
        ("estoy construyendo un proyecto llamado hipercampo", 0.8),
        ("odio que me hagan la pelota", 0.7),
        ("hoy he dormido mal", 0.2),                       # trivial, efímero
    ]
    for texto, imp in hechos:
        r = hc.remember(texto, imp)
        marca = "✓ recordado" if r["stored"] else "· ya lo sabía"
        print(f"  usuario: «{texto}»\n           {marca} (novedad {r['novelty']:.2f})")

    # ---- Sesión 2: intenta colar redundancia ----------------------------
    sesion("SESIÓN 2 · Repite algo casi idéntico (no debe duplicar)")
    r = hc.remember("me llamo Armando y trabajo como desarrollador", 0.9)
    print("  usuario: «me llamo Armando y trabajo como desarrollador»")
    veredicto = '✓ recordado' if r['stored'] else '· reconocido como conocido → reforzado'
    print(f"           {veredicto}")

    # ---- Claude necesita recordar antes de responder --------------------
    sesion("SESIÓN 3 · Claude consulta su memoria antes de responder")
    for pregunta in ["¿cómo se llama el usuario y a qué se dedica?",
                     "¿cómo prefiere que le hable?",
                     "¿en qué proyecto trabaja?"]:
        print(f"\n  Claude se pregunta: {pregunta}")
        for h in hc.recall(pregunta, k=2):
            print(f"     ↳ recuerda «{h['text']}»  (score {h['score']:.2f})")

    # ---- Fase de sueño --------------------------------------------------
    sesion("SESIÓN 4 · Fin del día: Claude 'duerme' (consolida)")
    # añadimos varios episodios parecidos sobre el proyecto
    for extra in ("usa hipervectores", "usa hipervectores no embeddings",
                  "usa hipervectores binarios"):
        hc.remember(f"hipercampo {extra}", 0.6)
    print("  antes de dormir:", hc.stats())
    print("  consolidando... ", hc.consolidate())
    print("  al despertar:   ", hc.stats())
    print("  → varios episodios sueltos se han fundido en conocimiento semántico")

    # ---- El tiempo pasa: olvido de lo trivial ---------------------------
    sesion("SESIÓN 5 · Pasan semanas: se olvida lo trivial, perdura lo importante")
    viejo = time.time() - 60 * 86400
    hc.store.db.execute("UPDATE memories SET last_access = ?", (viejo,))
    hc.store.commit()
    ensayo = hc.forget(dry_run=True)
    print(f"  ensayo de olvido → se olvidarían {ensayo['olvidados']} recuerdos triviales")
    hc.forget(dry_run=False)
    print("  tras olvidar:   ", hc.stats())

    print("\n  ¿Sigue recordando lo importante?")
    for h in hc.recall("¿quién es el usuario y qué prefiere?", k=2):
        print(f"     ↳ «{h['text']}»")
    print("\n  ¿Y lo trivial (dormir mal)?")
    hits = hc.recall("el usuario durmió mal", k=1)
    superviviente = [h for h in hits if "dormido mal" in h["text"]]
    print("     ↳", "aún lo recuerda" if superviviente else "olvidado, como debía ser")

    hc.store.close()
    linea("═")
    print("  Fin. Esto es lo que hipercampo le da a Claude: una memoria que")
    print("  distingue, prioriza, consolida y olvida — como un hipocampo.")
    linea("═")


if __name__ == "__main__":
    main()
