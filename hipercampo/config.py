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
