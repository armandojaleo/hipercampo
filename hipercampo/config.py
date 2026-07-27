"""Configuración compartida: dónde vive la memoria."""

import os


def default_db() -> str:
    """Ruta de la base de datos si no se define HIPERCAMPO_DB.

    - En Docker (existe /data, normalmente un volumen): /data/hipercampo.db
    - En local: ~/.hipercampo/hipercampo.db  (predecible y fácil de respaldar)
    """
    # La rama /data es para contenedores Linux (Docker). En Windows "/data" se
    # resolvería a <unidad>:\data por accidente, así que la exigimos solo en POSIX.
    if os.name == "posix" and os.path.isdir("/data"):
        return "/data/hipercampo.db"
    return os.path.join(os.path.expanduser("~"), ".hipercampo", "hipercampo.db")


def db_path() -> str:
    """La ruta efectiva: HIPERCAMPO_DB si está definida, si no la de por defecto."""
    return os.environ.get("HIPERCAMPO_DB", default_db())


def _pause_flag() -> str:
    """El fichero-bandera de 'memoria en pausa', junto a la base de datos."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path())) or ".",
                        "hipercampo.paused")


def paused() -> bool:
    """¿Está la memoria EN PAUSA (modo 'no recordar')? Se consulta en cada escritura.

    Dos fuentes, ambas válidas y consultadas EN CALIENTE (sin cachear), para que el
    visor pueda encender/apagar el modo sin reiniciar el servidor MCP ni el hook:
      - la variable HIPERCAMPO_PAUSED=1 (una sesión que nace en pausa), y
      - un fichero-bandera junto al .db (el interruptor que togglea el visor).
    Mientras esté activa, no se graban recuerdos nuevos ni se refuerzan los existentes;
    LEER sigue funcionando. No borra nada: solo deja de escribir.
    """
    if os.environ.get("HIPERCAMPO_PAUSED", "") not in ("", "0", "false", "False"):
        return True
    try:
        return os.path.isfile(_pause_flag())
    except OSError:
        return False


def set_paused(on: bool) -> bool:
    """Enciende o apaga la pausa creando/borrando el fichero-bandera. Devuelve el
    estado resultante. La variable de entorno, si está, manda por encima de esto."""
    flag = _pause_flag()
    try:
        if on:
            os.makedirs(os.path.dirname(flag) or ".", exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write("memoria en pausa (modo 'no recordar')\n")
        else:
            if os.path.isfile(flag):
                os.remove(flag)
    except OSError:
        pass
    return paused()


def _budget_file() -> str:
    """Fichero con el presupuesto de tokens del hook, junto a la base de datos.
    Persistir aquí (no solo en una variable de entorno) permite ajustarlo desde el
    visor y que el HOOK lo respete en el siguiente turno, sin tocar configs a mano."""
    return os.path.join(os.path.dirname(os.path.abspath(db_path())) or ".",
                        "hipercampo.budget")


def hook_budget_persisted() -> int | None:
    """El presupuesto guardado en fichero, o None si no se ha fijado (usar el de
    fábrica). La variable HIPERCAMPO_HOOK_BUDGET, si está, manda por encima de esto."""
    try:
        with open(_budget_file(), encoding="utf-8") as f:
            return max(0, int(f.read().strip()))
    except (OSError, ValueError):
        return None


def set_hook_budget(tokens: int | None) -> None:
    """Fija (o borra, con None) el presupuesto del hook. Se lee EN CALIENTE: el
    siguiente hook ya usa el valor nuevo, sin reiniciar nada."""
    flag = _budget_file()
    try:
        if tokens is None:
            if os.path.isfile(flag):
                os.remove(flag)
        else:
            os.makedirs(os.path.dirname(flag) or ".", exist_ok=True)
            with open(flag, "w", encoding="utf-8") as f:
                f.write(str(max(0, int(tokens))))
    except OSError:
        pass
