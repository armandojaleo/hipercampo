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
| **Escritura por sorpresa** | Doble veto: no guarda lo **redundante** (ya hay algo parecido) ni lo **predecible** (un modelo de lenguaje incremental interno ya lo predecía, medido en *bits* — compresión/MDL). Ahí está el ahorro de tokens. | Error de predicción hipocampal; compresión-como-inteligencia (Hutter) |
| **Consolidación ("sueño")** | Un proceso offline agrupa episodios parecidos, los funde en conocimiento semántico condensado y archiva los originales. | Replay hipocampo→córtex |
| **Olvido activo** | La fuerza de un recuerdo decae con el desuso; lo débil y poco importante se poda. La importancia alta protege. | Olvido adaptativo |

> **Honestidad de ingeniería.** La sorpresa combina dos señales: *novedad léxica*
> (`1 − máxima similitud con lo ya guardado`) y *error de predicción* real, estimado
> por un modelo de lenguaje incremental propio en bits/token (compresión/MDL, sin
> red neuronal ni GPU). El codificador base es **léxico**; para sinónimos hay un
> hook semántico opcional (más abajo). Todo es sustituible sin tocar el resto.

---

## Instalación (guía completa: [INSTALL.md](INSTALL.md))

**Vía rápida — Python local + Claude Code:**

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
pip install -e .                                  # instala hipercampo + deps
python scripts/demo.py                            # (opcional) ver el ciclo funcionando
claude mcp add hipercampo -- python -m hipercampo.server   # conectar a Claude Code
```

Reinicia Claude Code y tendrás 5 herramientas nuevas (`hc_remember`, `hc_recall`,
`hc_consolidate`, `hc_forget`, `hc_stats`). Para Docker, Claude Desktop, `.mcp.json`,
verificación y problemas frecuentes → **[INSTALL.md](INSTALL.md)**.

---

## Prueba en 30 segundos (sin Claude)

```bash
pip install numpy
python scripts/demo.py
```

Verás el álgebra distinguiendo el orden de las palabras y el ciclo completo
(sorpresa → recuerdo → sueño → olvido) funcionando.

---

## Batería de pruebas — que hace lo que dice

Tres niveles, todos sin dependencias extra (solo `numpy`):

```bash
python tests/test_vsa.py         # álgebra VSA (bind/bundle/orden)
python tests/test_memory.py      # el CICLO: sorpresa, recall, sueño, olvido, persistencia
python tests/test_properties.py  # invariantes con datos FABRICADOS al azar (8 rondas)
python scripts/scenarios.py      # historia narrada: Claude recordando a un usuario
```

- **test_memory.py** — 10 casos realistas, uno por promesa (no duplica lo conocido,
  prioriza lo relevante, la propagación trae asociados, el sueño condensa, la
  importancia protege del olvido, la memoria sobrevive a un reinicio…).
- **test_properties.py** — pruebas *generativas espontáneas*: cada invariante se
  comprueba con 8 juegos de datos distintos inventados en el momento. Si alguna
  promesa se rompe con **algún** dato, el test enseña el contraejemplo. Ejemplos:
  *un duplicado nunca crea un segundo recuerdo*, *una aguja se recupera entre 25
  distractores*, *el olvido nunca borra algo con importancia ≥ 0.8*, *consolidar
  nunca aumenta los episódicos*.

## Calidad de recuperación (medida, no prometida)

`python scripts/benchmark.py` mide MRR / hit@1 sobre preguntas con respuesta
conocida entre distractores. Resultados reales del codificador VSA puro (CPU):

| Escenario | hit@1 | MRR | Lectura |
|-----------|-------|-----|---------|
| **Fácil** — comparten palabras clave | 1.00 | **1.000** | recuperación perfecta |
| **Erratas** — palabras clave mal escritas | 1.00 | **1.000** | los trigramas de char lo salvan (sin ellos: 0.67) |
| **Difícil** — sinónimos puros, sin palabras comunes | 0.25 | **0.300** | límite del léxico: aquí entra el hook semántico |

Conclusión honesta: el ranking léxico es **excelente** cuando hay solape de
palabras (incluso con erratas) y **flojo** ante sinónimos.

### Hook semántico opcional (medido)

Para los sinónimos existe un **hook semántico opcional**: un embedding denso se
proyecta a hipervector vía SimHash y se liga con peso al resto (SEMANTIC_WEIGHT).

```bash
pip install "hipercampo[semantic]"          # trae sentence-transformers (Apache-2.0)
python scripts/benchmark.py --semantic       # descarga el modelo la 1ª vez
```

| Escenario | Solo léxico (por defecto) | + Semántico (peso 0.2) |
|-----------|:---:|:---:|
| Fácil (palabras compartidas) | **1.00** | 1.00 |
| Erratas | **1.00** | 0.79 |
| Sinónimos puros | 0.30 | **0.79** |

Activar semántica **casi triplica** los sinónimos (0.30 → 0.79) a cambio de algo de
robustez a erratas (1.00 → 0.79). El peso 0.2 es el mejor equilibrio medido; súbelo
para priorizar sinónimos. Por defecto el hook está **apagado** → cero GPU, cero
dependencias de terceros. En código:

```python
from hipercampo import encoder, semantic
encoder.set_semantic_hook(semantic.make_sentence_transformer_hook())
# o con tu propio modelo:  encoder.set_semantic_hook(semantic.make_hook(mi_embed_fn))
```

Ver [ATTRIBUTION.md](ATTRIBUTION.md) para licencias del modelo.

### Banco de estrés (10 hechos + 10 distractores del mismo tema)

`python scripts/stress.py [--semantic]` — condiciones duras: distractores que
comparten vocabulario con la respuesta correcta. MRR por categoría:

| Categoría | Léxico | + Semántico (peso 0.15) |
|-----------|:---:|:---:|
| keyword (palabras compartidas) | 1.00 | 1.00 |
| typo (palabras mal escritas) | 1.00 | 0.95 |
| synonym (paráfrasis) | 0.32 | **0.90** |
| **GLOBAL** | 0.77 | **0.95** |

Activar semántica sube el MRR global de **0.77 → 0.95**. Hallazgo medido: **poco
peso semántico (0.15) gana** — demasiado ahoga la pista léxica que distingue hechos
del mismo dominio. El modo semántico se activa con `HIPERCAMPO_SEMANTIC=1` en el
entorno del servidor (requiere el extra `[semantic]`).

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

- **Sorpresa aún mejor**: el error de predicción ya es real (modelo n-grama interno,
  `hipercampo/surprise.py`). Un siguiente paso sería un modelo local más potente o
  usar la propia perplejidad del LLM cliente como señal de sorpresa.
- **Olvido con criterio**: hoy la importancia es un número; podría ser un juicio
  aprendido de qué merece perdurar. La literatura de 2025-26 dice que "aprender a
  olvidar" sigue **sin resolver**.
- **Codificador híbrido**: enchufar embeddings semánticos al `bundle` VSA para unir
  parecido semántico + composicionalidad simbólica.

## Créditos intelectuales

Kanerva (*Sparse Distributed Memory*), Plate (*Holographic Reduced Representations*),
la librería **torchhd**, y la línea de trabajo Titans / MIRAS / HippoRAG (2024-2026).

## Licencia y atribución

MIT (ver [LICENSE](LICENSE)). Todo el código es original; las dependencias y las
ideas académicas en que nos inspiramos están acreditadas en
[ATTRIBUTION.md](ATTRIBUTION.md). Regla de la casa: **si usamos trabajo de otros,
sobre todo con copyright, se dice.**
