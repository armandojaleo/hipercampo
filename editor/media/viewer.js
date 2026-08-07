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
      filtrarTipo: "Filtrar por tipo", ordenar: "Ordenar",
      tipoTodos: "todos los tipos", ordReciente: "reciente", ordImp: "importancia",
      ordUsos: "usos", ordFuerza: "fuerza",
      vecindario: "vecindario", vecindarioTit: "Mostrar solo el nodo elegido y sus vecinos a N saltos (más legible que todo el grafo)",
      saltos: (n) => `${n} salto${n > 1 ? "s" : ""}`, elegirNodo: "Elige un nodo para ver su vecindario",
      optText: "texto", optRecall: "recall (agente)", optRecallAuto: "recall auto", optRecallNav: "recall nav", optMuse: "muse (eureka)",
      pausar: "Pausar la memoria (modo 'no recordar')", reanudar: "Reanudar la memoria",
      refrescar: "Refrescar", cambiarBD: "Cambiar base de datos", todosContextos: "todos los contextos",
      banner: "⏸ Memoria <b>en pausa</b>: no se graban recuerdos nuevos ni se refuerzan (leer sí funciona).",
      tabs: { list: "Lista", graph: "Mapa", timeline: "Tiempo", axes: "Ejes",
        ideas: "Ideas", facts: "Hechos", tokens: "Tokens", log: "Registro", status: "Estado" },
      factsCargando: "Leyendo los hechos…",
      factsVacio: "Sin hechos estructurados. Se crean con hc_remember_fact (SUJETO⊗PREDICADO⊗OBJETO): el diferenciador VSA, consultable por rol.",
      factsIntro: "Hechos estructurados por ROL (sujeto·predicado·objeto·tiempo·fuente), con validez temporal: un hecho nuevo cierra la verdad anterior sin borrarla.",
      factsCerrado: "cerrado",
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
      nodosVisitados: (n) => `${n} nodos visitados`,
      actMuse: "Conexiones (muse)", actWake: "Despertar", actMove: "Mover a otro contexto",
      actForget: "Olvidar (reversible)", actPurge: "Borrar del todo (irreversible)",
      leyAsociacion: "asociación", leyPuente: "puente onírico", leyAtomo: "átomo → fuente",
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
      tokRecall: (n) => `~${n} tok`,
      tokRecallTit: "Estimación de los tokens de este resultado (lo que cruzaría al agente por MCP). Siempre es aproximada.",
      errorLeer: "No se pudo leer la memoria:\n\n",
      issueTitle: "Reportar un problema (GitHub)",
      tejer: "Tejer el grafo de vecinos (densifica el mapa)",
      abrirLog: "Abrir el fichero de registro",
      backup: "Copia de seguridad",
      backupHint: "Crea una copia consistente del .db",
      sMcpDb: "memoria", sMcpCtx: "contexto",
      reiniciarActualizar: "Sirve código VIEJO — reiniciar para actualizar",
      sMcpViejo: (v) => `⚠ código viejo (${v || "?"})`,
      sMcpViejoAviso: "Este servidor arrancó antes de la última actualización de "
        + "hipercampo: sigue sirviendo el código anterior. Reinícialo (↻) para "
        + "que cargue lo nuevo; el cliente lo relanza al usarlo.",
      sMcpDesconocida: "(no legible en este sistema)",
      ideasCargando: "Buscando ideas (puentes entre recuerdos)…",
      ideasVacio: "Sin ideas nuevas por ahora. El sueño propone puentes cuando dos recuerdos comparten un asociado común pero no están conectados; con poca memoria aún no hay qué cruzar.",
      ideasIntro: "Conexiones que la memoria descubrió SOLA entre recuerdos lejanos: dos notas que no guardaste juntas pero que comparten un 'puente' común. Son pistas para ideas nuevas (💡), no verdades — no se graban. En cada una: los dos recuerdos y el puente que los enlaza.",
      ideasVia: "ambos evocan",
      ideasHipotesis: (a, b, via) => `«${a}» y «${b}» quizá se relacionan`,
      ideasSim: "afinidad",
      ideasDiag: "Diagnóstico",
      ideasRazones: { too_few_memories: "pocos recuerdos", no_links: "sin enlaces", graph_too_closed: "grafo demasiado cerrado", candidates_below_quality: "candidatos descartados por calidad", ok: "hay candidatos" },
    },
    en: {
      filtrar: "Filter by text…", comoBuscar: "How to search",
      filtrarTipo: "Filter by type", ordenar: "Sort",
      tipoTodos: "all types", ordReciente: "recent", ordImp: "importance",
      ordUsos: "uses", ordFuerza: "strength",
      vecindario: "neighborhood", vecindarioTit: "Show only the chosen node and its neighbors N hops away (more legible than the whole graph)",
      saltos: (n) => `${n} hop${n > 1 ? "s" : ""}`, elegirNodo: "Pick a node to see its neighborhood",
      optText: "text", optRecall: "recall (agent)", optRecallAuto: "recall auto", optRecallNav: "recall nav", optMuse: "muse (eureka)",
      pausar: "Pause the memory ('don't remember' mode)", reanudar: "Resume the memory",
      refrescar: "Refresh", cambiarBD: "Change database", todosContextos: "all contexts",
      banner: "⏸ Memory <b>paused</b>: no new memories are written or reinforced (reading still works).",
      tabs: { list: "List", graph: "Map", timeline: "Timeline", axes: "Axes",
        ideas: "Ideas", facts: "Facts", tokens: "Tokens", log: "Log", status: "Status" },
      factsCargando: "Reading facts…",
      factsVacio: "No structured facts yet. Created with hc_remember_fact (SUBJECT⊗PREDICATE⊗OBJECT): the VSA differentiator, queryable by role.",
      factsIntro: "Facts structured by ROLE (subject·predicate·object·time·source), with temporal validity: a new fact closes the previous truth without deleting it.",
      factsCerrado: "closed",
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
      nodosVisitados: (n) => `${n} nodes visited`,
      actMuse: "Connections (muse)", actWake: "Wake", actMove: "Move to another context",
      actForget: "Forget (reversible)", actPurge: "Delete for good (irreversible)",
      leyAsociacion: "association", leyPuente: "dream bridge", leyAtomo: "atom → source",
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
      tokRecall: (n) => `~${n} tok`,
      tokRecallTit: "Estimated tokens for this result (what would cross to the agent over MCP). Always approximate.",
      errorLeer: "Couldn't read the memory:\n\n",
      issueTitle: "Report a problem (GitHub)",
      tejer: "Weave the neighbor graph (densifies the map)",
      abrirLog: "Open the log file",
      backup: "Backup",
      backupHint: "Make a consistent copy of the .db",
      sMcpDb: "memory", sMcpCtx: "context",
      reiniciarActualizar: "Running OLD code — restart to update",
      sMcpViejo: (v) => `⚠ old code (${v || "?"})`,
      sMcpViejoAviso: "This server started before hipercampo's last update: it's still "
        + "serving the old code. Restart it (↻) to load the new one; the client "
        + "relaunches it on use.",
      sMcpDesconocida: "(not readable on this system)",
      ideasCargando: "Looking for ideas (bridges between memories)…",
      ideasVacio: "No new ideas yet. Dreaming proposes bridges when two memories share a common associate but aren't connected; with little memory there's nothing to cross yet.",
      ideasIntro: "Hypotheses the memory suggests — connections you didn't know yet. They're proposals, not truths: nothing has been saved.",
      ideasVia: "both evoke",
      ideasHipotesis: (a, b, via) => `“${a}” and “${b}” might be related`,
      ideasSim: "affinity",
      ideasDiag: "Diagnostic",
      ideasRazones: { too_few_memories: "too few memories", no_links: "no links", graph_too_closed: "graph too closed", candidates_below_quality: "candidates below quality", ok: "has candidates" },
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
  let NBHD = false;      // Mapa: modo vecindario (solo el nodo elegido + N saltos)
  let HOPS = 2;          // saltos del vecindario
  let MAPFOCO = null;    // id del nodo centro del vecindario

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

  // Color por ESTADO COGNITIVO del recuerdo (el diferenciador: Obsidian colorea por
  // carpeta; aquí el color cuenta la VIDA de la memoria). Prioridad: dormido/reemplazado
  // mandan sobre el tipo; el átomo (fragmento de un documento) va en verde como su arista.
  const EST_COL = {
    episodic: "#5cc8e8",     // cian — hipocampo, fresco
    semantic: "#d9a648",     // oro — córtex, conocimiento consolidado
    atom: "#78be8c",         // verde — fragmento → fuente (igual que la arista átomo)
    superseded: "#c98a8a",   // rojo apagado — verdad cerrada
    dormant: "#7a7f8a",      // gris — latente
  };
  const EST_LBL = {
    es: { episodic: "episódico", semantic: "semántico", atom: "átomo",
      superseded: "reemplazado", dormant: "latente" },
    en: { episodic: "episodic", semantic: "semantic", atom: "atom",
      superseded: "superseded", dormant: "dormant" },
  };
  function estadoNodo(m, atomSet) {
    if (m.dormant) return "dormant";
    if (m.superseded) return "superseded";
    if (atomSet && atomSet.has(m.id)) return "atom";
    if (m.kind === "semantic" || m.consolidated) return "semantic";
    return "episodic";
  }

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

  // átomos = destino de una arista type='atom'. Se calcula una vez por filtro/pintado.
  function atomSetGlobal() {
    const s = new Set();
    for (const e of EDGES) if (e.type === "atom") s.add(e.dst);
    return s;
  }

  // Memorias visibles: chips de namespace + filtro por tipo (estado cognitivo) +
  // (si modo texto) texto. El tipo usa la MISMA clasificación que el color del Mapa.
  function visibles() {
    let base = HITS !== null ? HITS : MEM;
    if (ACTIVE) base = base.filter((m) => ACTIVE.has(m.namespace));
    const kind = ($("kind") && $("kind").value) || "";
    if (kind) {
      const atomSet = atomSetGlobal();
      base = base.filter((m) => estadoNodo(m, atomSet) === kind);
    }
    const q = norm($("q").value.trim());
    if (q && $("mode").value === "text") {
      base = base.filter((m) => norm(m.text).includes(q)
        || norm(m.namespace).includes(q) || norm(m.kind).includes(q));
    }
    return base;
  }

  // Orden de la LISTA (client-side). En resultados de recall NO se reordena: el orden
  // es la relevancia que decidió el motor, y pisarla engañaría sobre qué priorizó.
  const ORDEN = {
    recent: (a, b) => (b.last_access || 0) - (a.last_access || 0),
    importance: (a, b) => (b.importance || 0) - (a.importance || 0),
    uses: (a, b) => (b.access_count || 0) - (a.access_count || 0),
    strength: (a, b) => (b.strength || 0) - (a.strength || 0),
  };

  // --- etiquetas estáticas: se aplican según el idioma al arrancar ----------
  function aplicarIdioma() {
    $("q").placeholder = L.filtrar;
    $("mode").title = L.comoBuscar;
    const opts = $("mode").options;
    opts[0].textContent = L.optText;
    opts[1].textContent = L.optRecall;
    opts[2].textContent = L.optRecallAuto;
    opts[3].textContent = L.optRecallNav;
    opts[4].textContent = L.optMuse;
    const ksel = $("kind");
    if (ksel) {
      ksel.title = L.filtrarTipo;
      const klbl = EST_LBL[lang];
      ksel.options[0].textContent = L.tipoTodos;
      for (const o of ksel.options) if (o.value && klbl[o.value]) o.textContent = klbl[o.value];
    }
    const ssel = $("sort");
    if (ssel) {
      ssel.title = L.ordenar;
      const st = { recent: L.ordReciente, importance: L.ordImp, uses: L.ordUsos, strength: L.ordFuerza };
      for (const o of ssel.options) if (st[o.value]) o.textContent = st[o.value];
    }
    const nl = $("nbhd-label"); if (nl) nl.textContent = L.vecindario;
    const nb = $("nbhd"); if (nb) nb.parentElement.title = L.vecindarioTit;
    const hp = $("hops");
    if (hp) for (const o of hp.options) o.textContent = L.saltos(Number(o.value));
    $("refresh").title = L.refrescar;
    $("choose-db").title = L.cambiarBD;
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
    const sc = $("scope");
    if (HITS !== null) {
      // Coste del payload que cruzaría al agente por MCP. Estimación honesta (~4 char/tok),
      // etiquetada como aproximada: el tokenizador exacto de Claude no es público.
      const tok = Math.max(0, Math.round(JSON.stringify(HITS).length / 4));
      sc.textContent = `${$("mode").value} · ${SCOPE}`;
      sc.title = "";
      const tk = document.createElement("span");
      tk.className = "toktag"; tk.textContent = " · " + L.tokRecall(tok); tk.title = L.tokRecallTit;
      sc.appendChild(tk);
    } else {
      sc.textContent = SCOPE; sc.title = "";
    }
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
    const comp = m.score_components || {};
    const compTitle = Object.keys(comp).length
      ? Object.entries(comp).map(([k, v]) => `${k}: ${(+v).toFixed(2)}`).join(" · ")
      : L.relevancia;
    const score = (m.score != null)
      ? `<span class="badge" title="${esc(compTitle)}">score ${(+m.score).toFixed(2)}</span>` : "";
    const route = (m.recall_mode && Number.isInteger(m.visited))
      ? `<span class="badge" title="${esc(L.nodosVisitados(m.visited))}">`
        + `${esc(m.recall_mode)} · ${m.visited}</span>`
      : "";
    const metrics = [metric(L.mImp, m.importance), metric(L.mFiab, m.confidence),
      metric(L.mFuerza, m.strength),
      (m.access_count != null ? `<span>${L.mUsos} <b>${m.access_count}</b></span>` : ""),
      (m.last_access != null ? `<span>${L.mVisto} <b>${fecha(m.last_access)}</b></span>` : "")]
      .filter(Boolean).join("");
    el.innerHTML =
      `<div class="head"><span class="id">#${m.id}</span>`
      + `<span class="badge">${esc(m.kind || "?")}</span>${ns}${score}${route}`
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
    // Al NAVEGAR (no en resultados de recall), ocultar los átomos: un trozo suelto
    // ("', consultable por rol.") no es un recuerdo. Se muestra la FUENTE coherente; el
    // átomo sigue existiendo para el recall preciso y se ve en el Mapa (enlace verde).
    // Y se aplica el ORDEN elegido (la relevancia del recall no se toca).
    if (HITS === null) {
      const hijos = atomSetGlobal();
      if (hijos.size) items = items.filter((m) => !hijos.has(m.id));
      const cmp = ORDEN[($("sort") && $("sort").value) || "recent"];
      if (cmp) items = [...items].sort(cmp);
    }
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

  // átomos = destino de una arista type='atom' (src=fuente, dst=átomo). Se colorean aparte.
  const atomosDe = (aristas) => new Set(aristas.filter((e) => e.type === "atom").map((e) => e.dst));

  // Vecindario a N saltos de un nodo (BFS sobre las aristas visibles, en ambos sentidos).
  // Es la clave de legibilidad: con 222 nodos, ver solo un barrio se lee; el todo no.
  function vecindarioIds(focoId, items, hops) {
    const idset = new Set(items.map((m) => m.id));
    if (!idset.has(focoId)) return idset;   // el foco ya no está: no filtrar
    const ady = new Map();
    const une = (a, b) => { if (!ady.has(a)) ady.set(a, []); ady.get(a).push(b); };
    for (const e of EDGES) {
      if (!idset.has(e.src) || !idset.has(e.dst)) continue;
      une(e.src, e.dst); une(e.dst, e.src);
    }
    const vistos = new Set([focoId]);
    let frente = [focoId];
    for (let h = 0; h < hops; h++) {
      const sig = [];
      for (const id of frente) for (const v of (ady.get(id) || [])) {
        if (!vistos.has(v)) { vistos.add(v); sig.push(v); }
      }
      frente = sig;
    }
    return vistos;
  }

  // Nodo con más conexiones (para arrancar el vecindario sin que el usuario elija).
  function nodoHub(items) {
    const grado = new Map();
    const idset = new Set(items.map((m) => m.id));
    for (const e of EDGES) {
      if (!idset.has(e.src) || !idset.has(e.dst)) continue;
      grado.set(e.src, (grado.get(e.src) || 0) + 1);
      grado.set(e.dst, (grado.get(e.dst) || 0) + 1);
    }
    let mejor = null, max = -1;
    for (const [id, g] of grado) if (g > max) { max = g; mejor = id; }
    return mejor != null ? mejor : (items[0] && items[0].id);
  }

  function renderGraph(items) {
    const canvas = $("graph-canvas");
    // MODO VECINDARIO: reduce a un barrio legible en vez de la maraña completa.
    if (NBHD) {
      if (MAPFOCO == null || !items.some((m) => m.id === MAPFOCO)) MAPFOCO = nodoHub(items);
      if (MAPFOCO != null) {
        const barrio = vecindarioIds(MAPFOCO, items, HOPS);
        items = items.filter((m) => barrio.has(m.id));
      }
    }
    const vis = new Set(items.map((m) => m.id));
    const aristas = EDGES.filter((e) => vis.has(e.src) && vis.has(e.dst));
    const sig = firmaNodos(items);

    // MISMO conjunto de nodos (caso típico del auto-refresh): NO resembrar ni
    // resimular —eso es lo que hacía saltar el mapa—; solo refrescar datos y redibujar.
    if (G && G.sig === sig) {
      const byId = new Map(items.map((m) => [m.id, m]));
      for (const n of G.nodos) n.m = byId.get(n.id) || n.m;
      G.aristas = aristas; G.atomSet = atomosDe(aristas);
      leyenda(items); ajustarCanvas(canvas); dibujarGrafo();
      return;
    }

    // Conjunto NUEVO: construir sembrando desde las posiciones guardadas (los nodos
    // que ya existían se quedan donde estaban; solo los nuevos entran por el círculo).
    if (G) cancelAnimationFrame(G.raf);
    const camPrev = G ? { scale: G.scale, ox: G.ox, oy: G.oy, touched: G.camTouched } : null;
    const nodos = items.map((m) => ({ m, id: m.id }));
    const idx = new Map(nodos.map((n, i) => [n.id, i]));
    let nuevos = 0;
    const R = 180;
    nodos.forEach((n, i) => {
      const g = GPOS.get(n.id);
      if (g) { n.x = g.x; n.y = g.y; } else {
        nuevos++;
        const a = (i / Math.max(1, nodos.length)) * Math.PI * 2;
        n.x = Math.cos(a) * R; n.y = Math.sin(a) * R;
      }
      n.vx = 0; n.vy = 0;
    });
    // RECALENTAMIENTO PROPORCIONAL: si casi todo ya tenía sitio (una recarga con un par
    // de nodos nuevos), apenas se agita; solo un layout desde cero se calienta del todo.
    // Así el mapa deja de "no parar de moverse" cuando el agente escribe de fondo.
    const alpha0 = nuevos === 0 ? 0.12 : Math.min(1, 0.3 + nuevos / nodos.length);
    // Auto-encuadre la primera vez (o si el usuario nunca movió la cámara): centra el
    // grafo en vez de dejarlo amontonado en una esquina.
    const camTouched = camPrev ? camPrev.touched : false;
    G = { canvas, ctx: canvas.getContext("2d"), nodos, idx, aristas, sig,
      atomSet: atomosDe(aristas),
      scale: (camPrev && camPrev.scale) || 1, ox: (camPrev && camPrev.ox) || 0, oy: (camPrev && camPrev.oy) || 0,
      sel: null, hover: null, drag: null, alpha: alpha0, raf: 0,
      camTouched, fitPending: !camTouched };
    leyenda(items);
    ajustarCanvas(canvas);
    correrSim(alpha0);
    engancharGrafo();
  }

  function leyenda(items) {
    // Leyenda por ESTADO (el color de los nodos): solo los estados presentes, para no
    // llenar de ruido. Los namespaces siguen en los chips de arriba (son un filtro).
    const atomSet = G ? G.atomSet : new Set();
    const presentes = [...new Set(items.map((m) => estadoNodo(m, atomSet)))];
    const orden = ["episodic", "semantic", "atom", "superseded", "dormant"];
    const lbl = EST_LBL[lang];
    const l = $("graph-legend");
    l.innerHTML = orden.filter((k) => presentes.includes(k)).map((k) =>
      `<div class="k"><span class="dot" style="background:${EST_COL[k]}"></span>${esc(lbl[k])}</div>`).join("")
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-foreground);opacity:.5"></span>${L.leyAsociacion}</div>`
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-textLink-foreground);border-top-style:dashed"></span>${L.leyPuente}</div>`
      + `<div class="k"><span class="ln" style="border-color:${EST_COL.atom}"></span>${L.leyAtomo}</div>`;
  }

  function ajustarCanvas(c) {
    const r = c.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    c.width = Math.max(1, r.width * dpr); c.height = Math.max(1, r.height * dpr);
    if (G) { G.ctx.setTransform(dpr, 0, 0, dpr, 0, 0); G.w = r.width; G.h = r.height; }
  }

  function correrSim(alpha0) {
    if (!G) return;
    cancelAnimationFrame(G.raf);
    if (alpha0 != null) G.alpha = alpha0;
    const paso = () => {
      // Se detiene si no estamos en el mapa o si el panel no se ve: cero CPU en reposo.
      if (!G || VIEW !== "graph" || document.hidden) { G.raf = 0; return; }
      if (!G.drag) tick();
      G.alpha *= 0.94;   // enfría más rápido: el mapa se asienta antes y deja de vibrar
      // al ASENTARSE: encuadrar una vez (si el usuario no ha tocado la cámara) y CONGELAR.
      if (G.alpha <= 0.03 && !G.drag) {
        if (G.fitPending && !G.camTouched) { G.fitPending = false; encuadrar(); }
        else dibujarGrafo();
        G.raf = 0;                       // congelado: ni un frame más hasta que algo lo pida
        return;
      }
      dibujarGrafo();
      G.raf = requestAnimationFrame(paso);
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
        let d2 = dx * dx + dy * dy;
        if (d2 < 25) { d2 = 25; if (dx === 0 && dy === 0) { dx = Math.random() - 0.5; dy = Math.random() - 0.5; } }
        const f = Math.min(K / d2, 400);   // cap: dos nodos casi encima no generan una fuerza infinita
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        fx += (dx / d) * f; fy += (dy / d) * f;
      }
      // gravedad al centro, MÁS FUERTE cuanto más lejos: evita que los nodos poco
      // conectados salgan disparados fuera de la vista (los "puntos dispares" lejanos).
      const dist = Math.hypot(ni.x, ni.y);
      const g = 0.03 + (dist > 700 ? (dist - 700) * 0.0004 : 0);
      fx += -ni.x * g; fy += -ni.y * g;
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
      let vx = (n.vx + n.fx * a) * 0.85, vy = (n.vy + n.fy * a) * 0.85;
      if (!isFinite(vx)) vx = 0; if (!isFinite(vy)) vy = 0;   // nunca dejar que NaN contamine
      const sp = Math.hypot(vx, vy);                          // límite de velocidad: sin latigazos
      if (sp > 40) { vx *= 40 / sp; vy *= 40 / sp; }
      n.vx = vx; n.vy = vy;
      n.x += vx; n.y += vy;
      const rad = Math.hypot(n.x, n.y);                       // frontera dura: nada se escapa del lienzo
      if (rad > 1600) { n.x *= 1600 / rad; n.y *= 1600 / rad; n.vx = 0; n.vy = 0; }
      GPOS.set(n.id, { x: n.x, y: n.y });   // recordar dónde quedó, para el próximo refresco
    }
  }

  function toScreen(n) { return { x: G.w / 2 + G.ox + n.x * G.scale, y: G.h / 2 + G.oy + n.y * G.scale }; }

  const radioNodo = (n) => (4 + (n.m.importance || 0.3) * 7) * Math.max(0.6, Math.min(1.6, G.scale));

  function dibujarGrafo() {
    const { ctx, w, h } = G;
    // el NODO en foco (hover manda sobre selección) rige el resaltado de vecinos.
    const foco = G.hover || G.sel;
    ctx.clearRect(0, 0, w, h);
    // aristas
    for (const e of G.aristas) {
      const s = G.nodos[G.idx.get(e.src)], t = G.nodos[G.idx.get(e.dst)];
      if (!s || !t) continue;
      const a = toScreen(s), b = toScreen(t);
      const puente = e.status === "proposed" || e.type === "bridge" || e.type === "dream";
      const knn = e.type === "knn";   // estructura de navegación: fina y tenue
      const atomo = e.type === "atom"; // átomo -> su texto fuente: se muestra claro
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = puente ? getVar("--vscode-textLink-foreground")
        : atomo ? "rgba(120,190,140,.6)"
          : (knn ? "rgba(140,140,140,.13)" : "rgba(140,140,140,.45)");
      ctx.lineWidth = puente ? 1.2 : atomo ? 1.5 : (knn ? 0.5 : Math.min(2.5, 0.5 + (e.weight || 0.5) * 1.5));
      if (puente) ctx.setLineDash([4, 4]); else ctx.setLineDash([]);
      const resaltar = foco && (e.src === foco || e.dst === foco);
      ctx.globalAlpha = foco && !resaltar ? 0.12 : 1;
      ctx.stroke(); ctx.globalAlpha = 1;
    }
    ctx.setLineDash([]);
    // nodos — círculo con GLOW suave del color de su estado (look "constelación")
    // ETIQUETAS: solo el nodo en foco y sus vecinos directos (estilo Obsidian: el texto
    // aparece al posar el ratón, no todo a la vez —222 textos era ilegible—).
    const etiquetar = [];
    for (const n of G.nodos) {
      const p = toScreen(n);
      const r = radioNodo(n);
      const enFoco = foco && (foco === n.id || vecino(foco, n.id));
      const atenua = foco && !enFoco;
      const col = EST_COL[estadoNodo(n.m, G.atomSet)];
      ctx.globalAlpha = atenua ? 0.18 : 1;
      ctx.shadowColor = col;
      ctx.shadowBlur = (enFoco ? 16 : 7) * Math.max(0.6, Math.min(1.4, G.scale));
      ctx.beginPath(); ctx.arc(p.x, p.y, r, 0, Math.PI * 2);
      ctx.fillStyle = col;
      ctx.fill();
      ctx.shadowBlur = 0;
      if (n.id === foco) { ctx.lineWidth = 2; ctx.strokeStyle = getVar("--vscode-focusBorder"); ctx.stroke(); }
      ctx.globalAlpha = 1;
      if (enFoco) etiquetar.push({ n, p, r, principal: n.id === foco });
    }
    // etiquetas encima de todo, con halo para que se lean sobre cualquier tema
    if (etiquetar.length) {
      ctx.font = "11px " + (getVar("--vscode-font-family") || "sans-serif");
      ctx.textBaseline = "middle";
      for (const { n, p, r } of etiquetar) {
        const txt = (n.m.text || "").replace(/\s+/g, " ").trim().slice(0, 26)
          + ((n.m.text || "").length > 26 ? "…" : "");
        if (!txt) continue;
        const x = p.x + r + 4, y = p.y;
        ctx.lineWidth = 3; ctx.strokeStyle = getVar("--vscode-editor-background");
        ctx.globalAlpha = 0.9; ctx.strokeText(txt, x, y); ctx.globalAlpha = 1;
        ctx.fillStyle = getVar("--vscode-foreground");
        ctx.fillText(txt, x, y);
      }
    }
  }

  // Encuadra el GRUESO de los nodos en el lienzo (zoom-to-fit). Usa percentiles 5–95
  // en vez de min/max: así un nodo suelto y lejano no encoge todo el mapa a un punto.
  function encuadrar() {
    if (!G || !G.nodos.length) return;
    const xs = G.nodos.map((n) => n.x).filter(isFinite).sort((a, b) => a - b);
    const ys = G.nodos.map((n) => n.y).filter(isFinite).sort((a, b) => a - b);
    if (!xs.length || !ys.length) { G.scale = 1; G.ox = 0; G.oy = 0; dibujarGrafo(); return; }
    const q = (arr, p) => arr[Math.min(arr.length - 1, Math.max(0, Math.floor(p * (arr.length - 1))))];
    const minX = q(xs, 0.05), maxX = q(xs, 0.95), minY = q(ys, 0.05), maxY = q(ys, 0.95);
    const bw = Math.max(1, maxX - minX), bh = Math.max(1, maxY - minY);
    const pad = 60;
    let scale = Math.min((G.w - pad * 2) / bw, (G.h - pad * 2) / bh);
    if (!isFinite(scale) || scale <= 0) scale = 1;
    G.scale = Math.max(0.2, Math.min(2.5, scale));
    G.ox = -((minX + maxX) / 2) * G.scale;
    G.oy = -((minY + maxY) / 2) * G.scale;
    if (!isFinite(G.ox)) G.ox = 0;
    if (!isFinite(G.oy)) G.oy = 0;
    dibujarGrafo();
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
        G.sel = n.id; detalle(n.m);
        // en modo vecindario, clicar un nodo recentra el barrio en él.
        if (NBHD) { MAPFOCO = n.id; renderGraph(visibles()); return; }
        G.drag = { node: n, dx: 0, dy: 0 };
        correrSim();
      } else { G.drag = { pan: true, sx: mx - G.ox, sy: my - G.oy }; G.sel = null; $("graph-detail").classList.add("hidden"); }
      c.setPointerCapture(e.pointerId);
    };
    c.onpointermove = (e) => {
      const rect = c.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      if (G.drag) {
        if (G.drag.pan) { G.camTouched = true; G.ox = mx - G.drag.sx; G.oy = my - G.drag.sy; dibujarGrafo(); }
        else { const n = G.drag.node; n.x = (mx - G.w / 2 - G.ox) / G.scale; n.y = (my - G.h / 2 - G.oy) / G.scale; n.vx = n.vy = 0; GPOS.set(n.id, { x: n.x, y: n.y }); dibujarGrafo(); }
        return;
      }
      // HOVER (sin arrastrar): ilumina el nodo y sus vecinos, atenúa el resto.
      const n = nodoEn(mx, my);
      const id = n ? n.id : null;
      c.style.cursor = n ? "pointer" : "default";
      if (id !== G.hover) { G.hover = id; if (!G.raf || G.alpha <= 0.02) dibujarGrafo(); }
    };
    c.onpointerleave = () => { if (G.hover) { G.hover = null; dibujarGrafo(); } };
    c.onpointerup = () => { const drag = G.drag; G.drag = null; correrSim(drag && !drag.pan ? 0.15 : null); };
    c.ondblclick = (e) => {
      const rect = c.getBoundingClientRect();
      if (!nodoEn(e.clientX - rect.left, e.clientY - rect.top)) encuadrar();
    };
    c.onwheel = (e) => {
      e.preventDefault();
      G.camTouched = true;
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
    // El hueco del semáforo SIEMPRE se reserva (aunque la fila no tenga estado), para
    // que todas las etiquetas alineen en la misma columna y no queden dentadas.
    const fila = (label, val, ok) =>
      `<div class="strow"><span class="sem ${ok === undefined ? "none" : ok ? "ok" : "no"}">`
      + `${ok === undefined ? "" : ok ? "●" : "○"}</span>`
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
            + `title="${p.stale ? L.reiniciarActualizar : L.matarServidor}">`
            + `${p.stale ? "↻" : "✕"}</button>`;
          const aviso = p.stale
            ? ` <span class="sbadge-old" title="${L.sMcpViejoAviso}">${L.sMcpViejo(p.version)}</span>`
            : "";
          return fila(`· ${quien}${aviso}`,
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
    const ult = serie.slice(-48);
    const maxTok = Math.max(1, ...ult.map((x) => x.tok));
    // mini-gráfico: últimas ~48 inyecciones como barras. El valor se lee arriba al pasar
    // el ratón (data-*), porque escribirlo en cada barra sería ilegible.
    const barras = ult.map((x, i) => {
      const h = Math.round((x.tok / maxTok) * 100);
      const over = x.tok > presup;
      return `<span class="tbar" data-i="${i}" style="height:${Math.max(3, h)}%;`
        + `background:${over ? "var(--sem-no,#e06c75)" : "var(--vscode-textLink-foreground)"}"></span>`;
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
            + `<div id="tok-readout" class="tok-readout">&nbsp;</div>`
            + `<div class="chart">${barras}</div></div>`
          : "")
      + `<p class="hint">${L.tEstimacion(esc(s.metodo || ""))}</p>`;
    // Lector del valor de cada barra al pasar el ratón (delegación en el contenedor).
    const chart = c.querySelector(".chart"), ro = $("tok-readout");
    if (chart && ro) {
      chart.addEventListener("pointermove", (e) => {
        const b = e.target.closest(".tbar");
        if (!b) { ro.innerHTML = "&nbsp;"; return; }
        const x = ult[+b.dataset.i]; if (!x) return;
        ro.textContent = `${x.tok} ${L.tTok} · ${esc(x.etiqueta || "")} · ${x.ts}`;
      });
      chart.addEventListener("pointerleave", () => { ro.innerHTML = "&nbsp;"; });
    }
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
  function renderIdeasDiagnostic(diag) {
    if (!diag) return "";
    const ctxs = diag.contexts || null;
    if (ctxs) {
      const rows = Object.entries(ctxs).map(([ns, x]) => {
        const r = L.ideasRazones[x.reason] || x.reason || "-";
        return `<div class="strow"><span class="slabel"><code>${esc(ns)}</code></span>`
          + `<span class="sval">${esc(r)} · ${x.memories || 0} mem · ${x.links || 0} links · ${x.open_wedges || 0} wedges</span></div>`;
      }).join("");
      return `<div class="scard"><h3>${L.ideasDiag}</h3>${rows}</div>`;
    }
    const r = L.ideasRazones[diag.reason] || diag.reason || "-";
    return `<div class="scard"><h3>${L.ideasDiag}</h3>`
      + `<div class="strow"><span class="slabel">${esc(r)}</span>`
      + `<span class="sval">${diag.memories || 0} mem · ${diag.links || 0} links · ${diag.open_wedges || 0} wedges · ${diag.scored || 0} scored</span></div></div>`;
  }
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
  // HECHOS (role-records: el diferenciador VSA, hecho visible)
  // ==========================================================================
  const _ROLES = ["subject", "predicate", "object", "time", "source"];
  function renderFacts(d) {
    const c = $("view-facts");
    if (!d) { c.innerHTML = `<p class="hint">${L.factsCargando}</p>`; return; }
    const fs = d.facts || [];
    if (!fs.length) { c.innerHTML = `<p class="hint">${L.factsVacio}</p>`; return; }
    const chip = (f) => {
      const s = f.fields.subject, p = f.fields.predicate, o = f.fields.object;
      return (s ? `<b>${esc(s)}</b> ` : "") + (p ? `<i>${esc(p)}</i> ` : "")
        + (o ? `<b>${esc(o)}</b>` : "");
    };
    c.innerHTML = `<p class="hint">${L.factsIntro}</p>` + fs.map((f) => {
      const extra = _ROLES.slice(3).filter((r) => f.fields[r])
        .map((r) => `${esc(r)}: ${esc(f.fields[r])}`).join(" · ");
      const estado = f.vigente ? "" : `<span class="fact-old">${L.factsCerrado}</span>`;
      const ctx = f.context ? `<span class="fact-ctx">⟨${esc(f.context)}⟩</span>` : "";
      return `<div class="fact${f.vigente ? "" : " cerrado"}">`
        + `<div class="fact-head"><span class="id">#${f.id}</span>${ctx}${estado}</div>`
        + `<div class="fact-triple">${chip(f)}</div>`
        + (extra ? `<div class="fact-extra"><small>${extra}</small></div>` : "")
        + `</div>`;
    }).join("");
  }

  // ==========================================================================
  // pestañas, búsqueda, mensajes
  // ==========================================================================
  const PIDE = {
    status: () => vscode.postMessage({ type: "status-request" }),
    tokens: () => vscode.postMessage({ type: "tokens-request" }),
    log: () => vscode.postMessage({ type: "log-request" }),
    ideas: () => vscode.postMessage({ type: "ideas-request" }),
    facts: () => vscode.postMessage({ type: "facts-request" }),
  };
  const PLACEHOLDER_VACIO = { status: renderStatus, tokens: renderTokens, log: renderLog,
    ideas: renderIdeas, facts: renderFacts };

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
    "recall-auto": L.phRecall,
    "recall-nav": L.phRecall,
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
      if (relanzarBusqueda) { relanzarBusqueda = false; lanzarBusquedaAgente(); return; }
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
    } else if (msg.type === "facts") {
      renderFacts(msg.data);
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
  $("kind").addEventListener("change", () => repintar());
  $("sort").addEventListener("change", () => { if (VIEW === "list") repintar(); });
  $("nbhd").addEventListener("change", () => {
    NBHD = $("nbhd").checked;
    if (NBHD && MAPFOCO == null && G && G.sel) MAPFOCO = G.sel;
    if (!NBHD) MAPFOCO = null;
    if (VIEW === "graph") renderGraph(visibles());
  });
  $("hops").addEventListener("change", () => {
    HOPS = Number($("hops").value) || 2;
    if (NBHD && VIEW === "graph") renderGraph(visibles());
  });
  // Refrescar = recargar de disco, SIN borrar la búsqueda. Si había una búsqueda de
  // agente en curso, se relanza al llegar los datos (bandera). Limpiar la caja es otra
  // cosa distinta (se hace vaciándola a mano), no lo que espera un botón de refresco.
  let relanzarBusqueda = false;
  $("refresh").onclick = () => {
    relanzarBusqueda = ($("mode").value !== "text" && !!$("q").value.trim());
    vscode.postMessage({ type: "refresh" });
  };
  $("choose-db").addEventListener("click", () =>
    vscode.postMessage({ type: "choose-db" }));
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
})();
