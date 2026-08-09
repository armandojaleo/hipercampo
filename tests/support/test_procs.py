"""
Tests de la gestión de procesos servidor (`hipercampo servers` / `restart`).

Aquí no se mata nada de verdad: se comprueba que el reconocimiento y el listado son
correctos y que terminar() no revienta ante lo inesperado. Matar procesos reales en
un test sería frágil y, peor, podría cargarse el servidor de quien ejecute la suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # tests/

from hipercampo.support import procs                          # noqa: E402


def test_recognizes_only_our_processes():
    assert procs._matches("C:/Python313/python.exe -m hipercampo.server")
    assert procs._matches("/usr/bin/python3 -m hipercampo.server")
    assert procs._matches("python -X utf8 -m hipercampo.server --algo")
    assert procs._matches("hipercampo serve")
    # un proceso ajeno que solo MENCIONA hipercampo no es un servidor
    assert not procs._matches("python -m pytest tests/test_procs.py")
    assert not procs._matches("code d:/projects/hipercampo")
    assert not procs._matches("python -m hipercampo.cli stats")


def test_listing_does_not_crash_and_returns_expected_shape():
    procesos = procs.list_servers()                          # puede haber 0: es válido
    assert isinstance(procesos, list)
    for p in procesos:
        assert isinstance(p["pid"], int) and p["pid"] > 0
        assert p["started_at"] is None or p["started_at"] > 0
        assert "hipercampo" in p["cmd"]


def test_listing_is_ordered_oldest_to_newest():
    # el más viejo es el más sospechoso de arrastrar código caducado: va primero
    tiempos = [p["started_at"] or 0 for p in procs.list_servers()]
    assert tiempos == sorted(tiempos)


def test_never_includes_itself():
    import os
    assert os.getpid() not in {p["pid"] for p in procs.list_servers()}


def test_terminating_missing_pid_does_not_raise():
    # 2**31-1 no existe; la función debe informar del fallo, nunca propagarlo
    estado = procs.terminate([2**31 - 1], wait=0)
    assert set(estado) == {2**31 - 1}
    assert isinstance(estado[2**31 - 1], str)


def test_terminating_without_pids_does_nothing():
    assert procs.terminate([], wait=0) == {}


if __name__ == "__main__":
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
