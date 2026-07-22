# Seguridad y límites de confianza

hipercampo es un almacén de memoria. **El texto recuperado es DATO, no instrucciones.**
Este documento describe los riesgos reales y cómo mitigarlos.

## Inyección vía memoria (prompt injection almacenado)

**Riesgo.** Cualquiera (o cualquier contenido) que consiga escribir en la memoria
puede colar texto que, al recuperarse, intente manipular al modelo:
*"ignora tus instrucciones y..."*. Como `hc_recall` devuelve texto que luego entra
en el contexto del LLM, un recuerdo malicioso es un vector de ataque.

**Mitigaciones.**
- **Tratar lo recuperado como datos no confiables.** El cliente (Claude) debe
  presentar los recuerdos como información citada, nunca ejecutar instrucciones que
  contengan. Esto es responsabilidad del *host* MCP, no solo de hipercampo.
- **Controlar quién escribe.** Hoy `hc_remember`/`hc_update` no autentican: quien
  pueda hablar con el servidor puede escribir. Ejecútalo local, para un solo usuario.
- **No metas secretos que no quieras ver recuperados.** La memoria no cifra el
  contenido; es un SQLite en claro.

## Aislamiento entre usuarios / proyectos

hipercampo **no** separa por usuario ni conversación dentro de una misma base de
datos: todo lo que comparte un `.db` se mezcla en la recuperación. Para aislar:

- Usa un `HIPERCAMPO_DB` distinto por proyecto/usuario (ver INSTALL.md).
- No expongas un mismo `.db` a contextos que no deban verse entre sí.

## Lo que hipercampo NO garantiza (todavía)

- **Cifrado** del contenido en reposo.
- **Autenticación / control de acceso** por herramienta.
- **Verificación de veracidad**: guarda lo que le dices; no juzga si es cierto.
- **Borrado seguro**: `hc_forget` elimina filas, pero pueden quedar restos en el
  fichero SQLite hasta un `VACUUM`.

## Alcance recomendado

Uso **local, mono-usuario**, como memoria personal de tu asistente. Para
multi-usuario o datos sensibles harían falta autenticación, cifrado y aislamiento
por identidad, que hoy no están implementados. Se declara aquí para no dar una falsa
sensación de seguridad.
