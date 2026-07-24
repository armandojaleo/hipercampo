# hipercampo — visor de memoria (VS Code)

Una ventana para **ver y explorar** la memoria de hipercampo sin salir del editor.
Local-first: no abre red ni base de datos; llama al CLI `hipercampo`, que ya sabe de
contextos y aislamiento. Es de **solo lectura para consultar**, y toda escritura
(olvidar / borrar) es una acción explícita que pasa por el propio CLI con confirmación.

## Cómo abrirlo

- Icono **🗄 memoria** en la **barra de estado** (abajo a la izquierda) → un clic.
- Icono de hipercampo en la **barra de actividad** (tira izquierda) → botón «Abrir el visor».
- O `Ctrl/Cmd+Shift+P` → **«hipercampo: ver memorias»**.

Se abre a un lado del editor.

## Qué muestra (cuatro pestañas)

- **Lista** — una tarjeta por recuerdo: texto, tipo (episódico / semántico / identidad),
  y sus ejes medidos (importancia, fiabilidad, fuerza, usos, última vez visto). Estado con
  iconos: 💤 latente · 📦 consolidado · ↩ reemplazado · ⚠️ pronto latente. Acciones por
  tarjeta: 💡 conexiones · 💤 olvidar / ☀️ despertar · 🗑️ borrar.
- **Mapa** — el grafo asociativo real: nodos = recuerdos (color por proyecto, tamaño por
  importancia), aristas = asociaciones. Arrastra nodos, rueda para zoom, arrastra el fondo
  para desplazar, clic en un nodo lo resalta con sus vecinos y muestra detalle. Los puentes
  oníricos (`hc_dream` propuestos) salen de puntos.
- **Tiempo** — recuerdos por acceso reciente, con barra de fuerza; marca los que están a
  punto de dormirse.
- **Ejes** — dispersión importancia × fiabilidad (tamaño = fuerza); pasa el ratón para ver
  el texto. Caza de un vistazo lo «importante pero poco fiable».

## Buscar y filtrar

- **Modo texto**: filtro instantáneo en cliente (sin acentos). Un visor debe *encontrar*,
  no abstenerse.
- **Modo recall / muse**: busca «como el agente». `recall` es el directo (sabe abstenerse);
  **muse** es la vía *eureka*: trae conexiones indirectas y recuerdos latentes. Escribe y
  pulsa Enter. El 💡 de cada tarjeta lanza `muse` desde ese recuerdo.
- **Chips de proyecto**: si hay varios contextos, aparecen arriba; clic para mostrar/ocultar
  cada uno. Afecta a todas las vistas.

## Olvidar vs. borrar

Igual que en el motor: **olvidar** (💤) solo adormece y es reversible (💤→☀️); **borrar**
(🗑️) es físico e irreversible y pide **confirmación modal** — hace el borrado seguro +
`VACUUM` del CLI (`hipercampo purge`).

## Requisitos

`hipercampo` instalado (`pip install --pre hipercampo`). Si no está en el PATH que ve VS
Code, la extensión prueba automáticamente `python -m hipercampo.cli`; y si tampoco, lo pones
en el ajuste `hipercampo.command`.

## Ajustes

| Ajuste | Por defecto | Para qué |
|---|---|---|
| `hipercampo.command` | `hipercampo` | Ejecutable. Si no está en el PATH: ruta completa o `python -m hipercampo.cli`. |
| `hipercampo.dbPath` | (vacío) | Fichero `.db` (`HIPERCAMPO_DB`). Vacío = el de por defecto. |
| `hipercampo.namespace` | (vacío) | Contexto (`HIPERCAMPO_NAMESPACE`). |
| `hipercampo.allNamespaces` | `true` | Mostrar todo el fichero, no solo un contexto. |

## Desarrollo

```bash
cd editor
npm install
npm run compile
```

Abre `editor/` en VS Code y **F5** (Run Extension). Publicación al Marketplace: ver
[PUBLISHING.md](PUBLISHING.md).

## Cómo lee los datos

Ejecuta `hipercampo graph --json` (nodos + aristas) y `recall`/`muse` para la búsqueda de
agente, con `HIPERCAMPO_LOG=0` para que el stdout sea JSON limpio. Esos comandos existen en
el CLI y sirven también fuera de aquí.
