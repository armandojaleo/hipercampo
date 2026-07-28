# Roadmap hacia producción (local-first)

**Meta: la mejor memoria local para un agente.** Cada usuario aloja hipercampo en
SU máquina, con SU fichero de memoria. No hay servidor central ni multiusuario: eso
sería coste e infraestructura innecesarios. Local-first = privado por diseño, gratis
de operar, sin datos de terceros que custodiar.

Por eso **queda fuera de alcance** (a propósito): autenticación, cifrado gestionado,
Postgres compartido, transporte de red, hosting multiusuario. Si alguien quisiera un
SaaS encima, sería otro proyecto; el núcleo se mantiene local y simple.

Estado: 🟢 hecho · 🟡 en marcha · ⚪ pendiente

## ¿Y el camino a "la panacea"? (triaje honesto de la crítica externa)

Revisiones externas (jul 2026) proponen cinco saltos. No todos valen lo mismo:

1. **Índice sublineal para >100k recuerdos** — SÍ, es el límite real medido
   (escaneo lineal: ~164 ms con 10k). Pero la respuesta local-first no es HNSW
   genérico: para Hamming binario basta un índice **multi-index hashing** (trocear
   el hipervector en bandas y precribar por banda exacta), que es simple, exacto
   en el re-rank y sin dependencias. ⚪ Fase 4.
2. **Sinónimos nativos sin embeddings (random indexing léxico)** — SÍ, y es la
   mejora más alineada con la filosofía del proyecto: co-ocurrencia acumulada en
   los propios hipervectores, aprendida del corpus del usuario. ⚪ Explorar.
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
- 🟢 Migraciones versionadas (`PRAGMA user_version`, 6 pasos idempotentes,
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
- ⚪ **Persistencia real** de los contadores unigrama/bigrama por namespace (hoy se
  reconstruye solo desde lo guardado; lo visto-y-rechazado no persiste al reiniciar).
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
- ⚪ Índice LSH sobre los binarios para sublineal a 100k+; carga perezosa de la matriz.

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
- ⚪ Integrar los role-records en el ciclo de memoria (guardar/consultar hechos
  estructurados vía MCP: `hc_remember_fact` / `hc_ask_role`) y persistir la item memory.
- ⚪ Consolidación con **resumen real** (summarizer LLM — el gancho ya existe),
  detección de conflictos, procedencia y validez temporal (`valid_from`/`valid_to`).
- ⚪ Relaciones tipadas y dirigidas (`supports`, `contradicts`, `updates`, `caused_by`).

## Fase 6 — Release y operación
- 🟢 CI (GitHub Actions) con las suites + benchmarks en 3.11–3.13.
- ⚪ Linting + type-check (ruff/mypy) + cobertura en CI.
- ⚪ Recuperación **explicable**: `score_components` (similitud directa, boost por
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
  Falta: exponer `max_scan` también por MCP (hoy en la API Python, la del embebido).
- 🟡 **`0.1.0b6` — El núcleo recuerda como un cerebro: grafo navegable (BANDERA).**
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
  Primera pieza landed: `hipercampo/navgraph.py` (algoritmo puro, sin tocar el camino
  caliente) + `tests/test_navgraph.py`. Siguientes fases: persistir el grafo en la tabla
  `links` (knn + atajos) al recordar, y que `recall` navegue (beam) desde un hub o el
  contexto actual, con respaldo a escaneo en memorias pequeñas. Promesa: *recall y
  escritura sublineales; recall@5 ≥0,9; medido en datos reales, no solo sintéticos.*
- ⚪ **`0.2.0b1` — Extensión seria.** Marketplace (publisher + `VSCE_PAT`), settings,
  i18n dentro, y UX que salga de usarlo de verdad.
- ⚪ **Benchmark en SBC real** (Liga A): latencia/RAM/consumo con 1k/10k/100k recuerdos
  en una Pi/Jetson. Sin ese número, "sirve para robots" es humo. Sirve de puerta a `1.0`.

**Fuera de alcance aquí** (sigue siendo otro proyecto): un core en C/Rust para
microcontroladores sin Linux (Liga B). El álgebra VSA es popcount+XOR y cabría en
pocos KB, pero es un spin-off; se anota, no se mete en este repo.

---

**Regla de la casa**: cada fase se cierra con *medición*, no con opinión. Nada de
afirmaciones fuertes sin un test o un benchmark que las respalde. Ver
[ATTRIBUTION.md](ATTRIBUTION.md) y [SECURITY.md](SECURITY.md).
