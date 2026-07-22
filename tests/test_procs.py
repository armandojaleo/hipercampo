"""
Tests de la gestión de procesos servidor (`hipercampo servers` / `restart`).

Aquí no se mata nada de verdad: se comprueba que el reconocimiento y el listado son
correctos y que terminar() no revienta ante lo inesperado. Matar procesos reales en
un test sería frágil y, peor, podría cargarse el servidor de quien ejecute la suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hipercampo import procs                          # noqa: E402


def test_reconoce_a_los_nuestros_y_solo_a_los_nuestros():
    assert procs._coincide("C:/Python313/python.exe -m hipercampo.server")
    assert procs._coincide("/usr/bin/python3 -m hipercampo.server")
    assert procs._coincide("python -X utf8 -m hipercampo.server --algo")
    assert procs._coincide("hipercampo serve")
    # un proceso ajeno que solo MENCIONA hipercampo no es un servidor
    assert not procs._coincide("python -m pytest tests/test_procs.py")
    assert not procs._coincide("code d:/projects/hipercampo")
    assert not procs._coincide("python -m hipercampo.cli stats")


def test_listar_no_revienta_y_devuelve_forma_esperada():
    procesos = procs.listar()                          # puede haber 0: es válido
    assert isinstance(procesos, list)
    for p in procesos:
        assert isinstance(p["pid"], int) and p["pid"] > 0
        assert p["arranque"] is None or p["arranque"] > 0
        assert "hipercampo" in p["cmd"]


def test_listar_viene_ordenado_del_mas_viejo_al_mas_nuevo():
    # el más viejo es el más sospechoso de arrastrar código caducado: va primero
    tiempos = [p["arranque"] or 0 for p in procs.listar()]
    assert tiempos == sorted(tiempos)


def test_nunca_se_incluye_a_si_mismo():
    import os
    assert os.getpid() not in {p["pid"] for p in procs.listar()}


def test_terminar_con_pid_inexistente_no_lanza():
    # 2**31-1 no existe; la función debe informar del fallo, nunca propagarlo
    estado = procs.terminar([2**31 - 1], espera=0)
    assert set(estado) == {2**31 - 1}
    assert isinstance(estado[2**31 - 1], str)


def test_terminar_sin_pids_no_hace_nada():
    assert procs.terminar([], espera=0) == {}


if __name__ == "__main__":
    for nombre, fn in sorted(globals().items()):
        if nombre.startswith("test_"):
            fn()
            print("OK", nombre)
