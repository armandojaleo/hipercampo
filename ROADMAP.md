# Roadmap hacia producción (local-first)

**Meta: la mejor memoria local para un agente.** Cada usuario aloja hipercampo en
SU máquina, con SU fichero de memoria. No hay servidor central ni multiusuario: eso
sería coste e infraestructura innecesarios. Local-first = privado por diseño, gratis
de operar, sin datos de terceros que custodiar.

Por eso **queda fuera de alcance** (a propósito): autenticación, cifrado gestionado,
Postgres compartido, transporte de red, hosting multiusuario. Si alguien quisiera un
SaaS encima, sería otro proyecto; el núcleo se mantiene local y simple.

Estado: 🟢 hecho · 🟡 en marcha · ⚪ pendiente

## Fase 1 — Cimientos de fiabilidad y aislamiento
- 🟢 **Aislamiento por namespace/contexto**: cada contexto ve solo lo suyo, en TODAS
  las operaciones (lecturas y escrituras por id: delete/touch/mark_*), y los enlaces
  no cruzan contextos. Tests en `tests/test_namespaces.py`.
- 🟢 **Concurrencia base**: SQLite en modo WAL + `busy_timeout` (lecturas mientras
  se escribe, sin corromper).
- 🟢 **Transacciones atómicas** en operaciones compuestas (update, consolidate):
  si algo falla a mitad, se revierte (`store.transaction()`).
- 🟢 **Validación de entradas en el núcleo**: texto no vacío + longitud máxima,
  `importance`/`confidence` acotados, `k`/`hops` acotados, namespace saneado.
- ⚪ Migraciones versionadas (tabla `schema_version`) en vez de `ALTER TABLE` ad-hoc.
- ⚪ `VACUUM` / borrado seguro para `hc_forget`.

## Fase 1b — Calibrar la sorpresa
- 🟢 **Umbral adaptativo**: "predecible" = cuantil inferior de la sorpresa reciente
  (respaldo absoluto con poco historial). Test que demuestra que el veto ES
  alcanzable con secuencias realistas (`tests/test_calibration.py`).
- 🟢 Aprender **después** del commit (el modelo no se adelanta a la BD si hay rollback)
  y reforzar solo si es redundante (no por un match débil al vetar por predecible).
- ⚪ **Persistencia real** de los contadores unigrama/bigrama por namespace (hoy se
  reconstruye solo desde lo guardado; lo visto-y-rechazado no persiste al reiniciar).
- ⚪ Calibrar `MIN_RECALL_SCORE` midiendo la **tasa de falsas recuperaciones** al crecer
  N (no solo Recall@k).

## Fase 2 — Credibilidad: demostrar la calidad
- 🟢 **Baselines** (`scripts/baselines.py`): BM25 y embeddings+coseno vs hipercampo.
  Resultado medido: hipercampo+semántico gana en MRR global (0.95 vs 0.87 de
  embeddings); en léxico ya supera a BM25 (erratas 0.95 vs 0.77). Pierde en
  abstención (falsaRec 1.00 vs 0.20) -> calibrar `MIN_RECALL_SCORE`.
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
- ⚪ Release **v0.1.0** (tag + changelog), publicación en **PyPI**.
- ⚪ Observabilidad: logging estructurado, métricas.

---

**Regla de la casa**: cada fase se cierra con *medición*, no con opinión. Nada de
afirmaciones fuertes sin un test o un benchmark que las respalde. Ver
[ATTRIBUTION.md](ATTRIBUTION.md) y [SECURITY.md](SECURITY.md).
