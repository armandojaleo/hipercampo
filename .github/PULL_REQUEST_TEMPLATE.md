# Pull request

*(Español o English, ambos valen.)*

## Qué cambia · What changes

<!-- Resume el cambio y el porqué. Enlaza la issue si existe (Closes #N). -->

## Cómo se ha comprobado · How it was verified

<!-- La regla de la casa: MEDIR antes de creer. Pega números o el test que lo prueba.
     The house rule: measure before believing. Paste numbers or the test. -->

```
# tests que pasan / benchmark antes-después
```

## Pegas conocidas · Known downsides

<!-- ¿Qué se pierde, se ralentiza o se complica? Si no hay, escribe "ninguna". -->

## Checklist

- [ ] Hay un **test** para lo que añado o arreglo (los bugs, con test de regresión)
- [ ] La **suite completa** pasa en local
- [ ] Si afirmo mejora de calidad/rendimiento, incluyo **números** (`benchmark.py`,
      `stress.py` o `baselines.py`)
- [ ] La documentación refleja el cambio, **incluidas sus limitaciones**
- [ ] Si uso trabajo de terceros, está declarado con su licencia en
      [ATTRIBUTION.md](../ATTRIBUTION.md)
- [ ] No introduzco dependencias pesadas en el núcleo (van en un extra opcional)
