"use strict";
/**
 * Previsualiza/valida el visor SIN VS Code: monta una versión "standalone" del webview
 * (CSS+JS inline + un stub de acquireVsCodeApi que le inyecta datos), la abre en un
 * navegador headless del sistema (Chrome/Edge) y guarda una captura. Sirve para:
 *   - validar la i18n EN/ES y el layout en un navegador de VERDAD (lo que el harness de
 *     Node no ve: CSS real), sin instalar el VSIX;
 *   - sacar capturas para el Marketplace.
 *
 * Uso:
 *   node tools/preview.js --lang en --view list
 *   node tools/preview.js --lang es --view graph --out tools/preview-out
 *   node tools/preview.js --data ../ruta/graph.json      # datos reales (hipercampo graph --json)
 *   node tools/preview.js --all                          # en+es × list+graph, todo de golpe
 *   node tools/preview.js --no-shot                      # solo genera el HTML, sin captura
 *
 * El navegador se autodetecta; se puede forzar con la variable CHROME_BIN.
 */
const fs = require("fs");
const path = require("path");
const os = require("os");
const { execFileSync } = require("child_process");

const MEDIA = path.join(__dirname, "..", "media");

// --- datos de muestra (no dependen de ninguna BD): cubren los estados del Mapa -------
const SAMPLE = {
  nodes: [
    { id: 1, text: "The payment API key starts with hcdemo_9f", kind: "episodic", namespace: "demo", importance: 0.9, confidence: 0.95, strength: 0.8, last_access: Date.now() / 1000 - 3600, access_count: 4 },
    { id: 2, text: "Production server is hosted in Frankfurt", kind: "semantic", namespace: "demo", importance: 0.7, confidence: 0.9, strength: 0.6, last_access: Date.now() / 1000 - 86400, access_count: 9, consolidated: 1 },
    { id: 3, text: "Analytics DB is a ClickHouse in the east region", kind: "semantic", namespace: "infra", importance: 0.6, confidence: 0.8, strength: 0.5, last_access: Date.now() / 1000 - 172800, access_count: 3 },
    { id: 4, text: "Old note: server was in Dublin", kind: "episodic", namespace: "demo", importance: 0.4, confidence: 0.5, strength: 0.2, last_access: Date.now() / 1000 - 2592000, access_count: 1, superseded: 1 },
    { id: 5, text: "Rarely used detail about the SSL cert", kind: "episodic", namespace: "infra", importance: 0.3, confidence: 0.4, strength: 0.15, last_access: Date.now() / 1000 - 5184000, access_count: 0, dormant: 1 },
    { id: 6, text: "the SSL cert of the domain expires on Dec 15", kind: "episodic", namespace: "infra", importance: 0.8, confidence: 0.9, strength: 0.7, last_access: Date.now() / 1000 - 7200, access_count: 2 },
    { id: 7, text: "atom: expires Dec 15", kind: "episodic", namespace: "infra", importance: 0.5, confidence: 0.7, strength: 0.5, last_access: Date.now() / 1000 - 7200, access_count: 1 },
  ],
  edges: [
    { src: 1, dst: 2, type: "assoc", weight: 0.6 },
    { src: 2, dst: 3, type: "assoc", weight: 0.5 },
    { src: 2, dst: 4, type: "dream", status: "proposed", weight: 0.3 },
    { src: 3, dst: 5, type: "knn", weight: 0.4 },
    { src: 6, dst: 7, type: "atom", weight: 0.9 },
    { src: 1, dst: 6, type: "assoc", weight: 0.4 },
  ],
};

function parseArgs(argv) {
  const a = { lang: "en", view: "list", out: path.join(__dirname, "preview-out"), shot: true, all: false, data: null };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === "--lang") a.lang = argv[++i];
    else if (k === "--view") a.view = argv[++i];
    else if (k === "--out") a.out = argv[++i];
    else if (k === "--data") a.data = argv[++i];
    else if (k === "--no-shot") a.shot = false;
    else if (k === "--all") a.all = true;
  }
  return a;
}

function findBrowser() {
  if (process.env.CHROME_BIN && fs.existsSync(process.env.CHROME_BIN)) return process.env.CHROME_BIN;
  const cands = process.platform === "win32"
    ? ["C:/Program Files/Google/Chrome/Application/chrome.exe",
       "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe",
       "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe",
       "C:/Program Files/Microsoft/Edge/Application/msedge.exe"]
    : process.platform === "darwin"
      ? ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
         "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
         "/Applications/Chromium.app/Contents/MacOS/Chromium"]
      : ["/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
         "/usr/bin/microsoft-edge", "/snap/bin/chromium"];
  return cands.find((p) => fs.existsSync(p)) || null;
}

function buildStandalone(lang, view, data) {
  const html = fs.readFileSync(path.join(MEDIA, "viewer.html"), "utf8");
  const css = fs.readFileSync(path.join(MEDIA, "viewer.css"), "utf8");
  const js = fs.readFileSync(path.join(MEDIA, "viewer.js"), "utf8");
  const scope = lang === "es" ? "todos los contextos" : "all contexts";
  const dataMsg = { type: "data", memories: data.nodes, edges: data.edges, scope, paused: false };
  const stub = "window.acquireVsCodeApi = () => ({ postMessage(){}, getState(){return null;}, setState(){} });";
  const feed = "window.dispatchEvent(new MessageEvent('message', { data: " + JSON.stringify(dataMsg) + " }));"
    + (view !== "list" ? " var _t=document.querySelector('[data-view=\"" + view + "\"]'); if(_t&&_t.onclick) _t.onclick();" : "");
  return html
    .replace(/<meta http-equiv="Content-Security-Policy"[^>]*>/, "")
    .replace(/%LANG%/g, lang)
    .replace('<link rel="stylesheet" href="%STYLE%">', "<style>\n" + css + "\n</style>")
    .replace(/<script nonce="%NONCE%" src="%SCRIPT%"><\/script>/,
      "<script>" + stub + "</script>\n<script>" + js + "</script>\n<script>" + feed + "</script>");
}

function shoot(browser, htmlFile, pngFile) {
  // headless clásico + virtual-time-budget: deja asentar la simulación del Mapa antes de capturar.
  execFileSync(browser, ["--headless", "--disable-gpu", "--no-sandbox", "--hide-scrollbars",
    "--window-size=1200,860", "--virtual-time-budget=4500",
    "--screenshot=" + pngFile, htmlFile], { stdio: "ignore" });
}

function main() {
  const a = parseArgs(process.argv);
  const data = a.data ? JSON.parse(fs.readFileSync(a.data, "utf8")) : SAMPLE;
  if (data.nodes && !data.edges) data.edges = [];
  fs.mkdirSync(a.out, { recursive: true });
  const combos = a.all
    ? [["en", "list"], ["es", "list"], ["en", "graph"], ["es", "graph"]]
    : [[a.lang, a.view]];
  const browser = a.shot ? findBrowser() : null;
  if (a.shot && !browser) console.warn("· sin navegador (Chrome/Edge); genero HTML sin captura. Fuerza con CHROME_BIN.");
  for (const [lang, view] of combos) {
    const page = buildStandalone(lang, view, data);
    const htmlFile = path.join(a.out, `viewer_${lang}_${view}.html`);
    fs.writeFileSync(htmlFile, page, "utf8");
    let line = "· " + path.relative(process.cwd(), htmlFile);
    if (browser) {
      const pngFile = path.join(a.out, `viewer_${lang}_${view}.png`);
      try { shoot(browser, htmlFile, pngFile); line += "  →  " + path.relative(process.cwd(), pngFile); }
      catch (e) { line += "  (captura falló: " + (e.message || e) + ")"; }
    }
    console.log(line);
  }
  console.log("navegador:", browser || "(ninguno)");
}

main();
