"""
Tests de la IDENTIDAD DE TRABAJO — la memoria del agente, no la del usuario.

Lo que se protege aquí: que lo aprendido trabajando (reglas, lecciones,
decisiones, preferencias) SOBREVIVA a cerrar la sesión, no se olvide por desuso,
esté disponible desde cualquier proyecto, y no se mezcle con la memoria del
mundo. Sin esto, cada sesión vuelve a tropezar en la misma piedra.

Ejecuta:  python tests/test_identity.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar, memoria      # noqa: E402
from hipercampo.identity import SELF_NAMESPACE      # noqa: E402
from hipercampo.memory import Hipercampo            # noqa: E402


def test_lo_aprendido_sobrevive_a_cerrar_la_sesion():
    """El punto entero: continuidad entre sesiones."""
    hc = memoria("id_sobrevive")
    ruta = hc.store.path
    hc.learn("medir antes de creer, y decir la verdad de los límites", "regla")
    hc.store.close()
    hc.close()

    otra_sesion = Hipercampo(ruta, namespace="test")      # sesión nueva, de cero
    texto = otra_sesion.identity()["texto"]
    assert "medir antes de creer" in texto, f"se perdió al cerrar: {texto}"
    otra_sesion.close()


def test_se_comparte_entre_proyectos():
    """La identidad es del agente, no de un proyecto: se ve desde cualquiera."""
    hc = memoria("id_compartida", namespace="proyecto_a")
    ruta = hc.store.path
    hc.learn("CI solo en Linux esconde bugs en una app local", "leccion")
    hc.close()

    otro = Hipercampo(ruta, namespace="proyecto_b")       # OTRO proyecto
    assert "CI solo en Linux" in otro.identity()["texto"], "no se comparte"
    otro.close()


def test_no_se_mezcla_con_la_memoria_del_mundo():
    hc = memoria("id_separada")
    hc.learn("Armando prefiere respuestas directas, sin peloteo", "preferencia")
    hc.remember("el servidor de produccion esta alojado en Frankfurt", 0.7)

    # la memoria normal del proyecto no ve la identidad
    textos = [r["text"] for r in hc.store.all(only_active=False)]
    assert not any("peloteo" in t for t in textos), "la identidad contaminó el proyecto"
    # y la identidad no ve la memoria del mundo
    assert "Frankfurt" not in hc.identity()["texto"], "el mundo contaminó la identidad"
    hc.close()


def test_no_entra_por_la_puerta_de_los_enlaces():
    """El agujero real: con HIPERCAMPO_LINKED='*' la identidad se colaba en recall
    como si fuera un proyecto más. '*' significa 'todos MIS PROYECTOS', no 'todo
    lo que hay en el fichero'."""
    hc = memoria("id_enlaces", namespace="proyecto_a")
    ruta = hc.store.path
    hc.learn("una leccion que no debe aparecer mezclada con el mundo", "leccion")
    hc.remember("un recuerdo normal del proyecto para que haya con que comparar", 0.6)
    hc.close()

    con_todo = Hipercampo(ruta, namespace="proyecto_a", linked=["*"])
    assert SELF_NAMESPACE not in con_todo.store.linked, (
        f"la identidad entró como proyecto enlazado: {con_todo.store.linked}")
    hits = con_todo.recall("una leccion que no debe aparecer mezclada")
    assert not any("no debe aparecer" in h["text"] for h in hits), (
        f"la identidad se coló en recall: {hits}")
    con_todo.close()

    # y tampoco si alguien la pide por su nombre explícitamente
    explicito = Hipercampo(ruta, namespace="proyecto_a", linked=[SELF_NAMESPACE])
    assert SELF_NAMESPACE not in explicito.store.linked, "se coló pidiéndola a mano"
    explicito.close()


def test_una_leccion_no_se_olvida_por_desuso():
    """El olvido activo poda lo débil; una lección aprendida no es débil."""
    hc = memoria("id_no_olvida")
    hc.learn("no reintentar escrituras que quizá ya se confirmaron", "leccion")
    fila = hc._self_store().all(only_active=False)[0]
    assert fila["importance"] >= 0.8, (
        f"quedaría desprotegida del olvido: importance={fila['importance']}")
    hc.close()


def test_repetir_una_regla_la_refuerza_en_vez_de_duplicarla():
    """Una regla que se repite es una regla que se confirma, no ruido."""
    hc = memoria("id_refuerza")
    r1 = hc.learn("medir antes de creer y decir la verdad de los limites", "regla")
    r2 = hc.learn("medir antes de creer y decir la verdad de los limites", "regla")
    assert r1["learned"] is True
    assert r2["learned"] is False and r2["reinforced"] == r1["id"], r2
    assert hc.identity()["n"] == 1, "duplicó una regla ya conocida"
    hc.close()


def test_los_tipos_se_validan():
    hc = memoria("id_tipos")
    r = hc.learn("algo con un tipo inventado", "chorrada")
    assert "error" in r and "validos" in r, r
    assert hc.identity()["n"] == 0, "guardó pese al tipo inválido"
    hc.close()


def test_se_puede_desaprender():
    """Una regla puede dejar de valer: entonces se borra de verdad."""
    hc = memoria("id_desaprende")
    r = hc.learn("una norma provisional que luego dejara de valer", "regla")
    assert hc.unlearn(r["id"])["unlearned"] == r["id"]
    assert hc.identity()["n"] == 0, "siguió guiando pese a estar desaprendida"
    assert "error" in hc.unlearn(9999), "debe avisar si no existe"
    hc.close()


def test_se_agrupa_por_tipo_para_leerlo_de_un_vistazo():
    hc = memoria("id_formato")
    hc.learn("medir antes de creer", "regla")
    hc.learn("el nucleo se queda local-first", "decision")
    texto = hc.identity()["texto"]
    assert "REGLAS" in texto and "DECISIONES" in texto, texto
    assert texto.index("REGLAS") < texto.index("DECISIONES"), "las reglas van primero"
    hc.close()


def test_el_contexto_reservado_no_se_pisa_con_uno_normal():
    hc = memoria("id_reservado")
    hc.learn("una regla cualquiera para ocupar el contexto reservado", "regla")
    assert hc._self_store().namespace == SELF_NAMESPACE
    assert hc.store.namespace != SELF_NAMESPACE
    hc.close()


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
