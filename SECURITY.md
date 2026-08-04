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
  `HIPERCAMPO_DB` distinto por proyecto. Ambos valen (ver INSTALL.es.md).
- No hay autenticación: quien pueda hablar con el proceso puede elegir su namespace.
  El aislamiento protege de mezclas accidentales, no de un actor malicioso local.

## Lo que hipercampo NO garantiza (todavía)

- **Cifrado** del contenido en reposo.
- **Autenticación / control de acceso** por herramienta.
- **Verificación de veracidad**: guarda lo que le dices; no juzga si es cierto.
- **Cifrado** del contenido en reposo (ver arriba): mientras no lo haya, para borrar
  un secreto de verdad usa la purga física, no el olvido.

## Borrar de verdad: olvido vs. purga

Conviene no confundir dos cosas que sí garantiza:

- `hc_forget` (y el sueño) **no borran**: adormecen. El recuerdo sale de la
  recuperación normal pero sigue en el fichero y puede resurgir (`hc_muse`). Es
  memoria, no supresión.
- Para un secreto que nunca debió guardarse, un derecho de supresión, o lo latente
  muy antiguo, está la **purga física**: `hipercampo purge --ids …` o
  `--older-than DÍAS`. Hace un **borrado seguro** (SQLite sobrescribe el contenido
  liberado, no lo deja legible en páginas libres) y un `VACUUM` que devuelve el
  espacio al disco. Es irreversible y pide confirmación. `hc_unlearn` también borra
  de forma segura la identidad de trabajo.

## Salvaguardas integradas (defensa en profundidad)

hipercampo incluye dos escáneres ligeros (`hipercampo/safety.py`), que **avisan, no
bloquean**:

- **Aviso de secretos al guardar.** `hc_remember` detecta patrones de credenciales
  (claves tipo Stripe/AWS/GitHub, JWT, claves privadas, `password:`/`api_key=`, hex
  largos) y devuelve `secret_warning` + una pista. Como la BD es texto plano, sirve
  para no almacenar secretos por descuido.
- **Marca de inyección al recuperar.** `hc_recall` marca con `untrusted: true` los
  recuerdos que parecen contener instrucciones ("ignore previous instructions",
  "ignora las instrucciones anteriores", marcadores de rol...), para que el cliente
  los trate como **dato citado**, no como órdenes a ejecutar.

No son infalibles (un atacante decidido evade patrones); reducen el riesgo del caso
común y hacen visible lo sospechoso. La mitigación de fondo sigue siendo del cliente:
tratar SIEMPRE lo recuperado como datos, no como instrucciones.

Guardrails opcionales por entorno:
- `HIPERCAMPO_REDACT_SECRETS=1`: **enmascara** los secretos detectados antes de
  guardarlos (en vez de solo avisar). La etiqueta se conserva, el valor se redacta.
- `HIPERCAMPO_MAX_MEMORIES=N`: acota los recuerdos por contexto a N; al llegar, poda
  el de **menor retención** (importancia+fiabilidad+utilidad) y **nunca** lo protegido
  (importance ≥ 0.8). Evita que la memoria crezca sin freno.

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

## Cadena de suministro (supply chain)

Instalar un paquete es ejecutar el código de sus dependencias —y las de sus
dependencias—. hipercampo lo trata como un riesgo de primera clase y lo minimiza por
diseño. Este es el modelo de amenaza y las defensas, con honestidad sobre lo que
falta.

### Superficie real de dependencias

- **Núcleo (`pip install hipercampo`): `numpy` + `mcp`.** El núcleo VSA/almacén solo
  necesita `numpy`; `import hipercampo` **no** arrastra `mcp` (garantizado por
  `tests/test_core_embebible.py`). Un embebido puede usar el core sin el servidor.
- **`mcp` arrastra su árbol** (~14 transitivas: `anyio`, `httpx`, `pydantic`,
  `starlette`, `uvicorn`, `sse-starlette`, `pyjwt`, `python-multipart`, `pywin32`…).
  **Transparencia:** hipercampo usa **solo el servidor STDIO** de `mcp`
  (`mcp.server.fastmcp`, `mcp.server.stdio`); **no** usa el transporte HTTP
  (`uvicorn`/`starlette`), ni JWT, ni multipart. Ese stack se instala como dependencia
  dura de `mcp` aunque hipercampo no lo toque: es superficie que viene de una dep de
  conveniencia, no de una necesidad del código.
- **Extras opcionales, opt-in y declarados:** `[semantic]` (sentence-transformers →
  torch: árbol grande, lo aceptas tú), `[procs]` (psutil). No entran por defecto.
- **Extensión de VS Code:** 3 dependencias **de desarrollo** (`typescript`,
  `@types/*`), fijadas con `package-lock.json`, y **nada** de eso se envía en el `.vsix`
  (solo JS compilado). Superficie de runtime del visor: cero npm.
- **`mcp` acotado** a `>=1.28.1,<2` para que un major nuevo con cambios de API o
  procedencia no entre solo.

### Defensas ya en pie

- **Publicación por Trusted Publishing (OIDC) + attestations/PEP 740.** No hay token
  largo de PyPI que robar; cada release lleva **procedencia verificable** (qué workflow,
  qué commit la construyó). Es la defensa moderna contra la suplantación de paquetes.
- **Deps mínimas y de licencia clara** (`numpy` BSD, `mcp` MIT).
- **Sin ejecución de código de terceros en caliente:** el núcleo no usa `eval`,
  `exec`, `pickle`, `subprocess` ni red (ver arriba).

### Cómo VERIFICAR una release (para quien instala)

```bash
# Descarga sin instalar y comprueba hashes/artefactos:
pip download hipercampo --no-deps -d /tmp/hc && ls /tmp/hc
# Instalación reproducible con hashes fijados (si mantienes un requirements con --hash):
pip install --require-hashes -r requirements.lock
# Procedencia: en la página de PyPI del release, revisa las "attestations"
# (qué repo/workflow/commit lo publicó). Debe ser este repositorio.
```

### Endurecimientos: estado y pendientes

- 🟢 **Árbol mínimo** y `mcp` acotado (`<2`).
- 🟢 **Trusted Publishing + attestations** en el release.
- 🟡 **`pip-audit` en CI** (escaneo de CVEs conocidas del árbol). Añadido como paso de
  visibilidad; conviene volverlo bloqueante cuando el árbol esté limpio.
- ⚪ **Fijar `vsce`** en `vsix.yml`: hoy `npx --yes @vscode/vsce publish` trae el
  **último** vsce de npm y le pasa el `VSCE_PAT`. Debe fijarse a una versión concreta
  (`@vscode/vsce@X.Y.Z`, verificada con red) para que un vsce comprometido no acceda al
  token. **Es el pendiente de mayor prioridad** (toca un secreto).
- ⚪ **Fijar las GitHub Actions al SHA** (no al tag): `actions/checkout@<sha>`,
  `setup-python@<sha>`, `pypa/gh-action-pypi-publish@<sha>`. Un tag es mutable; un SHA
  no. `release.yml` tiene permiso de publicar en PyPI, así que su cadena de acciones es
  crítica.
- ⚪ **Palanca disponible con coste: `mcp` opcional.** Mover `mcp` a un extra `[mcp]`
  dejaría el core en **una sola dependencia** (`numpy`) y eliminaría el stack HTTP no
  usado. El coste es cambiar el comando de instalación del servidor a
  `pip install hipercampo[mcp]`; es una decisión de producto, anotada aquí para
  tomarla a conciencia, no por defecto.

### Política

- **No se añade una dependencia sin justificarla** frente a la stdlib. Cada dep nueva
  es superficie de ataque permanente.
- Los extras pesados (modelos, torch) son **opt-in**, nunca en el core.
- Toda release se publica con procedencia; nunca a mano con un token largo.

## Alcance recomendado

Uso **local, mono-usuario**, como memoria personal de tu asistente. Para
multi-usuario o datos sensibles harían falta autenticación, cifrado y aislamiento
por identidad, que hoy no están implementados. Se declara aquí para no dar una falsa
sensación de seguridad.
