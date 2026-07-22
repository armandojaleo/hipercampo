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

## Aislamiento entre contextos / proyectos

hipercampo **sí** separa por **namespace** dentro de una misma base de datos: cada
recuerdo lleva su namespace y todas las lecturas y escrituras (incluidas las que van
por id: `delete`, `touch`, `mark_*`) están acotadas a él, y los enlaces no cruzan
contextos. Es aislamiento **local entre contextos** (proyectos, perfiles, agentes),
**no** una frontera de seguridad entre clientes de un servidor —hipercampo es
local-first, un proceso por contexto—. Para separar:

- Un `HIPERCAMPO_NAMESPACE` distinto por contexto (mismo `.db`), o un
  `HIPERCAMPO_DB` distinto por proyecto. Ambos valen (ver INSTALL.md).
- No hay autenticación: quien pueda hablar con el proceso puede elegir su namespace.
  El aislamiento protege de mezclas accidentales, no de un actor malicioso local.

## Lo que hipercampo NO garantiza (todavía)

- **Cifrado** del contenido en reposo.
- **Autenticación / control de acceso** por herramienta.
- **Verificación de veracidad**: guarda lo que le dices; no juzga si es cierto.
- **Borrado seguro**: `hc_forget` elimina filas, pero pueden quedar restos en el
  fichero SQLite hasta un `VACUUM`.

## ¿Es seguro instalar y ejecutar hipercampo?

Para quien lo instala en su máquina, la superficie de ataque es pequeña **por diseño**:

- **Local, sin red.** El servidor MCP habla por stdio con tu cliente Claude; no abre
  puertos ni escucha en la red. No es atacable remotamente.
- **No ejecuta código de tus recuerdos.** hipercampo solo *guarda y recupera texto*.
  No hay `eval`, `exec`, `os.system`, `subprocess` ni `pickle` en el núcleo.
- **SQL parametrizado.** Todas las consultas usan placeholders (`?`); no hay
  concatenación de strings en SQL → sin inyección.
- **Dependencias mínimas y auditables:** `numpy` (BSD) y `mcp` (MIT). El hook
  semántico es **opcional** y, si lo activas, descarga un modelo de HuggingFace
  (sentence-transformers, Apache-2.0): eso es una dependencia de cadena de
  suministro que aceptas tú al instalar el extra `[semantic]`.
- **El repositorio no contiene datos personales.** Las claves/contraseñas que veas
  en `scripts/` y `tests/` (p. ej. `hcdemo_9f`, `girasol2024`) son **fixtures
  ficticios** para los benchmarks, no credenciales reales.

Precauciones sensatas:
- La BD es **SQLite en claro** (sin cifrar). No guardes en la memoria secretos que
  no quieras tener en disco sin cifrar.
- Trata un fichero `.db` de **origen desconocido** como dato no confiable: su
  contenido acabará en el contexto del modelo al recuperarse (ver inyección arriba).
- Instala desde el repositorio oficial y revisa el código; es pequeño a propósito.

## Alcance recomendado

Uso **local, mono-usuario**, como memoria personal de tu asistente. Para
multi-usuario o datos sensibles harían falta autenticación, cifrado y aislamiento
por identidad, que hoy no están implementados. Se declara aquí para no dar una falsa
sensación de seguridad.
