"""
Memoria de IDENTIDAD DE TRABAJO — la memoria del agente, no la del usuario.

El resto de hipercampo guarda memoria **del mundo**: hechos, proyectos, gotchas.
Esto guarda lo otro, lo que se pierde cada vez que se cierra una sesión: **qué se
aprendió trabajando**. Las reglas que el usuario confirmó, los errores que no hay
que repetir, las decisiones que ya se tomaron y por qué. Sin esto, cada sesión
vuelve a empezar de cero y vuelve a tropezar en la misma piedra.

No es conciencia. Es **continuidad de criterio**, que es lo que de verdad separa
a una herramienta que se usa de una que crece:

    regla       cómo hay que trabajar (lo dijo el usuario, o se acordó)
    lección     qué salió mal y qué se aprendió (para no repetirlo)
    decisión    qué se decidió y POR QUÉ (para no volver a discutirlo)
    preferencia cómo le gusta al usuario que se le responda

Vive en un contexto reservado (`__self__`) que:
  - es LEGIBLE desde cualquier proyecto (la identidad no es de un proyecto),
  - solo se escribe a propósito (`hc_learn`), nunca por accidente,
  - NO se olvida con el tiempo: una lección aprendida no caduca por desuso.
"""

SELF_NAMESPACE = "__self__"

TIPOS = {
    "regla": "cómo hay que trabajar",
    "leccion": "qué salió mal y qué se aprendió",
    "decision": "qué se decidió y por qué",
    "preferencia": "cómo le gusta al usuario que se le responda",
}

# Una lección aprendida no se desvanece por no usarla durante un tiempo: se
# protege del olvido activo como cualquier recuerdo de importancia máxima.
IMPORTANCIA_IDENTIDAD = 0.95


def formatear(filas: list) -> str:
    """La identidad, en texto listo para inyectar al principio de una sesión."""
    if not filas:
        return ""
    por_tipo: dict[str, list[str]] = {}
    for r in filas:
        texto = r["text"]
        tipo, _, cuerpo = texto.partition(": ")
        if tipo not in TIPOS:
            tipo, cuerpo = "leccion", texto
        por_tipo.setdefault(tipo, []).append(cuerpo)

    plural = {"regla": "REGLAS", "preferencia": "PREFERENCIAS",
              "decision": "DECISIONES", "leccion": "LECCIONES"}
    partes = []
    for tipo in ("regla", "preferencia", "decision", "leccion"):
        if tipo in por_tipo:
            partes.append(f"{plural[tipo]} ({TIPOS[tipo]}):")
            partes += [f"  · {c}" for c in por_tipo[tipo]]
    return "\n".join(partes)
