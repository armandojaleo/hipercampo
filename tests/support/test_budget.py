"""
Token cost is a promise, so test it as one.

Unbounded memory eventually consumes the user's context window. These tests set the
minimum contract: respect the budget, DISCLOSE truncation instead of hiding it, and
do not interrupt when nobody asked and nothing is clearly relevant.
"""

import json
import os
import pytest
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

import helpers  # noqa: E402,F401  (imported for its side effects: scrubs the
# environment and opens the per-project opt-in gate, since a test is not a project)
from hipercampo.support import budget  # noqa: E402
from hipercampo.cycle.memory import Hipercampo  # noqa: E402
from hipercampo.cycle.policy import VOLUNTEER_MIN_SIM, _decide  # noqa: E402

_TMP = Path("data/_t_budget_dir")
_TMP.mkdir(parents=True, exist_ok=True)
_DB = str(_TMP / "presupuesto.db")

def _clean_db() -> None:
    _TMP.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        p = Path(_DB + suffix)
        try:
            p.unlink()
        except FileNotFoundError:
            pass
        except PermissionError:
            pass


@pytest.fixture(autouse=True)
def _aislar_db():
    _clean_db()
    yield
    _clean_db()


def _memoria():
    hc = Hipercampo(_DB, namespace="presupuesto")
    hc.remember("el servidor de produccion esta alojado en Frankfurt con IP fija", 0.8)
    hc.remember("los despliegues se hacen los martes por la manana, nunca en viernes", 0.8)
    hc.remember("la clave de la API de mapas se guarda en el gestor de secretos", 0.8)
    return hc


# --- estimación -------------------------------------------------------------

def test_estimate_is_proportional_to_text():
    corto = budget.estimate_tokens("hola")
    largo = budget.estimate_tokens("hola " * 100)
    assert 0 < corto < largo
    assert budget.estimate_tokens("") == 0


def test_estimate_is_explicitly_approximate():
    """The count is ALWAYS approximate, even when tiktoken is installed.

    tiktoken/cl100k_base is OpenAI's tokenizer, while this measures Claude cost and
    Claude's tokenizer is not public. It improves the estimate but cannot make it
    exact. This project must not claim otherwise."""
    assert budget.is_estimate() is True
    assert budget.method(), "the counting method must be DISCLOSED"


def test_counting_method_is_reported():
    m = budget.method()
    assert ("tiktoken" in m) == (budget._real_tokenizer() is not None)
    if budget._real_tokenizer() is not None:
        assert "OpenAI" in m, "the tokenizer owner must be disclosed"


# --- recorte ----------------------------------------------------------------

def test_truncate_respects_limit_and_marks_cut():
    texto = "palabra " * 200
    corto = budget.truncate(texto, 20)
    assert budget.estimate_tokens(corto) <= 25          # margen del marcador
    assert corto.endswith("[…]"), "a silent cut looks like corrupted text"


def test_truncate_does_not_split_words():
    texto = "supercalifragilisticoespialidoso " * 20
    corto = budget.truncate(texto, 10).replace(" […]", "")
    for palabra in corto.split():
        assert palabra in texto, "split a word in half"


def test_short_text_is_unchanged():
    assert budget.truncate("dos palabras", 500) == "dos palabras"


# --- ajuste al presupuesto --------------------------------------------------

def test_fit_respects_budget():
    lineas = ["[cabecera]"] + [f"- recuerdo largo numero {i} " + "relleno " * 60
                               for i in range(10)]
    salida, informe = budget.fit_budget(lineas, 200)
    assert informe["tokens"] <= 200, informe          # el techo es el techo
    assert informe["original"] > 1000, "el caso de prueba no era grande"


def test_omission_notice_fits_inside_budget():
    """The notice also costs tokens. Reserve space before appending it or the final
    step breaks the budget (measured: 40 -> 52, a 30% overrun). A budget that is
    exceeded is not a budget."""
    for tope in (30, 40, 60, 120, 350):
        lineas = ["[cabecera]"] + [f"- dato util numero {i} para el equipo"
                                   for i in range(4)] + ["x " * 400]
        salida, informe = budget.fit_budget(lineas, tope)
        real = sum(budget.estimate_tokens(x) for x in salida)
        assert real <= tope, f"presupuesto {tope} superado: {real} · {informe}"
        assert informe["tokens"] == real, "el informe no cuadra con la salida real"


def test_header_always_fits():
    salida, _ = budget.fit_budget(["[cabecera]", "x " * 5000], 30)
    assert salida[0] == "[cabecera]"


def test_omission_and_recovery_method_are_reported():
    salida, informe = budget.fit_budget(["[cabecera]"] + ["y " * 400] * 5, 100)
    assert informe["omitted"]
    aviso = "\n".join(salida)
    assert "don't fit" in aviso, "omitir en silencio hace creer que lo tiene todo"
    assert "hc_recall" in aviso, "hay que decir cómo recuperar lo que falta"


def test_memories_fit_whole_or_are_omitted():
    """A memory cut in half looks informative but is not; its reader may answer
    confidently from mutilated data."""
    entero = "- dato critico: la clave vive en el gestor de secretos, nunca en git"
    salida, _ = budget.fit_budget(["[cabecera]", entero, "x " * 500], 60)
    cuerpo = [ln for ln in salida if ln.startswith("- ")]
    assert entero in cuerpo, "recortó un recuerdo en vez de omitirlo"
    assert not any("[…]" in ln for ln in salida), "quedó un muñón de recuerdo"


def test_short_item_can_fit_when_long_item_cannot():
    largo, corto = "- " + "relleno " * 200, "- dato breve pero util"
    salida, _ = budget.fit_budget(["[cabecera]", largo, corto], 60)
    assert corto in salida and largo not in salida


def test_no_budget_omits_nothing():
    lineas = ["[cabecera]", "z " * 2000]
    salida, informe = budget.fit_budget(lineas, 0)
    assert salida == lineas and informe["omitted"] == 0


# --- no interrumpir sin motivo ---------------------------------------------

def test_does_not_interrupt_without_question_or_clear_relevance():
    """Measured motivating case: an ordinary technical instruction injected
    hundreds of irrelevant context tokens."""
    hc = _memoria()
    for ruido in ["arregla el bug del boton", "commitea los cambios",
                  "gracias, buen trabajo", "ponme un ejemplo en python"]:
        r = _decide(hc, ruido, k=3)
        assert r["action"] == "nothing", f"interrumpió con: {ruido} -> {r}"


def test_still_responds_when_asked():
    """The filter must not silence memory when a question is exactly when it should speak."""
    hc = _memoria()
    r = _decide(hc, "¿donde esta alojado el servidor de produccion?", k=3)
    assert r["action"] == "recall" and r["result"], r


def test_direct_similarity_is_in_every_result():
    """The filter relies on direct similarity, so detect its absence here, not in production."""
    hc = _memoria()
    hits = hc.recall("despliegues de los martes", k=3)
    assert hits and all("sim" in h for h in hits)
    assert all(0.0 <= h["sim"] <= 1.0 for h in hits)


def test_unaccented_que_does_not_pass_as_question():
    """The hole that still admitted noise: the unaccented interrogative.

    Unaccented «que» is extremely common in Spanish, so statements such as "espera
    que termine" were classified as questions and entered the injection branch
    WITHOUT requiring high relevance. In a measured session, two of three turns
    injected another project's memory without a question.

    The threshold concerns RELEVANCE, not grammar. A topical message with unaccented
    «que» may still answer because memory genuinely fits. This only prevents
    injection when the user neither asked nor supplied relevant context."""
    hc = _memoria()
    for atono in ["espera que termine la sesion que estamos mejorando",
                  "creo que esto esta mal",
                  "haz lo que te digo y no preguntes",
                  "lo que pasa es que no compila"]:
        r = _decide(hc, atono, k=3)
        assert r["action"] == "nothing", f"coló como pregunta: {atono} -> {r}"


def test_real_question_still_gets_answered():
    """Closing the hole must not silence memory: accents or question marks identify
    a real question that should be answered."""
    hc = _memoria()
    for clara in ["¿donde esta alojado el servidor de produccion?",
                  "qué sabes del servidor de produccion",
                  "recuerdas donde esta alojado el servidor de produccion"]:
        r = _decide(hc, clara, k=3)
        assert r["action"] == "recall" and r["result"], f"se calló ante: {clara}"


def test_ambiguous_question_answers_only_when_highly_relevant():
    """Without an accent the intent is ambiguous, so require the unsolicited-speech
    threshold. A clearly relevant memory may still answer."""
    hc = _memoria()
    r = _decide(hc, "donde esta alojado el servidor de produccion", k=3)
    if r["action"] == "recall":
        assert all(h["sim"] >= VOLUNTEER_MIN_SIM for h in r["result"]), \
            "una pregunta dudosa no puede inyectar por debajo del listón"


def test_invalid_environment_variable_does_not_break_startup():
    """budget is imported by the MCP server; an unchecked int() would turn a typo
    in .mcp.json into a startup failure with a stack trace."""
    # PYTHONIOENCODING=utf-8: el aviso "no es un número" lleva 'ú'. Sin esto, en
    # Windows el hijo lo escribiría en cp1252 (byte 0xFA) y el padre, que lee utf-8,
    # reventaría al decodificar. En Linux ya es utf-8; esto solo iguala Windows.
    env = dict(os.environ, HIPERCAMPO_HOOK_BUDGET="abc",
               HIPERCAMPO_IDENTITY_BUDGET="-", HIPERCAMPO_DB="data/_t_budget_env.db",
               PYTHONIOENCODING="utf-8")
    r = subprocess.run(
        [sys.executable, "-c",
         "import hipercampo.support.budget as b; print(b.HOOK_BUDGET, b.IDENTITY_BUDGET)"],
        capture_output=True, text=True, encoding="utf-8", env=env)
    assert r.returncode == 0, f"un valor ilegible tumbó el import: {r.stderr}"
    assert r.stdout.split() == ["350", "500"], r.stdout
    assert "is not a number" in r.stderr, "hay que AVISAR de que se ignoró el valor"


def test_persisted_budget_and_precedence():
    """The budget persists next to the database and a new hook process respects it
    on the next turn. The environment variable has higher precedence."""
    from hipercampo.support import config
    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_HOOK_BUDGET", None)
    try:
        config.set_hook_budget(500)
        assert config.hook_budget_persisted() == 500
        # un proceso NUEVO (como el hook) lee el valor persistido
        r = subprocess.run(
            [sys.executable, "-c",
             "from hipercampo.support import budget; print(budget.HOOK_BUDGET)"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        assert r.stdout.strip() == "500", r.stderr
        # la variable de entorno manda por encima del fichero
        r2 = subprocess.run(
            [sys.executable, "-c",
             "from hipercampo.support import budget; print(budget.HOOK_BUDGET)"],
            capture_output=True, text=True, encoding="utf-8",
            env={**os.environ, "HIPERCAMPO_HOOK_BUDGET": "200", "PYTHONIOENCODING": "utf-8"})
        assert r2.stdout.strip() == "200", r2.stderr
        config.set_hook_budget(None)
        assert config.hook_budget_persisted() is None
    finally:
        config.set_hook_budget(None)
        os.environ.pop("HIPERCAMPO_DB", None)


def test_interruption_threshold_is_stricter_than_answer_threshold():
    from hipercampo.cycle.policy import VOLUNTEER_MIN_SCORE
    assert VOLUNTEER_MIN_SIM > VOLUNTEER_MIN_SCORE, \
        "si nadie ha preguntado, callarse es gratis y equivocarse cuesta tokens"


# --- coste real del hook, de punta a punta ---------------------------------

def _hook(prompt: str, env: dict) -> str:
    r = subprocess.run([sys.executable, "-m", "hipercampo.cli", "hook"],
                       input=json.dumps({"prompt": prompt}), capture_output=True,
                       text=True, encoding="utf-8", env=env)
    d = json.loads(r.stdout or "{}")
    return d.get("hookSpecificOutput", {}).get("additionalContext", "")


def test_hook_stays_within_budget():
    hc = _memoria()
    # Seis recuerdos LARGOS y DISTINTOS ENTRE SÍ. Antes eran seis variantes de la misma
    # frase (solo cambiaba el índice) y `remember` descartaba cinco por redundantes: el
    # test creía llenar la memoria con seis y medía el presupuesto sobre UNO.
    detalles = [
        "el despliegue arranca con la copia de seguridad de la base y sigue con la "
        "migración del esquema, que puede tardar varios minutos si hay muchas filas",
        "el despliegue exige avisar al equipo de soporte con antelación porque durante "
        "la ventana el panel de administración queda en modo lectura para los clientes",
        "el despliegue se detiene solo si las pruebas de humo fallan dos veces seguidas "
        "y entonces revierte al paquete anterior sin intervención de nadie",
        "el despliegue publica primero en el entorno de preproducción y espera la "
        "aprobación manual de un responsable antes de tocar las máquinas de producción",
        "el despliegue deja un registro con la versión, la hora y quién lo lanzó, y ese "
        "registro se conserva un año entero para poder auditar cualquier incidencia",
        "el despliegue rota las credenciales del servicio de correo al terminar, de modo "
        "que las claves antiguas dejan de servir en cuanto la nueva versión está viva",
    ]
    guardados = sum(1 for d in detalles if hc.remember(d, 0.9).get("stored"))
    assert guardados == 6, f"el test necesita 6 recuerdos, se guardaron {guardados}"
    hc.close()
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="presupuesto",
               HIPERCAMPO_HOOK_BUDGET="120", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿que sabes del despliegue del servidor?", env)
    assert ctx, "debería haber respondido a una pregunta con memoria relevante"
    assert budget.estimate_tokens(ctx) <= 160, budget.estimate_tokens(ctx)


def test_hook_stays_quiet_when_no_memory_fits():
    """Measured in real memory: a 46-token heading plus an omission notice with no
    actual fact. It costs as much as useful memory, adds nothing, and gives the model
    no actionable retrieval cue. Silence is free."""
    hc = Hipercampo(_DB, namespace="nocabe")
    # Nota de UN solo átomo (sin fin de oración ni conectores): así el atomizador no la
    # trocea y sigue siendo un único recuerdo demasiado grande para el presupuesto — que
    # es lo que este test comprueba (presupuesto, no atomización).
    hc.remember("nota kilometrica del despliegue con " + "detalle larguisimo " * 120, 0.9)
    hc.close()
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="nocabe",
               HIPERCAMPO_HOOK_BUDGET="60", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿qué sabes del despliegue kilometrico?", env)
    assert ctx == "", f"inyectó {budget.estimate_tokens(ctx)} tok sin un solo dato: {ctx!r}"


def test_save_suggestion_is_not_mistaken_for_empty_output():
    """Useful content is not limited to memories: a save suggestion from assist IS
    content and must be delivered."""
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="sugerencia",
               HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("me llamo Armando y prefiero las respuestas directas", env)
    assert "suggestion" in ctx, f"se comió la recomendación de guardar: {ctx!r}"


def test_budget_can_be_disabled():
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_NAMESPACE="presupuesto",
               HIPERCAMPO_HOOK_BUDGET="0", HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_LINKED", None)
    ctx = _hook("¿que sabes del despliegue del servidor?", env)
    assert "presupuesto de memoria" not in ctx


# --- superficie de herramientas --------------------------------------------

def _tools(env: dict) -> list[str]:
    # MCP sobre stdio es una conversación, no un fichero por lotes: si se escriben
    # todas las peticiones y se cierra stdin inmediatamente, el servidor puede observar
    # EOF antes de terminar la respuesta (la carrera aparecía en CPython 3.13/Linux).
    p = subprocess.Popen(
        [sys.executable, "-m", "hipercampo.server"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, encoding="utf-8", errors="replace", bufsize=1, env=env,
    )

    def enviar(msg: dict) -> None:
        assert p.stdin is not None
        p.stdin.write(json.dumps(msg) + "\n")
        p.stdin.flush()

    def esperar(id_esperado: int) -> dict:
        assert p.stdout is not None
        for linea in p.stdout:
            try:
                respuesta = json.loads(linea)
            except json.JSONDecodeError:
                continue
            if respuesta.get("id") == id_esperado:
                return respuesta
        error = p.stderr.read() if p.stderr is not None else ""
        raise AssertionError(
            f"MCP cerró sin responder a id={id_esperado}; stderr={error!r}")

    try:
        enviar({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                "params": {"protocolVersion": "2024-11-05", "capabilities": {},
                           "clientInfo": {"name": "t", "version": "0"}}})
        esperar(1)
        enviar({"jsonrpc": "2.0", "method": "notifications/initialized"})
        enviar({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        respuesta = esperar(2)
        return [t["name"] for t in respuesta.get("result", {}).get("tools", [])]
    finally:
        if p.stdin is not None:
            p.stdin.close()
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill()
            p.wait(timeout=5)


def test_only_core_tools_are_advertised_by_default():
    env = dict(os.environ, HIPERCAMPO_DB=_DB, HIPERCAMPO_LOG="0")
    env.pop("HIPERCAMPO_TOOLS", None)
    nombres = _tools(env)
    assert "hc_recall" in nombres and "hc_remember" in nombres
    assert "hc_dream" not in nombres, "lo avanzado no debe ocupar sitio de entrada"
    assert "hc_tools" in nombres, "sin la puerta, lo avanzado sería inalcanzable"
    assert len(nombres) <= 8, nombres


def test_requesting_all_returns_full_contract():
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


def test_unadvertised_tools_remain_in_catalog():
    """Reducing the advertised surface must not remove capabilities; unadvertised
    tools remain available for activation."""
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_TOOLS", None)
    from hipercampo import server
    importlib.reload(server)
    catalogo = set(server._CATALOG)
    anunciadas = server.CORE | {"hc_tools"}
    assert "hc_dream" in catalogo and "hc_health" in catalogo
    assert not (catalogo & anunciadas), "no puede estar en los dos sitios"
    assert len(catalogo) == 12, sorted(catalogo)


def test_hot_activation_registers_and_executes_at_once():
    """Activation deliberately executes in the SAME call. If the client ignores
    tools/list_changed, the tool would otherwise remain unreachable; execution here
    guarantees the capability regardless."""
    import asyncio
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    os.environ.pop("HIPERCAMPO_TOOLS", None)
    from hipercampo import server
    importlib.reload(server)

    catalogo = asyncio.run(server.hc_tools())
    assert "hc_health" in catalogo["available"]
    assert catalogo["available"]["hc_health"], "cada una debe decir para qué sirve"

    r = asyncio.run(server.hc_tools(name="hc_health"))
    assert r["activated"] == "hc_health"
    assert r["result"]["integrity"] == "ok", r
    assert "hc_health" in server._ACTIVATED


def test_activating_unknown_tool_does_not_crash():
    import asyncio
    import importlib

    os.environ["HIPERCAMPO_DB"] = _DB
    from hipercampo import server
    importlib.reload(server)
    r = asyncio.run(server.hc_tools(name="hc_inventada"))
    assert "error" in r and r["available"]


if __name__ == "__main__":
    fallos = 0
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                _clean_db()
                fn()
                _clean_db()
                print(f"  ok  {nombre}")
            except AssertionError as e:
                fallos += 1
                print(f"FALLA  {nombre}: {e}")
    print("todo verde" if not fallos else f"{fallos} fallo(s)")
    raise SystemExit(1 if fallos else 0)
