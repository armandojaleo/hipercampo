"""hipercampo — memoria viva para Claude basada en hipervectores (VSA)."""

from .memory import Hipercampo

__all__ = ["Hipercampo"]

# Una sola fuente de verdad: la versión instalada (pyproject). Evita que el paquete
# declare una versión distinta de la publicada.
try:                                     # pragma: no cover
    from importlib.metadata import PackageNotFoundError, version
    __version__ = version("hipercampo")
except (ImportError, Exception):         # pragma: no cover
    __version__ = "0.0.0+unknown"
