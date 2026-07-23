"""
Tests del REGISTRO DE DECISIONES — la transparencia.

Una memoria que decide sola (guardar o no, olvidar, callarse) tiene que poder
explicarse. Este registro es esa explicación: si se rompe, hipercampo pasa a ser
una caja negra sin que nadie se entere. Y tiene una regla dura: **observar nunca
puede romper lo observado**.

Ejecuta:  python tests/test_audit.py
"""

import importlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from helpers import ejecutar, limpiar               # noqa: E402


def _audit_activo(tmp: str):
    """Recarga el módulo con el registro ENCENDIDO y apuntando a `tmp`."""
    import os
    os.environ["HIPERCAMPO_LOG"] = "1"
    from hipercampo import audit
    importlib.reload(audit)
    Path(tmp).parent.mkdir(parents=True, exist_ok=True)
    Path(_LOG).unlink(missing_ok=True)          # cada test parte de un registro limpio
    audit.set_logfile(tmp)
    return audit


# Carpeta propia: el registro vive junto a la BD, así que compartir carpeta con
# otras suites mezclaría sus líneas con las nuestras y los asertos medirían ruido.
_DIR = Path("data/_t_audit")
_DB = str(_DIR / "audit.db")
_LOG = str(_DIR / "hipercampo.log")


def test_registra_la_decision_con_sus_numeros():
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("remember", "guardado id=7", novedad=0.42, sorpresa=0.81)
    lineas = audit.tail(5)
    assert lineas and "remember" in lineas[-1], lineas
    assert "novedad=0.42" in lineas[-1] and "sorpresa=0.81" in lineas[-1], lineas[-1]
    Path(_LOG).unlink(missing_ok=True)


def test_omite_los_campos_vacios():
    """Un registro lleno de 'x=None' es ruido que estorba al leerlo."""
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("forget", "nada que podar", podados=0, evictado=None, motivo="")
    linea = audit.tail(1)[0]
    assert "evictado" not in linea and "motivo" not in linea, linea
    assert "podados=0" in linea, "un cero SÍ es información"
    Path(_LOG).unlink(missing_ok=True)


def test_apagarlo_lo_apaga_de_verdad():
    import os
    os.environ["HIPERCAMPO_LOG"] = "0"
    from hipercampo import audit
    importlib.reload(audit)
    Path(_LOG).unlink(missing_ok=True)
    audit.set_logfile(_DB)
    audit.log("remember", "esto no debe aparecer en ningun sitio")
    assert audit.logfile() is None, "con HIPERCAMPO_LOG=0 no debe haber fichero"
    assert audit.tail(5) == []
    assert not Path(_LOG).exists(), "escribió pese a estar desactivado"
    os.environ["HIPERCAMPO_LOG"] = "1"


def test_observar_nunca_rompe_lo_observado():
    """Si el registro falla (disco, permisos, campo raro), se traga el fallo."""
    audit = _audit_activo(_DB)

    class Explosivo:
        def __repr__(self):
            raise RuntimeError("no me puedes registrar")
        __str__ = __repr__

    audit.log("recall", "con un campo que explota al formatearse", raro=Explosivo())

    audit._PATH = Path("Z:/ruta/imposible/hipercampo.log")   # destino inescribible
    audit.log("remember", "esto no se puede escribir en ningun disco")
    audit._PATH = None
    assert audit.tail(3) == [], "sin fichero, tail devuelve vacío sin reventar"


def test_la_salida_a_una_tuberia_va_en_utf8():
    """El cliente MCP lee stderr como UTF-8: 'abstención' no puede llegar rota."""
    audit = _audit_activo(_DB)
    crudo = io.BytesIO()

    class TuberiaFalsa:
        """Como stderr cuando cuelga de una tubería: tiene .buffer y no es tty."""
        encoding = "cp1252"
        buffer = crudo

        def isatty(self):
            return False

        def write(self, _s):
            raise AssertionError("debió escribir bytes en .buffer, no texto")

        def flush(self):
            pass

    original = sys.stderr
    sys.stderr = TuberiaFalsa()
    try:
        audit.log("recall", "abstención: nada destaca del ruido")
    finally:
        sys.stderr = original
    bytes_escritos = crudo.getvalue()
    assert "abstención".encode() in bytes_escritos, (
        f"no salió en UTF-8: {bytes_escritos!r}")
    Path(_LOG).unlink(missing_ok=True)


def test_el_ciclo_real_deja_rastro_legible():
    """De punta a punta: guardar y recuperar tienen que verse en el registro."""
    _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    from hipercampo import audit
    from hipercampo.memory import Hipercampo
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)

    hc = Hipercampo(_DB, namespace="test")
    hc.remember("el amoniaco hierve a menos treinta y tres grados", 0.7)
    hc.recall("a que temperatura hierve el amoniaco")
    hc.store.close()

    texto = "\n".join(audit.tail(50))
    assert "remember" in texto and "recall" in texto, texto
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    Path(_LOG).unlink(missing_ok=True)


def test_los_filtros_del_registro():
    audit = _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    audit.log("recall", "abstención: nada destaca del ruido", n=18)
    audit.log("remember", "guardado id=1", texto="el diseño de Peñíscola")
    audit.log("ERROR", "recall: base de datos bloqueada")

    assert len(audit.tail(0, accion="recall")) == 1, "filtro por acción"
    assert len(audit.tail(0, accion="ERROR")) == 1, "los errores se filtran igual"
    # buscar sin acentos debe encontrar CON acentos: nadie escribe 'diseño' al buscar
    assert len(audit.tail(0, contiene="diseno")) == 1, "búsqueda insensible a acentos"
    assert len(audit.tail(0, contiene="ABSTENCION")) == 1, "insensible a mayúsculas"
    assert audit.tail(0, contiene="no aparece jamas") == []
    assert len(audit.tail(0, solo_hoy=True)) == 3, "todo esto es de hoy"
    assert set(audit.acciones()) == {"recall", "remember", "ERROR"}, audit.acciones()
    Path(_LOG).unlink(missing_ok=True)


def test_el_registro_dice_por_que_y_no_solo_que():
    """Un registro que dice 'abstención' sin decir contra qué no explica nada."""
    _audit_activo(_DB)
    Path(_LOG).unlink(missing_ok=True)
    from hipercampo import audit
    from hipercampo.memory import Hipercampo
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)

    hc = Hipercampo(_DB, namespace="test")
    hc.remember("el amoniaco hierve a menos treinta y tres grados", 0.7)
    hc.recall("a que temperatura hierve el amoniaco")
    hc.close()

    texto = "\n".join(audit.tail(50))
    for dato in ("novedad=", "sorpresa=", "mirados=", "mejor=", "ms="):
        assert dato in texto, f"falta {dato} en el registro:\n{texto}"
    for suf in ("", "-wal", "-shm"):
        Path(_DB + suf).unlink(missing_ok=True)
    Path(_LOG).unlink(missing_ok=True)


if __name__ == "__main__":
    limpiar()
    codigo = ejecutar(dict(globals()))
    Path(_LOG).unlink(missing_ok=True)
    sys.exit(codigo)
