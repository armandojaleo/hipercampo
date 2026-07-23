"""
Calibrar la ABSTENCIÓN midiendo, no opinando.  Ejecuta:
    python scripts/calibrate.py              # N = 20, 100, 500
    python scripts/calibrate.py --n 20,100,500,2000

El ROADMAP pedía "calibrar MIN_RECALL_SCORE midiendo la tasa de falsas
recuperaciones al crecer N". Esto lo hace, y hay una razón para que sea un script
propio y no un test: los tres umbrales que deciden si la memoria responde o se
calla (`MIN_RECALL_SCORE`, `ANSWER_MIN_SCORE`, `RECALL_Z`) son un COMPROMISO, no
un valor correcto. Subirlos calla falsos positivos y también aciertos. Lo único
honesto es enseñar la curva entera y elegir el codo a la vista.

Cómo funciona (y por qué así):
  1. Se ejecuta la memoria UNA vez por consulta con la puerta ABIERTA
     (`memory.GATE_ENABLED = False`), guardando las señales crudas que la puerta
     habría mirado — `Hipercampo.ultima_decision` — más el ranking completo.
  2. Se barren los umbrales sobre esas señales con `memory.abstention_gate`, la
     MISMA función que usa `recall()`. Barrer así cuesta una ejecución en vez de
     una por combinación, y sobre todo garantiza que lo medido es lo que corre en
     producción, no una reimplementación que puede divergir.

Métricas, en tensión deliberada:
  - MRR   (positivas): recuperar bien lo que SÍ se sabe. Más alto mejor.
  - falsaRec (negativas): consultas ajenas que devuelven algo. Más BAJO mejor.
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                       # noqa: E402

from hipercampo import audit, memory                     # noqa: E402
from hipercampo.memory import Hipercampo                 # noqa: E402
from scripts.stress import CASOS, DISTRACTORES           # noqa: E402

# --- consultas NEGATIVAS ---------------------------------------------------
# Las 5 de baselines.py daban una granularidad de 0.20: con 4 de 5 fallando no se
# distingue una mejora real de un empate. Aquí hay 30, de dominios muy lejanos al
# corpus (oficina/tecnología/empresa), para que la tasa signifique algo.
NEGATIVAS = [
    "recetas de cocina tailandesa con leche de coco",
    "resultados de la liga de baloncesto del domingo",
    "cómo plantar tomates en un huerto urbano",
    "historia de la música barroca europea",
    "precio del billete de tren a Sevilla",
    "cuántas calorías tiene un plátano maduro",
    "quién ganó el mundial de fútbol de 1986",
    "cómo se poda un rosal en invierno",
    "qué temperatura hace en Reikiavik en enero",
    "letra de una canción de flamenco antiguo",
    "cómo curar una tendinitis de hombro",
    "mejores playas del Caribe para bucear",
    "cómo se hace una paella valenciana auténtica",
    "biografía del pintor Joaquín Sorolla",
    "cuándo empieza la temporada de esquí alpino",
    "cómo adiestrar a un cachorro de pastor alemán",
    "distancia de la Tierra a la estrella Proxima Centauri",
    "qué se necesita para sacar el carnet de moto",
    "reglas del ajedrez para el enroque largo",
    "cómo hacer pan de masa madre en casa",
    "sinfonías más conocidas de Gustav Mahler",
    "cuánto dura el vuelo de Madrid a Tokio",
    "cómo se llama la capital de Mongolia",
    "trucos para dormir mejor por la noche",
    "qué vacunas necesita un gato doméstico",
    "cómo tejer una bufanda con dos agujas",
    "récord mundial de salto de longitud masculino",
    "ingredientes de un cóctel mojito cubano",
    "cuándo florecen los cerezos en Kioto",
    "cómo se restaura un mueble de madera antiguo",
]

# --- relleno para hacer crecer N -------------------------------------------
# Hechos sintéticos del MISMO dominio que el corpus base (oficina/empresa). Que
# sean del mismo dominio es el punto: relleno de otro tema sería ruido fácil de
# descartar y haría parecer la abstención mejor de lo que es. Estos compiten.
_SUJETOS = ["el equipo de soporte", "el departamento de compras", "la oficina de Bilbao",
            "el turno de noche", "la sala de reuniones grande", "el archivo de contratos",
            "la impresora de la segunda planta", "el comedor de empresa",
            "la centralita telefónica", "el almacén de material"]
_VERBOS = ["se revisa", "se actualiza", "se factura", "se reserva", "se inventaría",
           "se limpia", "se audita", "se renueva", "se supervisa", "se archiva"]
_PERIODOS = ["cada martes", "el primer día del mes", "dos veces al año", "cada trimestre",
             "en la última semana de agosto", "todos los viernes por la tarde",
             "cada quince días", "al cerrar el ejercicio", "cada mañana temprano",
             "una vez por semestre"]
_COLAS = ["según el protocolo interno", "y queda anotado en el registro",
          "salvo festivo nacional", "bajo supervisión de un responsable",
          "con aviso previo por correo", "y se guarda copia en papel",
          "si no hay incidencias abiertas", "conforme al manual de calidad",
          "y se comunica al comité", "sin excepciones desde el año pasado"]


def relleno(n: int) -> list[str]:
    """n hechos distintos y deterministas (sin azar: los resultados deben repetirse).

    Cada uno lleva un CÓDIGO propio. Sin él, las combinaciones de plantilla se
    parecen demasiado entre sí y `remember()` las descarta por redundantes: pedir
    500 dejaba 210 en la base y el eje N del estudio no era el que decía ser.
    """
    out = []
    for i in range(n):
        s = _SUJETOS[i % 10]
        v = _VERBOS[(i // 10) % 10]
        p = _PERIODOS[(i // 100) % 10]
        c = _COLAS[(i // 1000) % 10]
        out.append(f"el expediente {_codigo(i)}: {s} {v} {p} {c}")
    return out


def _codigo(i: int) -> str:
    """Identificador legible y único por índice (determinista, sin azar)."""
    cons, voc = "bcdfgjklmnprstvz", "aeiou"
    return (cons[i % 16] + voc[(i // 16) % 5] + cons[(i // 80) % 16]
            + voc[(i // 1280) % 5] + str(i))


# --- recogida de señales ----------------------------------------------------
def observar(n_objetivo: int, semantico: bool = False) -> dict:
    """Ejecuta la memoria con la puerta ABIERTA y devuelve las señales crudas."""
    from hipercampo import encoder
    encoder.set_semantic_hook(None)
    if semantico and not encoder.enable_semantic():
        raise SystemExit("El régimen semántico necesita sentence-transformers instalado.")

    base = [h for h, _ in CASOS] + DISTRACTORES
    facts = base + relleno(max(0, n_objetivo - len(base)))

    db = Path(f"data/_cal_{'sem' if semantico else 'lex'}_{n_objetivo}.db")
    for suf in ("", "-wal", "-shm"):
        Path(str(db) + suf).unlink(missing_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)

    hc = Hipercampo(str(db), namespace=f"cal{'s' if semantico else 'l'}{n_objetivo}")
    for f in facts:
        hc.remember(f, 0.5)
    guardados = hc.store.all(only_active=False)
    id_por_texto = {r["text"]: r["id"] for r in guardados}
    # N REAL, no el intentado: remember() descarta lo redundante, así que pedir 500
    # hechos no significa tener 500 en la base. Etiquetar la fila con el número que
    # se pidió y no con el que hay sería mentir sobre la escala a la que se midió.
    n_real = len(guardados)

    def sondear(q, objetivo_id=None):
        hits = hc.recall(q, k=len(facts), hops=1, include_history=True)
        diag = dict(hc.ultima_decision)
        # (activación por item, ordenados como los devolvió recall)
        acts = [(h["id"], h["activation"]) for h in hits]
        pos = None
        if objetivo_id is not None:
            ids = [i for i, _ in acts]
            pos = ids.index(objetivo_id) if objetivo_id in ids else None
        return {"diag": diag, "acts": acts, "pos_ids": [i for i, _ in acts],
                "objetivo": objetivo_id, "pos": pos}

    previo, memory.GATE_ENABLED = memory.GATE_ENABLED, False
    try:
        positivas = []
        for hecho, variantes in CASOS:
            oid = id_por_texto.get(hecho)
            for cat, q in variantes.items():
                positivas.append((cat, sondear(q, oid)))
        negativas = [sondear(q) for q in NEGATIVAS]
    finally:
        memory.GATE_ENABLED = previo
        hc.store.close()
        from hipercampo import encoder as _enc
        _enc.set_semantic_hook(None)
    return {"n": n_real, "pedidos": len(facts),
            "positivas": positivas, "negativas": negativas}


# --- evaluación de un juego de umbrales ------------------------------------
def evaluar(obs: dict, min_item: float, suelo: float, z: float) -> dict:
    """Recalcula MRR y falsaRec para unos umbrales, sin reejecutar la memoria."""
    def responde(s):
        # 1) filtro por ITEM (MIN_RECALL_SCORE): qué sobrevive de la lista
        vivos = [(i, a) for i, a in s["acts"] if a >= min_item]
        if not vivos:
            return False, None
        # 2) puerta de ABSTENCIÓN, con la misma función que usa recall()
        directa = np.array(sorted((a for _, a in s["acts"]), reverse=True))
        ok, _ = memory.abstention_gate(directa, len(vivos), semantic=False,
                                       suelo=suelo, zmin=z)
        if not ok:
            return False, None
        ids = [i for i, _ in vivos]
        obj = s["objetivo"]
        return True, (ids.index(obj) if obj in ids else None)

    por_cat: dict[str, list[float]] = {}
    for cat, s in obs["positivas"]:
        ok, pos = responde(s)
        rr = 1.0 / (pos + 1) if (ok and pos is not None) else 0.0
        por_cat.setdefault(cat, []).append(rr)
    mrr = {c: sum(v) / len(v) for c, v in por_cat.items()}
    glob = sum(mrr.values()) / len(mrr)
    falsa = sum(1 for s in obs["negativas"] if responde(s)[0]) / len(obs["negativas"])
    return {"mrr": mrr, "global": glob, "falsaRec": falsa}


def main(ns: list[int], semantico: bool = False):
    audit.set_enabled(False) if hasattr(audit, "set_enabled") else None
    actual = ((memory.MIN_RECALL_SCORE, memory.ANSWER_MIN_SCORE_SEM, memory.RECALL_Z_SEM)
              if semantico else
              (memory.MIN_RECALL_SCORE, memory.ANSWER_MIN_SCORE, memory.RECALL_Z))
    print(f"\nRégimen: {'SEMÁNTICO' if semantico else 'LÉXICO'}")
    print(f"Umbrales actuales: MIN_RECALL_SCORE={actual[0]} "
          f"{'ANSWER_MIN_SCORE_SEM' if semantico else 'ANSWER_MIN_SCORE'}={actual[1]} "
          f"{'RECALL_Z_SEM' if semantico else 'RECALL_Z'}={actual[2]}")
    print(f"Positivas: {len(CASOS) * 3} · Negativas: {len(NEGATIVAS)}\n")

    observaciones = {}
    for n in ns:
        print(f"  … midiendo N={n}", flush=True)
        observaciones[n] = observar(n, semantico)

    # 1) cómo se comportan los umbrales ACTUALES al crecer N -----------------
    print("\n=== Umbrales actuales, al crecer N ===")
    cab = (f"{'N real':>8}{'(pedidos)':>11}{'keyword':>10}{'typo':>10}"
           f"{'synonym':>10}{'global':>9}{'falsaRec':>10}")
    print(cab); print("-" * len(cab))
    for obs in observaciones.values():
        r = evaluar(obs, *actual)
        print(f"{obs['n']:>8}{obs['pedidos']:>11}" + "".join(f"{r['mrr'].get(c, 0):>10.3f}"
              for c in ("keyword", "typo", "synonym"))
              + f"{r['global']:>9.3f}{r['falsaRec']:>10.2f}")

    # 1b) LA distribución: es lo que decide si la abstención puede funcionar -----
    # Si la peor positiva puntúa por debajo de la mejor negativa, NINGÚN umbral
    # absoluto las separa. Enseñarlo evita perseguir un valor que no existe.
    print("\n=== Distribución del mejor ancla directo (`mejor`) ===")
    cab = f"{'N':>7}  {'positivas p5/mediana/p95':>28}  {'negativas p5/mediana/p95':>28}  solape"
    print(cab); print("-" * len(cab))
    for obs in observaciones.values():
        pos = np.array([s["diag"].get("mejor", 0.0) for _, s in obs["positivas"]])
        neg = np.array([s["diag"].get("mejor", 0.0) for s in obs["negativas"]])
        p = np.percentile(pos, [5, 50, 95]); q = np.percentile(neg, [5, 50, 95])
        # fracción de negativas por encima de la positiva mediana: irreducible
        solape = float((neg >= np.median(pos)).mean())
        print(f"{obs['n']:>7}  {p[0]:>8.3f}/{p[1]:.3f}/{p[2]:.3f}      "
              f"  {q[0]:>8.3f}/{q[1]:.3f}/{q[2]:.3f}      {solape:>6.2f}")

    # 2) barrido: el compromiso, a la vista ----------------------------------
    n_max = max(observaciones)
    obs = observaciones[n_max]
    print(f"\n=== Barrido de umbrales (N={obs['n']}) ===")
    cab = (f"{'MIN_ITEM':>9}{'SUELO':>8}{'Z':>6}"
           f"{'keyword':>10}{'typo':>10}{'synonym':>10}{'global':>9}{'falsaRec':>10}")
    print(cab); print("-" * len(cab))
    # El rango se DERIVA de lo observado, no se fija a mano: el régimen semántico
    # comprime las activaciones y una rejilla léxica caería entera fuera de escala.
    _neg = np.array([s["diag"].get("mejor", 0.0) for s in obs["negativas"]])
    _pos = np.array([s["diag"].get("mejor", 0.0) for _, s in obs["positivas"]])
    lo, hi = float(np.percentile(_neg, 5)), float(np.percentile(_pos, 95))
    suelos = [round(lo + (hi - lo) * i / 9, 3) for i in range(10)]

    filas = []
    for min_item in (0.03, 0.08):
        for suelo in suelos:
            for z in (2.0, 3.0):
                r = evaluar(obs, min_item, suelo, z)
                filas.append((min_item, suelo, z, r))
                print(f"{min_item:>9.2f}{suelo:>8.2f}{z:>6.1f}"
                      + "".join(f"{r['mrr'].get(c, 0):>10.3f}"
                                for c in ("keyword", "typo", "synonym"))
                      + f"{r['global']:>9.3f}{r['falsaRec']:>10.2f}")

    # 3) el codo: mejor MRR entre los que más se callan ----------------------
    mejor_falsa = min(f[3]["falsaRec"] for f in filas)
    candidatos = [f for f in filas if f[3]["falsaRec"] <= mejor_falsa + 0.02]
    codo = max(candidatos, key=lambda f: f[3]["global"])
    print(f"\nMejor falsaRec alcanzable: {mejor_falsa:.2f}")
    print(f"Codo (máximo MRR ahí): MIN_RECALL_SCORE={codo[0]} "
          f"ANSWER_MIN_SCORE={codo[1]} RECALL_Z={codo[2]} "
          f"-> MRR {codo[3]['global']:.3f} · falsaRec {codo[3]['falsaRec']:.2f}")
    print("\n(La elección es un COMPROMISO: no hay fila que gane en las dos columnas.)")


if __name__ == "__main__":
    ns = [20, 100, 500]
    for i, a in enumerate(sys.argv):
        if a == "--n" and i + 1 < len(sys.argv):
            ns = [int(x) for x in sys.argv[i + 1].split(",")]
    main(ns, semantico="--semantic" in sys.argv)
