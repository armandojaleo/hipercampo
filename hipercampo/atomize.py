"""
Atomizador de texto — trocear en unidades atómicas antes de codificar.

El porqué, MEDIDO: al meter T hechos en un único hipervector (bundle), la señal de
cada uno baja ~1/√T. Una consulta corta que busca UN hecho enterrado en un texto largo
casi no lo encuentra: a 64 hechos por texto, acierto@1 monolítico ≈ 0.15; atomizado ≈
1.00 (ver scripts/atom_probe.py). La cura no es más dimensiones: es partir la entrada en
átomos —oraciones, y cláusulas dentro de oraciones muy largas— y codificar cada uno.

Es una segmentación LÉXICA, sin dependencias ni modelo: reglas robustas para español e
inglés. No pretende análisis lingüístico perfecto; pretende que un hecho enterrado deje
de ser irrecuperable. Un LLM podría atomizar mejor, pero no debe ser un requisito.
"""

import re

# Fin de oración: . ! ? ; … y saltos de línea. Se evita cortar en abreviaturas y
# decimales comunes (no exhaustivo: prioriza no romper de más).
_ABREV = {"sr", "sra", "dr", "dra", "st", "sta", "etc", "vs", "ej", "p.ej", "núm",
          "no", "art", "fig", "pág", "cap", "ee.uu", "ee", "uu", "mr", "mrs", "ms",
          "e.g", "i.e", "vol", "col", "op", "cf", "al"}
_FIN = re.compile(r"([.!?;…]+|\n+)")
# Cláusulas dentro de una oración larga: conectores y separadores fuertes.
_CLAUSULA = re.compile(
    r"\s*(?:,|:|—|–|\bpero\b|\bporque\b|\baunque\b|\bmientras\b|\by luego\b|"
    r"\bademás\b|\bsin embargo\b|\bhowever\b|\bbecause\b|\balthough\b|\bwhile\b|"
    r"\bbut\b|\band then\b)\s*", re.IGNORECASE)

_MIN_ATOMO = 12          # menos de esto no es un átomo con contenido, se descarta
_LARGA = 160             # una oración más larga que esto se parte en cláusulas


def _termina_en_abrev(frag: str) -> bool:
    m = re.search(r"(\w+)\.?$", frag.strip().lower())
    return bool(m and m.group(1) in _ABREV)


def _por_oraciones(texto: str) -> list[str]:
    partes, buff = [], ""
    for trozo in _FIN.split(texto):
        if _FIN.fullmatch(trozo or ""):
            buff += "" if "\n" in trozo else trozo
            if _termina_en_abrev(buff):          # abreviatura: no cerrar aún
                buff += " "
                continue
            if buff.strip():
                partes.append(buff.strip())
            buff = ""
        else:
            buff += trozo
    if buff.strip():
        partes.append(buff.strip())
    return partes


def atomize(texto: str) -> list[str]:
    """Trocea un texto en átomos (oraciones; las muy largas, en cláusulas). Devuelve
    los átomos con contenido, en orden. Un texto corto o de una sola idea se devuelve
    entero (lista de un elemento): atomizar no debe fragmentar lo que ya es atómico."""
    if not isinstance(texto, str) or not texto.strip():
        return []
    oraciones = _por_oraciones(texto) or [texto.strip()]
    atomos: list[str] = []
    for o in oraciones:
        if len(o) > _LARGA:
            trozos = [c.strip() for c in _CLAUSULA.split(o) if c and c.strip()]
            for c in trozos:
                if len(c) >= _MIN_ATOMO:
                    atomos.append(c)
        elif len(o.strip()) >= _MIN_ATOMO or len(oraciones) == 1:
            atomos.append(o.strip())
    # Nada sobrevivió el filtro (texto muy corto): devolver el original entero.
    return atomos or [texto.strip()]
