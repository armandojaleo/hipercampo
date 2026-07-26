"""
El CONTRATO del núcleo embebible — la frontera entre memoria y transporte.

hipercampo quiere caber en sistemas embebidos y robots (SBC con Linux). Para eso el
NÚCLEO (VSA + store + el ciclo de memoria) no puede depender de `mcp`, que es solo UNO
de los transportes. Hoy eso se cumple por suerte: `mcp` únicamente se importa en
`server.py` (y perezosamente en el subcomando `serve` de la CLI). Este test lo convierte
en un CONTRATO: si alguien mete `from .server import ...` o `import mcp` arriba de un
módulo del núcleo, aquí salta y no en la Raspberry Pi de un tercero.

Frontera:
  - TRANSPORTE (puede tocar mcp): server.py, cli.py
  - NÚCLEO (no puede): todo lo demás del paquete

Ejecuta:  python tests/test_core_embebible.py
"""

import ast
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from helpers import ejecutar, limpiar     # noqa: E402
import hipercampo                          # noqa: E402
from hipercampo import Hipercampo          # noqa: E402

_PAQUETE = Path(hipercampo.__file__).resolve().parent
# Capa de transporte: estos SÍ pueden importar mcp. El resto es núcleo y no.
_TRANSPORTE = {"server.py", "cli.py"}
# Lo que un embebido puede asumir del núcleo (el ciclo de memoria completo).
_API_NUCLEO = (
    "remember", "recall", "update", "consolidate", "forget", "purge",
    "sleep", "dream", "muse", "learn", "remember_fact", "ask_role",
    "identity", "unlearn", "assist", "accept_bridge", "reject_bridge",
    "stats", "health", "close",
)
_PROHIBIDO = ("mcp",)          # módulos que el núcleo no puede arrastrar


def _modulos_nucleo():
    for p in sorted(_PAQUETE.glob("*.py")):
        if p.name not in _TRANSPORTE:
            yield p


def _imports_de(path: Path):
    """Todos los módulos importados (top-level o dentro de funciones) por un fichero."""
    arbol = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    nombres = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            nombres.update(a.name.split(".")[0] for a in nodo.names)
        elif isinstance(nodo, ast.ImportFrom):
            if nodo.module:
                nombres.add(nodo.module.split(".")[0])
            if nodo.level:                        # from .algo import x  ->  .algo
                nombres.add("." + (nodo.module or "").split(".")[0])
    return nombres


def test_ningun_modulo_del_nucleo_importa_mcp():
    """La frontera dura: ni un `import mcp` colado arriba de memory.py/store.py/…"""
    culpables = {}
    for p in _modulos_nucleo():
        malos = _imports_de(p) & set(_PROHIBIDO)
        if malos:
            culpables[p.name] = malos
    assert not culpables, (
        f"módulos del núcleo importando transporte: {culpables}. "
        "El núcleo debe poder embeberse sin mcp.")


def test_el_nucleo_no_importa_el_servidor():
    """El núcleo tampoco puede depender de .server (que sí arrastra mcp)."""
    culpables = {p.name for p in _modulos_nucleo() if ".server" in _imports_de(p)}
    assert not culpables, f"el núcleo importa .server en: {culpables}"


def test_importar_hipercampo_no_carga_mcp():
    """La prueba viva: importar el paquete no debe traer mcp a memoria, ni siquiera
    con mcp instalado en el entorno. Se mide en un intérprete LIMPIO."""
    codigo = (
        "import sys, hipercampo; "
        "from hipercampo import Hipercampo; "
        "assert 'mcp' not in sys.modules, 'importar hipercampo arrastró mcp'; "
        "print('OK')"
    )
    r = subprocess.run([sys.executable, "-c", codigo],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stderr
    assert "OK" in r.stdout


def test_la_api_del_nucleo_esta_completa():
    """Lo que un embebido puede llamar: el ciclo de memoria entero, sin mcp de por medio."""
    faltan = [m for m in _API_NUCLEO if not callable(getattr(Hipercampo, m, None))]
    assert not faltan, f"faltan métodos del núcleo: {faltan}"


def test_el_paquete_expone_hipercampo():
    """La superficie pública mínima del paquete."""
    assert hasattr(hipercampo, "Hipercampo")
    assert "Hipercampo" in getattr(hipercampo, "__all__", [])
    assert getattr(hipercampo, "__version__", None), "el paquete debe declarar versión"


if __name__ == "__main__":
    limpiar()
    sys.exit(ejecutar(dict(globals())))
