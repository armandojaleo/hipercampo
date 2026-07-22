# 🧠 hipercampo

[![CI](https://github.com/armandojaleo/hipercampo/actions/workflows/ci.yml/badge.svg)](https://github.com/armandojaleo/hipercampo/actions/workflows/ci.yml)

🌍 **English: [README.md](README.md)** · Estás leyendo la versión en español.

**Una memoria viva para Claude, basada en hipervectores — no en embeddings.**

La mayoría de las memorias para LLMs son lo mismo: trocear texto, convertirlo en
vectores densos y buscar los más parecidos (ANN / top-k). Eso mide *parecido*,
pero no *relevancia*, no *importancia*, y nunca *olvida*. Es un vertedero con buscador.

`hipercampo` prueba otra cosa. Es un servidor **MCP** que le da a Claude una memoria
que imita al hipocampo, con cuatro ideas integradas en un ciclo:

| Idea | Qué hace | Inspiración |
|------|----------|-------------|
| **VSA / hipervectores** | Recuerdos como vectores binarios de 10.000 bits con álgebra real (`bind`/`bundle`). Distingue *"el perro muerde al hombre"* de su inverso — cosa que un embedding denso difumina. Corre en CPU con popcount, sin GPU. | Kanerva (SDM), Plate (HRR) |
| **Escritura por sorpresa** | Doble veto: no guarda lo **redundante** (ya hay algo parecido) ni lo **predecible** (un modelo de lenguaje incremental interno ya lo predecía, medido en *bits* — compresión/MDL). Ahí *apunta* el ahorro de tokens (aún no medido de extremo a extremo). | Error de predicción hipocampal; compresión-como-inteligencia (Hutter) |
| **Consolidación ("sueño")** | Un proceso offline **agrupa** episodios parecidos en un recuerdo semántico (agrupación estructural: reduce nodos, el texto se une; con un `summarizer` opcional se resume de verdad) y archiva los originales. | Replay hipocampo→córtex |
| **Olvido activo** | La fuerza decae con el desuso; lo débil queda **latente** (no borrado, como la mente humana) y puede **resurgir** con `hc_muse`. La importancia alta protege. | Olvido adaptativo |

> **Honestidad de ingeniería.** La sorpresa combina dos señales: *novedad léxica*
> (`1 − máxima similitud con lo ya guardado`) y *error de predicción* real, estimado
> por un modelo de lenguaje incremental propio en bits/token (compresión/MDL, sin
> red neuronal ni GPU). El codificador base es **léxico**; para sinónimos hay un
> hook semántico opcional (más abajo). Todo es sustituible sin tocar el resto.

---

## Instalación (guía completa: [INSTALL.md](INSTALL.md))

**Vía rápida — desde PyPI:**

```bash
pip install hipercampo                # o: pip install "hipercampo[semantic]"
claude mcp add --scope user hipercampo -- python -m hipercampo.server
```

**Desde el código (colaboradores):**

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo && pip install -e .
python scripts/demo.py                # ver el ciclo funcionando
```

Reinicia Claude Code y tendrás 12 herramientas de memoria (`hc_remember`, `hc_recall`,
`hc_muse`, `hc_dream`, `hc_accept_bridge`, `hc_reject_bridge`, `hc_update`, `hc_remember_fact`, `hc_ask_role`,
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

**Casos de uso reales** en [`examples/`](examples/): un asistente personal que
recuerda entre sesiones, una base de conocimiento con consultas por rol, y
brainstorming creativo donde los recuerdos olvidados resurgen.

---

## Batería de pruebas — que hace lo que dice

```bash
python tests/test_vsa.py          # álgebra VSA (bind/bundle/orden)
python tests/test_memory.py       # el CICLO: sorpresa, recall, sueño, olvido, persistencia
python tests/test_namespaces.py   # aislamiento de contextos, concurrencia, transacciones
python tests/test_calibration.py  # sorpresa adaptativa, rollback, consulta vacía, cohesión
python tests/test_properties.py   # invariantes con datos fabricados (8 rondas)
python scripts/scenarios.py       # historia narrada: Claude recordando a un usuario
```

18 suites en total, todas verdes en CI (Python 3.11–3.13). Ejemplos de invariantes
comprobadas: *un duplicado nunca crea un segundo recuerdo*, *una aguja se recupera
entre 25 distractores*, *el olvido nunca borra algo con importancia ≥ 0.8*, *un
contexto no ve ni puede modificar lo de otro*, *una transacción fallida no deja rastro*.

## Comparativa con baselines (Fase 2)

`python scripts/baselines.py [--semantic]` enfrenta hipercampo a los métodos
estándar sobre el mismo corpus (10 hechos + 10 distractores confusos). MRR por
categoría + tasa de **falsa recuperación** (consultas ajenas que devuelven algo):

| método | keyword | typo | synonym | global | falsaRec |
|--------|:---:|:---:|:---:|:---:|:---:|
| BM25 (léxico exacto) | 1.00 | 0.77 | 0.33 | 0.70 | 1.00 |
| embeddings + coseno | 0.95 | 0.88 | 0.79 | 0.87 | **0.20** |
| hipercampo (léxico) | 1.00 | 0.95 | 0.37 | 0.77 | 1.00 |
| **hipercampo + semántico** | 1.00 | 0.95 | **0.90** | **0.95** | 1.00 |

Lectura honesta:
- **En ranking (MRR), hipercampo+semántico gana** (0.95): junta precisión léxica
  (keyword/typo) con alcance semántico (sinónimos). En léxico puro ya supera a BM25,
  sobre todo en **erratas** (0.95 vs 0.77) gracias a los trigramas de carácter.
- **En abstención, pierde**: embeddings rechaza negativas con su umbral de coseno
  (falsaRec 0.20); hipercampo aún no (1.00). Hay que calibrar `MIN_RECALL_SCORE`.
- Corpus **pequeño y sintético**: es una señal, no una prueba a escala. Ver [ROADMAP.md](ROADMAP.md).

## Escala y latencia (medido)

| Recuerdos | `recall()` completo (CPU) | ¿Encuentra la aguja? |
|-----------|:---:|:---:|
| 2.000 | ~40 ms | sí, posición #1 |
| 10.000 | ~164 ms | sí, posición #1 |

Escaneo **vectorizado** (XOR de toda la matriz + popcount nativo de NumPy 2.0):
~5× más rápido que fila-a-fila. Lineal (sin índice ANN): sobrado para memoria
personal (cientos a miles); a ~100k haría falta un índice. Límite conocido, no oculto.

## Herramientas que gana Claude

| Herramienta | Para qué |
|-------------|----------|
| `hc_remember(text, importance, confidence)` | Guarda algo (si es novedoso/sorprendente). `importance` = cuánto importa (≥0.8 protege del olvido); `confidence` = cuán fiable (pesa en el ranking). |
| `hc_recall(query, k, include_history)` | Recupera por similitud + propagación. Puede **abstenerse** (devolver `[]`). |
| `hc_muse(query, k)` | **Recuerdo inspirador**: trae conexiones *indirectas* y recuerdos **latentes** que pueden resurgir y atar ideas. Para intuición/brainstorming. |
| `hc_dream(max_bridges, dry_run)` | **Sueño creativo**: propone *puentes* entre recuerdos con un asociado común. Las hipótesis **no contaminan la memoria**: no propagan hasta confirmarse. |
| `hc_accept_bridge / hc_reject_bridge` | Confirma una hipótesis del sueño (pasa a ser asociación real) o la descarta. |
| `hc_update(target, new_text, memory_id)` | **Actualiza un hecho que cambió** (supersesión segura; el viejo queda como historia). |
| `hc_consolidate()` | Fase de sueño: agrupa episodios en conocimiento semántico. |
| `hc_forget(dry_run)` | Olvido activo. `dry_run=True` ensaya sin borrar. |
| `hc_remember_fact(subject, predicate, object, …)` | Guarda un **hecho estructurado** (VSA composicional). |
| `hc_ask_role(role, …campos conocidos…)` | Pregunta un campo sabiendo otros: *"¿quién muerde al hombre?"* → unbinding. |
| `hc_stats()` | Estado de la memoria (incluye la ruta de la BD). |

Guardrails (entorno): `HIPERCAMPO_MAX_MEMORIES` acota los recuerdos por contexto
(poda el de menor retención, nunca lo protegido); `HIPERCAMPO_REDACT_SECRETS=1`
enmascara los secretos detectados antes de guardarlos en vez de solo avisar.

## Los cuatro ejes de un recuerdo (novedad ≠ importancia ≠ fiabilidad ≠ utilidad)

| Eje | Qué mide | Quién lo pone | Para qué se usa |
|-----|----------|--------------|-----------------|
| **novedad / sorpresa** | ¿nuevo o predecible? (MDL) | derivado | decidir si **escribir** |
| **importancia** | ¿cuánto importa? | quien lo dice (`importance`) | **proteger** del olvido |
| **fiabilidad** | ¿cuán cierto? | quien lo dice (`confidence`) | **ranking** en la recuperación |
| **utilidad** | ¿cuánto se usa? | derivado (`access_count`) | **proteger** del olvido por uso |

El olvido combina los tres últimos en una *retención* transparente
(`0.4·importancia + 0.3·fiabilidad + 0.3·utilidad`): el tiempo marca candidatos,
pero el **valor** decide.

## Memoria composicional con roles (el diferenciador)

Lo que los embeddings **no** pueden: preguntar *quién hizo qué a quién* y acertar
por rol. Un hecho se codifica ligando cada valor a su ROL y agrupando; luego se
recupera cualquier campo por *unbinding* (`hipercampo/roles.py`):

```python
from hipercampo.roles import ItemMemory, encode_fact, query_role
im = ItemMemory()
hecho = encode_fact({"subject": "perro", "predicate": "muerde", "object": "hombre"}, im)
query_role(hecho, "subject", im)   # -> [("perro", 0.74)]
query_role(hecho, "object",  im)   # -> [("hombre", 0.76)]
```

`python scripts/roles_demo.py` enseña la clave: *"perro muerde hombre"* y *"hombre
muerde perro"* tienen los **mismos valores** pero el sujeto/objeto recuperados están
**invertidos** — un embedding denso los pone casi en el mismo punto; VSA los mantiene
distintos. Medido: recupera el valor correcto por rol con margen claro (0.74 vs 0.54)
y capacidad hasta 5 roles. Integrarlo en el ciclo MCP vivo es el siguiente paso
(ver [ROADMAP.md](ROADMAP.md)).

## Contextos, Docker, seguridad

- **Contextos**: namespaces (`HIPERCAMPO_NAMESPACE`) para aislar proyectos/perfiles
  en una misma BD, o ficheros distintos (`HIPERCAMPO_DB`). Aislamiento **local**, no
  seguridad multiusuario — hipercampo es local-first. Ver [SECURITY.md](SECURITY.md).
- **Docker**: `docker compose build && docker compose run --rm hipercampo`.
- **Seguridad**: el texto recuperado es **dato, no instrucciones**. Salvaguardas
  integradas (`hipercampo/safety.py`): `hc_remember` avisa de posibles **secretos**
  (BD en claro), `hc_recall` marca como `untrusted` los recuerdos con pinta de
  **instrucciones inyectadas**. Avisan, no bloquean. Detalles en [SECURITY.md](SECURITY.md).

## Arquitectura

```
texto ──▶ encoder.py ──▶ hipervector (10.000 bits)
                              │
        vsa.py  (bind / bundle / permute / popcount vectorizado)
                              │
     memory.py  ── sorpresa · recuerdo+propagación · sueño · olvido · 4 ejes
                              │
      store.py  ── SQLite WAL (recuerdos + grafo, aislado por namespace, transaccional)
                              │
     server.py  ── MCP (stdio) ──▶ Claude
```

## Trabajo relacionado y posicionamiento honesto

hipercampo **no inventa** la computación hiperdimensional (HDC/VSA existe desde los
90: Kanerva, Plate), ni es el primer intento de memoria para agentes (Mem0, Letta,
Graphiti, MemGPT; MnemoCore usa HDC). Lo original es **la combinación concreta**:
VSA + sorpresa (MDL) + consolidación + olvido + cuatro ejes, como servidor **MCP**,
tratando la memoria como un **ciclo**. No afirmamos superar a las memorias híbridas;
exploramos un paradigma distinto, con sus límites medidos.

## Licencia y atribución

MIT (ver [LICENSE](LICENSE)). Código original; dependencias e ideas acreditadas en
[ATTRIBUTION.md](ATTRIBUTION.md). Regla de la casa: **si usamos trabajo de otros,
sobre todo con copyright, se dice.**

## Agradecimientos

Construido por **Armando Jaleo** con **Claude** (Anthropic), midiendo antes de creer
y diciendo la verdad de los límites. Gracias a Pentti Kanerva y Tony Plate, cuyas
ideas de hace décadas siguen vivas aquí. Y a quien audita con rigor: la crítica
honesta hizo mejor a este proyecto en cada vuelta.

*Y sí — ¡felicidades a España! 🇪🇸⚽ Algunos recuerdos merecen `confidence=1.0`.*

> Una memoria no es un almacén: es un ciclo que guarda, relaciona, consolida y olvida.
> Si algún día esto ayuda a que las máquinas recuerden **con criterio** —y a que
> quien las usa pueda auditarlo—, habrá valido la pena. — hecho con cuidado. 🧠
