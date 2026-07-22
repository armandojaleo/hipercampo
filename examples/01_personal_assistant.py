"""
Caso de uso 1 · Asistente personal con memoria entre sesiones.
Ejecuta:  python examples/01_personal_assistant.py

Claude recuerda quién eres y tus preferencias, las actualiza cuando cambian, y
distingue lo importante de lo trivial. Simula tres "sesiones".
"""

import sys
from pathlib import Path

# Salida UTF-8 aunque se redirija (en Windows, cp1252 rompe con «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

DB = "data/ex_assistant.db"


def limpiar():
    for s in ("", "-wal", "-shm"):
        Path(DB + s).unlink(missing_ok=True)


def main():
    limpiar()
    hc = Hipercampo(DB, namespace="usuario")

    print("── Sesión 1: te conoce ──")
    for texto, imp in [("me llamo Ana y soy diseñadora UX", 0.9),
                       ("prefiero explicaciones visuales con ejemplos", 0.8),
                       ("uso Figma a diario", 0.6),
                       ("hoy tengo dolor de cabeza", 0.2)]:
        r = hc.remember(texto, imp)
        print(f"  guardado: «{texto}»" if r["stored"] else f"  (ya lo sabía)")

    print("\n── Sesión 2: un dato cambia ──")
    r = hc.update("uso Figma a diario", "ahora uso Penpot a diario en vez de Figma")
    if r.get("superseded_id"):
        print(f"  actualizado: Figma → Penpot  (el viejo #{r['superseded_id']} queda como historia)")
    else:
        print(f"  guardado como dato nuevo (no había match fiable que reemplazar)")

    print("\n── Sesión 3: Claude consulta antes de responder ──")
    for pregunta in ["¿cómo se llama y a qué se dedica?",
                     "¿qué herramienta de diseño usa ahora?",
                     "¿cómo prefiere las explicaciones?"]:
        hits = hc.recall(pregunta, k=1)
        resp = hits[0]["text"] if hits else "(no lo sé)"
        print(f"  P: {pregunta}\n     → {resp}")

    print("\n  Nota: 'Figma' quedó como historia (superado por Penpot); 'dolor de")
    print("  cabeza' es trivial y se desvanecerá. Lo importante perdura.")
    hc.store.close()
    limpiar()


if __name__ == "__main__":
    main()
