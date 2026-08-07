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

// --- datos de muestra (no dependen de ninguna BD; GENÉRICOS, sin nada privado) --------
// Cubren los cinco estados del Mapa y los tres tipos de arista, y son suficientes para
// que la constelación se lea como tal en las capturas del Marketplace.
const now = Date.now() / 1000;
const N = (id, text, kind, ns, imp, conf, str, days, uses, extra) =>
  Object.assign({ id, text, kind, namespace: ns, importance: imp, confidence: conf,
    strength: str, last_access: now - days * 86400, access_count: uses }, extra || {});
const SAMPLE = {
  nodes: [
    N(1, "The payment API key starts with demo_9f", "episodic", "app", 0.9, 0.95, 0.8, 0.04, 4),
    N(2, "Production server is hosted in Frankfurt", "semantic", "app", 0.7, 0.9, 0.6, 1, 9, { consolidated: 1 }),
    N(3, "Analytics DB is a ClickHouse in the east region", "semantic", "infra", 0.6, 0.8, 0.5, 2, 3),
    N(4, "Old note: the server used to be in Dublin", "episodic", "app", 0.4, 0.5, 0.2, 30, 1, { superseded: 1 }),
    N(5, "A rarely used detail about the SSL cert", "episodic", "infra", 0.3, 0.4, 0.15, 60, 0, { dormant: 1 }),
    N(6, "The SSL cert of the domain expires on Dec 15", "episodic", "infra", 0.8, 0.9, 0.7, 0.08, 2),
    N(7, "expires Dec 15", "episodic", "infra", 0.5, 0.7, 0.5, 0.08, 1),
    N(8, "The nightly data pipeline runs at 03:00", "semantic", "infra", 0.6, 0.85, 0.55, 1.5, 5, { consolidated: 1 }),
    N(9, "Security lead is on the platform team", "semantic", "app", 0.65, 0.8, 0.5, 3, 4),
    N(10, "Feature flags live in the config service", "episodic", "app", 0.55, 0.7, 0.45, 0.5, 3),
    N(11, "Rollback command is deploy --revert", "episodic", "infra", 0.7, 0.9, 0.6, 0.2, 6),
    N(12, "The staging env mirrors production weekly", "semantic", "infra", 0.5, 0.75, 0.4, 4, 2),
    N(13, "Design note: keep the map legible at scale", "episodic", "notes", 0.6, 0.6, 0.5, 0.3, 2),
    N(14, "Idea: color nodes by cognitive state", "episodic", "notes", 0.7, 0.7, 0.6, 0.1, 3),
    N(15, "runs at 03:00", "episodic", "infra", 0.45, 0.7, 0.45, 1.5, 1),
    N(16, "Old deploy step, replaced by the pipeline", "episodic", "infra", 0.35, 0.5, 0.2, 45, 0, { superseded: 1 }),
    N(17, "Backups are verified every Sunday", "semantic", "infra", 0.55, 0.8, 0.45, 5, 2),
    N(18, "A seldom-touched runbook for incidents", "episodic", "notes", 0.3, 0.5, 0.15, 90, 0, { dormant: 1 }),
  ],
  edges: [
    { src: 1, dst: 2, type: "assoc", weight: 0.6 }, { src: 2, dst: 3, type: "assoc", weight: 0.5 },
    { src: 2, dst: 4, type: "dream", status: "proposed", weight: 0.3 }, { src: 3, dst: 5, type: "knn", weight: 0.4 },
    { src: 6, dst: 7, type: "atom", weight: 0.9 }, { src: 1, dst: 6, type: "assoc", weight: 0.4 },
    { src: 8, dst: 15, type: "atom", weight: 0.9 }, { src: 3, dst: 8, type: "assoc", weight: 0.5 },
    { src: 8, dst: 11, type: "assoc", weight: 0.45 }, { src: 8, dst: 16, type: "dream", status: "proposed", weight: 0.3 },
    { src: 9, dst: 2, type: "assoc", weight: 0.4 }, { src: 10, dst: 11, type: "knn", weight: 0.35 },
    { src: 11, dst: 12, type: "assoc", weight: 0.5 }, { src: 12, dst: 17, type: "assoc", weight: 0.4 },
    { src: 13, dst: 14, type: "assoc", weight: 0.7 }, { src: 14, dst: 10, type: "knn", weight: 0.3 },
    { src: 17, dst: 18, type: "knn", weight: 0.3 }, { src: 6, dst: 12, type: "assoc", weight: 0.35 },
    { src: 9, dst: 10, type: "assoc", weight: 0.4 }, { src: 1, dst: 9, type: "knn", weight: 0.3 },
  ],
};

// Paleta VS Code Dark+ para las variables de tema (el standalone no hereda el tema real;
// esto da capturas oscuras coherentes con el branding del Marketplace).
const DARK = {
  "editor-background": "#1e1e1e", "foreground": "#cccccc", "descriptionForeground": "#9d9d9d",
  "focusBorder": "#007fd4", "panel-border": "#2b2b2b", "editorWidget-background": "#252526",
  "input-background": "#3c3c3c", "input-foreground": "#cccccc", "input-border": "#3c3c3c",
  "button-background": "#0e639c", "button-foreground": "#ffffff", "button-hoverBackground": "#1177bb",
  "badge-background": "#4d4d4d", "badge-foreground": "#ffffff", "textLink-foreground": "#3794ff",
  "errorForeground": "#f48771", "toolbar-hoverBackground": "rgba(90,93,94,.31)",
  "scrollbarSlider-background": "rgba(121,121,121,.4)", "charts-purple": "#b180d7",
  "textBlockQuote-background": "#222222", "inputValidation-errorBackground": "#5a1d1d",
  "font-family": "-apple-system, system-ui, sans-serif", "editor-font-family": "monospace",
  "font-size": "13px",
};
function themeStyle(theme) {
  if (theme !== "dark") return "";
  const vars = Object.entries(DARK).map(([k, v]) => `--vscode-${k}:${v};`).join("");
  return `<style>:root{${vars}} html,body{background:#1e1e1e;}</style>`;
}

function parseArgs(argv) {
  const a = { lang: "en", view: "list", out: path.join(__dirname, "preview-out"), shot: true, all: false, data: null, theme: "light" };
  for (let i = 2; i < argv.length; i++) {
    const k = argv[i];
    if (k === "--lang") a.lang = argv[++i];
    else if (k === "--view") a.view = argv[++i];
    else if (k === "--out") a.out = argv[++i];
    else if (k === "--data") a.data = argv[++i];
    else if (k === "--theme") a.theme = argv[++i];
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

function buildStandalone(lang, view, data, theme) {
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
    .replace('<link rel="stylesheet" href="%STYLE%">', "<style>\n" + css + "\n</style>\n" + themeStyle(theme))
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
    const page = buildStandalone(lang, view, data, a.theme);
    const tag = `${lang}_${view}${a.theme === "dark" ? "_dark" : ""}`;
    const htmlFile = path.join(a.out, `viewer_${tag}.html`);
    fs.writeFileSync(htmlFile, page, "utf8");
    let line = "· " + path.relative(process.cwd(), htmlFile);
    if (browser) {
      const pngFile = path.join(a.out, `viewer_${tag}.png`);
      try { shoot(browser, htmlFile, pngFile); line += "  →  " + path.relative(process.cwd(), pngFile); }
      catch (e) { line += "  (captura falló: " + (e.message || e) + ")"; }
    }
    console.log(line);
  }
  console.log("navegador:", browser || "(ninguno)");
}

main();
