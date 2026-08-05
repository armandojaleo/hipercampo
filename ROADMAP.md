# Roadmap hacia producción (local-first)

**Meta: la mejor memoria local para un agente.** Cada usuario aloja hipercampo en
SU máquina, con SU fichero de memoria. No hay servidor central ni multiusuario: eso
sería coste e infraestructura innecesarios. Local-first = privado por diseño, gratis
de operar, sin datos de terceros que custodiar.

Por eso **queda fuera de alcance** (a propósito): autenticación, cifrado gestionado,
Postgres compartido, transporte de red, hosting multiusuario. Si alguien quisiera un
SaaS encima, sería otro proyecto; el núcleo se mantiene local y simple.

Estado: 🟢 hecho · 🟡 en marcha · ⚪ pendiente
## Estado actual — v0.1.0b12 (30 jul 2026)

La beta b12 está cerrada y publicada en PyPI tras CI multiplataforma verde.

- ✅ **CI multiplataforma:** suites completas en Windows, macOS y Ubuntu con Python 3.11–3.13.
- ✅ **Puertas de calidad:** Ruff, Mypy y cobertura ejecutados en CI; benchmarks bloquean regresiones.
- ✅ **MCP operativo:** dependencia compatible, smoke de release y herramientas acotables por presupuesto.
- ✅ **Memoria navegable:** índice/grafo con navegación y fallback seguro a escaneo; `nav=auto` y `max_scan` expuestos por MCP.
- ✅ **Fiabilidad Windows:** cierres SQLite, migraciones y procesos auxiliares cubiertos en CI.
- ✅ **Publicación:** `v0.1.0b12` publicada mediante Trusted Publishing y attestations.
- 🟡 **Calidad semántica:** el banco sintético marca el siguiente cuello de botella: sinónimos (global ~0.742 en modo léxico).

### Siguiente tramo

1. ✅ Recuperación explicable (`score_components`) en core/MCP y tooltip visible en la
   extensión; contrato protegido por tests.
2. ✅ Grafo navegable persistente, incremental y jerárquico, aislado por namespace.
   En 100.000 recuerdos estructurados: precisión de grupo@5=1,000, p50=6,07 ms,
   p95=6,94 ms y 1,094% visitado; índice residente 141,5 MB y reutilización 0,073 ms.
   La prueba reproducible vive en `scripts/nav_scale.py`.
   **Validado también en corpus REAL** (`scripts/nav_real.py`: docstrings de la stdlib,
   texto inglés difuso, offline): la **fidelidad navegar-vs-escaneo es 1.000** —navegar
   recupera exactamente el mismo top-5 que escanear también en texto real, no solo en el
   banco sintético—. Con 12/12 y atajos adaptados a la topología visita **42,6%** a
   ese N (~650), frente al 81,3% del antiguo 48/48; el gate exige menos del 55%.
   En grafos comunitarios o separados conserva los atajos small-world. A 10.000
   recuerdos conserva precisión@5=1,000 visitando 1,751% (p95 ~2,2 ms). La
   **precisión de grupo léxica es ~0.50** (igual navegando que escaneando):
   la navegación no degrada la calidad; ese techo es del *encoding* léxico → cuello de los sinónimos (abajo 🟡).
3. ✅ Integración multiagente: Claude y Codex comparten el MCP y el namespace del
   proyecto; instrucciones seguras en el handshake, configuración y contrato probado.
4. ✅ Continuidad de sorpresa entre procesos: estado incremental aislado por namespace,
   persistente, acotado y atómico; una observación rechazada ya no se pierde al reiniciar.
5. 🟡 El corpus real de la stdlib ya es un gate automático de fidelidad, latencia,
   memoria y coste navegable; faltan ablaciones y datasets externos estándar.
6. Selección de namespace y UX estable de la extensión; la extensión no se etiqueta como producto estable todavía.

## ¿Y el camino a "la panacea"? (triaje honesto de la crítica externa)

Revisiones externas (jul 2026) proponen cinco saltos. No todos valen lo mismo:

1. **Índice sublineal para >100k recuerdos** — SÍ, es el límite real medido
   (escaneo lineal: ~164 ms con 10k). Pero la respuesta local-first no es HNSW
   genérico: para Hamming binario basta un índice **multi-index hashing** (trocear
   el hipervector en bandas y precribar por banda exacta), que es simple, exacto
   en el re-rank y sin dependencias. ⚪ Fase 4.
2. **Sinónimos nativos sin embeddings (random indexing léxico)** — MEDIDO Y
   DESCARTADO. Se prototipó random indexing (co-ocurrencia por ventana) sobre un
   corpus REAL de 354k palabras: la señal es marginal —media coseno sinónimos 0.095
   vs azar 0.052, y solo **1 de 8** pares supera el p95 del ruido—. Aprender sinónimos
   de la co-ocurrencia necesita escala tipo word2vec (millones-miles de millones de
   palabras); una memoria personal no la tiene, y ni un corpus técnico de 350k separó.
   Conclusión honesta: **la vía de sinónimos es el hook semántico OPCIONAL** (`[semantic]`),
   no reimplementar word2vec a medias en el core. El léxico da typo/morfología gratis
   (trigramas, hit@1=1.0); el sinónimo puro es lo que resuelve un modelo semántico.
3. **Aprender los pesos de retención (RL ligero)** — A MEDIAS. Aprender de la
   utilidad real observada sí (ya se registra `access_count`); una red que decida
   qué olvidar sin explicación, no: la retención transparente y auditable es una
   característica, no una limitación. Se hará **ajuste medido**, no caja negra.
4. **Vectores de tamaño dinámico** — NO por ahora: los 5 roles medidos bastan para
   hechos atómicos, y la solución a "un contrato entero" no es un vector más
   gordo, sino trocear en hechos (que ya existe). Coste alto, beneficio dudoso.
5. **Multi-tenant cloud / cifrado homomórfico** — NO en este repo: fuera de
   alcance por diseño (ver arriba). La vía honesta es un **spin-off con
   financiación** si algún día llega — declarado en el README. El núcleo local
   y MIT no cambia.

La memoria entre proyectos (leer enlazado, escribir propio) está hecha: 🟢 abajo.

## Fase 1 — Cimientos de fiabilidad y aislamiento
- 🟢 **Memoria entre proyectos (contextos enlazados, solo lectura)**: `linked=` /
  `HIPERCAMPO_LINKED` ("proy1,proy2" o `*`). recall/muse/dream leen los proyectos
  enlazados y etiquetan el origen (`project`); toda escritura, refuerzo, olvido y
  consolidación queda en el propio. Lo no enlazado sigue invisible.
  Tests en `tests/test_linked.py`.
- 🟢 **Aislamiento por namespace/contexto**: cada contexto ve solo lo suyo, en TODAS
  las operaciones (lecturas y escrituras por id: delete/touch/mark_*), y los enlaces
  no cruzan contextos. Tests en `tests/test_namespaces.py`.
- 🟢 **Concurrencia base**: SQLite en modo WAL + `busy_timeout` (lecturas mientras
  se escribe, sin corromper).
- 🟢 **Transacciones atómicas** en operaciones compuestas (update, consolidate):
  si algo falla a mitad, se revierte (`store.transaction()`).
- 🟢 **Validación de entradas en el núcleo**: texto no vacío + longitud máxima,
  `importance`/`confidence` acotados, `k`/`hops` acotados, namespace saneado.
- 🟢 Migraciones versionadas (`PRAGMA user_version`, 7 pasos idempotentes,
  copia previa, reanudables). Tests en `tests/test_migration.py`.
- 🟢 **Purga física / borrado seguro** (no confundir con el olvido, que solo adormece):
  `hipercampo purge --ids …` / `--older-than DÍAS` para secretos, derecho de supresión
  o latentes muy antiguos. Borrado seguro (SQLite sobrescribe, no deja el texto en
  páginas libres) + `VACUUM`, con confirmación. `hc_unlearn` también borra seguro.
  Tests en `tests/test_purge.py` (verifica que el texto ya no está en los bytes del `.db`).

## Fase 1b — Calibrar la sorpresa
- 🟢 **Umbral adaptativo**: "predecible" = cuantil inferior de la sorpresa reciente
  (respaldo absoluto con poco historial). Test que demuestra que el veto ES
  alcanzable con secuencias realistas (`tests/test_calibration.py`).
- 🟢 Aprender **después** del commit (el modelo no se adelanta a la BD si hay rollback)
  y reforzar solo si es redundante (no por un match débil al vetar por predecible).
- 🟢 **Persistencia real de la sorpresa por namespace**: unigramas/bigramas y la
  ventana adaptativa de 300 observaciones sobreviven al reinicio, incluyendo lo
  visto-y-rechazado. Los tokens se persisten como hashes, no como texto literal;
  aprendizaje y memoria comparten transacción. Migración v7 y tests de continuidad,
  aislamiento, rollback y crecimiento acotado.
- 🟢 Calibrada la **abstención** midiendo la tasa de falsas recuperaciones al crecer N
  (`scripts/calibrate.py`). Hallazgo: `MIN_RECALL_SCORE` era **inerte** (moverlo no cambia
  ni MRR ni falsaRec); la palanca real, `ANSWER_MIN_SCORE`, estaba **por debajo** del
  percentil 5 de las consultas ajenas, así que no filtraba nada. Recalibrado **0.08→0.19**
  (léxico) y **0.05→0.17** (semántico): falsaRec **1.00→0.17** (léxico, estable en
  N=20/100/500) y **~0.10** (semántico), manteniendo vivo el sinónimo. `RECALL_Z` resultó
  inerte a escala. Se intentó normalizar por longitud y se **descartó tras medirlo** (a
  falsaRec igualada perdía en los dos bancos; queda documentado como límite → trocear).

## Fase 2 — Credibilidad: demostrar la calidad
- 🟢 **Baselines** (`scripts/baselines.py`): BM25 y embeddings+coseno vs hipercampo.
  Resultado medido: hipercampo+semántico gana en MRR global (0.95 vs 0.87 de
  embeddings); en léxico ya supera a BM25 (erratas 0.95 vs 0.77). La abstención
  (falsaRec) estaba en 1.00 por un umbral mal puesto; **calibrada a 0.17-0.20**, a la
  par de embeddings (ver Fase 1b y `scripts/calibrate.py`).
- 🟡 **Ablación**: sin propagación (medida: no cambia en este corpus). Faltan
  sin-sorpresa / sin-consolidación / sin-confianza aisladas.
- ⚪ Sobre datasets **estándar** (LongMemEval, MemoryAgentBench), no solo el propio.
- ⚪ Métricas extra: precisión de abstención calibrada, tokens metidos en contexto,
  latencia p50/p95.

## Fase 3 — Rendimiento a escala
- 🟢 **Escaneo vectorizado**: XOR de toda la matriz + popcount nativo (NumPy 2.0) con
  tabla de respaldo. ~5× más rápido (10k: 224→47 ms). recall() 2k ~40ms, 10k ~164ms.
- 🟢 **Índice navegable jerárquico a 100k**: landmarks por isla semántica + selección
  VSA vectorizada + beam local. En el banco estructurado reproducible (30 consultas),
  precisión de grupo@5 **1,000**, p50 **6,07 ms**, p95 **6,94 ms**, **1,094%** visitado.
  La matriz VSA posicional, la carga streaming y la adyacencia CSR bajan la construcción de
  14,6→**7,46 s**, el pico de 558,8→**189,7 MB** y dejan **141,5 MB residentes**;
  reutilización 0,073 ms. La validación externa sigue abierta.

## Fase 4 — Aislamiento local de contextos (NO servidor multiusuario)
Fuera de alcance auth/cifrado/Postgres/red: cada usuario es local. Lo útil aquí es
separar contextos *dentro de una misma máquina*:
- 🟢 **Namespaces integrales**: aislar proyectos/perfiles en una misma BD, en todas
  las operaciones y en los enlaces. Ya implementado y probado.
- ⚪ Selección de namespace cómoda (por proyecto) desde el cliente.
- ⚪ Endurecer contra inyección vía memoria a nivel de cliente (ver [SECURITY.md](SECURITY.md)).

## Fase 5 — La ventaja diferencial (VSA de verdad)
- 🟢 **Memoria composicional con roles** (`hipercampo/roles.py`): `SUJETO⊗ ·
  PREDICADO⊗ · OBJETO⊗ · TIEMPO⊗ · FUENTE⊗`, con recuperación por *unbinding*
  ("¿quién mordió a quién?"). Medido: recupera el valor correcto por rol con margen
  claro (0.74 vs 0.54) y capacidad hasta 5 roles; distingue el hecho de su inverso.
  Tests en `tests/test_roles.py`, demo en `scripts/roles_demo.py`.
- 🟢 **Role-records integrados en el ciclo** (`RoleMemory` en `roles.py`): `remember_fact`/
  `ask_role` en el core y por MCP (`hc_remember_fact`/`hc_ask_role`), persistidos en la
  tabla `facts` y **aislados por namespace**. La item memory (cleanup) se **reconstruye
  al abrir** desde los hechos guardados, así que persiste sin estado extra. Cada hecho
  guarda su **sombra textual** (entra en recall/muse/consolidación/olvido) y lleva
  **validez temporal**: un hecho nuevo con mismo sujeto+predicado y otro objeto CIERRA
  al anterior (no lo borra) — historia, no sobrescritura. Tests en `test_roles.py`.
- ✅ **Hechos visibles.** `hipercampo facts [--json]` y la pestaña **Facts** del visor
  permiten consultar los role-records y su historia temporal sin salir de la UI.
- ⚪ Consolidación con **resumen real** (summarizer LLM — el gancho ya existe),
  detección de conflictos, procedencia y validez temporal (`valid_from`/`valid_to`).
- ⚪ Relaciones tipadas y dirigidas (`supports`, `contradicts`, `updates`, `caused_by`).

## Fase 6 — Release y operación
- 🟢 CI (GitHub Actions) con las suites + benchmarks en 3.11–3.13.
- ✅ Linting + type-check (ruff/mypy) + cobertura en CI; compilación y smoke sintáctico
  del webview añadidos como puerta independiente.
- ✅ Recuperación **explicable**: `score_components` (similitud directa, boost por
  asociación, factor de confianza, penalización por superado).
- 🟢 Release v0.1.0-alpha publicada en **PyPI** (trusted publishing + attestations).
- ⚪ Observabilidad: logging estructurado, métricas.

## Fase 7 — Madurez de ingeniería y camino a embebido
El núcleo funciona; ahora toca que sea **serio para producción** y apto para
sistemas embebidos y robots (SBC con Linux: Raspberry Pi, Jetson, ROS2). No es
investigación: es fiabilidad, estructura y disciplina de release. Se lanza en
**betas pequeñas, cada una con una promesa medible**, para que el camino se vea.

- 🟢 **`0.1.0b2` — El core se despega (la abstracción).** `mcp` solo se importa en
  `server.py` (y perezosamente en el subcomando `serve`): `import hipercampo` no
  arrastra `mcp` (medido en intérprete limpio). **Garantizado** por el test-guardia
  `tests/test_core_embebible.py` (falla el CI si un módulo del núcleo importa
  `mcp`/`.server`), y la **API pública del core** documentada en `__init__.py`.
- 🟢 **`0.1.0b3` — Red de seguridad de CI.** Ruff (ya estaba) + **mypy** + cobertura
  como **puertas**. Config de mypy en `pyproject.toml` (no `--strict`: caza Nones sin
  comprobar y asignaciones incompatibles sin ahogar el numpy/dicts JSON). Suelo de
  cobertura en 78% (total real 79%; no se sube el suelo para no dejarlo frágil). Y se
  arregló un hueco: la matriz enumeraba los tests **a mano** y se dejaba fuera de
  Windows/macOS cuatro ficheros (`list`, `budget`, `purge`, `core_embebible`) —justo
  donde viven los bugs de plataforma—; ahora corre por **glob**. Falta: smoke del webview.
- 🟢 **`0.1.0b4` — Idioma + mejoras del visor (extensión v0.6.0).** i18n del visor por
  el idioma de VS Code (en/es): diccionario en el webview, `package.nls` para el
  manifiesto, y el idioma inyectado desde `vscode.env.language`. Promesa cumplida: *el
  visor arranca en inglés en un VS Code en inglés.* De paso, mejoras pedidas por el
  dueño: pestaña **Ideas** (los puentes que propone el sueño —hipótesis— vía nuevo
  `hipercampo dream --json`, dry-run: no contamina); en **Estado**, botón para abrir el
  registro, identidad de cada **servidor MCP** (qué fichero de memoria sirve) y botón de
  **backup**; y botón de **nueva issue** a GitHub. Falta: revisar los mensajes es/en
  mezclados del *core* (el visor ya está).
- 🟢 **`0.1.0b5` — Fiabilidad bajo estrés.** Lo que un robot exige: recall con **cota
  de tiempo/RAM** (`max_scan=N`: mira solo los N recuerdos más vivos —fuerza y
  recencia—; el registro dice cuántos miró y si acotó, sin caps silenciosos). Se midió
  primero y la cota INGENUA salía **más lenta** (el `ORDER BY` sin índice costaba más
  que escanear todo); se añadió el índice `idx_vivos` y entonces sí: a **10k recuerdos,
  cota p50 ~35 ms vs ~200 ms completo (5–6×) y PLANA con N**. La BD corrupta/bloqueada/
  llena ya estaba cubierta (`test_resilience`/`test_failures`). Tests en `test_bounded.py`;
  latencia p50/p95/p99 publicada en CI (`scripts/latency.py`) — cierra hueco de Fase 2.
  Cerrado en b6: `max_scan` también está expuesto por MCP (`hc_recall`) para que agentes/robots puedan acotar CPU/RAM sin depender de la API Python.
- 🟢 **`0.1.0b6` — El núcleo recuerda como un cerebro: grafo navegable (BANDERA).**
  El límite real medido no era la velocidad del escaneo, sino *escanear*. A 100k:
  ~1,8 s y 542 MB — inviable para un robot. La idea (de Armando): no escanear, sino
  **navegar un grafo de vecinos**, como un GPS; se recuerda por conexiones, no mirándolo
  todo. Medido en sondas antes de construir:
  - un grafo solo de vecinos NO es navegable (se rompe en islas, recall 0,12); los
    **atajos débiles de largo alcance** lo vuelven navegable (recall **0,97-1,0**) —
    small-world de Watts-Strogatz. Y esos atajos son los mismos que dan ideas (los
    puentes del `dream`): **creatividad e índice son lo mismo**.
  - **sublineal de verdad**: el % de memoria visitado ENCOGE con N (13,9%→**3,0%** de 2k
    a 16k; ~log N). Extrapolado, 1M de recuerdos ≈ ~1000 nodos visitados (~0,1%).
  - **insertar tampoco escanea**: se navega el grafo para colocar cada recuerdo
    (~293 visitas, constante), estilo HNSW. recall del grafo así construido: 1,0.
  Ya está integrado: `remember` mantiene vecinos KNN sin reindexado global y `recall`
  navega con beam, expone `visited`/`recall_mode` y conserva el escaneo como fallback.
  El grafo sobrevive al reinicio y no cruza namespaces; lo prueban `test_navgraph.py` y
  `test_navindex.py`. La UI hace visible el modo y coste de cada recall. La búsqueda ya
  devuelve resultados+visitas en una sola pasada y el índice queda residente e invalidado
  ante cambios locales/externos. El salto de escala añade una capa jerárquica: detecta
  islas semánticas, compara sus landmarks con popcount VSA vectorizado y navega localmente
  desde las cuatro más cercanas. En 100.000 recuerdos estructurados (30 consultas):
  precisión de grupo@5 **1,000** (antes **0,400** con una entrada), p50 **6,07 ms**,
  p95 **6,94 ms** y **1,094%** visitado. Después, una matriz VSA única sin 100.000 vistas y la carga streaming evitan
  materializar recuerdos/enlaces completos, y CSR compacta las calles del GPS: construcción
  fría **14,6→7,46 s**, pico **558,8→189,7 MB**, residente **141,5 MB** y reutilización
  0,073 ms. El coste frente a la versión CSR previa es +0,83 s de arranque por -15,7 MB
  residentes. `scripts/nav_scale.py` lo reproduce. Siguiente reto: carga binaria por lotes y
  validar recall@5 ≥0,9 en corpus externo, sin esconder el fallback.
- ⚪ **`0.2.0b1` — Extensión seria.** Marketplace (publisher + `VSCE_PAT`), settings,
  i18n dentro, y UX que salga de usarlo de verdad.
- ⚪ **Benchmark en SBC real** (Liga A): latencia/RAM/consumo con 1k/10k/100k recuerdos
  en una Pi/Jetson. Sin ese número, "sirve para robots" es humo. Sirve de puerta a `1.0`.

**Fuera de alcance aquí** (sigue siendo otro proyecto): un core en C/Rust para
microcontroladores sin Linux (Liga B). El álgebra VSA es popcount+XOR y cabría en
pocos KB, pero es un spin-off; se anota, no se mete en este repo.

## Ideas (backlog vivo)

Aquí se quedan las ideas y se van **actualizando** — no es una promesa, es un depósito
que evoluciona. Cuando una madura, sube a una fase con su medición.

- ✅ **Vista de hechos en el visor.** `hipercampo facts [--json]` y la pestaña **Facts**
  de la extensión ya permiten explorar y consultar los hechos estructurados (el
  diferenciador VSA, "¿quién muerde a quién?") de forma visual.
- **Cadena de suministro (necesitan red):** fijar `vsce` a versión exacta en `vsix.yml`
  (protege el `VSCE_PAT`) y las GitHub Actions al SHA. Detalle en [SECURITY.md](SECURITY.md).
- **Decisión abierta: `mcp` opcional** (`[mcp]`) → core de 1 dependencia (numpy). Reduce
  superficie de ataque; coste: cambia el comando de instalación del servidor.
- **Sinónimos:** medido que el random indexing no rinde a esta escala; la vía es el hook
  semántico opcional. Idea a revisitar solo si aparece un recurso léxico compacto y libre.
- **Consolidación con resumen real** (summarizer), relaciones tipadas
  (`supports`/`contradicts`/`updates`), datasets externos estándar (LongMemEval…).

### Dirección de largo plazo (backlog técnico)

Ideas de más calado, filtradas con la regla de la casa (local-first, CPU, medir antes
de creer). Cada una entra en una fase solo con su medición delante:

1. **Atomización** — 🟢 HECHO. Ataca el límite nº1 (dilución 1/√T en textos largos):
   `remember()` trocea el texto en átomos (`hipercampo/atomize.py`, sin dependencias) y
   guarda cada uno enlazado a su fuente (`type='atom'`). Medido (`scripts/atom_probe.py`):
   un hecho enterrado en un texto de 64 ideas pasa de **acierto@1 0.15 (monolítico) a 1.00
   (atomizado)**; end-to-end, una pista corta recupera el átomo exacto. Desactivable con
   `HIPERCAMPO_NO_ATOMIZE=1`. Tests en `test_atomize.py` y `test_atomize_remember.py`.
   **Encoding MULTICANAL — MEDIDO y NO justificado (para recuperación de texto).** Se
   prototipó (contenido + lugar + tiempo por canal vs bundle único, con consultas por
   aspecto): **empate a Recall@1 1.000**, incluso con contenido "confuso" que menciona
   otros lugares. La dilución baja la similitud absoluta pero NO el ranking, y los
   **bigramas** del encoder ya distinguen "almacen norte" (campo) de un "norte" suelto.
   Un HV por canal sería un rediseño grande para cero ganancia medida en texto. Podría
   tener sentido en multimodal (sensores/robots), pero eso es el spin-off, no el core.
2. **Benchmarks externos multilingües** (LongMemEval, LoCoMo, MuSiQue, BEIR) — convertir
   los claims en evidencia fuera del banco propio. Cierra el hueco "datasets estándar".
3. **Meta-memoria: admisión por UTILIDAD+sorpresa** (no solo sorpresa, que no equivale a
   utilidad y ni persiste hoy): features explícitas + regresión online / bandit
   contextual **conservador y auditable** (nunca caja negra; los límites duros —secretos,
   protegidos— siguen siendo política, no aprendizaje).
4. **Abstención CALIBRADA** (conformal/isotónica sobre un conjunto de calibración
   independiente): garantía de riesgo selectivo, no umbrales a ojo.
5. **Consolidación con procedencia + contradicciones por afirmación** (no dar por cierto
   un resumen de LLM) y **microclustering incremental** para quitar el O(N²).
6. **Dimensionalidad configurable por perfil** (menos bits = menos RAM en edge) + MIH como
   índice alternativo al grafo para el perfil micro.
7. **Refactor a interfaces `Protocol`** (Encoder/Index/Store/AdmissionPolicy/…) para
   experimentar sin romper; kernels en Rust vía PyO3 **solo tras perfilar**.

La visión que orienta esto: no "otra vector-DB", sino **memoria temporal, explicable y
frugal que sigue funcionando sin cloud**. Un SaaS multi-tenant o robótica a escala serían
un **spin-off con financiación** (otro proyecto); el núcleo se queda **MIT y local-first**.

---

**Regla de la casa**: cada fase se cierra con *medición*, no con opinión. Nada de
afirmaciones fuertes sin un test o un benchmark que las respalde. Ver
[ATTRIBUTION.md](ATTRIBUTION.md) y [SECURITY.md](SECURITY.md).
