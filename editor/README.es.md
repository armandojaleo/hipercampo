# hipercampo — visor de memoria para VS Code

Una ventana para **ver y explorar** la memoria de hipercampo sin salir del editor.
Local-first: no abre red ni base de datos; llama al CLI `hipercampo`, que ya sabe de
contextos y aislamiento. Es de **solo lectura para consultar**, y toda escritura
(olvidar / borrar) es una acción explícita que pasa por el propio CLI con confirmación.

[Read in English](README.md).

## Cómo abrirlo

- Botón **🗄 Hipercampo** en la **barra de estado** (abajo) → abre el panel ancho a un lado.
- Icono de Hipercampo en la **barra de actividad** (tira izquierda) → el **visor completo**
  vive ahí mismo (ensancha la barra arrastrando su borde si quieres más sitio).
- O `Ctrl/Cmd+Shift+P` → **«hipercampo: ver memorias»**.

**Se refresca solo**: vigila el `.db` y el `.log`, así que según el agente va guardando,
recordando y decidiendo, las pestañas se actualizan en vivo sin cerrar y abrir.

## Qué muestra (nueve pestañas)

- **Lista** — una tarjeta por recuerdo: texto, tipo (episódico / semántico / identidad),
  y sus ejes medidos (importancia, fiabilidad, fuerza, usos, última vez visto). Estado con
  iconos: 💤 latente · 📦 consolidado · ↩ reemplazado · ⚠️ pronto latente. Acciones por
  tarjeta: 💡 conexiones · 💤 olvidar / ☀️ despertar · 🗑️ borrar.
- **Mapa** — el grafo asociativo real: nodos = recuerdos (color por proyecto, tamaño por
  importancia), aristas = asociaciones. Arrastra nodos, rueda para zoom, arrastra el fondo
  para desplazar, clic en un nodo lo resalta con sus vecinos y muestra detalle. Los puentes
  oníricos (`hc_dream` propuestos) salen de puntos. Las posiciones se conservan entre
  refrescos (no re-baila).
- **Tiempo** — recuerdos por acceso reciente, con barra de fuerza; marca los que están a
  punto de dormirse.
- **Ejes** — dispersión importancia × fiabilidad (tamaño = fuerza); pasa el ratón para ver
  el texto. Caza de un vistazo lo «importante pero poco fiable».
- **Ideas** — hipótesis explícitas creadas por puentes entre recuerdos distantes.
- **Hechos** — registros estructurados sujeto/predicado/objeto/tiempo/fuente y su historial.
- **Tokens** — la **factura**: gastados, ahorrados por el presupuesto, inyecciones, hoy;
  un medidor de media-por-inyección contra el presupuesto y el historial en barras. Siempre
  es una estimación, y lo dice.
- **Registro** — el log de decisiones en vivo (recall / remember / sleep / forget / tokens…),
  coloreado por acción, más reciente arriba.
- **Estado** — salud con semáforos: CLI, base de datos (integridad, esquema, tamaño),
  memoria por contexto, servidor MCP (en marcha o no) y registro.

## Buscar y filtrar

- **Modo texto**: filtro instantáneo en cliente (sin acentos). Un visor debe *encontrar*,
  no abstenerse.
- **Recall explicable**: las tarjetas muestran el score y, al pasar el ratón, sus
  componentes (`activation`, fuerza, confianza y penalización por superado). También
  enseñan si se usó navegación y cuántos nodos visitó (`nav · N`).
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
[PUBLISHING.es.md](PUBLISHING.es.md).

## Cómo lee los datos

Todo por el CLI (que ya sabe de contextos y aislamiento): `graph --json` (nodos + aristas
+ ruta del `.db`), `list --json`, `status`, `tokens`, `log --json`, y `recall`/`muse` para
la búsqueda de agente. La auditoría va a stderr, así que el stdout es JSON limpio. Esos
comandos existen en el CLI y sirven también fuera de aquí.
