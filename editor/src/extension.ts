import * as vscode from "vscode";
import { execFile } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as crypto from "crypto";
import { hostMessages } from "./i18n";

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
  // OJO: no se pone HIPERCAMPO_LOG=0. La auditoría escribe a stderr y al fichero,
  // nunca a stdout (execFile los separa), así que el JSON sale limpio igual; y en
  // cambio LOG=0 anula la RUTA del registro y dejaba la pestaña Registro sin poder
  // leerlo ("registro desactivado" + código 1 = error en el visor).
  const env: NodeJS.ProcessEnv = { ...process.env };
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
  throw new Error(hostMessages(vscode.env.language).commandNotFound);
}

async function fetchGraph(): Promise<{ memories: Memory[]; edges: any[]; scope: string; db?: string; paused?: boolean }> {
  // El visor SIEMPRE trae todos los contextos; la selección (ver uno, ver todos) es
  // client-side vía los chips. Así, desmarcar "todos los contextos" nunca vacía la
  // pantalla por depender del fetch de un namespace que quizá no existe.
  const out = await run(["graph", "--all-namespaces"]);
  const data = JSON.parse(out);
  const scope = hostMessages(vscode.env.language).allContexts;
  return { memories: data.nodes || [], edges: data.edges || [], scope, db: data.db, paused: !!data.paused };
}

// Búsqueda "como el agente": recall (directo, sabe abstenerse) o muse (creativo, trae
// asociados y latentes — la vía «eureka»). Ambos van al namespace del entorno.
async function agentSearch(query: string, mode: "recall" | "recall-auto" | "recall-nav" | "muse"): Promise<Memory[]> {
  const args = mode === "recall-nav" ? ["recall", "--nav", query]
    : mode === "recall-auto" ? ["recall", "--nav-auto", query]
    : [mode, query];
  const out = await run(args);
  const hits = JSON.parse(out);
  return Array.isArray(hits) ? hits : [];
}

// Estado de salud: CLI, base de datos, servidor MCP y registro. Lo que dice si el
// motor está vivo, no solo qué hay guardado.
async function fetchStatus(): Promise<any> {
  const out = await run(["status"]);
  return JSON.parse(out);
}

// El registro de decisiones (recall/remember/sleep/forget/tokens…), estructurado.
async function fetchLog(): Promise<any> {
  const out = await run(["log", "-n", "300", "--json"]);
  return JSON.parse(out);
}

// La factura de tokens: agregado + serie temporal. El rasgo de la casa, visible.
async function fetchTokens(): Promise<any> {
  const out = await run(["tokens"]);
  return JSON.parse(out);
}

// Ideas: PUENTES que el sueño propone entre recuerdos distantes con un asociado común
// (hipótesis, no evidencia). dry-run por construcción: solo se muestran, no se graban.
async function fetchIdeas(): Promise<any> {
  const out = await run(["dream", "--json", "--max", "12", "--all-namespaces"]);
  return JSON.parse(out);
}

// Hechos estructurados (role-records): el diferenciador VSA, de todos los contextos.
async function fetchFacts(): Promise<any> {
  const out = await run(["facts", "--json", "--all-namespaces"]);
  return JSON.parse(out);
}

async function chooseDatabase(): Promise<boolean> {
  const text = hostMessages(vscode.env.language);
  const picked = await vscode.window.showOpenDialog({
    canSelectFiles: true,
    canSelectFolders: false,
    canSelectMany: false,
    filters: { "SQLite / hipercampo": ["db", "sqlite", "sqlite3"] },
    title: text.chooseDatabase,
  });
  const file = picked?.[0]?.fsPath;
  if (!file) return false;
  await cfg().update("dbPath", file, vscode.ConfigurationTarget.Global);
  vscode.window.showInformationMessage(text.activeMemory(file));
  return true;
}
/** Mueve un recuerdo a otro contexto (curación). Pregunta el destino: uno existente
 * o uno nuevo. Es reversible (se puede volver a mover), así que no pide modal. */
async function reclassify(id: number, namespace: string | undefined): Promise<boolean> {
  const origen = namespace || "default";
  let nss: string[] = [];
  try {
    const data = JSON.parse(await run(["graph", "--all-namespaces"]));
    nss = [...new Set((data.nodes || []).map((n: any) => n.namespace))]
      .filter((n): n is string => typeof n === "string" && n !== origen).sort();
  } catch { /* sin lista, se podrá teclear uno nuevo igual */ }
  const text = hostMessages(vscode.env.language);
  const NUEVO = text.newContext;
  const pick = await vscode.window.showQuickPick([...nss, NUEVO], {
    placeHolder: text.moveFrom(origen),
  });
  if (!pick) return false;
  let destino: string | undefined = pick;
  if (pick === NUEVO) {
    destino = (await vscode.window.showInputBox({
      prompt: text.targetContextName,
    }))?.trim();
  }
  if (!destino) return false;
  await run(["reclassify", "--ids", String(id), "--to", destino, "--namespace", origen]);
  return true;
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
  const text = hostMessages(vscode.env.language);
  const ok = await vscode.window.showWarningMessage(
    text.purgePrompt(id), { modal: true }, text.purgeAction);
  if (ok !== text.purgeAction) return false;
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
  private quietUntil = 0;   // ignora eventos del vigilante hasta aquí (ver más abajo)
  private readonly disposables: vscode.Disposable[] = [];

  constructor(private readonly webview: vscode.Webview,
              private readonly ctx: vscode.ExtensionContext) {
    webview.options = { enableScripts: true };
    webview.html = html(webview, ctx);
    this.disposables.push(webview.onDidReceiveMessage((m) => this.onMessage(m)));
  }

  private post(m: any) { this.webview.postMessage(m); }

  // CLAVE contra el bucle de CPU: cada comando del visor abre la BD en WAL, y ESO
  // toca los ficheros -wal/-shm, que el propio vigilante vería como un cambio y
  // dispararía otra recarga… en bucle. Tras cada operación nuestra silenciamos al
  // vigilante un rato, para que solo reaccione a cambios EXTERNOS (el agente, otra
  // sesión), no a los que causamos al leer.
  private silenciar() { this.quietUntil = Date.now() + 1500; }

  private async onMessage(msg: any) {
    this.silenciar();
    try {
      if (msg.type === "ready" || msg.type === "refresh") {
        await this.load();
      } else if (msg.type === "setAllNamespaces") {
        await cfg().update("allNamespaces", !!msg.value, vscode.ConfigurationTarget.Global);
        await this.load();
      } else if (msg.type === "choose-db") {
        if (await chooseDatabase()) {
          resolved = undefined;
          await this.load();
        }
      } else if (msg.type === "search") {
        const hits = await agentSearch(msg.query, msg.mode === "muse" ? "muse" : msg.mode === "recall-nav" ? "recall-nav" : msg.mode === "recall-auto" ? "recall-auto" : "recall");
        this.post({ type: "search-result", memories: hits, query: msg.query, mode: msg.mode });
      } else if (msg.type === "mutate") {
        const changed = await mutate(msg.id, msg.namespace, msg.action);
        if (changed) { await this.load(); }
      } else if (msg.type === "reclassify") {
        const changed = await reclassify(msg.id, msg.namespace);
        if (changed) { await this.load(); }
      } else if (msg.type === "status-request") {
        this.post({ type: "status", data: await fetchStatus() });
      } else if (msg.type === "log-request") {
        this.post({ type: "log", data: await fetchLog() });
      } else if (msg.type === "tokens-request") {
        this.post({ type: "tokens", data: await fetchTokens() });
      } else if (msg.type === "ideas-request") {
        this.post({ type: "ideas", data: await fetchIdeas() });
      } else if (msg.type === "facts-request") {
        this.post({ type: "facts", data: await fetchFacts() });
      } else if (msg.type === "setPaused") {
        await run([msg.value ? "pause" : "resume"]);
        await this.load();
      } else if (msg.type === "backup") {
        const out = (await run(["backup"])).trim();
        vscode.window.showInformationMessage(out || hostMessages(vscode.env.language).backupCreated);
        this.post({ type: "status", data: await fetchStatus() });   // refrescar tamaños
      } else if (msg.type === "open-log") {
        if (msg.path) {
          const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(msg.path));
          await vscode.window.showTextDocument(doc, { preview: true });
        } else {
          vscode.window.showInformationMessage(hostMessages(vscode.env.language).logDisabled);
        }
      } else if (msg.type === "open-external") {
        if (msg.url) { await vscode.env.openExternal(vscode.Uri.parse(msg.url)); }
      } else if (msg.type === "kill-server") {
        await run(["restart", "--pids", String(msg.pid)]);
        this.post({ type: "status", data: await fetchStatus() });   // refrescar la lista
      } else if (msg.type === "set-budget") {
        await run(msg.reset ? ["budget", "--reset"] : ["budget", "--set", String(msg.value)]);
        this.post({ type: "tokens", data: await fetchTokens() });
      } else if (msg.type === "reindex") {
        const out = JSON.parse(await run(["reindex", "--neighbors", "4", "--all-namespaces"]));
        vscode.window.showInformationMessage(
          hostMessages(vscode.env.language).graphWoven(out.enlaces_tejidos ?? 0));
        await this.load();                              // refresca el mapa, ya denso
      }
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    }
  }

  async load() {
    this.silenciar();
    try {
      // Un solo fetch: `graph` trae nodos, aristas y la RUTA del .db (para vigilarla).
      const { memories, edges, scope, db, paused } = await fetchGraph();
      this.post({ type: "data", memories, edges, scope, paused });
      if (db && db !== this.db) { this.db = db; this.vigilar(db); }
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    } finally {
      this.silenciar();   // la lectura recién hecha tocó -wal/-shm: no re-disparar por eso
    }
  }

  // Vigila el fichero .db: si cambia (lo toca el agente u otra sesión), recarga sola.
  // Con rebote, porque SQLite en modo WAL dispara varios eventos por una escritura.
  private vigilar(db: string) {
    this.watcher?.close();
    try {
      const dir = path.dirname(db);
      // El tronco del nombre (sin extensión) cubre .db, .db-wal, .db-shm Y el .log,
      // que viven en la misma carpeta: así el registro en vivo también refresca.
      const stem = path.basename(db).replace(/\.db$/, "");
      this.watcher = fs.watch(dir, (_ev, fn) => {
        if (!fn || !fn.startsWith(stem)) return;
        if (Date.now() < this.quietUntil) return;   // fue nuestra propia lectura: ignora
        clearTimeout(this.pend);
        this.pend = setTimeout(() => { if (Date.now() >= this.quietUntil) this.load(); }, 700);
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
  const nonce = crypto.randomBytes(16).toString("base64");
  const uri = (f: string) =>
    webview.asWebviewUri(vscode.Uri.file(path.join(ctx.extensionPath, "media", f)));
  const csp = `default-src 'none'; style-src ${webview.cspSource} 'unsafe-inline'; `
    + `script-src 'nonce-${nonce}';`;
  // Idioma del visor = el de VS Code (es/en). La comunidad es bilingüe; por defecto
  // inglés, español si VS Code está en español. El webview lee document.documentElement.lang.
  const lang = vscode.env.language.toLowerCase().startsWith("es") ? "es" : "en";
  let page = fs.readFileSync(path.join(ctx.extensionPath, "media", "viewer.html"), "utf8");
  return page
    .replace(/%CSP%/g, csp)
    .replace(/%NONCE%/g, nonce)
    .replace(/%LANG%/g, lang)
    .replace(/%SCRIPT%/g, String(uri("viewer.js")))
    .replace(/%STYLE%/g, String(uri("viewer.css")));
}

/** El panel ancho, a un lado del editor (bueno para el mapa). */
class Panel {
  private static current: { ctrl: Controller; panel: vscode.WebviewPanel } | undefined;

  static show(ctx: vscode.ExtensionContext) {
    if (Panel.current) { Panel.current.panel.reveal(); Panel.current.ctrl.load(); return; }
    const panel = vscode.window.createWebviewPanel(
      "hipercampoViewer", hostMessages(vscode.env.language).panelTitle, vscode.ViewColumn.Beside,
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
  status.text = "$(database) Hipercampo";
  status.tooltip = hostMessages(vscode.env.language).statusTooltip;
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
