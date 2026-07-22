"""
Utilidades compartidas por los tests. Antes cada fichero repetía su propio
_open/_clean (15 de 19 ficheros): aquí vive una sola vez.

    from helpers import memoria, limpiar

    hc = memoria("mi_test")        # BD temporal propia, cerrando la anterior
    ...
    limpiar()                      # cierra y borra (.db, -wal, -shm)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo.memory import Hipercampo             # noqa: E402

_abierta: Hipercampo | None = None
_ruta: str | None = None


def memoria(nombre: str, namespace: str = "test") -> Hipercampo:
    """Abre una memoria limpia en una BD temporal propia de ese test."""
    global _abierta, _ruta
    limpiar()
    _ruta = f"data/_t_{nombre}.db"
    _abierta = Hipercampo(_ruta, namespace=namespace)
    return _abierta


def limpiar() -> None:
    """Cierra la memoria abierta y borra sus ficheros (Windows bloquea si no)."""
    global _abierta, _ruta
    if _abierta is not None:
        try:
            _abierta.store.close()
        except Exception:
            pass
        _abierta = None
    if _ruta:
        for suf in ("", "-wal", "-shm"):
            Path(_ruta + suf).unlink(missing_ok=True)


def ejecutar(globs) -> int:
    """Runner común: ejecuta las funciones test_* del módulo y resume."""
    fails = 0
    for nombre, fn in sorted(globs.items()):
        if nombre.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"ok   {nombre}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {nombre}: {e}")
            except Exception as e:
                fails += 1
                print(f"ERROR {nombre}: {e}")
            finally:
                limpiar()
    print(f"\n{'OK' if not fails else f'{fails} FALLARON'}")
    return 1 if fails else 0
