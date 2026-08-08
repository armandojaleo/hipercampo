"""
AUDITORÍA de la inyección automática (el hook UserPromptSubmit corre en CADA turno).
Mide lo que de verdad importa para que hipercampo AHORRE tokens en vez de quemarlos:
  - coste real por turno (media/p95/máx, del registro auditable)
  - tasa de inyección (cuántos turnos inyectan algo vs se callan)
  - RELEVANCIA: de lo inyectado, ¿cuánto es del tema (namespace) correcto vs ruido cruzado?
    (con HIPERCAMPO_LINKED=* se leen TODOS los proyectos: aquí se ve el coste de eso.)

Uso:
  python scripts/injection_audit.py            # sobre la memoria real
  python scripts/injection_audit.py --json
"""
import argparse
import json
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from hipercampo import audit, budget                       # noqa: E402
from hipercampo.config import db_path                       # noqa: E402
from hipercampo.memory import Hipercampo                   # noqa: E402

# batería etiquetada por el tema esperado (el namespace que DEBERÍA dominar la inyección)
PROMPTS = [
    ("proj-hipercampo", "¿cómo funciona el grafo navegable y el recall en hipercampo?"),
    ("proj-hipercampo", "¿qué decidimos sobre el rumbo del release y las ramas?"),
    ("proj-hipercampo", "recuérdame cómo va la fase de evidencia y el paper"),
    ("proj-hipercampo", "¿qué es la abstención y el olvido en la memoria?"),
    ("proj-hipercampo", "estado del visor y la extensión de VS Code"),
    ("proj-player", "¿cómo se comparten listas en M Player?"),
    ("proj-player", "¿cómo genera listas con IA el player?"),
    ("personal", "¿cómo prefiere Armando que le respondan?"),
    ("generic", "escribe un bucle for en python que sume una lista"),
    ("generic", "¿qué tiempo hace hoy en Madrid?"),
]


def coste_real():
    """Distribución del coste de inyección del registro auditable real."""
    toks = []
    for ln in audit.tail(0, accion="tokens"):
        m = re.search(r"(\d+) tok", ln)
        if m and "inyect" in ln.lower():
            toks.append(int(m.group(1)))
    if not toks:
        return {}
    toks.sort()

    def p(q):
        return toks[min(len(toks) - 1, int(q * len(toks)))]
    return {"inyecciones": len(toks), "media": round(sum(toks) / len(toks)),
            "p50": p(0.5), "p95": p(0.95), "max": toks[-1],
            "caros_>200": sum(1 for t in toks if t > 200)}


def audita_relevancia(ns, linked):
    hc = Hipercampo(db_path(), namespace=ns, linked=linked)
    filas = []
    try:
        for tema, prompt in PROMPTS:
            r = hc.assist(prompt)
            accion = r.get("action") or "nothing"
            res = r.get("result") or []
            # coste igual que el hook: cabecera + recuerdos, recortado al presupuesto
            lineas = [f"[memoria · {accion}] {r.get('why', '')}"] + \
                     [f"- {h.get('text', '')}" for h in res]
            _, gasto = budget.ajustar(lineas)
            nss = [h.get("namespace") for h in res if h.get("namespace")]
            fuera = sum(1 for n in nss if n != tema) if tema not in ("generic",) else 0
            filas.append({"tema": tema, "accion": accion, "n": len(res),
                          "tokens": gasto["tokens"], "ns": nss,
                          "cross": fuera, "total_ns": len(nss)})
    finally:
        hc.close()
    return filas


def resumen(filas):
    inyectan = [f for f in filas if f["accion"] != "nothing" and f["n"] > 0]
    total_ns = sum(f["total_ns"] for f in filas)
    cross = sum(f["cross"] for f in filas)
    toks = [f["tokens"] for f in inyectan] or [0]
    return {
        "prompts": len(filas),
        "inyeccion_rate": round(len(inyectan) / len(filas), 2),
        "tokens_medios_cuando_inyecta": round(sum(toks) / len(toks)),
        "cross_namespace_rate": round(cross / total_ns, 3) if total_ns else 0.0,
        "recuerdos_inyectados": total_ns, "de_otro_tema": cross,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--namespace", default="proj-hipercampo")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    audit.set_logfile(db_path())        # leer el registro REAL (junto a la BD real)
    audit._ENABLED = False
    coste = coste_real()
    # con linking (como el hook real: LINKED=*) vs aislado, para VER el coste del cruce
    con = resumen(audita_relevancia(a.namespace, "*"))
    aislado = resumen(audita_relevancia(a.namespace, ""))
    out = {"coste_real_registro": coste, "linked_*": con, "aislado": aislado}
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2)); return
    print("AUDITORÍA DE INYECCIÓN")
    print("-" * 58)
    if coste:
        print(f"coste real (registro): {coste['inyecciones']} inyecciones · "
              f"media {coste['media']} · p50 {coste['p50']} · p95 {coste['p95']} · "
              f"máx {coste['max']} tok · caras(>200)={coste['caros_>200']}")
    print()
    print(f"{'':<28}{'LINKED=*':>12}{'aislado':>12}")
    for k in ("inyeccion_rate", "tokens_medios_cuando_inyecta",
              "cross_namespace_rate", "de_otro_tema"):
        print(f"{k:<28}{str(con[k]):>12}{str(aislado[k]):>12}")
    print("-" * 58)
    print("cross_namespace_rate alto = recuerdos de OTRO proyecto colándose "
          "(ruido que paga tokens cada turno).")


if __name__ == "__main__":
    main()
