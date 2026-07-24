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

async function fetchGraph(): Promise<{ memories: Memory[]; edges: any[]; scope: string }> {
  const all = cfg().get<boolean>("allNamespaces");
  const args = ["graph"];
  if (all) args.push("--all-namespaces");
  const out = await run(args);
  const data = JSON.parse(out);
  const scope = data.all_namespaces ? "todos los contextos" : `contexto «${data.namespace}»`;
  return { memories: data.nodes || [], edges: data.edges || [], scope };
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

class Viewer {
  private static current: Viewer | undefined;
  private readonly panel: vscode.WebviewPanel;

  static show(context: vscode.ExtensionContext) {
    if (Viewer.current) {
      Viewer.current.panel.reveal();
      Viewer.current.load();
      return;
    }
    const panel = vscode.window.createWebviewPanel(
      "hipercampoViewer", "hipercampo — memoria",
      vscode.ViewColumn.Beside,   // a un lado del editor actual, no como pestaña central
      { enableScripts: true, retainContextWhenHidden: true });
    Viewer.current = new Viewer(panel, context);
  }

  static refresh() {
    Viewer.current?.load();
  }

  constructor(panel: vscode.WebviewPanel, private readonly ctx: vscode.ExtensionContext) {
    this.panel = panel;
    this.panel.webview.html = this.html();
    this.panel.onDidDispose(() => { Viewer.current = undefined; });
    this.panel.webview.onDidReceiveMessage(async (msg) => {
      try {
        if (msg.type === "ready" || msg.type === "refresh") {
          await this.load();
        } else if (msg.type === "setAllNamespaces") {
          await cfg().update("allNamespaces", !!msg.value, vscode.ConfigurationTarget.Global);
          await this.load();
        } else if (msg.type === "search") {
          // 'text' se filtra en el propio webview; aquí solo la búsqueda del agente.
          const hits = await agentSearch(msg.query, msg.mode === "muse" ? "muse" : "recall");
          this.post({ type: "search-result", memories: hits, query: msg.query, mode: msg.mode });
        } else if (msg.type === "mutate") {
          const changed = await mutate(msg.id, msg.namespace, msg.action);
          if (changed) { await this.load(); }
        }
      } catch (e: any) {
        this.post({ type: "error", message: e.message || String(e) });
      }
    });
  }

  private post(m: any) { this.panel.webview.postMessage(m); }

  private async load() {
    try {
      // Un solo fetch: `graph` trae nodos Y aristas; todas las pestañas se pintan
      // en cliente desde ahí (lista/tiempo/ejes usan nodos; el mapa, nodos+aristas).
      const { memories, edges, scope } = await fetchGraph();
      this.post({ type: "data", memories, edges, scope });
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    }
  }

  private html(): string {
    const w = this.panel.webview;
    const nonce = String(Math.random()).slice(2);
    const uri = (f: string) =>
      w.asWebviewUri(vscode.Uri.file(path.join(this.ctx.extensionPath, "media", f)));
    const csp = `default-src 'none'; style-src ${w.cspSource} 'unsafe-inline'; `
      + `script-src 'nonce-${nonce}';`;
    // El HTML base vive en media/viewer.html; se inyecta CSP, nonce y las URIs.
    let page = fs.readFileSync(
      path.join(this.ctx.extensionPath, "media", "viewer.html"), "utf8");
    page = page
      .replace(/%CSP%/g, csp)
      .replace(/%NONCE%/g, nonce)
      .replace(/%SCRIPT%/g, String(uri("viewer.js")))
      .replace(/%STYLE%/g, String(uri("viewer.css")));
    return page;
  }
}

/** Vista vacía en la barra de actividad: solo sostiene el botón de bienvenida
 * (viewsWelcome) que abre el visor. No lista nada por sí misma. */
class HomeProvider implements vscode.TreeDataProvider<never> {
  getTreeItem(): vscode.TreeItem { return new vscode.TreeItem(""); }
  getChildren(): never[] { return []; }
}

export function activate(context: vscode.ExtensionContext) {
  // Botón siempre visible en la barra de estado (abajo): un clic abre el visor.
  const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  status.text = "$(database) memoria";
  status.tooltip = "hipercampo: ver memorias";
  status.command = "hipercampo.showMemories";
  status.show();

  context.subscriptions.push(
    status,
    vscode.window.registerTreeDataProvider("hipercampo.home", new HomeProvider()),
    vscode.commands.registerCommand("hipercampo.showMemories", () => Viewer.show(context)),
    vscode.commands.registerCommand("hipercampo.refresh", () => Viewer.refresh()),
  );
}

export function deactivate() { /* nada que limpiar: el visor no abre recursos propios */ }
