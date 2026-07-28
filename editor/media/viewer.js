// Webview del visor. Sin frameworks ni librerías externas (la CSP bloquea CDNs):
// DOM + canvas a mano. Habla con la extensión por mensajes.
(function () {
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);

  // --- idioma (es/en) — lo fija la extensión desde vscode.env.language ----------
  // Comunidad bilingüe: por defecto inglés, español si VS Code está en español.
  const lang = (document.documentElement.lang || "en").toLowerCase().startsWith("es")
    ? "es" : "en";
  const DICT = {
    es: {
      filtrar: "Filtrar por texto…", comoBuscar: "Cómo buscar",
      optText: "texto", optRecall: "recall (agente)", optMuse: "muse (eureka)",
      pausar: "Pausar la memoria (modo 'no recordar')", reanudar: "Reanudar la memoria",
      refrescar: "Refrescar", todosContextos: "todos los contextos",
      banner: "⏸ Memoria <b>en pausa</b>: no se graban recuerdos nuevos ni se refuerzan (leer sí funciona).",
      tabs: { list: "Lista", graph: "Mapa", timeline: "Tiempo", axes: "Ejes",
        ideas: "Ideas", tokens: "Tokens", log: "Registro", status: "Estado" },
      vacio: "Nada que mostrar.",
      vacioHint: "Prueba a limpiar el buscador o activa «todos los contextos».",
      guion: "—", hoy: "hoy", dias: (n) => `hace ${n} d`, mes: (n) => `hace ${n} mes`,
      anos: (x) => `hace ${x} a`,
      chipTitle: "Mostrar/ocultar este contexto",
      deTotal: (n, t) => `${n} de ${t}`,
      escribeConsulta: (m) => `Escribe una consulta y pulsa Enter para buscar con ${m}.`,
      noEncontro: "No encontró nada. En modo recall puede haberse abstenido (sabe decir «no tengo nada»); prueba muse para conexiones indirectas.",
      nadaMostrar: "Nada que mostrar. Prueba a limpiar el buscador o activa «todos los contextos».",
      mImp: "imp", mFiab: "fiab", mFuerza: "fuerza", mUsos: "usos", mVisto: "visto",
      relevancia: "relevancia", flagsTitle: "latente/consolidado/reemplazado/pronto-latente",
      actMuse: "Conexiones (muse)", actWake: "Despertar", actMove: "Mover a otro contexto",
      actForget: "Olvidar (reversible)", actPurge: "Borrar del todo (irreversible)",
      leyAsociacion: "asociación", leyPuente: "puente onírico",
      detMuse: "💡 conexiones", detWake: "☀️ despertar", detForget: "💤 olvidar",
      detPurge: "🗑️ borrar",
      tlLatente: "💤 latente", tlPronto: "⚠️ pronto latente",
      axImportancia: "importancia →", axFiabilidad: "fiabilidad →",
      consultandoEstado: "Consultando estado…",
      hCLI: "CLI", hBD: "Base de datos", hMemoria: "Memoria", hMCP: "Servidor MCP",
      hRegistro: "Registro (hooks y decisiones)",
      sVersion: "versión", sPython: "python", sMemoria: "memoria",
      sEnPausa: "EN PAUSA (no recuerda)", sActiva: "activa (recordando)",
      sEstado: "estado", sSana: "sana", sConProblemas: "con problemas",
      sIntegridad: "integridad", sEsquema: "esquema",
      sEsperada: (v, e) => `v${v} / esperada v${e}`,
      sEscribible: "escribible", sSi: "sí", sNo: "no", sTamano: "tamaño", sRuta: "ruta",
      sTotal: "total", sRecuerdos: (n) => `${n} recuerdos`,
      sEpisodicos: "episódicos activos", sSemanticos: "semánticos",
      sLatentes: "latentes", sArchivados: "archivados",
      sTokensTurno: "tokens/turno (presup.)",
      sEnMarcha: "en marcha", sMcpSi: (n) => `sí (${n})`, sMcpNo: "no (se arranca al usarse)",
      sDesde: (f) => `desde ${f}`,
      sActivo: "activo", sLogNo: "no (HIPERCAMPO_LOG=0)", sUltima: "última actividad",
      estadoHint: "El estado se consulta al abrir esta pestaña. Pulsa ↻ para actualizarlo.",
      calculandoFactura: "Calculando la factura…",
      tGastados: "tokens gastados", tAhorrados: "ahorrados por el presupuesto",
      tInyecciones: "inyecciones", tHoy: "hoy",
      tMediaVs: "Media por inyección vs. presupuesto",
      tMedia: "media", tPresupHook: "presupuesto hook", tPresupId: "presupuesto identidad",
      tReset: "reset", matarServidor: "Cerrar este servidor (el cliente lo relanza al usarlo)",
      tTok: "tok", tTokTurno: "tok/turno",
      tHistoria: (n) => `Historia (${n} inyecciones · rojo = sobre presupuesto)`,
      tEstimacion: (m) => `Siempre es una <b>estimación</b> y lo dice: ${m}. El tokenizador de Claude no es público; solo su API es exacta.`,
      leyendoRegistro: "Leyendo el registro…",
      registroVacio: "El registro está vacío o desactivado (HIPERCAMPO_LOG=0).",
      phRecall: "Escribe una consulta y pulsa Enter (recall, como el agente)…",
      phMuse: "Escribe una semilla y pulsa Enter (muse: conexiones eureka)…",
      buscandoCon: (m) => `buscando con ${m}…`,
      errorLeer: "No se pudo leer la memoria:\n\n",
      issueTitle: "Reportar un problema (GitHub)",
      tejer: "Tejer el grafo de vecinos (densifica el mapa)",
      abrirLog: "Abrir el fichero de registro",
      backup: "Copia de seguridad",
      backupHint: "Crea una copia consistente del .db",
      sMcpDb: "memoria", sMcpCtx: "contexto",
      sMcpDesconocida: "(no legible en este sistema)",
      ideasCargando: "Buscando ideas (puentes entre recuerdos)…",
      ideasVacio: "Sin ideas nuevas por ahora. El sueño propone puentes cuando dos recuerdos comparten un asociado común pero no están conectados; con poca memoria aún no hay qué cruzar.",
      ideasIntro: "Hipótesis que la memoria sugiere — conexiones que aún no sabías. Son propuestas, no verdades: no se han grabado.",
      ideasVia: "ambos evocan",
      ideasHipotesis: (a, b, via) => `«${a}» y «${b}» quizá se relacionan`,
      ideasSim: "afinidad",
    },
    en: {
      filtrar: "Filter by text…", comoBuscar: "How to search",
      optText: "text", optRecall: "recall (agent)", optMuse: "muse (eureka)",
      pausar: "Pause the memory ('don't remember' mode)", reanudar: "Resume the memory",
      refrescar: "Refresh", todosContextos: "all contexts",
      banner: "⏸ Memory <b>paused</b>: no new memories are written or reinforced (reading still works).",
      tabs: { list: "List", graph: "Map", timeline: "Timeline", axes: "Axes",
        ideas: "Ideas", tokens: "Tokens", log: "Log", status: "Status" },
      vacio: "Nothing to show.",
      vacioHint: "Try clearing the search or turn on “all contexts”.",
      guion: "—", hoy: "today", dias: (n) => `${n}d ago`, mes: (n) => `${n}mo ago`,
      anos: (x) => `${x}y ago`,
      chipTitle: "Show/hide this context",
      deTotal: (n, t) => `${n} of ${t}`,
      escribeConsulta: (m) => `Type a query and press Enter to search with ${m}.`,
      noEncontro: "Nothing found. In recall mode it may have abstained (it can say “I have nothing”); try muse for indirect connections.",
      nadaMostrar: "Nothing to show. Try clearing the search or turn on “all contexts”.",
      mImp: "imp", mFiab: "conf", mFuerza: "strength", mUsos: "uses", mVisto: "seen",
      relevancia: "relevance", flagsTitle: "dormant/consolidated/superseded/soon-dormant",
      actMuse: "Connections (muse)", actWake: "Wake", actMove: "Move to another context",
      actForget: "Forget (reversible)", actPurge: "Delete for good (irreversible)",
      leyAsociacion: "association", leyPuente: "dream bridge",
      detMuse: "💡 connections", detWake: "☀️ wake", detForget: "💤 forget",
      detPurge: "🗑️ delete",
      tlLatente: "💤 dormant", tlPronto: "⚠️ soon dormant",
      axImportancia: "importance →", axFiabilidad: "reliability →",
      consultandoEstado: "Checking status…",
      hCLI: "CLI", hBD: "Database", hMemoria: "Memory", hMCP: "MCP server",
      hRegistro: "Log (hooks and decisions)",
      sVersion: "version", sPython: "python", sMemoria: "memory",
      sEnPausa: "PAUSED (not remembering)", sActiva: "active (remembering)",
      sEstado: "state", sSana: "healthy", sConProblemas: "has problems",
      sIntegridad: "integrity", sEsquema: "schema",
      sEsperada: (v, e) => `v${v} / expected v${e}`,
      sEscribible: "writable", sSi: "yes", sNo: "no", sTamano: "size", sRuta: "path",
      sTotal: "total", sRecuerdos: (n) => `${n} memories`,
      sEpisodicos: "active episodic", sSemanticos: "semantic",
      sLatentes: "dormant", sArchivados: "archived",
      sTokensTurno: "tokens/turn (budget)",
      sEnMarcha: "running", sMcpSi: (n) => `yes (${n})`, sMcpNo: "no (starts on use)",
      sDesde: (f) => `since ${f}`,
      sActivo: "enabled", sLogNo: "no (HIPERCAMPO_LOG=0)", sUltima: "last activity",
      estadoHint: "Status is fetched when you open this tab. Press ↻ to refresh it.",
      calculandoFactura: "Computing the bill…",
      tGastados: "tokens spent", tAhorrados: "saved by the budget",
      tInyecciones: "injections", tHoy: "today",
      tMediaVs: "Average per injection vs. budget",
      tMedia: "average", tPresupHook: "hook budget", tPresupId: "identity budget",
      tReset: "reset", matarServidor: "Close this server (the client relaunches it on use)",
      tTok: "tok", tTokTurno: "tok/turn",
      tHistoria: (n) => `History (${n} injections · red = over budget)`,
      tEstimacion: (m) => `Always an <b>estimate</b>, and it says so: ${m}. Claude's tokenizer isn't public; only its API is exact.`,
      leyendoRegistro: "Reading the log…",
      registroVacio: "The log is empty or disabled (HIPERCAMPO_LOG=0).",
      phRecall: "Type a query and press Enter (recall, like the agent)…",
      phMuse: "Type a seed and press Enter (muse: eureka connections)…",
      buscandoCon: (m) => `searching with ${m}…`,
      errorLeer: "Couldn't read the memory:\n\n",
      issueTitle: "Report a problem (GitHub)",
      tejer: "Weave the neighbor graph (densifies the map)",
      abrirLog: "Open the log file",
      backup: "Backup",
      backupHint: "Make a consistent copy of the .db",
      sMcpDb: "memory", sMcpCtx: "context",
      sMcpDesconocida: "(not readable on this system)",
      ideasCargando: "Looking for ideas (bridges between memories)…",
      ideasVacio: "No new ideas yet. Dreaming proposes bridges when two memories share a common associate but aren't connected; with little memory there's nothing to cross yet.",
      ideasIntro: "Hypotheses the memory suggests — connections you didn't know yet. They're proposals, not truths: nothing has been saved.",
      ideasVia: "both evoke",
      ideasHipotesis: (a, b, via) => `“${a}” and “${b}” might be related`,
      ideasSim: "affinity",
    },
  };
  const L = DICT[lang];

  // --- estado ---------------------------------------------------------------
  let MEM = [];          // nodos (memorias) del último fetch
  let EDGES = [];        // aristas del grafo
  let SCOPE = "";
  let HITS = null;       // resultados de recall/muse (null = no hay búsqueda de agente)
  let ACTIVE = null;     // Set de namespaces activos (chips); null = todos
  let VIEW = "list";
  let PAUSED = false;    // modo 'no recordar'

  // --- utilidades -----------------------------------------------------------
  const norm = (s) => String(s || "").toLowerCase()
    .normalize("NFD").replace(/[̀-ͯ]/g, "");

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    })[c]);
  }

  // Color estable por namespace (mismo proyecto -> mismo tono).
  function hue(ns) {
    let h = 0;
    for (const ch of String(ns || "")) h = (h * 31 + ch.charCodeAt(0)) % 360;
    return h;
  }
  const nsColor = (ns) => `hsl(${hue(ns)} 60% 55%)`;

  function fecha(ts) {
    if (!ts) return L.guion;
    const d = (Date.now() / 1000 - ts) / 86400;
    if (d < 1) return L.hoy;
    if (d < 30) return L.dias(Math.round(d));
    if (d < 365) return L.mes(Math.round(d / 30));
    return L.anos((d / 365).toFixed(1));
  }

  // Heurística "pronto latente": débil, viejo y aún despierto. Es aproximada (el
  // decaimiento real vive en el motor), y se etiqueta como tal en la UI.
  function prontoLatente(m) {
    if (m.dormant) return false;
    const edad = (Date.now() / 1000 - (m.last_access || 0)) / 86400;
    return (m.strength || 0) < 0.4 && edad > 7 && (m.importance || 0) < 0.8;
  }

  // Memorias visibles: filtro por chips de namespace + (si modo texto) por texto.
  function visibles() {
    let base = HITS !== null ? HITS : MEM;
    if (ACTIVE) base = base.filter((m) => ACTIVE.has(m.namespace));
    const q = norm($("q").value.trim());
    if (q && $("mode").value === "text") {
      base = base.filter((m) => norm(m.text).includes(q)
        || norm(m.namespace).includes(q) || norm(m.kind).includes(q));
    }
    return base;
  }

  // --- etiquetas estáticas: se aplican según el idioma al arrancar ----------
  function aplicarIdioma() {
    $("q").placeholder = L.filtrar;
    $("mode").title = L.comoBuscar;
    const opts = $("mode").options;
    opts[0].textContent = L.optText;
    opts[1].textContent = L.optRecall;
    opts[2].textContent = L.optMuse;
    $("refresh").title = L.refrescar;
    $("weave").title = L.tejer;
    $("issue").title = L.issueTitle;
    $("paused-banner").innerHTML = L.banner;
    $("all-label").textContent = L.todosContextos;
    document.querySelectorAll(".tab").forEach((t) => {
      const k = t.dataset.view;
      if (L.tabs[k]) t.textContent = L.tabs[k];
    });
    const emptyPs = $("empty").querySelectorAll("p");
    if (emptyPs[0]) emptyPs[0].textContent = L.vacio;
    if (emptyPs[1]) emptyPs[1].textContent = L.vacioHint;
    pintarPausa();   // fija el título del botón de pausa según idioma+estado
  }

  // --- chips de namespace ---------------------------------------------------
  function pintarChips() {
    const cont = $("chips");
    const todos = [...new Set(MEM.map((m) => m.namespace))].sort();
    if (todos.length <= 1) { cont.innerHTML = ""; return; }
    cont.innerHTML = "";
    for (const ns of todos) {
      const on = !ACTIVE || ACTIVE.has(ns);
      const el = document.createElement("span");
      el.className = "chip" + (on ? " on" : "");
      el.style.setProperty("--chip", nsColor(ns));
      el.textContent = ns;
      el.title = L.chipTitle;
      el.onclick = () => {
        // Clic = ver SOLO este contexto; volver a pulsarlo (ya aislado) = ver todos.
        const soloEste = ACTIVE && ACTIVE.size === 1 && ACTIVE.has(ns);
        ACTIVE = soloEste ? null : new Set([ns]);
        sincronizarAll(todos); pintarChips(); repintar();
      };
      cont.appendChild(el);
    }
  }

  // El checkbox "todos los contextos" refleja si se ven todos; nunca deja la pantalla
  // vacía. Marcarlo = ver todos; desmarcarlo = aislar UNO (el primero), no ninguno.
  function sincronizarAll(todos) {
    const chk = $("all");
    if (chk) chk.checked = (ACTIVE === null);
  }

  // --- cabecera / contador --------------------------------------------------
  function cabecera(n) {
    const total = (HITS !== null ? HITS : MEM).length;
    $("scope").textContent = HITS !== null
      ? `${$("mode").value} · ${SCOPE}` : SCOPE;
    $("count").textContent = n === total ? `${total}` : L.deTotal(n, total);
  }

  // --- repintar la vista activa --------------------------------------------
  function mensajeVacio() {
    const m = $("mode").value;
    if (m !== "text" && HITS === null)
      return L.escribeConsulta(m);
    if (HITS !== null)
      return L.noEncontro;
    return L.nadaMostrar;
  }

  function repintar() {
    if (PIDE[VIEW]) return;   // estado/tokens/registro no se pintan desde aquí
    const items = visibles();
    const vacio = items.length === 0;
    $("empty").classList.toggle("hidden", !vacio);
    if (vacio) $("empty").querySelector("p").textContent = mensajeVacio();
    $("error").classList.add("hidden");
    cabecera(items.length);
    if (VIEW === "list") renderList(items);
    else if (VIEW === "graph") renderGraph(items);
    else if (VIEW === "timeline") renderTimeline(items);
    else if (VIEW === "axes") renderAxes(items);
    else if (VIEW === "status") { /* se pide aparte, ver activarVista */ }
  }

  // ==========================================================================
  // LISTA
  // ==========================================================================
  function metric(label, v) {
    if (v == null) return "";
    const pct = Math.max(0, Math.min(1, v));
    return `<span>${label} <b>${v.toFixed(2)}</b><span class="bar" style="--v:${pct}"></span></span>`;
  }

  function card(m) {
    const el = document.createElement("div");
    el.className = "card" + (m.dormant ? " dormant" : "") + (m.superseded ? " superseded" : "");
    el.style.setProperty("--accent", nsColor(m.namespace));
    const flags = [m.dormant ? "💤" : "", m.consolidated ? "📦" : "",
      m.superseded ? "↩" : "", prontoLatente(m) ? "⚠️" : ""].join("");
    const ns = m.namespace ? `<span class="ns" style="color:${nsColor(m.namespace)}">⟨${esc(m.namespace)}⟩</span>` : "";
    const score = (m.score != null)
      ? `<span class="badge" title="${L.relevancia}">score ${(+m.score).toFixed(2)}</span>` : "";
    const metrics = [metric(L.mImp, m.importance), metric(L.mFiab, m.confidence),
      metric(L.mFuerza, m.strength),
      (m.access_count != null ? `<span>${L.mUsos} <b>${m.access_count}</b></span>` : ""),
      (m.last_access != null ? `<span>${L.mVisto} <b>${fecha(m.last_access)}</b></span>` : "")]
      .filter(Boolean).join("");
    el.innerHTML =
      `<div class="head"><span class="id">#${m.id}</span>`
      + `<span class="badge">${esc(m.kind || "?")}</span>${ns}${score}`
      + `<span class="flags" title="${L.flagsTitle}">${flags}</span>`
      + `<span class="actions">`
      + `<button data-act="muse" title="${L.actMuse}">💡</button>`
      + `<button data-act="move" title="${L.actMove}">📁</button>`
      + (m.dormant
          ? `<button data-act="wake" title="${L.actWake}">☀️</button>`
          : `<button data-act="forget" title="${L.actForget}">💤</button>`)
      + `<button data-act="purge" title="${L.actPurge}">🗑️</button>`
      + `</span></div>`
      + `<div class="text">${esc(m.text || "")}</div>`
      + (metrics ? `<div class="metrics">${metrics}</div>` : "");
    el.querySelectorAll("button[data-act]").forEach((b) => {
      b.onclick = () => accion(b.dataset.act, m);
    });
    return el;
  }

  function accion(act, m) {
    if (act === "muse") {
      $("mode").value = "muse"; $("q").value = m.text.slice(0, 60);
      lanzarBusquedaAgente();
    } else if (act === "move") {
      vscode.postMessage({ type: "reclassify", id: m.id, namespace: m.namespace });
    } else {
      vscode.postMessage({ type: "mutate", id: m.id, namespace: m.namespace, action: act });
    }
  }

  function renderList(items) {
    const c = $("view-list");
    c.innerHTML = "";
    const frag = document.createDocumentFragment();
    for (const m of items) frag.appendChild(card(m));
    c.appendChild(frag);
  }

  // ==========================================================================
  // MAPA (grafo force-directed en canvas)
  // ==========================================================================
  let G = null;             // estado del grafo (nodos con posición, cámara, animación)
  const GPOS = new Map();   // id -> {x,y} PERSISTENTE entre refrescos (no re-baila)

  const firmaNodos = (items) => items.map((m) => m.id).sort((a, b) => a - b).join(",");

  function renderGraph(items) {
    const canvas = $("graph-canvas");
    const vis = new Set(items.map((m) => m.id));
    const aristas = EDGES.filter((e) => vis.has(e.src) && vis.has(e.dst));
    const sig = firmaNodos(items);

    // MISMO conjunto de nodos (caso típico del auto-refresh): NO resembrar ni
    // resimular —eso es lo que hacía saltar el mapa—; solo refrescar datos y redibujar.
    if (G && G.sig === sig) {
      const byId = new Map(items.map((m) => [m.id, m]));
      for (const n of G.nodos) n.m = byId.get(n.id) || n.m;
      G.aristas = aristas;
      leyenda(items); ajustarCanvas(canvas); dibujarGrafo();
      return;
    }

    // Conjunto NUEVO: construir sembrando desde las posiciones guardadas (los nodos
    // que ya existían se quedan donde estaban; solo los nuevos entran por el círculo).
    if (G) cancelAnimationFrame(G.raf);
    const nodos = items.map((m) => ({ m, id: m.id }));
    const idx = new Map(nodos.map((n, i) => [n.id, i]));
    const R = 180;
    nodos.forEach((n, i) => {
      const g = GPOS.get(n.id);
      if (g) { n.x = g.x; n.y = g.y; } else {
        const a = (i / Math.max(1, nodos.length)) * Math.PI * 2;
        n.x = Math.cos(a) * R; n.y = Math.sin(a) * R;
      }
      n.vx = 0; n.vy = 0;
    });
    G = { canvas, ctx: canvas.getContext("2d"), nodos, idx, aristas, sig,
      scale: (G && G.scale) || 1, ox: (G && G.ox) || 0, oy: (G && G.oy) || 0,
      sel: null, drag: null, alpha: 1, raf: 0 };
    leyenda(items);
    ajustarCanvas(canvas);
    correrSim();
    engancharGrafo();
  }

  function leyenda(items) {
    const nss = [...new Set(items.map((m) => m.namespace))].sort();
    const l = $("graph-legend");
    l.innerHTML = nss.map((ns) =>
      `<div class="k"><span class="dot" style="background:${nsColor(ns)}"></span>${esc(ns)}</div>`).join("")
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-foreground);opacity:.5"></span>${L.leyAsociacion}</div>`
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-textLink-foreground);border-top-style:dashed"></span>${L.leyPuente}</div>`;
  }

  function ajustarCanvas(c) {
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.max(1, r.width * dpr); c.height = Math.max(1, r.height * dpr);
    if (G) { G.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); G.w = r.width; G.h = r.height; }
  }

  function correrSim() {
    if (!G) return;
    cancelAnimationFrame(G.raf);
    G.alpha = 1;
    const paso = () => {
      // Se detiene si no estamos en el mapa o si el panel no se ve: cero CPU en reposo.
      if (!G || VIEW !== "graph" || document.hidden) return;
      if (!G.drag) tick();
      dibujarGrafo();
      G.alpha *= 0.97;
      if (G.alpha > 0.02 || G.drag) G.raf = requestAnimationFrame(paso);
    };
    G.raf = requestAnimationFrame(paso);
  }

  function tick() {
    const N = G.nodos, E = G.aristas, a = G.alpha;
    const K = 6000;   // repulsión
    for (let i = 0; i < N.length; i++) {
      let fx = 0, fy = 0;
      const ni = N[i];
      for (let j = 0; j < N.length; j++) {
        if (i === j) continue;
        const nj = N[j];
        let dx = ni.x - nj.x, dy = ni.y - nj.y;
        let d2 = dx * dx + dy * dy || 0.01;
        const f = K / d2;
        const d = Math.sqrt(d2);
        fx += (dx / d) * f; fy += (dy / d) * f;
      }
      fx += -ni.x * 0.02; fy += -ni.y * 0.02;   // gravedad al centro
      ni.fx = fx; ni.fy = fy;
    }
    for (const e of E) {                          // muelles por arista
      const s = N[G.idx.get(e.src)], t = N[G.idx.get(e.dst)];
      if (!s || !t) continue;
      let dx = t.x - s.x, dy = t.y - s.y;
      const d = Math.hypot(dx, dy) || 0.01;
      // los knn son muchos: muelle más largo y flojo para que el clúster respire y no
      // se colapse en una pelota; los enlaces con significado tiran más y juntan.
      const knn = e.type === "knn";
      const rest = knn ? 130 : 70;
      const f = (d - rest) * (knn ? 0.006 : 0.02) * (0.4 + (e.weight || 0.5));
      const ux = dx / d, uy = dy / d;
      s.fx += ux * f; s.fy += uy * f; t.fx -= ux * f; t.fy -= uy * f;
    }
    for (const n of N) {
      if (n === (G.drag && G.drag.node)) continue;
      n.vx = (n.vx + n.fx * a) * 0.85; n.vy = (n.vy + n.fy * a) * 0.85;
      n.x += n.vx; n.y += n.vy;
      GPOS.set(n.id, { x: n.x, y: n.y });   // recordar dónde quedó, para el próximo refresco
    }
  }

  function toScreen(n) { return { x: G.w / 2 + G.ox + n.x * G.scale, y: G.h / 2 + G.oy + n.y * G.scale }; }

  function dibujarGrafo() {
    const { ctx, w, h } = G;
    ctx.clearRect(0, 0, w, h);
    // aristas
    for (const e of G.aristas) {
      const s = G.nodos[G.idx.get(e.src)], t = G.nodos[G.idx.get(e.dst)];
      if (!s || !t) continue;
      const a = toScreen(s), b = toScreen(t);
      const puente = e.status === "proposed" || e.type === "bridge" || e.type === "dream";
      const knn = e.type === "knn";   // estructura de navegación: fina y tenue
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = puente ? getVar("--vscode-textLink-foreground")
        : (knn ? "rgba(140,140,140,.13)" : "rgba(140,140,140,.45)");
      ctx.lineWidth = puente ? 1.2 : (knn ? 0.5 : Math.min(2.5, 0.5 + (e.weight || 0.5) * 1.5));
      if (puente) ctx.setLineDash([4, 4]); else ctx.setLineDash([]);
      const resaltar = G.sel && (e.src === G.sel || e.dst === G.sel);
      ctx.globalAlpha = G.sel && !resaltar ? 0.15 : 1;
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    ctx.setLineDash([]);
    // nodos
    for (const n of G.nodos) {
      const p = toScreen(n);
      const r = (4 + (n.m.importance || 0.3) * 7) * Math.max(0.6, Math.min(1.6, G.scale));
      const atenua = G.sel && G.sel !== n.id && !vecino(G.sel, n.id);
      ctx.globalAlpha = atenua ? 0.25 : 1;
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = nsColor(n.m.namespace);
      if (n.m.dormant) { ctx.globalAlpha *= 0.4; }
      ctx.fill();
      if (n.id === G.sel) { ctx.lineWidth = 2; ctx.strokeStyle = getVar("--vscode-focusBorder"); ctx.stroke(); }
      ctx.globalAlpha = 1;
    }
  }

  function vecino(a, b) {
    return G.aristas.some((e) => (e.src === a && e.dst === b) || (e.src === b && e.dst === a));
  }

  function getVar(name) {
    return getComputedStyle(document.body).getPropertyValue(name).trim() || "#8ab4f8";
  }

  function nodoEn(mx, my) {
    for (let i = G.nodos.length - 1; i >= 0; i--) {
      const p = toScreen(G.nodos[i]);
      const r = (4 + (G.nodos[i].m.importance || 0.3) * 7) * Math.max(0.6, Math.min(1.6, G.scale)) + 3;
      if ((mx - p.x) ** 2 + (my - p.y) ** 2 <= r * r) return G.nodos[i];
    }
    return null;
  }

  function engancharGrafo() {
    const c = G.canvas;
    c.onpointerdown = (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const n = nodoEn(mx, my);
      if (n) {
        G.sel = n.id; G.drag = { node: n, dx: 0, dy: 0 }; detalle(n.m);
        correrSim();
      } else { G.drag = { pan: true, sx: mx - G.ox, sy: my - G.oy }; G.sel = null; $("graph-detail").classList.add("hidden"); }
      c.setPointerCapture(e.pointerId);
    };
    c.onpointermove = (e) => {
      if (!G.drag) return;
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      if (G.drag.pan) { G.ox = mx - G.drag.sx; G.oy = my - G.drag.sy; dibujarGrafo(); }
      else { const n = G.drag.node; n.x = (mx - G.w / 2 - G.ox) / G.scale; n.y = (my - G.h / 2 - G.oy) / G.scale; n.vx = n.vy = 0; GPOS.set(n.id, { x: n.x, y: n.y }); dibujarGrafo(); }
    };
    c.onpointerup = () => { G.drag = null; correrSim(); };
    c.onwheel = (e) => {
      e.preventDefault();
      const f = e.deltaY < 0 ? 1.1 : 0.9;
      G.scale = Math.max(0.2, Math.min(4, G.scale * f));
      dibujarGrafo();
    };
  }

  function detalle(m) {
    const d = $("graph-detail");
    d.classList.remove("hidden");
    d.innerHTML = `<div class="head"><span class="id">#${m.id}</span>`
      + `<span class="badge">${esc(m.kind)}</span>`
      + `<span class="ns" style="color:${nsColor(m.namespace)}">⟨${esc(m.namespace)}⟩</span></div>`
      + `<div class="text">${esc(m.text)}</div>`
      + `<div class="actions">`
      + `<button data-act="muse">${L.detMuse}</button>`
      + (m.dormant ? `<button data-act="wake">${L.detWake}</button>` : `<button data-act="forget">${L.detForget}</button>`)
      + `<button data-act="purge">${L.detPurge}</button></div>`;
    d.querySelectorAll("button[data-act]").forEach((b) => b.onclick = () => accion(b.dataset.act, m));
  }

  // ==========================================================================
  // TIEMPO
  // ==========================================================================
  function renderTimeline(items) {
    const c = $("view-timeline");
    const orden = [...items].sort((a, b) => (b.last_access || 0) - (a.last_access || 0));
    c.innerHTML = orden.map((m) => {
      const s = Math.max(0, Math.min(1, m.strength || 0));
      const col = nsColor(m.namespace);
      const flag = m.dormant ? L.tlLatente : (prontoLatente(m) ? L.tlPronto : "");
      return `<div class="tl">`
        + `<span class="tl-date">${fecha(m.last_access)}</span>`
        + `<span class="tl-bar"><span class="tl-fill" style="width:${(s * 100).toFixed(0)}%;background:${col}"></span></span>`
        + `<span class="tl-txt">#${m.id} ${esc((m.text || "").slice(0, 70))}</span>`
        + `<span class="tl-flag">${flag}</span></div>`;
    }).join("") || "";
  }

  // ==========================================================================
  // EJES (scatter importancia × fiabilidad)
  // ==========================================================================
  let AX = null;
  function renderAxes(items) {
    const canvas = $("axes-canvas");
    ajustarCanvasSimple(canvas);
    const ctx = canvas.getContext("2d");
    const r = canvas.getBoundingClientRect();
    const pad = 40, W = r.width, H = r.height;
    ctx.clearRect(0, 0, W, H);
    const px = (v) => pad + v * (W - pad * 1.5);
    const py = (v) => (H - pad) - v * (H - pad * 1.5);
    // ejes
    ctx.strokeStyle = "rgba(140,140,140,.5)"; ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(pad, H - pad); ctx.lineTo(W - pad / 2, H - pad);
    ctx.moveTo(pad, H - pad); ctx.lineTo(pad, pad / 2); ctx.stroke();
    ctx.fillStyle = getVar("--vscode-descriptionForeground"); ctx.font = "11px sans-serif";
    ctx.fillText(L.axImportancia, W - 110, H - pad + 16);
    ctx.save(); ctx.translate(14, pad + 60); ctx.rotate(-Math.PI / 2);
    ctx.fillText(L.axFiabilidad, 0, 0); ctx.restore();
    // guía diagonal (importante pero poco fiable = arriba-izq / abajo-der)
    AX = { canvas, pts: [] };
    for (const m of items) {
      const x = px(m.importance || 0), y = py(m.confidence || 0);
      const rad = 3 + (m.strength || 0) * 6;
      ctx.beginPath(); ctx.arc(x, y, rad, 0, Math.PI * 2);
      ctx.fillStyle = nsColor(m.namespace);
      ctx.globalAlpha = m.dormant ? 0.35 : 0.85; ctx.fill(); ctx.globalAlpha = 1;
      AX.pts.push({ x, y, r: rad + 3, m });
    }
    canvas.onpointermove = (e) => {
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const hit = AX.pts.find((p) => (mx - p.x) ** 2 + (my - p.y) ** 2 <= p.r * p.r);
      const tip = $("axes-tip");
      if (hit) {
        tip.classList.remove("hidden");
        tip.style.left = Math.min(mx + 12, rect.width - 300) + "px";
        tip.style.top = (my + 12) + "px";
        tip.innerHTML = `#${hit.m.id} <b>${esc(hit.m.namespace)}</b><br>${esc((hit.m.text || "").slice(0, 160))}`
          + `<br><small>${L.mImp} ${(hit.m.importance || 0).toFixed(2)} · ${L.mFiab} ${(hit.m.confidence || 0).toFixed(2)} · ${L.mFuerza} ${(hit.m.strength || 0).toFixed(2)}</small>`;
      } else tip.classList.add("hidden");
    };
    canvas.onpointerleave = () => $("axes-tip").classList.add("hidden");
  }

  function ajustarCanvasSimple(c) {
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.max(1, r.width * dpr); c.height = Math.max(1, r.height * dpr);
    c.getContext("2d").setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // ==========================================================================
  // ESTADO (salud: CLI, BD, servidor MCP, registro)
  // ==========================================================================
  function bytes(n) {
    if (n == null) return L.guion;
    if (n < 1024) return n + " B";
    if (n < 1048576) return (n / 1024).toFixed(0) + " KB";
    return (n / 1048576).toFixed(1) + " MB";
  }
  const semaforo = (ok) => `<span class="sem ${ok ? "ok" : "no"}">${ok ? "●" : "○"}</span>`;

  function renderStatus(s) {
    const c = $("view-status");
    if (!s) { c.innerHTML = `<p class="hint">${L.consultandoEstado}</p>`; return; }
    const db = s.db || {}, mcp = s.mcp || {}, log = s.log || {}, st = s.stats || {};
    const schemaOk = db.schema === db.schema_expected;
    const fila = (label, val, ok) =>
      `<div class="strow">${ok === undefined ? "" : semaforo(ok)}`
      + `<span class="slabel">${label}</span><span class="sval">${val}</span></div>`;
    c.innerHTML =
      `<div class="scard"><h3>${L.hCLI}</h3>`
      + fila(L.sVersion, esc(s.version || "?"), true)
      + fila(L.sPython, esc(s.python || "?"))
      + fila(L.sMemoria, s.paused ? L.sEnPausa : L.sActiva, !s.paused)
      + `</div>`
      + `<div class="scard"><h3>${L.hBD}</h3>`
      + fila(L.sEstado, db.healthy ? L.sSana : L.sConProblemas, !!db.healthy)
      + fila(L.sIntegridad, esc(db.integrity || "?"), db.integrity === "ok")
      + fila(L.sEsquema, L.sEsperada(db.schema, db.schema_expected), schemaOk)
      + fila(L.sEscribible, db.writable ? L.sSi : L.sNo, !!db.writable)
      + fila(L.sTamano, bytes(db.size))
      + fila(L.sRuta, `<code>${esc(db.path || "?")}</code>`)
      + `<div class="strow"><button class="sbtn" data-cmd="backup" title="${L.backupHint}">💾 ${L.backup}</button></div>`
      + `</div>`
      + `<div class="scard"><h3>${L.hMemoria}</h3>`
      + fila(L.sTotal, L.sRecuerdos(st.total ?? "?"))
      + fila(L.sEpisodicos, st.episodicos_activos ?? L.guion)
      + fila(L.sSemanticos, st.semanticos ?? L.guion)
      + fila(L.sLatentes, st.latentes ?? L.guion)
      + fila(L.sArchivados, st.archivados ?? L.guion)
      + (st.por_contexto ? Object.entries(st.por_contexto).sort((a, b) => b[1] - a[1])
          .map(([ns, n]) => fila(`· ${esc(ns)}`,
            `<span style="color:${nsColor(ns)}">${n}</span>`)).join("") : "")
      + (st.tokens ? fila(L.sTokensTurno, st.tokens.presupuesto_por_turno ?? L.guion) : "")
      + `</div>`
      + `<div class="scard"><h3>${L.hMCP}</h3>`
      + fila(L.sEnMarcha, mcp.running ? L.sMcpSi(mcp.running) : L.sMcpNo, mcp.running > 0)
      + ((mcp.servers || []).map((p) => {
          const fichero = (p.db || "").split(/[\\/]/).pop();
          const ctx = p.namespace ? `${L.sMcpCtx}: ${esc(p.namespace)}` : "";
          const quien = ctx
            ? ctx + (fichero ? ` · ${esc(fichero)}` : "")
            : (fichero ? `${L.sMcpDb}: ${esc(fichero)}` : L.sMcpDesconocida);
          const cerrar = `<button class="sbtn kill" data-cmd="kill" data-pid="${p.pid}" `
            + `title="${L.matarServidor}">✕</button>`;
          return fila(`· ${quien}`,
            `${L.sDesde(p.arranque ? fecha(p.arranque) : "?")} · pid ${p.pid} ${cerrar}`);
        }).join(""))
      + `</div>`
      + `<div class="scard"><h3>${L.hRegistro}</h3>`
      + fila(L.sActivo, log.enabled ? L.sSi : L.sLogNo, !!log.enabled)
      + (log.last_activity ? fila(L.sUltima, fecha(log.last_activity)) : "")
      + (log.path ? fila(L.sRuta, `<code>${esc(log.path)}</code>`) : "")
      + (log.path ? `<div class="strow"><button class="sbtn" data-cmd="open-log" data-path="${esc(log.path)}">📄 ${L.abrirLog}</button></div>` : "")
      + `</div>`
      + `<p class="hint">${L.estadoHint} `
      + `<button class="sbtn" data-cmd="refresh-status">↻ ${L.refrescar}</button></p>`;
    c.querySelectorAll("button[data-cmd]").forEach((b) => {
      b.onclick = () => {
        if (b.dataset.cmd === "backup") vscode.postMessage({ type: "backup" });
        else if (b.dataset.cmd === "open-log")
          vscode.postMessage({ type: "open-log", path: b.dataset.path || "" });
        else if (b.dataset.cmd === "refresh-status") {
          renderStatus(null);                 // "consultando…"
          vscode.postMessage({ type: "status-request" });
        }
        else if (b.dataset.cmd === "kill")
          vscode.postMessage({ type: "kill-server", pid: Number(b.dataset.pid) });
      };
    });
  }

  // ==========================================================================
  // TOKENS (la factura de la casa, hecha visible)
  // ==========================================================================
  function renderTokens(d) {
    const c = $("view-tokens");
    if (!d) { c.innerHTML = `<p class="hint">${L.calculandoFactura}</p>`; return; }
    const s = d.summary || {}, serie = d.series || [];
    const media = s.media_por_inyeccion || 0, presup = s.presupuesto_hook || 350;
    const usoPct = Math.min(100, Math.round((media / presup) * 100));
    const maxTok = Math.max(1, ...serie.map((x) => x.tok));
    // mini-gráfico: últimas ~48 inyecciones como barras
    const barras = serie.slice(-48).map((x) => {
      const h = Math.round((x.tok / maxTok) * 100);
      const over = x.tok > presup;
      return `<span class="tbar" style="height:${Math.max(3, h)}%;`
        + `background:${over ? "var(--sem-no,#e06c75)" : "var(--vscode-textLink-foreground)"}" `
        + `title="${x.ts} · ${x.tok} tok (${esc(x.etiqueta || "")})"></span>`;
    }).join("");
    c.innerHTML =
      `<div class="hero">`
      + `<div class="hnum"><span class="hbig">${s.total ?? 0}</span><span class="hlbl">${L.tGastados}</span></div>`
      + `<div class="hnum good"><span class="hbig">${s.ahorrado_por_presupuesto ?? 0}</span><span class="hlbl">${L.tAhorrados}</span></div>`
      + `<div class="hnum"><span class="hbig">${s.inyecciones ?? 0}</span><span class="hlbl">${L.tInyecciones}</span></div>`
      + `<div class="hnum"><span class="hbig">${s.hoy ?? 0}</span><span class="hlbl">${L.tHoy}</span></div>`
      + `</div>`
      + `<div class="scard"><h3>${L.tMediaVs}</h3>`
      + `<div class="gauge"><span class="gfill" style="width:${usoPct}%"></span>`
      + `<span class="gmark" title="${L.tPresupHook} ${presup}"></span></div>`
      + `<div class="strow"><span class="slabel">${L.tMedia}</span><span class="sval">${media} ${L.tTok}</span></div>`
      + `<div class="strow"><span class="slabel">${L.tPresupHook}</span><span class="sval">`
      + `<button class="sbtn" data-budget="-50" title="−50">−</button> `
      + `<b>${presup}</b> ${L.tTokTurno} `
      + `<button class="sbtn" data-budget="50" title="+50">+</button> `
      + `<button class="sbtn" data-budget="reset">${L.tReset}</button></span></div>`
      + `<div class="strow"><span class="slabel">${L.tPresupId}</span><span class="sval">${s.presupuesto_identidad ?? L.guion} ${L.tTok}</span></div>`
      + `</div>`
      + (serie.length
          ? `<div class="scard"><h3>${L.tHistoria(serie.length)}</h3>`
            + `<div class="chart">${barras}</div></div>`
          : "")
      + `<p class="hint">${L.tEstimacion(esc(s.metodo || ""))}</p>`;
    c.querySelectorAll("button[data-budget]").forEach((b) => {
      b.onclick = () => {
        const op = b.dataset.budget;
        if (op === "reset") vscode.postMessage({ type: "set-budget", reset: true });
        else vscode.postMessage({ type: "set-budget", value: Math.max(0, presup + Number(op)) });
      };
    });
  }

  // ==========================================================================
  // REGISTRO (el log de decisiones, en vivo y coloreado)
  // ==========================================================================
  const LOG_COL = {
    recall: "#4aa3df", remember: "#7ec36b", update: "#7ec36b", sleep: "#c48ae0",
    dream: "#d08770", forget: "#e0a33f", purge: "#e06c75", unlearn: "#e06c75",
    tokens: "#56b6c2", assist: "#8a8a8a", learn: "#7ec36b", ERROR: "#e06c75",
  };
  function renderLog(d) {
    const c = $("view-log");
    if (!d) { c.innerHTML = `<p class="hint">${L.leyendoRegistro}</p>`; return; }
    const ent = (d.entries || []).slice().reverse();   // más reciente arriba
    if (!ent.length) {
      c.innerHTML = `<p class="hint">${L.registroVacio}</p>`;
      return;
    }
    c.innerHTML = ent.map((e) => {
      const col = LOG_COL[e.accion] || "var(--vscode-descriptionForeground)";
      const hora = (e.ts || "").slice(11);
      return `<div class="lrow"><span class="ltime">${esc(hora)}</span>`
        + `<span class="lact" style="color:${col};border-color:${col}">${esc(e.accion || "?")}</span>`
        + `<span class="lmsg">${esc(e.mensaje || "")}</span></div>`;
    }).join("");
  }

  // ==========================================================================
  // IDEAS (puentes que propone el sueño: hipótesis, no evidencia)
  // ==========================================================================
  function renderIdeas(d) {
    const c = $("view-ideas");
    if (!d) { c.innerHTML = `<p class="hint">${L.ideasCargando}</p>`; return; }
    const br = d.bridges || [];
    if (!br.length) { c.innerHTML = `<p class="hint">${L.ideasVacio}</p>`; return; }
    const corta = (s) => esc((s || "").slice(0, 70));
    c.innerHTML = `<p class="hint">${L.ideasIntro}</p>` + br.map((b) =>
      `<div class="idea">`
      + `<div class="idea-h">💡 ${esc(L.ideasHipotesis(corta(b.a), corta(b.b), corta(b.via)))}</div>`
      + `<div class="idea-pair">`
      + `<span class="idea-node">#${b.a_id} ${esc(b.a || "")}</span>`
      + `<span class="idea-node">#${b.b_id} ${esc(b.b || "")}</span></div>`
      + `<div class="idea-via"><small>${L.ideasVia}: «${esc(b.via || "")}» · `
      + `${L.ideasSim} ${(+b.similarity || 0).toFixed(2)}</small></div>`
      + `</div>`).join("");
  }

  // ==========================================================================
  // pestañas, búsqueda, mensajes
  // ==========================================================================
  const PIDE = {
    status: () => vscode.postMessage({ type: "status-request" }),
    tokens: () => vscode.postMessage({ type: "tokens-request" }),
    log: () => vscode.postMessage({ type: "log-request" }),
    ideas: () => vscode.postMessage({ type: "ideas-request" }),
  };
  const PLACEHOLDER_VACIO = { status: renderStatus, tokens: renderTokens, log: renderLog,
    ideas: renderIdeas };

  function activarVista(v) {
    VIEW = v;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
    document.querySelectorAll(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
    if (PIDE[v]) {
      $("empty").classList.add("hidden");
      PLACEHOLDER_VACIO[v](null);   // "cargando…"
      PIDE[v]();
    } else repintar();
  }

  const PLACEHOLDER = {
    text: L.filtrar,
    recall: L.phRecall,
    muse: L.phMuse,
  };

  function actualizarModo(foco) {
    const m = $("mode").value;
    $("q").placeholder = PLACEHOLDER[m] || PLACEHOLDER.text;
    if (foco) $("q").focus();
  }

  function lanzarBusquedaAgente() {
    const q = $("q").value.trim();
    if (!q) { HITS = null; repintar(); return; }   // sin semilla: repintar avisa
    $("scope").textContent = L.buscandoCon($("mode").value);
    vscode.postMessage({ type: "search", query: q, mode: $("mode").value });
  }

  window.addEventListener("message", (ev) => {
    const msg = ev.data;
    if (msg.type === "data") {
      MEM = msg.memories || []; EDGES = msg.edges || []; SCOPE = msg.scope || "";
      HITS = null; ACTIVE = null;
      PAUSED = !!msg.paused; pintarPausa();
      const w = $("weave"); if (w) w.disabled = false;   // re-activar tras tejer
      pintarChips();
      if (PIDE[VIEW]) PIDE[VIEW]();   // estado/tokens/registro se re-piden en cada refresco
      else repintar();
    } else if (msg.type === "search-result") {
      HITS = msg.memories || [];
      repintar();
    } else if (msg.type === "status") {
      renderStatus(msg.data);
    } else if (msg.type === "tokens") {
      renderTokens(msg.data);
    } else if (msg.type === "log") {
      renderLog(msg.data);
    } else if (msg.type === "ideas") {
      renderIdeas(msg.data);
    } else if (msg.type === "error") {
      $("error").classList.remove("hidden");
      $("error").textContent = L.errorLeer + msg.message;
    }
  });

  // eventos de UI
  document.querySelectorAll(".tab").forEach((t) => t.onclick = () => activarVista(t.dataset.view));
  $("q").addEventListener("input", () => {
    if ($("mode").value === "text") repintar();   // filtro instantáneo en cliente
  });
  $("q").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && $("mode").value !== "text") lanzarBusquedaAgente();
  });
  $("mode").addEventListener("change", () => {
    HITS = null;
    actualizarModo(true);   // cambia el placeholder y enfoca la caja
    if ($("mode").value === "text") repintar(); else lanzarBusquedaAgente();
  });
  $("refresh").onclick = () => { $("q").value = ""; HITS = null; vscode.postMessage({ type: "refresh" }); };
  $("all").addEventListener("change", () => {
    const todos = [...new Set(MEM.map((m) => m.namespace))].sort();
    // Marcar = ver todos; desmarcar = aislar UNO (nunca dejar la pantalla vacía).
    ACTIVE = ($("all").checked || !todos.length) ? null : new Set([todos[0]]);
    pintarChips(); repintar();
  });
  $("pause").addEventListener("click", () =>
    vscode.postMessage({ type: "setPaused", value: !PAUSED }));
  $("issue").addEventListener("click", () =>
    vscode.postMessage({ type: "open-external",
      url: "https://github.com/armandojaleo/hipercampo/issues/new" }));
  $("weave").addEventListener("click", () => {
    $("weave").disabled = true;
    vscode.postMessage({ type: "reindex" });
  });

  function pintarPausa() {
    $("paused-banner").classList.toggle("hidden", !PAUSED);
    const b = $("pause");
    b.textContent = PAUSED ? "▶️" : "⏸";
    b.title = PAUSED ? L.reanudar : L.pausar;
    b.classList.toggle("on", PAUSED);
  }

  window.addEventListener("resize", () => {
    if (VIEW === "graph" && G) { ajustarCanvas(G.canvas); dibujarGrafo(); }
    else if (VIEW === "axes") repintar();
  });

  aplicarIdioma();
  $("all").checked = true;
  vscode.postMessage({ type: "ready" });
}());
