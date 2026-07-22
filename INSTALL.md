# Guía de instalación de hipercampo

De cero a "Claude tiene memoria" en unos minutos. Elige **una** de las dos vías
(A: Python local — la más simple para empezar; B: Docker — más portable).

Requisitos: **Python 3.11+** (vía A) o **Docker** (vía B). Windows, macOS o Linux.

---

## Paso 0 · Conseguir el código

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
```

---

## Vía A · Python local (recomendada para empezar)

### A.1 Instalar

```bash
pip install -e .
```

Esto instala `hipercampo` y su única dependencia real (numpy) + el SDK de MCP.

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

Reinicia Claude Code. Deberías ver 5 herramientas nuevas: `hc_remember`,
`hc_recall`, `hc_consolidate`, `hc_forget`, `hc_stats`.

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

### Híbrida: memoria personal + memoria por proyecto (recomendada con varios proyectos)

Dos servidores con **BD distinta**, para que lo técnico de un proyecto no se mezcle
con otro pero Claude te siga conociendo en todos:

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

Cambia `proj-NOMBRE.db` por proyecto (`proj-mplayer.db`, `proj-web.db`...). Claude
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

Debe listar las 5 herramientas `hc_*`.

---

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

Las 5 herramientas te dan control total, sin tocar código:

| Quieres… | Pídele a Claude (usa la tool) |
|----------|-------------------------------|
| Ver cuánto recuerda y dónde | `hc_stats` |
| Que guarde algo concreto | `hc_remember` (con `importance` alta para que no se olvide) |
| Que recuerde algo | `hc_recall` |
| Condensar (fase de sueño) | `hc_consolidate` |
| Podar lo viejo/trivial | `hc_forget` (usa `dry_run=true` para ver antes qué se iría) |
| Empezar de cero | cierra el server y borra el fichero `.db` |

Los umbrales (cuándo algo es "novedoso", "predecible", cuándo se olvida) están al
inicio de [`hipercampo/memory.py`](hipercampo/memory.py) — comentados y ajustables.

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
