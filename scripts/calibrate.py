"""
Calibrate ABSTENTION through measurement, not opinion. Run:
    python scripts/calibrate.py              # N = 20, 100, 500
    python scripts/calibrate.py --n 20,100,500,2000

The ROADMAP asked to calibrate MIN_RECALL_SCORE by measuring the false-retrieval
rate as N grows. This script does that. It is deliberately a script rather than a
test: the three thresholds deciding whether memory answers or abstains
(`MIN_RECALL_SCORE`, `ANSWER_MIN_SCORE`, `RECALL_Z`) are a TRADE-OFF, not a single
correct value. Raising them suppresses both false positives and correct answers.
The honest approach is to show the whole curve and choose the knee visibly.

How it works:
  1. Run memory ONCE per query with the gate OPEN (`memory.GATE_ENABLED = False`),
     recording the raw signals the gate would inspect (`Hipercampo.last_decision`)
     plus the full ranking.
  2. Sweep thresholds over those signals with `memory.abstention_gate`, the SAME
     function used by `recall()`. This costs one run instead of one per combination
     and guarantees that measurement follows production behavior.

Metrics are deliberately in tension:
  - MRR (positive queries): retrieve known facts well. Higher is better.
  - false recall (negative queries): unrelated queries returning anything. Lower is better.
"""

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np                                       # noqa: E402

from hipercampo.support import audit                     # noqa: E402
from hipercampo.cycle import memory
from hipercampo.cycle.memory import Hipercampo                 # noqa: E402
from scripts.stress import CASES, DISTRACTORS            # noqa: E402

# --- NEGATIVE queries ------------------------------------------------------
# The five queries in baselines.py gave 0.20 granularity, too coarse to distinguish
# a real improvement from a tie. These 30 Spanish retrieval samples come from domains
# far from the office/technology/company corpus, making the rate meaningful.
NEGATIVE_QUERIES = [
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

# --- filler used to grow N -------------------------------------------------
# Synthetic facts come from the SAME domain as the base corpus (office/company).
# That is the point: another topic would be easy noise and make abstention look
# better than it is. Spanish template text is intentional retrieval test data.
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


def filler(n: int) -> list[str]:
    """Return n distinct deterministic facts so results remain reproducible.

    Each fact has a unique CODE. Without it, template combinations look too similar
    and `remember()` rejects them as redundant: requesting 500 left only 210 in the
    database, so the study's N axis did not mean what it claimed.
    """
    out = []
    for i in range(n):
        s = _SUJETOS[i % 10]
        v = _VERBOS[(i // 10) % 10]
        p = _PERIODOS[(i // 100) % 10]
        c = _COLAS[(i // 1000) % 10]
        out.append(f"el expediente {_code(i)}: {s} {v} {p} {c}")
    return out


def _code(i: int) -> str:
    """Return a readable unique identifier for an index, without randomness."""
    cons, voc = "bcdfgjklmnprstvz", "aeiou"
    return (cons[i % 16] + voc[(i // 16) % 5] + cons[(i // 80) % 16]
            + voc[(i // 1280) % 5] + str(i))


# --- signal collection -----------------------------------------------------
def observe(target_n: int, semantic: bool = False) -> dict:
    """Run memory with the gate OPEN and return raw signals."""
    from hipercampo.core import encoder
    encoder.set_semantic_hook(None)
    if semantic and not encoder.enable_semantic():
        raise SystemExit("Semantic mode requires sentence-transformers.")

    base = [fact for fact, _ in CASES] + DISTRACTORS
    facts = base + filler(max(0, target_n - len(base)))

    db = Path(f"data/_cal_{'sem' if semantic else 'lex'}_{target_n}.db")
    for suf in ("", "-wal", "-shm"):
        Path(str(db) + suf).unlink(missing_ok=True)
    db.parent.mkdir(parents=True, exist_ok=True)

    hc = Hipercampo(str(db), namespace=f"cal{'s' if semantic else 'l'}{target_n}")
    for f in facts:
        hc.remember(f, 0.5)
    guardados = hc.store.all(only_active=False)
    id_por_texto = {r["text"]: r["id"] for r in guardados}
    # ACTUAL N, not requested N: remember() rejects redundant data, so requesting 500
    # facts does not guarantee 500 rows. Labeling with the request would misrepresent
    # the scale actually measured.
    n_real = len(guardados)

    def sondear(q, objetivo_id=None):
        hits = hc.recall(q, k=len(facts), hops=1, include_history=True)
        diag = dict(hc.last_decision)
        # Per-item activation in recall order.
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
        for hecho, variantes in CASES:
            oid = id_por_texto.get(hecho)
            for cat, q in variantes.items():
                positivas.append((cat, sondear(q, oid)))
        negativas = [sondear(q) for q in NEGATIVE_QUERIES]
    finally:
        memory.GATE_ENABLED = previo
        hc.store.close()
        from hipercampo.core import encoder as _enc
        _enc.set_semantic_hook(None)
    return {"n": n_real, "pedidos": len(facts),
            "positivas": positivas, "negativas": negativas}


# --- threshold-set evaluation ---------------------------------------------
def evaluar(obs: dict, min_item: float, suelo: float, z: float) -> dict:
    """Recompute MRR and false recall for thresholds without rerunning memory."""
    def responde(s):
        # 1) ITEM filter (MIN_RECALL_SCORE): what survives from the list.
        vivos = [(i, a) for i, a in s["acts"] if a >= min_item]
        if not vivos:
            return False, None
        # 2) ABSTENTION gate, using the same function as recall().
        directa = np.array(sorted((a for _, a in s["acts"]), reverse=True))
        ok, _ = memory.abstention_gate(directa, len(vivos), semantic=False,
                                       floor=suelo, zmin=z)
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
    print(f"\nMode: {'SEMANTIC' if semantico else 'LEXICAL'}")
    print(f"Current thresholds: MIN_RECALL_SCORE={actual[0]} "
          f"{'ANSWER_MIN_SCORE_SEM' if semantico else 'ANSWER_MIN_SCORE'}={actual[1]} "
          f"{'RECALL_Z_SEM' if semantico else 'RECALL_Z'}={actual[2]}")
    print(f"Positive: {len(CASES) * 3} · Negative: {len(NEGATIVE_QUERIES)}\n")

    observaciones = {}
    for n in ns:
        print(f"  … measuring N={n}", flush=True)
        observaciones[n] = observe(n, semantico)

    # 1) CURRENT threshold behavior as N grows -----------------------------
    print("\n=== Current thresholds as N grows ===")
    cab = (f"{'actual N':>8}{'(requested)':>11}{'keyword':>10}{'typo':>10}"
           f"{'synonym':>10}{'global':>9}{'falsaRec':>10}")
    print(cab); print("-" * len(cab))
    for obs in observaciones.values():
        r = evaluar(obs, *actual)
        print(f"{obs['n']:>8}{obs['pedidos']:>11}" + "".join(f"{r['mrr'].get(c, 0):>10.3f}"
              for c in ("keyword", "typo", "synonym"))
              + f"{r['global']:>9.3f}{r['falsaRec']:>10.2f}")

    # 1b) Distribution decides whether abstention can work. If the weakest positive
    # scores below the strongest negative, NO absolute threshold separates them.
    print("\n=== Best direct-anchor (`best`) distribution ===")
    cab = f"{'N':>7}  {'positive p5/median/p95':>28}  {'negative p5/median/p95':>28}  overlap"
    print(cab); print("-" * len(cab))
    for obs in observaciones.values():
        pos = np.array([s["diag"].get("best", 0.0) for _, s in obs["positivas"]])
        neg = np.array([s["diag"].get("best", 0.0) for s in obs["negativas"]])
        p = np.percentile(pos, [5, 50, 95]); q = np.percentile(neg, [5, 50, 95])
        # Fraction of negatives above the median positive: irreducible overlap.
        solape = float((neg >= np.median(pos)).mean())
        print(f"{obs['n']:>7}  {p[0]:>8.3f}/{p[1]:.3f}/{p[2]:.3f}      "
              f"  {q[0]:>8.3f}/{q[1]:.3f}/{q[2]:.3f}      {solape:>6.2f}")

    # 2) Sweep: make the trade-off visible. ---------------------------------
    n_max = max(observaciones)
    obs = observaciones[n_max]
    print(f"\n=== Threshold sweep (N={obs['n']}) ===")
    cab = (f"{'MIN_ITEM':>9}{'SUELO':>8}{'Z':>6}"
           f"{'keyword':>10}{'typo':>10}{'synonym':>10}{'global':>9}{'falsaRec':>10}")
    print(cab); print("-" * len(cab))
    # Derive the range from observations. Semantic mode compresses activations, so
    # a hard-coded lexical grid could fall entirely outside the useful scale.
    _neg = np.array([s["diag"].get("best", 0.0) for s in obs["negativas"]])
    _pos = np.array([s["diag"].get("best", 0.0) for _, s in obs["positivas"]])
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

    # 3) Knee: best MRR among configurations that abstain most. -------------
    mejor_falsa = min(f[3]["falsaRec"] for f in filas)
    candidatos = [f for f in filas if f[3]["falsaRec"] <= mejor_falsa + 0.02]
    codo = max(candidatos, key=lambda f: f[3]["global"])
    print(f"\nBest achievable false recall: {mejor_falsa:.2f}")
    print(f"Knee (maximum MRR there): MIN_RECALL_SCORE={codo[0]} "
          f"ANSWER_MIN_SCORE={codo[1]} RECALL_Z={codo[2]} "
          f"-> MRR {codo[3]['global']:.3f} · falsaRec {codo[3]['falsaRec']:.2f}")
    print("\n(The choice is a TRADE-OFF: no row wins in both columns.)")


if __name__ == "__main__":
    ns = [20, 100, 500]
    for i, a in enumerate(sys.argv):
        if a == "--n" and i + 1 < len(sys.argv):
            ns = [int(x) for x in sys.argv[i + 1].split(",")]
    main(ns, semantico="--semantic" in sys.argv)
