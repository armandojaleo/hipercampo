"""
El coste en tokens es una promesa, así que se comprueba como tal.

Una memoria que crece sin techo acaba comiéndose la ventana de contexto del
usuario. Estos tests fijan el suelo: que el presupuesto se respete, que el recorte
se DIGA en vez de esconderse, y que hipercampo no interrumpa cuando nadie le ha
preguntado y no tiene nada claramente relevante que decir.
"""

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo import budget  # noqa: E402
from hipercampo.memory import Hipercampo  # noqa: E402
from hipercampo.policy import VOLUNTEER_MIN_SIM, _decide  # noqa: E402

_TMP = Path(tempfile.mkdtemp(prefix="hc_budget_"))
_DB = str(_TMP / "presupuesto.db")


def _memoria():
    hc = Hipercampo(_DB, namespace="presupuesto")
    hc.remember("el servidor de produccion esta alojado en Frankfurt con IP fija", 0.8)
    hc.remember("los despliegues se hacen los martes por la manana, nunca en viernes", 0.8)
    hc.remember("la clave de la API de mapas se guarda en el gestor de secretos", 0.8)
    return hc


# --- estimación -------------------------------------------------------------

def test_estimar_es_proporcional_al_texto():
    corto = budget.estimate_tokens("hola")
    largo = budget.estimate_tokens("hola " * 100)
    assert 0 < corto < largo
    assert budget.estimate_tokens("") == 0


def test_se_admite_que_es_una_estimacion():
    """La cuenta es SIEMPRE aproximada, también con tiktoken instalado.

    tiktoken/cl100k_base es el tokenizador de OpenAI y aquí se mide lo que cuesta
    en Claude, cuyo tokenizador no es público: con él la estimación mejora, pero
    no se vuelve exacta. Antes se declaraba exacta, que es justo lo que este
    proyecto no hace."""
    assert budget.es_estimacion() is True
    assert budget.metodo(), "hay que poder DECIR con qué se ha contado"


def test_se_dice_con_que_se_ha_contado():
    m = budget.metodo()
    assert ("tiktoken" in m) == (budget._real() is not None)
    if budget._real() is not None:
        assert "OpenAI" in m, "no puede callar de quién es el tokenizador"


# --- recorte ----------------------------------------------------------------

def test_truncar_respeta_el_limite_y_marca_el_corte():
    texto = "palabra " * 200
    corto = budget.truncar(texto, 20)
    assert budget.estimate_tokens(corto) <= 25          # margen del marcador
    assert corto.endswith("[…]"), "un corte silencioso se lee como texto corrupto"


def test_truncar_no_parte_palabras_por_la_mitad():
    texto = "supercalifragilisticoespialidoso " * 20
    corto = budget.truncar(texto, 10).replace(" […]", "")
    for palabra in corto.split():
        assert palabra in texto, "cortó a mitad de palabra"


def test_texto_corto_no_se_toca():
    assert budget.truncar("dos palabras", 500) == "dos palabras"


# --- ajuste al presupuesto --------------------------------------------------

def test_ajustar_respeta_el_presupuesto():
    lineas = ["[cabecera]"] + [f"- recuerdo largo numero {i} " + "relleno " * 60
                               for i in range(10)]
    salida, informe = budget.ajustar(lineas, 200)
    assert informe["tokens"] <= 200, informe          # el techo es el techo
    assert informe["original"] > 1000, "el caso de prueba no era grande"


def test_el_aviso_de_omision_cabe_dentro_del_presupuesto():
    """El aviso también cuesta tokens. Se añade al final, así que si no se reserva
    antes el presupuesto se incumple justo al aplicarlo (medido: 40 -> 52, un 30%
    de más). Un presupuesto que se pasa no es un presupuesto."""
    for tope in (30, 40, 60, 120, 350):
        lineas = ["[cabecera]"] + [f"- dato util numero {i} para el equipo"
                                   for i in range(4)] + ["x " * 400]
        salida, informe = budget.ajustar(lineas, tope)
        real = sum(budget.estimate_tokens(x) for x in salida)
        assert real <= tope, f"presupuesto {tope} superado: {real} · {informe}"
        assert informe["tokens"] == real, "el informe no cuadra con la salida real"


def test_la_cabecera_siempre_entra():
    salida, _ = budget.ajustar(["[cabecera]", "x " * 5000], 30)
    assert salida[0] == "[cabecera]"


def test_la_omision_se_dice_y_se_dice_como_recuperarla():
    salida, informe = budget.ajustar(["[cabecera]"] + ["y " * 400] * 5, 100)
    assert informe["omitidas"]
    aviso = "\n".join(salida)
    assert "no caben" in aviso, "omitir en silencio hace creer que lo tiene todo"
    assert "hc_recall" in aviso, "hay que decir cómo recuperar lo que falta"


def test_los_recuerdos_entran_enteros_o_no_entran():
    """Un recuerdo cortado por la mitad parece información y no lo es: quien lo
    lee responde con confianza sobre un dato mutilado."""
    entero = "- dato critico: la clave vive en el gestor de secretos, nunca en git"
    salida, _ = budget.ajustar(["[cabecera]", entero, "x " * 500], 60)
    cuerpo = [ln for ln in salida if ln.startswith("- ")]
    assert entero in cuerpo, "recortó un recuerdo en vez de omitirlo"
    assert not any("[…]" in ln for ln in salida), "quedó un muñón de recuerdo"


def test_uno_corto_puede_colarse_donde_no_cabia_uno_largo():
    largo, corto = "- " + "relleno " * 200, "- dato breve pero util"
    salida, _ = budget.ajustar(["[cabecera]", largo, corto], 60)
    assert corto in salida and largo not in salida


def test_sin_presupuesto_no_se_omite_nada():
    lineas = ["[cabecera]", "z " * 2000]
    salida, informe = budget.ajustar(lineas, 0)
    assert salida == lineas and informe["omitidas"] == 0


# --- no interrumpir sin motivo ---------------------------------------------

def test_no_interrumpe_cuando_nadie_pregunta_y_no_hay_nada_claro():
    """El caso medido que motivó todo esto: una orden técnica cualquiera hacía
    inyectar cientos de tokens de contexto que no venían a cuento."""
    hc = _memoria()
    for ruido in ["arregla el bug del boton", "commitea los cambios",
                  "gracias, buen trabajo", "ponme un ejemplo en python"]:
        r = _decide(hc, ruido, k=3)
        assert r["action"] == "nothing", f"interrumpió con: {ruido} -> {r}"


def test_si_preguntan_sigue_respondiendo():
    """El filtro anterior no puede volver muda a la memoria: preguntar es
    justamente el caso en el que debe hablar."""
    hc = _memoria()
    r = _decide(hc, "¿donde esta alojado el servidor de produccion?", k=3)
    assert r["action"] == "recall" and r["result"], r


def test_la_similitud_directa_viaja_en_cada_resultado():
    """El filtro se apoya en ella, así que si desaparece hay que enterarse aquí y
    no en producción."""
    hc = _memoria()
    hits = hc.recall("despliegues de los martes", k=3)
    assert hits and all("sim" in h for h in hits)
    assert all(0.0 <= h["sim"] <= 1.0 for h in hits)


def test_un_que_atono_no_cuela_como_pregunta():
    """El agujero por el que seguía entrando el ruido: el interrogativo SIN tilde.

    «que» átono es de las palabras más frecuentes del español, así que "espera que
    termine" o "creo que esto está mal" se clasificaban como preguntas y entraban
    por la rama que inyecta memoria SIN exigir relevancia alta. Medido en una
    sesión real: 2 de 3 turnos inyectaron memoria de otro proyecto sin que nadie
    preguntase nada.

    Ojo: el listón es de RELEVANCIA, no de gramática. Un mensaje con «que» átono
    que además va del tema (ej. "haz lo que te digo con el servidor") sí responde,
    y debe: ahí la memoria encaja de verdad. Lo que se cierra es inyectar cuando
    ni preguntó ni viene a cuento."""
    hc = _memoria()
    for atono in ["espera que termine la sesion que estamos mejorando",
                  "creo que esto esta mal",
                  "haz lo que te digo y no preguntes",
                  "lo que pasa es que no compila"]:
        r = _decide(hc, atono, k=3)
        assert r["action"] == "nothing", f"coló como pregunta: {atono} -> {r}"


def test_una_pregunta_de_verdad_sigue_respondiendo():
    """Cerrar el agujero no puede volver muda a la memoria: con tilde o con signos,
    es una pregunta y hay que contestarla."""
    hc = _memoria()
    for clara in ["¿donde esta alojado el servidor de produccion?",
                  "qué sabes del servidor de produccion",
                  "recuerdas donde esta alojado el servidor de produccion"]:
        r = _decide(hc, clara, k=3)
        assert r["action"] == "recall" and r["result"], f"se calló ante: {clara}"


def test_una_pregunta_dudosa_responde_si_encaja_de_sobra():
    """Sin tilde no sabemos si preguntó, así que se le exige el listón de hablar
    sin que nadie pregunte: si la memoria encaja claramente, contesta igual."""
    hc = _memoria()
    r = _decide(hc, "donde esta alojado el servidor de produccion", k=3)
    if r["action"] == "recall":
        assert all(h["sim"] >= VOLUNTEER_MIN_SIM for h in r["result"]), \
            "una pregunta dudosa no puede inyectar por debajo del listón"


def test_una_variable_de_entorno_ilegible_no_tumba_el_arranque():
    """budget se importa desde el servidor MCP: un int() suelto al importar
    convierte un typo en .mcp.json en 'no arranca', con stacktrace."""
    env = dict(os.environ, HIPERCAMPO_HOOK_BUDGET="abc",
               HIPERCAMPO_IDENTITY_BUDGET="-")
    r = subprocess.run(
        [sys.executable, "-c",
         "import hipercampo.budget as b; print(b.HOOK_BUDGET, b.IDENTITY_BUDGET)"],
        capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, f"un valor ilegible tumbó el import: {r.stderr}"
    assert r.stdout.split() == ["350", "500"], r.stdout
    assert "no es un número" in r.stderr, "hay que AVISAR de que se ignoró el valor"


def test_el_umbral_de_interrupcion_es_mas_exigente_que_el_de_respuesta():
    from hipercampo.policy import VOLUNTEER_MIN_SCORE
    assert VOLUNTEER_MIN_SIM > VOLUNTEER_MIN_SCORE, \
        "si nadie ha preguntado, callarse es gratis y equivocarse cuesta tokens"


# --- coste real del hook, de punta a punta ---------------------------------

def _hook(prompt: str, env: dict) -> str:
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", "hook"],
                       input=json.dumps({"prompt": prompt}), capture_output=True,
                       text=True, encoding="utf-8", env=env)
    d = json.loads(r.stdout or "{}")
    return d.get("hookSpecificOutput", {}).get("additionalContext", "")


def test_el_hook_no_se_pasa_del_presupuesto():
    hc = _memoria()
    for i in range(6):                                # recuerdos largos de verdad
        hc.remember(f"nota {i} sobre el despliegue: " + "detalle importante " * 40, 0.9)
    hc.close()
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="presupuesto",
               HIPERCAMPO_HOOK_BUDGET="120", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿que sabes del despliegue del servidor?", env)
    assert ctx, "debería haber respondido a una pregunta con memoria relevante"
    assert budget.estimate_tokens(ctx) <= 160, budget.estimate_tokens(ctx)


def test_si_no_cabe_ni_un_recuerdo_se_calla_en_vez_de_avisar_a_secas():
    """Medido en la memoria real: 46 tokens de cabecera + "hay 1 que no cabe", sin
    un solo dato. Se paga igual que un recuerdo útil, no aporta nada y el modelo ni
    siquiera sabe qué pedir. Callarse es gratis."""
    hc = Hipercampo(_DB, namespace="nocabe")
    hc.remember("nota kilometrica sobre el despliegue: " + "detalle larguisimo " * 120, 0.9)
    hc.close()
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="nocabe",
               HIPERCAMPO_HOOK_BUDGET="60", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿qué sabes del despliegue kilometrico?", env)
    assert ctx == "", f"inyectó {budget.estimate_tokens(ctx)} tok sin un solo dato: {ctx!r}"


def test_una_sugerencia_de_guardar_no_se_confunde_con_estar_vacio():
    """El cuerpo útil no son solo recuerdos: si assist recomienda guardar algo, esa
    sugerencia ES el contenido y tiene que llegar."""
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="sugerencia",
               HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("me llamo Armando y prefiero las respuestas directas", env)
    assert "sugerencia" in ctx, f"se comió la recomendación de guardar: {ctx!r}"


def test_el_presupuesto_se_puede_desactivar():
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="presupuesto",
               HIPERCAMPO_HOOK_BUDGET="0", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿que sabes del despliegue del servidor?", env)
    assert "presupuesto de memoria" not in ctx


# --- superficie de herramientas --------------------------------------------

def _tools(env: dict) -> list[str]:
    msgs = "\n".join([
        json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                               "clientInfo": {"name": "t", "version": "0"}}}),
        json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
        json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})])
    r = subprocess.run([sys.executable, "-m", "hipercampo.server"], input=msgs,
                       capture_output=True, text=True, encoding="utf-8", env=env)
    for linea in r.stdout.splitlines():
        try:
            d = json.loads(linea)
        except json.JSONDecodeError:
            continue
        if d.get("id") == 2:
            return [t["name"] for t in d.get("result", {}).get("tools", [])]
    return []


def test_por_defecto_solo_se_anuncia_el_nucleo():
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_TOOLS", None)
    nombres = _tools(env)
    assert "hc_recall" in nombres and "hc_remember" in nombres
    assert "hc_dream" not in nombres, "lo avanzado no debe ocupar sitio de entrada"
    assert "hc_tools" in nombres, "sin la puerta, lo avanzado sería inalcanzable"
    assert len(nombres) <= 8, nombres


def test_pedir_todas_devuelve_el_contrato_completo():
    """Quien dependa de la superficie antigua tiene que poder recuperarla entera."""
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_LOG="0",
               HIPERCAMPO_TOOLS="all")
    nombres = _tools(env)
    for imprescindible in ("hc_remember", "hc_recall", "hc_dream", "hc_muse",
                           "hc_forget", "hc_health", "hc_identity", "hc_stats",
                           "hc_remember_fact", "hc_ask_role", "hc_consolidate",
                           "hc_sleep", "hc_accept_bridge", "hc_reject_bridge",
                           "hc_unlearn", "hc_update", "hc_learn", "hc_assist"):
        assert imprescindible in nombres, imprescindible


def test_nada_se_pierde_lo_no_anunciado_sigue_en_el_catalogo():
    """Reducir la superficie no puede significar perder capacidades: lo que no se
    anuncia tiene que seguir estando, listo para activarse."""
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_TOOLS", None)
    from hipercampo import server
    importlib.reload(server)
    catalogo = set(server._CATALOGO)
    anunciadas = server.CORE | {"hc_tools"}
    assert "hc_dream" in catalogo and "hc_health" in catalogo
    assert not (catalogo & anunciadas), "no puede estar en los dos sitios"
    assert len(catalogo) == 12, sorted(catalogo)


def test_activar_en_caliente_registra_y_ejecuta_a_la_vez():
    """La activación se ejecuta EN LA MISMA llamada a propósito: si el cliente
    ignora la notificación tools/list_changed, la herramienta seguiría siendo
    inalcanzable. Ejecutándola aquí, la capacidad está garantizada igual."""
    import asyncio
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_TOOLS", None)
    from hipercampo import server
    importlib.reload(server)

    catalogo = asyncio.run(server.hc_tools())
    assert "hc_health" in catalogo["disponibles"]
    assert catalogo["disponibles"]["hc_health"], "cada una debe decir para qué sirve"

    r = asyncio.run(server.hc_tools(name="hc_health"))
    assert r["activada"] == "hc_health"
    assert r["resultado"]["integridad"] == "ok", r
    assert "hc_health" in server._ACTIVADAS


def test_activar_algo_que_no_existe_no_revienta():
    import asyncio
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    from hipercampo import server
    importlib.reload(server)
    r = asyncio.run(server.hc_tools(name="hc_inventada"))
    assert "error" in r and r["disponibles"]


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  ok  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FALLA  {nombre}: {e}")
    print("todo verde" if not fallos else f"{fallos} fallo(s)")
    raise SystemExit(1 if fallos else 0)
