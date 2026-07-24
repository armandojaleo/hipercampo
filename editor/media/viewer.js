// Webview del visor. Sin frameworks ni librerías externas (la CSP bloquea CDNs):
// DOM + canvas a mano. Habla con la extensión por mensajes.
(function () {
  const vscode = acquireVsCodeApi();
  const $ = (id) => document.getElementById(id);

  // --- estado ---------------------------------------------------------------
  let MEM = [];          // nodos (memorias) del último fetch
  let EDGES = [];        // aristas del grafo
  let SCOPE = "";
  let HITS = null;       // resultados de recall/muse (null = no hay búsqueda de agente)
  let ACTIVE = null;     // Set de namespaces activos (chips); null = todos
  let VIEW = "list";

  // --- utilidades -----------------------------------------------------------
  const norm = (s) => String(s || "").toLowerCase()
    .normalize("NFD").replace(/[\u0300-\u036f]/g, "");

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
    if (!ts) return "—";
    const d = (Date.now() / 1000 - ts) / 86400;
    if (d < 1) return "hoy";
    if (d < 30) return `hace ${Math.round(d)} d`;
    if (d < 365) return `hace ${Math.round(d / 30)} mes`;
    return `hace ${(d / 365).toFixed(1)} a`;
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
      el.title = "Mostrar/ocultar este contexto";
      el.onclick = () => {
        if (!ACTIVE) ACTIVE = new Set(todos);
        if (ACTIVE.has(ns)) ACTIVE.delete(ns); else ACTIVE.add(ns);
        if (ACTIVE.size === todos.length) ACTIVE = null;
        pintarChips(); repintar();
      };
      cont.appendChild(el);
    }
  }

  // --- cabecera / contador --------------------------------------------------
  function cabecera(n) {
    const total = (HITS !== null ? HITS : MEM).length;
    $("scope").textContent = HITS !== null
      ? `${$("mode").value} · ${SCOPE}` : SCOPE;
    $("count").textContent = n === total ? `${total}` : `${n} de ${total}`;
  }

  // --- repintar la vista activa --------------------------------------------
  function mensajeVacio() {
    const m = $("mode").value;
    if (m !== "text" && HITS === null)
      return `Escribe una consulta y pulsa Enter para buscar con ${m}.`;
    if (HITS !== null)
      return "No encontró nada. En modo recall puede haberse abstenido (sabe decir «no tengo nada»); prueba muse para conexiones indirectas.";
    return "Nada que mostrar. Prueba a limpiar el buscador o activa «todos los contextos».";
  }

  function repintar() {
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
      ? `<span class="badge" title="relevancia">score ${(+m.score).toFixed(2)}</span>` : "";
    const metrics = [metric("imp", m.importance), metric("fiab", m.confidence),
      metric("fuerza", m.strength),
      (m.access_count != null ? `<span>usos <b>${m.access_count}</b></span>` : ""),
      (m.last_access != null ? `<span>visto <b>${fecha(m.last_access)}</b></span>` : "")]
      .filter(Boolean).join("");
    el.innerHTML =
      `<div class="head"><span class="id">#${m.id}</span>`
      + `<span class="badge">${esc(m.kind || "?")}</span>${ns}${score}`
      + `<span class="flags" title="latente/consolidado/reemplazado/pronto-latente">${flags}</span>`
      + `<span class="actions">`
      + `<button data-act="muse" title="Conexiones (muse)">💡</button>`
      + (m.dormant
          ? `<button data-act="wake" title="Despertar">☀️</button>`
          : `<button data-act="forget" title="Olvidar (reversible)">💤</button>`)
      + `<button data-act="purge" title="Borrar del todo (irreversible)">🗑️</button>`
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
  let G = null;   // estado del grafo (nodos con posición, cámara, animación)

  function renderGraph(items) {
    const canvas = $("graph-canvas");
    const vis = new Set(items.map((m) => m.id));
    const nodos = items.map((m) => ({ m, id: m.id }));
    const idx = new Map(nodos.map((n, i) => [n.id, i]));
    const aristas = EDGES.filter((e) => vis.has(e.src) && vis.has(e.dst));

    // Semilla determinista de posiciones (en círculo), para que no baile en cada pintado.
    const R = 180;
    nodos.forEach((n, i) => {
      const a = (i / Math.max(1, nodos.length)) * Math.PI * 2;
      n.x = Math.cos(a) * R; n.y = Math.sin(a) * R; n.vx = 0; n.vy = 0;
    });

    G = { canvas, ctx: canvas.getContext("2d"), nodos, idx, aristas,
      scale: 1, ox: 0, oy: 0, sel: null, drag: null, alpha: 1, raf: 0 };
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
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-foreground);opacity:.5"></span>asociación</div>`
      + `<div class="k"><span class="ln" style="border-color:var(--vscode-textLink-foreground);border-top-style:dashed"></span>puente onírico</div>`;
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
      if (!G || VIEW !== "graph") return;
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
      const rest = 70;
      const f = (d - rest) * 0.02 * (0.4 + (e.weight || 0.5));
      const ux = dx / d, uy = dy / d;
      s.fx += ux * f; s.fy += uy * f; t.fx -= ux * f; t.fy -= uy * f;
    }
    for (const n of N) {
      if (n === (G.drag && G.drag.node)) continue;
      n.vx = (n.vx + n.fx * a) * 0.85; n.vy = (n.vy + n.fy * a) * 0.85;
      n.x += n.vx; n.y += n.vy;
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
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y);
      ctx.strokeStyle = puente ? getVar("--vscode-textLink-foreground") : "rgba(140,140,140,.35)";
      ctx.lineWidth = puente ? 1.2 : Math.min(2.5, 0.5 + (e.weight || 0.5) * 1.5);
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
      else { const n = G.drag.node; n.x = (mx - G.w / 2 - G.ox) / G.scale; n.y = (my - G.h / 2 - G.oy) / G.scale; n.vx = n.vy = 0; dibujarGrafo(); }
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
      + `<button data-act="muse">💡 conexiones</button>`
      + (m.dormant ? `<button data-act="wake">☀️ despertar</button>` : `<button data-act="forget">💤 olvidar</button>`)
      + `<button data-act="purge">🗑️ borrar</button></div>`;
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
      const flag = m.dormant ? "💤 latente" : (prontoLatente(m) ? "⚠️ pronto latente" : "");
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
    ctx.fillText("importancia →", W - 110, H - pad + 16);
    ctx.save(); ctx.translate(14, pad + 60); ctx.rotate(-Math.PI / 2);
    ctx.fillText("fiabilidad →", 0, 0); ctx.restore();
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
          + `<br><small>imp ${(hit.m.importance || 0).toFixed(2)} · fiab ${(hit.m.confidence || 0).toFixed(2)} · fuerza ${(hit.m.strength || 0).toFixed(2)}</small>`;
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
  // pestañas, búsqueda, mensajes
  // ==========================================================================
  function activarVista(v) {
    VIEW = v;
    document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t.dataset.view === v));
    document.querySelectorAll(".view").forEach((s) => s.classList.toggle("active", s.id === "view-" + v));
    repintar();
  }

  const PLACEHOLDER = {
    text: "Filtrar por texto…",
    recall: "Escribe una consulta y pulsa Enter (recall, como el agente)…",
    muse: "Escribe una semilla y pulsa Enter (muse: conexiones eureka)…",
  };

  function actualizarModo(foco) {
    const m = $("mode").value;
    $("q").placeholder = PLACEHOLDER[m] || PLACEHOLDER.text;
    if (foco) $("q").focus();
  }

  function lanzarBusquedaAgente() {
    const q = $("q").value.trim();
    if (!q) { HITS = null; repintar(); return; }   // sin semilla: repintar avisa
    $("scope").textContent = `buscando con ${$("mode").value}…`;
    vscode.postMessage({ type: "search", query: q, mode: $("mode").value });
  }

  window.addEventListener("message", (ev) => {
    const msg = ev.data;
    if (msg.type === "data") {
      MEM = msg.memories || []; EDGES = msg.edges || []; SCOPE = msg.scope || "";
      HITS = null; ACTIVE = null;
      pintarChips(); repintar();
    } else if (msg.type === "search-result") {
      HITS = msg.memories || [];
      repintar();
    } else if (msg.type === "error") {
      $("error").classList.remove("hidden");
      $("error").textContent = "No se pudo leer la memoria:\n\n" + msg.message;
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
  $("all").addEventListener("change", (e) =>
    vscode.postMessage({ type: "setAllNamespaces", value: e.target.checked }));

  window.addEventListener("resize", () => {
    if (VIEW === "graph" && G) { ajustarCanvas(G.canvas); dibujarGrafo(); }
    else if (VIEW === "axes") repintar();
  });

  $("all").checked = true;
  vscode.postMessage({ type: "ready" });
}());
