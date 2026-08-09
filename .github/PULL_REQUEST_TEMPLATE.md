# Pull request

*(English or Español — both fine.)*

## What changes · Qué cambia

<!-- Summarise the change and why. Link the issue if there is one (Closes #N). -->

## How it was verified · Cómo se ha comprobado

<!-- The house rule: MEASURE before believing. Paste numbers, or the test that proves it.
     La regla de la casa: medir antes de creer. Pega números o el test que lo prueba. -->

```
# passing tests / before-after benchmark
```

## Known downsides · Pegas conocidas

<!-- What gets lost, slower or more complicated? If nothing, write "none". -->

## Checklist

- [ ] There's a **test** for what I add or fix (bugs get a regression test)
- [ ] The **full suite** passes locally (`python -m pytest -q`)
- [ ] `python -m ruff check hipercampo/ tests/ scripts/ examples/` is clean
- [ ] If I claim a quality/performance improvement, I include **numbers**
      (`benchmark.py`, `stress.py` or `baselines.py`)
- [ ] The docs reflect the change, **including its limitations**
- [ ] Third-party work is declared with its licence in
      [ATTRIBUTION.md](../docs/ATTRIBUTION.md)
- [ ] No heavy dependencies added to the core (those go in an optional extra)
