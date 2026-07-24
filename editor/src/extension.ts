import * as vscode from "vscode";
import { execFile } from "child_process";
import * as path from "path";
import * as fs from "fs";

/**
 * Visor de memoria de hipercampo. No habla SQLite ni conoce el esquema: llama al
 * CLI `hipercampo` (que ya sabe de namespaces y aislamiento) y pinta lo que devuelve.
 * Así el visor no puede corromper nada — es de solo lectura por construcción.
 */

interface Memory {
  id: number;
  text: string;
  kind: string;
  namespace?: string;
  importance?: number;
  confidence?: number;
  strength?: number;
  access_count?: number;
  created?: number;
  last_access?: number;
  dormant?: number;
  consolidated?: number;
  superseded?: number;
}

function cfg() {
  return vscode.workspace.getConfiguration("hipercampo");
}

/** Divide "python -m hipercampo.cli" en ejecutable + argumentos base. */
function split(raw: string): { exe: string; prefix: string[] } {
  const parts = raw.trim().split(/\s+/);
  return { exe: parts[0], prefix: parts.slice(1) };
}

// Candidatos a probar cuando el comando por defecto no está en el PATH. VS Code
// lanzado desde el menú (no desde una terminal) no hereda el PATH del shell, así que
// «hipercampo» a secas suele no encontrarse aunque esté instalado; `python -m
// hipercampo.cli` sí funciona si el paquete está en ese Python.
const FALLBACKS = ["python -m hipercampo.cli", "python3 -m hipercampo.cli",
  "py -m hipercampo.cli"];

// El comando que ya se comprobó que funciona; se cachea para no reintentar cada vez.
let resolved: string | undefined;

function candidates(): string[] {
  const conf = (cfg().get<string>("command") || "hipercampo").trim();
  // Si el usuario configuró algo distinto del default, se respeta y no se adivina.
  if (conf && conf !== "hipercampo") return [conf];
  return [conf, ...FALLBACKS];
}

function childEnv(): NodeJS.ProcessEnv {
  const env: NodeJS.ProcessEnv = { ...process.env, HIPERCAMPO_LOG: "0" };
  const db = (cfg().get<string>("dbPath") || "").trim();
  const ns = (cfg().get<string>("namespace") || "").trim();
  if (db) env.HIPERCAMPO_DB = db;
  if (ns) env.HIPERCAMPO_NAMESPACE = ns;
  return env;
}

/** Lanza un comando concreto. `notFound` distingue "no existe el ejecutable"
 * (probar el siguiente candidato) de un fallo real del comando (que se reporta). */
function tryRun(cmd: string, args: string[]): Promise<{ out: string } | { notFound: true } | { fail: string }> {
  const { exe, prefix } = split(cmd);
  return new Promise((res) => {
    execFile(exe, [...prefix, ...args], { env: childEnv(), maxBuffer: 32 * 1024 * 1024 },
      (err, stdout, stderr) => {
        if (!err) return res({ out: stdout });
        if ((err as any).code === "ENOENT") return res({ notFound: true });
        res({ fail: stderr || err.message });
      });
  });
}

/** Ejecuta el CLI probando el comando cacheado o los candidatos hasta dar con uno
 * que exista. Rechaza con un mensaje legible si ninguno se encuentra o si falla. */
async function run(args: string[]): Promise<string> {
  const orden = resolved ? [resolved, ...candidates()] : candidates();
  let ultimoFallo = "";
  for (const cmd of orden) {
    const r = await tryRun(cmd, args);
    if ("out" in r) { resolved = cmd; return r.out; }
    if ("fail" in r) ultimoFallo = r.fail;   // existe pero falló: es un error real
  }
  if (ultimoFallo) throw new Error(ultimoFallo);
  throw new Error(
    "No se encontró «hipercampo» (ni «python -m hipercampo.cli»). Instálalo con "
    + "«pip install --pre hipercampo», o pon la ruta en el ajuste hipercampo.command.");
}

async function fetchGraph(): Promise<{ memories: Memory[]; edges: any[]; scope: string; db?: string }> {
  const all = cfg().get<boolean>("allNamespaces");
  const args = ["graph"];
  if (all) args.push("--all-namespaces");
  const out = await run(args);
  const data = JSON.parse(out);
  const scope = data.all_namespaces ? "todos los contextos" : `contexto «${data.namespace}»`;
  return { memories: data.nodes || [], edges: data.edges || [], scope, db: data.db };
}

// Búsqueda "como el agente": recall (directo, sabe abstenerse) o muse (creativo, trae
// asociados y latentes — la vía «eureka»). Ambos van al namespace del entorno.
async function agentSearch(query: string, mode: "recall" | "muse"): Promise<Memory[]> {
  const out = await run([mode, query]);
  const hits = JSON.parse(out);
  return Array.isArray(hits) ? hits : [];
}

/** Adormece/despierta o purga un recuerdo, tras confirmación. Devuelve true si tocó algo. */
async function mutate(id: number, namespace: string | undefined,
  action: "forget" | "wake" | "purge"): Promise<boolean> {
  const nsArgs = namespace ? ["--namespace", namespace] : [];
  if (action === "wake") {
    await run(["dormant", "--ids", String(id), "--wake", ...nsArgs]);
    return true;
  }
  if (action === "forget") {
    await run(["dormant", "--ids", String(id), ...nsArgs]);
    return true;
  }
  // purge: físico e irreversible -> confirmación MODAL antes de nada
  const ok = await vscode.window.showWarningMessage(
    `¿Borrar del todo el recuerdo #${id}? Es físico e irreversible (no es el olvido, `
    + `que solo adormece).`, { modal: true }, "Borrar del todo");
  if (ok !== "Borrar del todo") return false;
  await run(["purge", "--ids", String(id), "--yes", ...nsArgs]);
  return true;
}

/** Lógica común a las DOS caras del visor (el panel lateral y la vista de la barra
 * de actividad): pinta el HTML, atiende los mensajes del webview, y se auto-refresca
 * cuando cambia el fichero .db (para que no haya que cerrar y abrir). */
class Controller {
  private db: string | undefined;
  private watcher: fs.FSWatcher | undefined;
  private pend: NodeJS.Timeout | undefined;
  private readonly disposables: vscode.Disposable[] = [];

  constructor(private readonly webview: vscode.Webview,
              private readonly ctx: vscode.ExtensionContext) {
    webview.options = { enableScripts: true };
    webview.html = html(webview, ctx);
    this.disposables.push(webview.onDidReceiveMessage((m) => this.onMessage(m)));
  }

  private post(m: any) { this.webview.postMessage(m); }

  private async onMessage(msg: any) {
    try {
      if (msg.type === "ready" || msg.type === "refresh") {
        await this.load();
      } else if (msg.type === "setAllNamespaces") {
        await cfg().update("allNamespaces", !!msg.value, vscode.ConfigurationTarget.Global);
        await this.load();
      } else if (msg.type === "search") {
        const hits = await agentSearch(msg.query, msg.mode === "muse" ? "muse" : "recall");
        this.post({ type: "search-result", memories: hits, query: msg.query, mode: msg.mode });
      } else if (msg.type === "mutate") {
        const changed = await mutate(msg.id, msg.namespace, msg.action);
        if (changed) { await this.load(); }
      }
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    }
  }

  async load() {
    try {
      // Un solo fetch: `graph` trae nodos, aristas y la RUTA del .db (para vigilarla).
      const { memories, edges, scope, db } = await fetchGraph();
      this.post({ type: "data", memories, edges, scope });
      if (db && db !== this.db) { this.db = db; this.vigilar(db); }
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    }
  }

  // Vigila el fichero .db: si cambia (lo toca el agente u otra sesión), recarga sola.
  // Con rebote, porque SQLite en modo WAL dispara varios eventos por una escritura.
  private vigilar(db: string) {
    this.watcher?.close();
    try {
      const dir = path.dirname(db), base = path.basename(db);
      this.watcher = fs.watch(dir, (_ev, fn) => {
        if (fn && (fn === base || fn.startsWith(base))) {   // .db, .db-wal, .db-shm
          clearTimeout(this.pend);
          this.pend = setTimeout(() => this.load(), 500);
        }
      });
    } catch { /* si no se puede vigilar, el botón ↻ sigue estando */ }
  }

  dispose() {
    clearTimeout(this.pend);
    this.watcher?.close();
    this.disposables.forEach((d) => d.dispose());
  }
}

function html(webview: vscode.Webview, ctx: vscode.ExtensionContext): string {
  const nonce = String(Math.random()).slice(2);
  const uri = (f: string) =>
    webview.asWebviewUri(vscode.Uri.file(path.join(ctx.extensionPath, "media", f)));
  const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; `
    + `script-src 'nonce-${nonce}';`;
  let page = fs.readFileSync(path.join(ctx.extensionPath, "media", "viewer.html"), "utf8");
  return page
    .replace(/%CSP%/g, csp)
    .replace(/%NONCE%/g, nonce)
    .replace(/%SCRIPT%/g, String(uri("viewer.js")))
    .replace(/%STYLE%/g, String(uri("viewer.css")));
}

/** El panel ancho, a un lado del editor (bueno para el mapa). */
class Panel {
  private static current: { ctrl: Controller; panel: vscode.WebviewPanel } | undefined;

  static show(ctx: vscode.ExtensionContext) {
    if (Panel.current) { Panel.current.panel.reveal(); Panel.current.ctrl.load(); return; }
    const panel = vscode.window.createWebviewPanel(
      "hipercampoViewer", "hipercampo — memoria", vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true });
    const ctrl = new Controller(panel.webview, ctx);
    Panel.current = { ctrl, panel };
    // Al volver a enfocar el panel, refresca (por si cambió algo mientras no se veía).
    panel.onDidChangeViewState((e) => { if (e.webviewPanel.visible) ctrl.load(); });
    panel.onDidDispose(() => { ctrl.dispose(); Panel.current = undefined; });
  }

  static refresh() { Panel.current?.ctrl.load(); }
}

/** La MISMA memoria dentro de la barra de actividad (tira izquierda): el icono abre
 * el visor entero ahí, no un mensaje con un botón. */
class SidebarProvider implements vscode.WebviewViewProvider {
  constructor(private readonly ctx: vscode.ExtensionContext) {}
  resolveWebviewView(view: vscode.WebviewView) {
    view.webview.options = { enableScripts: true };
    const ctrl = new Controller(view.webview, this.ctx);
    view.onDidChangeVisibility(() => { if (view.visible) ctrl.load(); });
    view.onDidDispose(() => ctrl.dispose());
  }
}

export function activate(context: vscode.ExtensionContext) {
  // Botón siempre visible en la barra de estado (abajo): un clic abre el panel ancho.
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.text = "$(database) memoria";
  status.tooltip = "hipercampo: ver memorias";
  status.command = "hipercampo.showMemories";
  status.show();

  context.subscriptions.push(
    status,
    vscode.window.registerWebviewViewProvider("hipercampo.home", new SidebarProvider(context),
      { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("hipercampo.showMemories", () => Panel.show(context)),
    vscode.commands.registerCommand("hipercampo.refresh", () => Panel.refresh()),
  );
}

export function deactivate() { /* nada global que limpiar: cada visor libera lo suyo */ }
