"""
Banco de ESTRÉS categorizado — pone a prueba la recuperación de hipercampo en
condiciones duras y compara modo léxico vs semántico, sin piedad.

Ejecuta:
    python scripts/stress.py                # solo léxico
    python scripts/stress.py --semantic     # léxico + hook semántico (descarga modelo)

Tres categorías de consulta sobre los MISMOS hechos:
    keyword   la pregunta comparte palabras distintivas con el hecho
    typo      igual, pero con las palabras clave MAL escritas
    synonym   parafraseada con sinónimos, casi sin palabras compartidas

El corpus incluye hechos del MISMO dominio que se confunden entre sí (distractores
"confusos"), no ruido fácil. Mide MRR y hit@1 por categoría.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

# hecho -> {categoria: pregunta}
CASOS = [
    ("la clave de la API de pagos empieza por sk_live_9f", {
        "keyword": "¿cuál es la clave de la API de pagos?",
        "typo": "¿cuál es la clabe de la API de pgos?",
        "synonym": "¿qué credencial usa la pasarela de cobros?"}),
    ("el servidor de producción está alojado en Frankfurt", {
        "keyword": "¿dónde está alojado el servidor de producción?",
        "typo": "¿dónde está el servidr de produción?",
        "synonym": "¿en qué ciudad se hospedan las máquinas en vivo?"}),
    ("la base de datos de analítica es un ClickHouse en la región este", {
        "keyword": "¿qué base de datos se usa para analítica?",
        "typo": "¿qué base de dtos se usa para analitca?",
        "synonym": "¿qué almacén guarda las métricas de negocio?"}),
    ("el backup completo se restaura con el comando restore-all", {
        "keyword": "¿cómo se restaura el backup completo?",
        "typo": "¿cómo se restora el bakup completo?",
        "synonym": "¿de qué modo recupero una copia íntegra?"}),
    ("el responsable de seguridad se llama Marta Ndiaye", {
        "keyword": "¿quién es el responsable de seguridad?",
        "typo": "¿quién es el responsble de segurdad?",
        "synonym": "¿quién dirige la protección de los sistemas?"}),
    ("el certificado ssl del dominio caduca el quince de diciembre", {
        "keyword": "¿cuándo caduca el certificado ssl?",
        "typo": "¿cuándo caduca el certifcado ssl?",
        "synonym": "¿cuándo expira el cifrado del sitio web?"}),
    ("el pipeline de datos se ejecuta cada noche a las tres", {
        "keyword": "¿cuándo se ejecuta el pipeline de datos?",
        "typo": "¿cuándo corre el pipeln de dtos?",
        "synonym": "¿a qué hora procesa el flujo de información?"}),
    ("el cliente más importante es una empresa de logística marítima", {
        "keyword": "¿quién es el cliente más importante?",
        "typo": "¿quién es el clinte más imortante?",
        "synonym": "¿cuál es nuestra principal cuenta de transporte por mar?"}),
    ("el presupuesto anual de marketing es de cincuenta mil euros", {
        "keyword": "¿cuál es el presupuesto anual de marketing?",
        "typo": "¿cuál es el presupesto anual de marketng?",
        "synonym": "¿cuánto dinero hay al año para publicidad?"}),
    ("la oficina central está en la calle Serrano de Madrid", {
        "keyword": "¿dónde está la oficina central?",
        "typo": "¿dónde está la oficna central?",
        "synonym": "¿en qué domicilio está la sede principal?"}),
]

# Distractores del MISMO universo (confusos): comparten vocabulario pero no
# responden a ninguna pregunta.
DISTRACTORES = [
    "la clave de la wifi de invitados se renueva cada mes",
    "el servidor de pruebas se reinicia los domingos",
    "la base de datos de usuarios es un postgres replicado",
    "el backup incremental corre cada hora en segundo plano",
    "el responsable de infraestructura se llama Luis Prieto",
    "el certificado del correo se renovó en enero",
    "el pipeline de facturación se lanza los días uno",
    "el cliente nuevo es una startup de energía solar",
    "el presupuesto de formación es de diez mil euros",
    "la oficina satélite está en Lisboa",
]


def evaluar(hc, casos, categoria):
    hit1 = 0
    rr = 0.0
    fallos = []
    for hecho, qs in casos:
        hits = hc.recall(qs[categoria], k=5)
        pos = next((i for i, h in enumerate(hits) if h["text"] == hecho), None)
        if pos == 0:
            hit1 += 1
        rr += 1.0 / (pos + 1) if pos is not None else 0.0
        if pos != 0:
            fallos.append((qs[categoria], pos))
    n = len(casos)
    return {"hit@1": hit1 / n, "MRR": rr / n, "fallos": fallos}


def cargar():
    Path("data/_stress.db").unlink(missing_ok=True)
    hc = Hipercampo("data/_stress.db")
    for hecho, _ in CASOS:
        hc.remember(hecho, 0.6)
    for d in DISTRACTORES:
        hc.remember(d, 0.4)
    return hc


if __name__ == "__main__":
    if "--semantic" in sys.argv:
        from hipercampo import encoder
        print("Activando semántica (descarga modelo la 1ª vez)...")
        ok = encoder.enable_semantic()
        print("semántica:", "ACTIVA" if ok else "NO disponible (modo léxico)")

    hc = cargar()
    print(f"\nCorpus: {len(CASOS)} hechos + {len(DISTRACTORES)} distractores confusos")
    print(f"{'categoría':10} {'hit@1':>7} {'MRR':>7}")
    print("-" * 26)
    total_mrr = 0.0
    for cat in ("keyword", "typo", "synonym"):
        r = evaluar(hc, CASOS, cat)
        total_mrr += r["MRR"]
        print(f"{cat:10} {r['hit@1']:>7.2f} {r['MRR']:>7.3f}")
    print("-" * 26)
    print(f"{'GLOBAL':10} {'':>7} {total_mrr / 3:>7.3f}")
    hc.store.close()
    Path("data/_stress.db").unlink(missing_ok=True)
