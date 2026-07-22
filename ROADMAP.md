# Roadmap hacia producción (servicio multiusuario)

hipercampo hoy es **usable en local, mono-usuario**. El objetivo es un **servicio
multiusuario** fiable. Esto es honesto sobre lo que falta y en qué orden. No es un
fin de semana: son meses e implica decisiones de infraestructura.

Estado: 🟢 hecho · 🟡 en marcha · ⚪ pendiente

## Fase 1 — Cimientos de fiabilidad y aislamiento
- 🟢 **Aislamiento por inquilino** (namespaces): cada usuario ve solo lo suyo,
  incluida la lectura por id. Tests en `tests/test_tenancy.py`.
- 🟢 **Concurrencia base**: SQLite en modo WAL + `busy_timeout` (lecturas mientras
  se escribe, sin corromper).
- ⚪ Transacciones explícitas alrededor de operaciones compuestas (update, consolidate).
- ⚪ Migraciones versionadas (tabla `schema_version`) en vez de `ALTER TABLE` ad-hoc.
- ⚪ `VACUUM` / borrado seguro para `hc_forget`.

## Fase 2 — Credibilidad: demostrar la calidad
- ⚪ **Benchmark contra baselines externos**: BM25 (SQLite FTS5), embeddings+coseno,
  híbrido. Sobre datasets estándar (LongMemEval, MemoryAgentBench), no solo el propio.
- ⚪ **Ablaciones**: sin sorpresa / sin propagación / sin consolidación / sin confianza,
  para aislar qué aporta cada pieza (y si VSA es la causa real de la mejora).
- ⚪ Métricas: Recall@k, MRR, precisión de abstención, actualización correcta,
  latencia p50/p95, tokens metidos en contexto.

## Fase 3 — Rendimiento a escala
- ⚪ Sustituir el escaneo lineal: **popcount vectorizado** (XOR de toda la matriz de
  hipervectores de golpe) o índice LSH sobre los binarios. Objetivo: 100k+ en <100ms.
- ⚪ Índice por namespace; carga perezosa; medición de memoria/almacenamiento.

## Fase 4 — Seguridad y multi-tenencia real
- 🟡 Namespaces en el modelo de datos (hecho); falta que el namespace venga de una
  **identidad autenticada**, no del entorno.
- ⚪ **Transporte de red** (MCP sobre HTTP/SSE) en vez de un proceso stdio por cliente.
- ⚪ **AuthN/AuthZ** por inquilino (tokens); rate limiting.
- ⚪ **Cifrado en reposo** (SQLCipher o a nivel de aplicación).
- ⚪ Decisión de motor: SQLite por inquilino vs **Postgres** compartido para alta
  concurrencia. (SQLite escala sorprendentemente bien por-fichero; Postgres si hay
  miles de inquilinos concurrentes.)
- ⚪ Endurecer contra inyección vía memoria (ver [SECURITY.md](SECURITY.md)).

## Fase 5 — La ventaja diferencial (VSA de verdad)
- ⚪ **Memoria composicional con roles**: `SUJETO⊗ · PREDICADO⊗ · OBJETO⊗ · TIEMPO⊗ ·
  FUENTE⊗`, con recuperación por *unbinding* ("¿quién mordió a quién?"), no solo por
  similitud global. Es lo que separaría hipercampo de un índice léxico.
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
