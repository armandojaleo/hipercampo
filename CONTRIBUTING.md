# Contribuir a hipercampo · Contributing

*(Español primero · English below)*

---

## 🇪🇸 Español

¡Gracias por estar aquí! hipercampo es un proyecto pequeño y experimental con una
regla por encima de todas:

> **Medir antes de creer, y decir la verdad de los límites.**

Nada entra por opinión. Si un cambio afirma que mejora algo, viene con un test o un
número. Si algo no funciona bien, se escribe en el README en vez de esconderlo.

### Preparar el entorno

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
pip install -e .           # o: pip install -e ".[semantic]"
```

Antes de abrir un PR, pasa todo:

```bash
python -m pytest -q              # la suite entera (tests/core, storage, cycle, support, contracts)
python -m ruff check hipercampo/ tests/ scripts/ examples/
python scripts/baselines.py      # calidad frente a BM25 (y embeddings con --semantic)
```

Aquí había una lista de 17 tests enumerados a mano, y al agrupar la suite en carpetas
todas esas rutas dejaron de existir. Enumerar a mano es justo lo que hace que un
fichero nuevo no se ejecute nunca y nadie se entere: usa el descubrimiento.

El CI ejecuta lo mismo en Python 3.11–3.13 sobre Linux, Windows y macOS, más los
benchmarks y los ejemplos. Cada fichero de test también se puede correr suelto
(`python tests/core/test_vsa.py`), que es como los ejecuta el CI para que un fallo
dependiente de plataforma salga con nombre y apellidos.

### Qué hace bueno a un PR

- **Un test** para lo que añades o arreglas. Los bugs llevan test de regresión.
- **Números** para cualquier afirmación de calidad o rendimiento
  (`scripts/benchmark.py`, `scripts/stress.py`, `scripts/baselines.py`): pon el
  antes/después.
- **Documentación honesta**: si tu cambio tiene una pega, dilo en el README/ROADMAP.
- Mantén el núcleo ligero (numpy + mcp). Lo pesado va en un *extra* opcional y se
  acredita en [ATTRIBUTION.md](docs/ATTRIBUTION.md).
- Sigue el estilo de alrededor: los comentarios explican el *porqué*, no el *qué*.

### Atribución

Si usas trabajo de otros —código, datos, un modelo, una idea— **dilo**, con su
licencia, en [ATTRIBUTION.md](docs/ATTRIBUTION.md). Aquí no es negociable.

### Buenos primeros aportes

Lo pendiente está en [ROADMAP.md](docs/ROADMAP.md). Algunos autocontenidos:

- Persistir los contadores del modelo de sorpresa entre reinicios.
- Un índice LSH para que la recuperación siga siendo sublineal pasados ~100k recuerdos.
- Ablaciones (sin sorpresa / propagación / consolidación) en `scripts/baselines.py`.
- Evaluar con un dataset externo (LongMemEval, MemoryAgentBench).

### Bugs y seguridad

Bugs: abre una issue con la plantilla. Seguridad: mira [SECURITY.md](SECURITY.md).

Al contribuir aceptas que tu trabajo se publique bajo la licencia MIT del proyecto.

---

## 🇬🇧 English

Thanks for being here! hipercampo is a small, experimental project with one rule
above all others:

> **Measure before you believe, and tell the truth about the limits.**

Nothing goes in on the strength of an opinion. If a change claims an improvement, it
comes with a test or a benchmark number. If something doesn't work well, we write it
in the README instead of hiding it.

### Setup

```bash
git clone https://github.com/armandojaleo/hipercampo.git
cd hipercampo
pip install -e .           # or: pip install -e ".[semantic]"
```

Before opening a PR:

```bash
python -m pytest -q              # the whole suite (tests/core, storage, cycle, support, contracts)
python -m ruff check hipercampo/ tests/ scripts/ examples/
python scripts/baselines.py      # quality against BM25 (and embeddings with --semantic)
```

CI runs the same on Python 3.11–3.13 across Linux, Windows and macOS, plus benchmarks
and examples. Every test file also runs on its own (`python tests/core/test_vsa.py`),
which is how CI runs them so a platform-specific failure comes out named.

### What makes a good pull request

- **A test** for the behaviour you add or fix; bugs get a regression test.
- **Numbers** for any quality/performance claim — post the before/after.
- **Honest docs**: if your change has a downside, say so.
- Keep the core dependency-light (numpy + mcp); heavier things go behind an optional
  extra and are credited in [ATTRIBUTION.md](docs/ATTRIBUTION.md).

### Attribution

If you use someone else's work — code, data, a model, an idea — **say so**, with its
licence, in [ATTRIBUTION.md](docs/ATTRIBUTION.md). Non-negotiable here.

### Good first contributions

See [ROADMAP.md](docs/ROADMAP.md) (surprise-model persistence, physical purge policy, an
LSH index, ablations, external datasets).

Bugs: open an issue. Security: see [SECURITY.md](SECURITY.md). By contributing you
agree your work is released under the project's MIT licence.
