"""
Retrieval-quality benchmark — run: python scripts/benchmark.py

Measure hipercampo retrieval quality numerically. The golden rule of optimization is
MEASURE BEFORE CHANGING. Without this, "improvement" is guesswork.

Metrics over questions with known answers, mixed with distractors:
  hit@1   fraction whose top result IS correct
  hit@3   fraction whose correct result is in the top three
  MRR     Mean Reciprocal Rank: mean 1/(rank of the correct result).
          1.0 = always first; 0.5 = typically second; and so on.
"""

import sys
from pathlib import Path

# Keep UTF-8 output when redirected (Windows cp1252 breaks «» ✨ ─).
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.cycle.memory import Hipercampo             # noqa: E402

# (hecho_a_recordar, pregunta_parafraseada_que_debe_recuperarlo)
QA = [
    ("la clave de la API de pagos empieza por hcdemo_9f",
     "¿cuál es la clave de la API de pagos?"),
    ("el servidor de producción está alojado en Frankfurt",
     "¿dónde está alojado el servidor de producción?"),
    ("el equipo hace la reunión diaria a las nueve de la mañana",
     "¿a qué hora es la reunión diaria del equipo?"),
    ("la contraseña del wifi de la oficina es girasol2024",
     "¿cuál es la contraseña del wifi de la oficina?"),
    ("el cliente más importante es una empresa de logística marítima",
     "¿quién es el cliente más importante?"),
    ("el despliegue de la versión dos falló por un timeout de red",
     "¿por qué falló el despliegue de la versión dos?"),
    ("el backup completo se restaura con el comando restore-all",
     "¿cómo se restaura el backup completo?"),
    ("el pipeline de datos se ejecuta cada noche a las tres",
     "¿cuándo se ejecuta el pipeline de datos?"),
    ("la base de datos del proyecto orion es postgres replicada",
     "¿qué base de datos usa el proyecto orion?"),
    ("el logo de la empresa es de color naranja intenso",
     "¿de qué color es el logo de la empresa?"),
    ("el presupuesto anual de marketing es de cincuenta mil euros",
     "¿cuál es el presupuesto anual de marketing?"),
    ("el responsable de seguridad se llama Marta Ndiaye",
     "¿quién es el responsable de seguridad?"),
    ("la oficina central está en la calle Serrano de Madrid",
     "¿dónde está la oficina central?"),
    ("el certificado ssl caduca el quince de diciembre",
     "¿cuándo caduca el certificado ssl?"),
    ("el proveedor de correo transaccional es una empresa francesa",
     "¿quién es el proveedor de correo transaccional?"),
]

# Distractors: plausible same-domain noise that answers none of the queries.
DISTRACTORES = [
    "el gato de la oficina se llama Pixel",
    "las sillas nuevas llegaron el martes",
    "hay café descafeinado en la segunda planta",
    "el ascensor estuvo averiado dos días",
    "se cambió la moqueta de la sala de reuniones",
    "el aparcamiento tiene veinte plazas",
    "la impresora del pasillo imprime en color",
    "el termostato está puesto a veintiún grados",
    "los viernes se sale una hora antes",
    "la planta del recibidor necesita más luz",
]


# Hard mode: same answers, but SYNONYM queries share almost no words with the fact.
# This exposes lexical encoder weakness and potential semantic encoder value.
QA_HARD = [
    ("la clave de la API de pagos empieza por hcdemo_9f",
     "¿qué credencial usa el sistema de cobros?"),
    ("el servidor de producción está alojado en Frankfurt",
     "¿en qué ciudad viven las máquinas en vivo?"),
    ("el equipo hace la reunión diaria a las nueve de la mañana",
     "¿cuándo se juntan cada jornada los compañeros?"),
    ("el cliente más importante es una empresa de logística marítima",
     "¿cuál es la principal cuenta que atendemos?"),
    ("el backup completo se restaura con el comando restore-all",
     "¿cómo recupero una copia de seguridad íntegra?"),
    ("la base de datos del proyecto orion es postgres replicada",
     "¿qué almacén de información emplea orion?"),
    ("el responsable de seguridad se llama Marta Ndiaye",
     "¿quién dirige la protección de los sistemas?"),
    ("el certificado ssl caduca el quince de diciembre",
     "¿cuándo expira el cifrado del sitio web?"),
]


def run(dataset=QA) -> dict:
    Path("data/_bench.db").unlink(missing_ok=True)
    hc = Hipercampo("data/_bench.db")

    hechos = {h for h, _ in dataset}
    for hecho in hechos:
        hc.remember(hecho, 0.6)
    for d in DISTRACTORES:
        hc.remember(d, 0.3)

    hit1 = hit3 = 0
    rr_sum = 0.0
    fallos = []
    for hecho, pregunta in dataset:
        hits = hc.recall(pregunta, k=5)
        pos = next((i for i, h in enumerate(hits) if h["text"] == hecho), None)
        if pos == 0:
            hit1 += 1
        if pos is not None and pos < 3:
            hit3 += 1
        rr_sum += 1.0 / (pos + 1) if pos is not None else 0.0
        if pos != 0:
            fallos.append((pregunta, pos, [h["text"][:40] for h in hits[:2]]))

    hc.store.close()
    Path("data/_bench.db").unlink(missing_ok=True)
    n = len(dataset)
    return {"n": n, "hit@1": hit1 / n, "hit@3": hit3 / n, "MRR": rr_sum / n,
            "fallos": fallos}


def _informe(titulo, r):
    print(f"\n{titulo}")
    print(f"  hit@1 = {r['hit@1']:.2f}   hit@3 = {r['hit@3']:.2f}   MRR = {r['MRR']:.3f}")
    if r["fallos"]:
        print(f"  {len(r['fallos'])} no salieron primeras:")
        for preg, pos, _top in r["fallos"]:
            donde = f"pos {pos}" if pos is not None else "NO recuperado"
            print(f"   · «{preg[:48]}» → {donde}")


# Typo mode: misspelled keywords. Character trigrams should help because a typo
# retains nearly all of its trigrams.
QA_TYPO = [
    ("la clave de la API de pagos empieza por hcdemo_9f",
     "¿cuál es la clabe de la API de pgos?"),
    ("el servidor de producción está alojado en Frankfurt",
     "¿dónde está el servidr de produción?"),
    ("la contraseña del wifi de la oficina es girasol2024",
     "¿cuál es la contrseña del wify de la ofcina?"),
    ("el pipeline de datos se ejecuta cada noche a las tres",
     "¿cuándo corre el pipline de dats?"),
    ("la base de datos del proyecto orion es postgres replicada",
     "¿qué base de datos usa el proyecto orin?"),
    ("el responsable de seguridad se llama Marta Ndiaye",
     "¿quién es el responsble de segurdad?"),
]


if __name__ == "__main__":
    modo_sem = "--semantic" in sys.argv
    if modo_sem:
        from hipercampo.core import encoder, semantic
        print("Enabling semantic hook (sentence-transformers)... "
              "(descarga el modelo la 1ª vez)")
        encoder.set_semantic_hook(semantic.make_sentence_transformer_hook())
        print("Hook activo.\n")

    print(f"Distractors: {len(DISTRACTORES)}  |  semantics: {'ON' if modo_sem else 'OFF'}")
    _informe("== EASY (shared keywords) ==", run(QA))
    _informe("== ERRATAS (palabras clave mal escritas) ==", run(QA_TYPO))
    _informe("== HARD (synonyms, almost no shared words) ==", run(QA_HARD))
