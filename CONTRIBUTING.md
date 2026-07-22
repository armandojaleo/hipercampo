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
for t in vsa semantic surprise memory update axes hardening namespaces \
         calibration roles safety factstore guardrails muse dream migration properties; do
  python tests/test_$t.py || exit 1
done
python scripts/baselines.py      # calidad frente a BM25 (y embeddings con --semantic)
```

El CI ejecuta lo mismo en Python 3.11–3.13, más los benchmarks y los ejemplos.

### Qué hace bueno a un PR

- **Un test** para lo que añades o arreglas. Los bugs llevan test de regresión.
- **Números** para cualquier afirmación de calidad o rendimiento
  (`scripts/benchmark.py`, `scripts/stress.py`, `scripts/baselines.py`): pon el
  antes/después.
- **Documentación honesta**: si tu cambio tiene una pega, dilo en el README/ROADMAP.
- Mantén el núcleo ligero (numpy + mcp). Lo pesado va en un *extra* opcional y se
  acredita en [ATTRIBUTION.md](ATTRIBUTION.md).
- Sigue el estilo de alrededor: los comentarios explican el *porqué*, no el *qué*.

### Atribución

Si usas trabajo de otros —código, datos, un modelo, una idea— **dilo**, con su
licencia, en [ATTRIBUTION.md](ATTRIBUTION.md). Aquí no es negociable.

### Buenos primeros aportes

Lo pendiente está en [ROADMAP.md](ROADMAP.md). Algunos autocontenidos:

- Persistir los contadores del modelo de sorpresa entre reinicios.
- Política de purga física / `VACUUM` para lo latente muy antiguo.
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

Run the full suite before opening a PR (see the loop above); CI runs the same on
Python 3.11–3.13 plus benchmarks and examples.

### What makes a good pull request

- **A test** for the behaviour you add or fix; bugs get a regression test.
- **Numbers** for any quality/performance claim — post the before/after.
- **Honest docs**: if your change has a downside, say so.
- Keep the core dependency-light (numpy + mcp); heavier things go behind an optional
  extra and are credited in [ATTRIBUTION.md](ATTRIBUTION.md).

### Attribution

If you use someone else's work — code, data, a model, an idea — **say so**, with its
licence, in [ATTRIBUTION.md](ATTRIBUTION.md). Non-negotiable here.

### Good first contributions

See [ROADMAP.md](ROADMAP.md) (surprise-model persistence, physical purge policy, an
LSH index, ablations, external datasets).

Bugs: open an issue. Security: see [SECURITY.md](SECURITY.md). By contributing you
agree your work is released under the project's MIT licence.
