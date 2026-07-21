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

## Semántica opcional (para sinónimos)

Por defecto hipercampo es léxico (CPU, sin GPU). Si quieres que capte sinónimos:

```bash
pip install -e ".[semantic]"     # trae sentence-transformers (Apache-2.0)
```

Y en tu arranque:

```python
from hipercampo import encoder, semantic
encoder.set_semantic_hook(semantic.make_sentence_transformer_hook())
```

Ver [ATTRIBUTION.md](ATTRIBUTION.md) para licencias del modelo.

---

## Problemas frecuentes

| Síntoma | Causa / solución |
|---|---|
| `No module named hipercampo` | No hiciste `pip install -e .` en la carpeta del proyecto. |
| Claude no ve las herramientas | Reinicia el cliente tras editar la config; revisa que la ruta/comando sea correcta. |
| El comando `hipercampo` no existe | Usa `python -m hipercampo.server` (el script de consola puede no estar en el PATH). |
| Docker: "cannot access stdin" | Falta `-i` en `docker run` (MCP habla por stdin). |
| La memoria "se pierde" | En Docker, comprueba que montas el volumen `-v hipercampo_data:/data`. |
