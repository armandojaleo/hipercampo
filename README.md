# 🧠 hipercampo

**Una memoria viva para Claude, basada en hipervectores — no en embeddings.**

La mayoría de las memorias para LLMs son lo mismo: trocear texto, convertirlo en
vectores densos y buscar los más parecidos (ANN / top-k). Eso mide *parecido*,
pero no *relevancia*, no *importancia*, y nunca *olvida*. Es un vertedero con buscador.

`hipercampo` prueba otra cosa. Es un servidor **MCP** que le da a Claude una memoria
que imita al hipocampo, con cuatro ideas integradas en un ciclo:

| Idea | Qué hace | Inspiración |
|------|----------|-------------|
| **VSA / hipervectores** | Recuerdos como vectores binarios de 10.000 bits con álgebra real (`bind`/`bundle`). Distingue *"el perro muerde al hombre"* de su inverso — cosa que un embedding denso difumina. Corre en CPU con popcount, sin GPU. | Kanerva (SDM), Plate (HRR) |
| **Escritura por sorpresa** | Solo graba lo que **no** era predecible desde lo ya sabido. Lo redundante refuerza el recuerdo existente. Ahí está el ahorro de tokens. | Error de predicción hipocampal |
| **Consolidación ("sueño")** | Un proceso offline agrupa episodios parecidos, los funde en conocimiento semántico condensado y archiva los originales. | Replay hipocampo→córtex |
| **Olvido activo** | La fuerza de un recuerdo decae con el desuso; lo débil y poco importante se poda. La importancia alta protege. | Olvido adaptativo |

> **Honestidad de ingeniería.** La "sorpresa" aquí es un *proxy por novedad*
> (`1 − máxima similitud con lo ya sabido`), no el error de predicción real del
> modelo — eso queda como gancho abierto. Y el codificador es **léxico** (basado en
> palabras), no semántico profundo: es transparente y sin GPU, a cambio de no captar
> sinónimos por sí solo. Ambas cosas son sustituibles sin tocar el resto.

---

## Prueba en 30 segundos (sin Docker, sin Claude)

```bash
pip install numpy
python scripts/demo.py
```

Verás el álgebra distinguiendo el orden de las palabras y el ciclo completo
(sorpresa → recuerdo → sueño → olvido) funcionando.

---

## Levantar con Docker

```bash
docker compose build
docker compose run --rm hipercampo   # arranca el servidor MCP (habla por stdio)
```

La memoria persiste en el volumen `hipercampo_data` (`/data/hipercampo.db`).

---

## Conectar con Claude

`hipercampo` es un **servidor MCP**. Añádelo a la config de tu cliente Claude.

**Claude Desktop** — edita `claude_desktop_config.json`:

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

**Claude Code** — en la raíz del proyecto:

```bash
claude mcp add hipercampo -- docker run --rm -i -v hipercampo_data:/data hipercampo:latest
```

(O sin Docker: `command: "python"`, `args: ["-m", "hipercampo.server"]`, con
`HIPERCAMPO_DB` apuntando a un fichero local.)

Reinicia el cliente y Claude tendrá cinco herramientas nuevas.

---

## Herramientas que gana Claude

| Herramienta | Para qué |
|-------------|----------|
| `hc_remember(text, importance)` | Guarda algo (solo si es novedoso). `importance>=0.8` lo protege del olvido. |
| `hc_recall(query, k)` | Recupera por similitud **+ propagación de activación** por asociaciones. |
| `hc_consolidate()` | Fase de sueño: funde episodios en conocimiento semántico. |
| `hc_forget(dry_run)` | Olvido activo. `dry_run=True` ensaya sin borrar. |
| `hc_stats()` | Estado de la memoria. |

---

## Arquitectura

```
texto ──▶ encoder.py ──▶ hipervector (10.000 bits)
                              │
        vsa.py  (bind / bundle / permute / hamming)
                              │
     memory.py  ── sorpresa · recuerdo+propagación · sueño · olvido
                              │
      store.py  ── SQLite (recuerdos + grafo de asociaciones)
                              │
     server.py  ── MCP (stdio) ──▶ Claude
```

---

## Dónde puedes aportar (esto es un punto de partida, no un final)

- **Sorpresa real**: sustituir el proxy de novedad por error de predicción de un
  modelo pequeño local. *(el hueco más interesante)*
- **Olvido con criterio**: hoy la importancia es un número; podría ser un juicio
  aprendido de qué merece perdurar. La literatura de 2025-26 dice que "aprender a
  olvidar" sigue **sin resolver**.
- **Codificador híbrido**: enchufar embeddings semánticos al `bundle` VSA para unir
  parecido semántico + composicionalidad simbólica.

## Créditos intelectuales

Kanerva (*Sparse Distributed Memory*), Plate (*Holographic Reduced Representations*),
la librería **torchhd**, y la línea de trabajo Titans / MIRAS / HippoRAG (2024-2026).

## Licencia

MIT.
