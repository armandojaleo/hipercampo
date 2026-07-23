# Guía de instalación de hipercampo

🌍 **English: [INSTALL.md](INSTALL.md)** · Estás leyendo la versión en español.

De cero a "Claude tiene memoria" en unos minutos. Elige **una** de las dos vías
(A: Python local — la más simple para empezar; B: Docker — más portable).

Requisitos: **Python 3.11+** (vía A) o **Docker** (vía B). Windows, macOS o Linux.

---

## El mapa: cómo se organiza la memoria

Antes de configurar nada, el modelo mental. Toda la memoria es **un solo fichero
SQLite**. Dentro, los *namespaces* son cajones separados. Un ejemplo con dos
proyectos imaginarios, `webshop` y `blog`:

```
                UN SOLO FICHERO:  ~/.hipercampo/hipercampo.db
                ─────────────────────────────────────────────
                  (los namespaces son cajones dentro de él)

   ┌─ __self__ ─────────────┐        ┌─ personal ─────────────┐
   │ identidad de trabajo   │        │ quién eres tú:         │
   │ del agente: reglas,    │        │ rol, preferencias,     │
   │ decisiones, lecciones  │        │ cómo te gusta trabajar │
   └────────────────────────┘        └────────────────────────┘
     se lee en cada sesión             servidor "memoria", global

   ┌─ proj-webshop ─────────┐        ┌─ proj-blog ────────────┐
   │ lo técnico de la       │        │ lo técnico del         │
   │ tienda: stack, deploy, │        │ blog: stack, deploy,   │
   │ gotchas, decisiones    │        │ gotchas, decisiones    │
   └────────────────────────┘        └────────────────────────┘
        ▲                                 ▲
        │ servidor "proyecto"             │ servidor "proyecto"
        │ (.mcp.json de la tienda)        │ (.mcp.json del blog)
     ~/code/webshop                    ~/code/blog


   QUIÉN VE A QUIÉN   (con HIPERCAMPO_LINKED="*")
   ─────────────────────────────────────────────
    trabajando en webshop:   ══> ESCRIBE en  proj-webshop  ← y solo ahí
                             ──> lee de      personal, __self__, proj-blog

    trabajando en blog:      ══> ESCRIBE en  proj-blog
                             ──> lee de      personal, __self__, proj-webshop

   ══> flecha de ESCRITURA: una sola, hacia tu propio cajón
   ──> flecha de LECTURA: hacia los enlazados, y nunca vuelve
```

**La asimetría es la garantía**: lo enlazado **se lee, nunca se toca**. Guardar,
reforzar, actualizar, consolidar y olvidar operan solo sobre el proyecto propio.
Un proyecto no enlazado es directamente invisible.

> ⚠️ **El cajón `default`.** Si guardas recuerdos antes de definir
> `HIPERCAMPO_NAMESPACE`, van a un cajón llamado `default`. No es un error —
> funciona— pero es un cajón sin dueño: cualquier proyecto lo lee y nadie lo
> siente suyo. Si te ha pasado, reparte su contenido a los cajones que le
> corresponden (ver *Mover recuerdos de un cajón a otro*, más abajo).

---

## Paso 0 · Conseguir el código

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
```

---

## Vía A · Instalar desde PyPI (recomendada)

```bash
pip install hipercampo                 # o: pip install "hipercampo[semantic]"
```

### Desde el código fuente (colaboradores)

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo && pip install -e .
```

### A.2 Comprobar que funciona (sin Claude todavía)

```bash
python scripts/demo.py        # ves el ciclo completo: sorpresa, recuerdo, sueño, olvido
python -m pytest -q           # o: python tests/test_memory.py
```

### A.3 Arrancar el servidor MCP a mano (opcional, para verlo vivo)

```bash
python -m hipercampo.server
```

Se queda esperando por stdio (es lo normal en MCP). Córtalo con Ctrl+C. No hace
falta lanzarlo tú: lo lanzará Claude automáticamente al conectarlo (paso siguiente).

---

## Vía B · Docker

```bash
docker compose build
```

La memoria se guarda en el volumen `hipercampo_data`. Para una prueba manual:

```bash
docker compose run --rm hipercampo   # arranca el server (stdio); Ctrl+C para salir
```

---

## Paso final · Conectar con Claude

### Claude Code (CLI / extensión de VSCode)

**Opción 1 — con el comando** (desde la carpeta del proyecto):

```bash
# Vía A (Python):
claude mcp add hipercampo -- python -m hipercampo.server

# Vía B (Docker):
claude mcp add hipercampo -- docker run --rm -i -v hipercampo_data:/data hipercampo:latest
```

**Opción 2 — a mano**: crea un archivo `.mcp.json` en la raíz del proyecto:

```json
{
  "mcpServers": {
    "hipercampo": {
      "command": "python",
      "args": ["-m", "hipercampo.server"],
      "env": { "HIPERCAMPO_DB": "./data/hipercampo.db" }
    }
  }
}
```

Reinicia Claude Code. Deberías ver 18 herramientas: `hc_remember`, `hc_recall`,
`hc_muse`, `hc_dream`, `hc_accept_bridge`, `hc_reject_bridge`, `hc_update`,
`hc_remember_fact`, `hc_ask_role`, `hc_consolidate`, `hc_forget`, `hc_stats`.

### Memoria compartida entre TODOS los proyectos (global)

El `.mcp.json` del paso anterior activa hipercampo **solo en ese proyecto**. Como la
base de datos ya vive en una ruta global (`~/.hipercampo/hipercampo.db`), los datos
se comparten igual; lo único "por proyecto" es el registro del servidor.

Para que Claude tenga las herramientas en **cualquier** proyecto, registra el
servidor a nivel **usuario**:

```bash
claude mcp add --scope user hipercampo -- python -m hipercampo.server
```

O a mano, añade un bloque `mcpServers` de nivel raíz en `~/.claude.json` (Claude
Code) — misma forma que el `.mcp.json`, pero en el archivo global del usuario. Usa
rutas absolutas del ejecutable de Python y de `HIPERCAMPO_DB`. Reinicia Claude Code.

> Puedes tener ambos (global + `.mcp.json` del repo): si apuntan a la misma BD y
> comando, es inofensivo. El `.mcp.json` del repo es útil para quien clone el proyecto.

### Aislar contextos: namespaces (recomendado) o ficheros distintos

Dos formas de que lo de un proyecto no se mezcle con otro (local-first, ambas válidas):

**Opción A — namespaces (una sola BD).** Añade `HIPERCAMPO_NAMESPACE` al `env` de
cada servidor. Cada recuerdo lleva su contexto y **nada cruza** (lecturas, escrituras
por id y enlaces, todo acotado):

```json
"env": {
  "HIPERCAMPO_DB": "C:/Users/tu/.hipercampo/hipercampo.db",
  "HIPERCAMPO_NAMESPACE": "proj-webshop"
}
```

**Opción B — ficheros distintos.** Un `HIPERCAMPO_DB` por proyecto (abajo). Es
aislamiento **local entre contextos**, no una frontera de seguridad multiusuario
(ver [SECURITY.md](SECURITY.md)).

### Híbrida: memoria personal + memoria por proyecto

Dos servidores con **BD distinta** (o mismo fichero y distinto namespace), para que
lo técnico de un proyecto no se mezcle con otro pero Claude te siga conociendo:

**1) Personal (global, `~/.claude.json`)** — un servidor `memoria` con su propia BD:

```json
"mcpServers": {
  "memoria": {
    "command": "C:/Python313/python.exe",
    "args": ["-m", "hipercampo.server"],
    "env": { "HIPERCAMPO_DB": "C:/Users/tu/.hipercampo/personal.db" }
  }
}
```

**2) Por proyecto (`.mcp.json` en la raíz de cada proyecto)** — un servidor
`proyecto` con una BD propia por proyecto:

```json
{
  "mcpServers": {
    "proyecto": {
      "command": "C:/Python313/python.exe",
      "args": ["-m", "hipercampo.server"],
      "env": { "HIPERCAMPO_DB": "C:/Users/tu/.hipercampo/proj-NOMBRE.db" }
    }
  }
}
```

Cambia `proj-NOMBRE.db` por proyecto (`proj-webshop.db`, `proj-blog.db`...). Claude
verá dos juegos de herramientas (`memoria` y `proyecto`) y elegirá dónde guardar
cada cosa. Para copiar tu memoria actual a la personal: `python -m hipercampo.backup
C:/Users/tu/.hipercampo/personal.db` (con `HIPERCAMPO_DB` apuntando a la vieja).

### Claude Desktop

Edita el archivo de configuración:

- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

```json
{
  "mcpServers": {
    "hipercampo": {
      "command": "docker",
      "args": ["run", "--rm", "-i",
               "-v", "hipercampo_data:/data",
               "hipercampo:latest"]
    }
  }
}
```

(O con Python: `"command": "python"`, `"args": ["-m", "hipercampo.server"]`, y
`"env": {"HIPERCAMPO_DB": "C:/ruta/a/hipercampo.db"}`.)

Reinicia Claude Desktop.

---

## Comprobar que Claude ya tiene memoria

En una conversación con Claude, pídele:

> «Guarda en tu memoria que prefiero respuestas directas» → usará `hc_remember`.
> Más tarde: «¿qué recuerdas sobre cómo prefiero que me hables?» → usará `hc_recall`.

También puedes verificar el servidor sin Claude, con un handshake MCP crudo:

```bash
printf '%s\n' \
'{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"t","version":"0"}}}' \
'{"jsonrpc":"2.0","method":"notifications/initialized"}' \
'{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | python -m hipercampo.server
```

Debe listar las 18 herramientas `hc_*`.

---

## Modo SINÁPTICO (que la memoria dispare sola en cada turno)

Por defecto, la memoria es *pull*: Claude decide cuándo llamarla. Con un **hook** de
Claude Code puede dispararse **en cada mensaje tuyo**, como una sinapsis.

hipercampo decide solo qué toca (`hipercampo assist`): recordar si preguntas,
inspirar si estás atascado, sugerir guardar/actualizar si afirmas algo nuevo, o
**callarse** si no hay nada relevante. Nunca escribe por su cuenta.

En `~/.claude/settings.json` (global) o `.claude/settings.json` (del proyecto):

```json
{
  "hooks": {
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "hipercampo hook",
            "timeout": 15,
            "statusMessage": "consultando la memoria..."
          }
        ]
      }
    ]
  }
}
```

`hipercampo hook` lee el JSON del hook por **stdin**, decide qué toca y devuelve el
contexto a inyectar (`hookSpecificOutput.additionalContext`). Si no hay nada
relevante devuelve `{}`: **no molesta**. Pruébalo a mano antes:

```bash
echo '{"prompt":"¿dónde está alojado el servidor?"}' | hipercampo hook
echo '{"prompt":"mañana compraré pan"}' | hipercampo hook     # -> {} : se calla
```

Tras editarlo, abre `/hooks` una vez (recarga la configuración) o reinicia Claude
Code. Si prefieres no usar hooks, la herramienta **`hc_assist`** hace lo mismo
cuando Claude la llama al principio del turno.

### Ver qué está haciendo (transparencia)

Cada decisión se registra —a stderr (visible en los logs del servidor MCP) y a un
fichero junto a la base de datos:

```bash
hipercampo log -n 20     # qué ha decidido últimamente y por qué
hipercampo doctor        # ruta de la BD, permisos, versión, dependencias
```

```
20:47:05 remember  guardado id=1 · novedad=1.0 · sorpresa=1.0
20:47:06 remember  saltado: redundante · novedad=0.0 · sorpresa=0.57
20:47:07 recall    abstención: nada destaca del ruido · n=14
20:47:07 assist    nothing: nada relevante que aportar en este turno
```

Se desactiva con `HIPERCAMPO_LOG=0`.

### Lo que cuesta en tokens (y cómo bajarlo)

Una memoria que se come la ventana de contexto no ayuda: estorba. hipercampo
gasta por dos sitios muy distintos, y conviene saber cuál es cuál:

```bash
python scripts/tokens.py       # la factura, medida en tu propia máquina
```

| Fuente | Coste | Cuándo se paga |
|---|---:|---|
| Herramientas anunciadas (7, por defecto) | ~810 tok | en **cada** petición |
| …con `HIPERCAMPO_TOOLS=all` (las 18) | ~2.070 tok | en cada petición |
| Identidad de trabajo (al arrancar) | ≤500 tok | 1 vez por sesión |
| Inyección del hook | ≤350 tok | solo en los turnos que disparan |

Lo caro **no** es la memoria: son las descripciones de las herramientas, que
viajan en cada petición aunque nunca la uses. Por eso, de entrada solo se anuncian
las seis de uso diario (`hc_remember`, `hc_recall`, `hc_update`, `hc_learn`,
`hc_assist`, `hc_stats`) más `hc_tools`.

**No se pierde nada.** Las otras doce están a una llamada:

```
hc_tools()                                     -> lista lo que hay, una línea cada una
hc_tools(name="hc_dream", args={"max_bridges": 3})   -> la activa Y la ejecuta
```

Al activarse quedan registradas y el servidor avisa al cliente
(`tools/list_changed`), así que a partir de ahí se llaman como cualquier otra. Se
ejecutan además en la misma llamada a propósito: si un cliente ignora el aviso, la
capacidad tiene que seguir estando disponible igual.

¿Prefieres las 18 anunciadas desde el principio? `"HIPERCAMPO_TOOLS": "all"`.

Los presupuestos de inyección se ajustan con `HIPERCAMPO_HOOK_BUDGET` (350 por
defecto, `0` lo desactiva) y `HIPERCAMPO_IDENTITY_BUDGET` (500). Los recuerdos
entran **enteros o no entran**: uno cortado por la mitad parece información y no lo
es, así que el que no cabe se omite y **se dice cuántos faltan** y cómo pedirlos.

Para ver la factura acumulada: `hipercampo log --accion tokens`, o el campo
`tokens` de `hc_stats`. Aviso honesto: la cuenta es una **estimación** por
caracteres (~3,7 por token); instala `tiktoken` si quieres exactitud.

### ¿Está sana la memoria?

```bash
hipercampo doctor          # entorno: ruta, permisos, dependencias, estado
```

o la herramienta **`hc_health`** desde el chat: comprueba integridad del fichero,
esquema, lectura y permiso de escritura. Si la base de datos falla en medio de una
operación, hipercampo **avisa en el registro, reconecta y reintenta una vez**; si aun
así no puede, devuelve un error legible en vez de tirar el servidor MCP.

### Memoria entre proyectos (contextos enlazados)

Cada proyecto sigue teniendo su memoria aislada, pero puedes **enlazar** otros en
solo lectura para que te den ideas:

```jsonc
// .mcp.json del proyecto
"env": { "HIPERCAMPO_NAMESPACE": "mi-proyecto",
         "HIPERCAMPO_LINKED": "otro-proyecto,tercero" }   // o "*" = todos
```

Las respuestas de `hc_recall`/`hc_muse` marcan lo ajeno con `"project": "..."`.
La asimetría es la garantía: lo enlazado **se lee, nunca se toca** — escribir,
reforzar, actualizar, consolidar y olvidar operan solo sobre el proyecto propio,
y un proyecto no enlazado sigue siendo invisible.

### Sueño autónomo

Cada **50 escrituras** (variable `HIPERCAMPO_AUTOSLEEP_EVERY`, `0` lo desactiva)
hipercampo **se mantiene sola**: consolida, adormece lo que ya no vale y propone
puentes. Como un cerebro que duerme sin que se lo manden. También puedes pedírselo:
`hipercampo sleep` o la herramienta `hc_sleep`.

## Controlar y respaldar la memoria

Toda la memoria de hipercampo es **un único fichero SQLite**. Fácil de ver, mover,
copiar o borrar.

### ¿Dónde está?

Por defecto:

- **Local (Windows)**: `C:\Users\<tú>\.hipercampo\hipercampo.db`
- **Local (macOS/Linux)**: `~/.hipercampo/hipercampo.db`
- **Docker**: dentro del volumen `hipercampo_data` (`/data/hipercampo.db`)

Puedes cambiarla con la variable **`HIPERCAMPO_DB`** (en el `env` de la config MCP,
o al lanzar el server). Y puedes preguntárselo a Claude: la herramienta `hc_stats`
devuelve el campo `db` con la ruta absoluta.

### Controlar su uso desde Claude

Las 18 herramientas te dan control total, sin tocar código:

| Quieres… | Pídele a Claude (usa la tool) |
|----------|-------------------------------|
| Ver cuánto recuerda y dónde | `hc_stats` |
| Que guarde algo concreto | `hc_remember` (con `importance` alta para que no se olvide) |
| Que recuerde algo | `hc_recall` |
| Actualizar un hecho que cambió | `hc_update` |
| Condensar (fase de sueño) | `hc_consolidate` |
| Podar lo viejo/trivial | `hc_forget` (usa `dry_run=true` para ver antes qué se iría) |
| Empezar de cero | cierra el server y borra el fichero `.db` |

Los umbrales (cuándo algo es "novedoso", "predecible", cuándo se olvida) están al
inicio de [`hipercampo/memory.py`](hipercampo/memory.py) — comentados y ajustables.

### Mover recuerdos de un cajón a otro

Si empezaste sin namespaces y todo cayó en `default`, o quieres que lo técnico de
un proyecto viva en su propio cajón, se reparte con SQL. **Haz copia primero** —
esto toca la memoria viva:

```bash
python -m hipercampo.backup            # copia de seguridad, siempre lo primero
```

```sql
-- Ver qué hay y dónde:
SELECT namespace, count(*) FROM memories GROUP BY 1;
SELECT id, namespace, substr(text,1,80) FROM memories WHERE namespace='default';

-- Mover unos recuerdos concretos a su proyecto (ids 3, 13, 14 de ejemplo):
UPDATE memories SET namespace='proj-webshop' WHERE id IN (3,13,14);
UPDATE links    SET namespace='proj-webshop' WHERE src IN (3,13,14) AND dst IN (3,13,14);

-- Los enlaces que quedan cruzando entre cajones distintos son ruido: bórralos.
DELETE FROM links
 WHERE (src IN (3,13,14)) != (dst IN (3,13,14));
```

Dos avisos por experiencia propia: **mueve los enlaces con los recuerdos** (si no,
el grafo se queda cojo), y **antes de borrar un duplicado compara el texto entero**,
no solo el principio. Al terminar, comprueba que no quedan huérfanos:

```sql
SELECT src, dst FROM links
 WHERE src NOT IN (SELECT id FROM memories) OR dst NOT IN (SELECT id FROM memories);
```

### Backup y restauración

```bash
# Copia de seguridad (consistente, aunque el server esté activo):
python -m hipercampo.backup                       # -> <db>.YYYYMMDD-HHMMSS.bak
python -m hipercampo.backup C:\copias\hc.db        # -> a la ruta que elijas

# Restaurar desde una copia:
python -m hipercampo.backup --restore C:\copias\hc.db
```

O simplemente **copia el fichero `.db`** con el server parado; es igual de válido.
En Docker: `docker run --rm -v hipercampo_data:/data -v "%cd%":/backup alpine \
cp /data/hipercampo.db /backup/`.

---

## Semántica opcional (para sinónimos)

Por defecto hipercampo es léxico (CPU, sin GPU). Si quieres que capte sinónimos:

```bash
pip install -e ".[semantic]"     # trae sentence-transformers (Apache-2.0)
```

Y actívala en el servidor con una variable de entorno (en el `env` de tu config MCP):

```json
"env": {
  "HIPERCAMPO_DB": "C:/Users/tu/.hipercampo/hipercampo.db",
  "HIPERCAMPO_SEMANTIC": "1"
}
```

(O en código: `from hipercampo import encoder; encoder.enable_semantic()`.)

Sube el MRR global de recuperación de **0.77 a 0.95** en el banco de estrés
(`python scripts/stress.py --semantic`). La 1ª vez descarga el modelo. Ver
[ATTRIBUTION.md](ATTRIBUTION.md) para licencias del modelo.

---

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `No module named hipercampo` | No hiciste `pip install -e .` en la carpeta del proyecto. |
| Claude no ve las herramientas | Reinicia el cliente tras editar la config; revisa que la ruta/comando sea correcta. |
| El comando `hipercampo` no existe | Usa `python -m hipercampo.server` (el script de consola puede no estar en el PATH). |
| Docker: "cannot access stdin" | Falta `-i` en `docker run` (MCP habla por stdin). |
| La memoria "se pierde" | En Docker, comprueba que montas el volumen `-v hipercampo_data:/data`. |
