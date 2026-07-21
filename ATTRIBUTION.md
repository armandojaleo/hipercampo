# Atribución y procedencia

Este proyecto es explícito sobre qué es original y qué debe crédito a terceros.
Regla de la casa: **si usamos trabajo de otros, sobre todo con copyright, se dice.**

## Código

**Todo el código de `hipercampo/` es original**, escrito para este proyecto (por
Armando Jaleo con asistencia de Claude, de Anthropic). No se ha copiado código con
copyright de otros proyectos. El álgebra de hipervectores (`bind`=XOR,
`bundle`=voto por mayoría, `permute`=rotación, distancia de Hamming) son
operaciones matemáticas estándar de dominio público, no una implementación ajena.

## Dependencias de software (con su licencia)

Se instalan por separado vía `pip`; **su código no se incluye** en este repositorio.

| Dependencia | Uso | Licencia |
|-------------|-----|----------|
| [NumPy](https://numpy.org) | operaciones sobre los hipervectores | BSD-3-Clause |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | servidor MCP (`FastMCP`) | MIT |
| Python (stdlib: `sqlite3`, `hashlib`, `re`) | persistencia y utilidades | PSF |

Cada una conserva su propia licencia y copyright.

### Dependencia OPCIONAL del hook semántico (no se instala por defecto)

Solo si activas la semántica con `pip install hipercampo[semantic]`:

| Dependencia / recurso | Uso | Licencia |
|-----------------------|-----|----------|
| [sentence-transformers](https://github.com/UKPLab/sentence-transformers) | generar embeddings densos | Apache-2.0 |
| Modelo `paraphrase-multilingual-MiniLM-L12-v2` (por defecto) | embeddings multilingües | Apache-2.0 (autores del modelo) |

El puente SimHash (`semantic.embedding_to_hv`) que convierte esos embeddings en
hipervectores es **código original nuestro**. El modelo lo descarga el usuario y se
rige por su propia licencia; puedes sustituirlo por cualquier otro con `make_hook`.

## Ideas y trabajo académico en el que nos inspiramos

hipercampo **no implementa** estos trabajos; se inspira en sus ideas y las cita
como es debido. Los conceptos son de sus autores:

- **Pentti Kanerva** — *Sparse Distributed Memory* (memoria asociativa dispersa).
- **Tony A. Plate** — *Holographic Reduced Representations* (HRR / binding).
- **Torchhd** — Heddes et al., *JMLR* 2023: librería de referencia HD/VSA. La
  citamos como estado del arte; **no usamos su código** (implementamos VSA propio).
- Línea reciente de memoria en LLMs (2024-2026): **Titans**, **MIRAS**, **HippoRAG**,
  **MemGPT**, y la relación *atención ≈ SDM* (Bricken & Pehlevan, 2021). Sirvieron
  para situar el hueco a explorar; ninguna aportó código a este repo.

## El "hook" semántico opcional

`encoder.set_semantic_hook()` permite enchufar un codificador semántico externo
(por ejemplo un modelo de embeddings). **hipercampo no incluye ningún modelo.**
Si conectas uno, ese modelo trae su propia licencia y sus propios términos, y eres
tú quien los acepta: decláralo en tu despliegue.

## Cómo citar hipercampo

> Jaleo, A. (2026). *hipercampo: memoria asociativa para LLMs basada en
> hipervectores*. https://github.com/armandojaleo/hipercampo
