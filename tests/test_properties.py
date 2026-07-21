"""
Pruebas GENERATIVAS ESPONTÁNEAS (estilo property-based).

En vez de casos escritos a mano, estas pruebas FABRICAN datos nuevos en cada
ejecución (con una semilla distinta por ronda) y comprueban que las PROMESAS del
sistema se cumplen SIEMPRE, no solo en ejemplos afortunados. Si alguna invariante
se rompe con algún dato generado, el test falla y te enseña el contraejemplo.

Ejecuta:  python tests/test_properties.py
"""

import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.encoder import encode_text          # noqa: E402
from hipercampo.memory import Hipercampo             # noqa: E402
from hipercampo.vsa import bind, bundle, random_hv, similarity   # noqa: E402

_DB = "data/_test_props.db"
_open: Hipercampo | None = None

SUJETOS = ["el sistema", "el usuario", "el agente", "la API", "el cluster",
           "el modelo", "la caché", "el worker", "la cola", "el índice"]
VERBOS = ["procesó", "rechazó", "almacenó", "reintentó", "descartó",
          "priorizó", "duplicó", "consolidó", "expiró", "recuperó"]
OBJETOS = ["la petición", "el token", "el lote", "la sesión", "el evento",
           "el registro", "la transacción", "el mensaje", "el snapshot", "la tarea"]
COLAS = ["de madrugada", "bajo carga", "sin errores", "con latencia alta",
         "tras el reinicio", "en la región este", "por timeout", "manualmente"]


def frase(rng) -> str:
    return f"{rng.choice(SUJETOS)} {rng.choice(VERBOS)} {rng.choice(OBJETOS)} {rng.choice(COLAS)}"


def fresh() -> Hipercampo:
    global _open
    if _open is not None:
        _open.store.close()
    Path(_DB).unlink(missing_ok=True)
    _open = Hipercampo(_DB)
    return _open


# ---------------------------------------------------------------------------
# INVARIANTE 1: un duplicado exacto NUNCA crea un segundo recuerdo.
# ---------------------------------------------------------------------------
def prop_duplicado_no_crece(rng):
    hc = fresh()
    f = frase(rng)
    hc.remember(f, 0.5)
    for _ in range(5):
        hc.remember(f, 0.5)             # el mismo, cinco veces
    assert hc.stats()["total"] == 1, f"un duplicado se duplicó: «{f}»"


# ---------------------------------------------------------------------------
# INVARIANTE 2: re-escribir algo idéntico es MENOS novedoso que algo nuevo.
# (la sorpresa mide de verdad la novedad relativa)
# ---------------------------------------------------------------------------
def prop_novedad_ordena_bien(rng):
    hc = fresh()
    base = frase(rng)
    hc.remember(base, 0.5)
    nov_dup = hc.remember(base, 0.5)["novelty"]
    # una frase con sujeto/verbo/objeto distintos debería ser más novedosa
    nueva = "el planeta orbitó una estrella lejana silenciosamente"
    nov_new = hc.remember(nueva, 0.5)["novelty"]
    assert nov_new > nov_dup, f"novedad mal ordenada: dup={nov_dup} new={nov_new}"


# ---------------------------------------------------------------------------
# INVARIANTE 3: una "aguja" plantada se recupera entre muchos distractores.
# ---------------------------------------------------------------------------
def prop_aguja_en_el_pajar(rng):
    hc = fresh()
    for _ in range(25):                          # pajar de ruido
        hc.remember(frase(rng), 0.3)
    aguja = "la clave secreta del cofre es un dragón púrpura dormido"
    hc.remember(aguja, 0.9)
    hits = hc.recall("¿cuál es la clave secreta del cofre?", k=3)
    textos = [h["text"] for h in hits]
    assert aguja in textos, f"no encontró la aguja entre 25 distractores: {textos}"


# ---------------------------------------------------------------------------
# INVARIANTE 4: el olvido NUNCA borra un recuerdo importante (>=0.8).
# ---------------------------------------------------------------------------
def prop_olvido_respeta_importancia(rng):
    hc = fresh()
    criticos = []
    for _ in range(10):
        f = frase(rng)
        imp = rng.choice([0.1, 0.2, 0.9, 0.95])
        r = hc.remember(f, imp)
        if r.get("stored") and imp >= 0.8:
            criticos.append(r["id"])
    # envejecer todo un año y forzar el olvido
    hc.store.db.execute("UPDATE memories SET last_access = ?", (time.time() - 365 * 86400,))
    hc.store.commit()
    hc.forget(dry_run=False)
    vivos = {r["id"] for r in hc.store.all(only_active=False)}
    for cid in criticos:
        assert cid in vivos, f"se olvidó un recuerdo importante (id={cid})"


# ---------------------------------------------------------------------------
# INVARIANTE 5: consolidar NUNCA aumenta los episódicos activos (solo condensa).
# ---------------------------------------------------------------------------
def prop_consolidar_no_crece(rng):
    hc = fresh()
    for _ in range(15):
        hc.remember(frase(rng), 0.5)
    antes = hc.stats()["episodicos_activos"]
    hc.consolidate()
    despues = hc.stats()["episodicos_activos"]
    assert despues <= antes, f"consolidar aumentó episódicos: {antes}->{despues}"


# ---------------------------------------------------------------------------
# INVARIANTE 6 (VSA puro): bind es su propia inversa, para CUALQUIER par.
# ---------------------------------------------------------------------------
def prop_bind_involutivo(rng):
    a = random_hv(rng.randrange(2**31))
    b = random_hv(rng.randrange(2**31))
    assert (bind(bind(a, b), b) == a).all(), "bind no fue reversible"


# ---------------------------------------------------------------------------
# INVARIANTE 7 (VSA puro): un bundle se parece a TODOS sus componentes más
# que dos vectores al azar entre sí. (la superposición realmente "contiene")
# ---------------------------------------------------------------------------
def prop_bundle_contiene(rng):
    comps = [random_hv(rng.randrange(2**31)) for _ in range(rng.randint(3, 7))]
    mezcla = bundle(comps)
    for c in comps:
        assert similarity(mezcla, c) > 0.55, "el bundle no recuerda a un componente"


PROPS = [prop_duplicado_no_crece, prop_novedad_ordena_bien, prop_aguja_en_el_pajar,
         prop_olvido_respeta_importancia, prop_consolidar_no_crece,
         prop_bind_involutivo, prop_bundle_contiene]

RONDAS = 8   # cada invariante se prueba con 8 juegos de datos distintos


if __name__ == "__main__":
    fails = 0
    for prop in PROPS:
        errores = []
        for ronda in range(RONDAS):
            rng = random.Random(1000 + ronda)      # semilla distinta, reproducible
            try:
                prop(rng)
            except AssertionError as e:
                errores.append(f"ronda {ronda}: {e}")
        if errores:
            fails += 1
            print(f"FAIL {prop.__name__}  ({len(errores)}/{RONDAS} rondas)")
            for e in errores[:3]:
                print(f"      {e}")
        else:
            print(f"ok   {prop.__name__}  ({RONDAS}/{RONDAS} rondas)")
    if _open is not None:
        _open.store.close()
    Path(_DB).unlink(missing_ok=True)
    print(f"\n{'TODAS LAS INVARIANTES SE SOSTIENEN' if not fails else f'{fails} INVARIANTES ROTAS'}")
    sys.exit(1 if fails else 0)
