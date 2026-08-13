import * as vscode from "vscode";
import { execFile } from "child_process";
import * as path from "path";
import * as fs from "fs";
import * as os from "os";
import * as crypto from "crypto";
import { hostMessages } from "./i18n";

/**
 * Hipercampo memory viewer. It neither talks to SQLite nor knows the schema: it calls
 * the `hipercampo` CLI (which already handles namespaces and isolation) and renders
 * its output. This prevents the viewer from corrupting data: it is read-only by design.
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

/** Split "python -m hipercampo.cli" into an executable and base arguments. */
function split(raw: string): { exe: string; prefix: string[] } {
  const parts = raw.trim().split(/\s+/);
  return { exe: parts[0], prefix: parts.slice(1) };
}

// Candidates to try when the default command is not on PATH. VS Code launched from
// a menu (rather than a terminal) does not inherit the shell's PATH, so a bare
// `hipercampo` is often unavailable even when installed; `python -m hipercampo.cli`
// still works when the package is installed in that Python environment.
const FALLBACKS = ["python -m hipercampo.cli", "python3 -m hipercampo.cli",
  "py -m hipercampo.cli"];

// Cache the command known to work so each invocation does not retry every candidate.
let resolved: string | undefined;

function candidates(): string[] {
  const conf = (cfg().get<string>("command") || "hipercampo").trim();
  // Honor an explicit non-default command without guessing alternatives.
  if (conf && conf !== "hipercampo") return [conf];
  return [conf, ...FALLBACKS];
}

function childEnv(): NodeJS.ProcessEnv {
  // Do not set HIPERCAMPO_LOG=0. Auditing writes to stderr and the log file, never to
  // stdout (execFile keeps them separate), so JSON remains clean. LOG=0 also removes
  // the log path and would prevent the Log tab from reading it ("log disabled" plus
  // exit code 1 becomes a viewer error).
  const env: NodeJS.ProcessEnv = { ...process.env };
  const db = (cfg().get<string>("dbPath") || "").trim();
  const ns = (cfg().get<string>("namespace") || "").trim();
  const linked = cfg().get<string>("linked");
  if (db) env.HIPERCAMPO_DB = db;
  if (ns) env.HIPERCAMPO_NAMESPACE = ns;
  // An explicit empty string means "no linked contexts", overriding whatever the
  // MCP server's own env has; only an untouched (undefined) setting leaves it alone.
  if (linked !== undefined) env.HIPERCAMPO_LINKED = linked;
  return env;
}

/** Run one concrete command. `notFound` distinguishes a missing executable (try the
 * next candidate) from a genuine command failure (report it). */
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

/** Run the CLI, trying the cached command or candidates until one exists. Reject with
 * a readable message when none is found or a real invocation fails. */
async function run(args: string[]): Promise<string> {
  const commands = resolved ? [resolved, ...candidates()] : candidates();
  let lastFailure = "";
  for (const cmd of commands) {
    const r = await tryRun(cmd, args);
    if ("out" in r) { resolved = cmd; return r.out; }
    if ("fail" in r) lastFailure = r.fail;   // The executable exists: this is a real error.
  }
  if (lastFailure) throw new Error(lastFailure);
  throw new Error(hostMessages(vscode.env.language).commandNotFound);
}

// --- ambient value: make memory visible in the status bar ---------------------------
// There is no telemetry: owners see their own "bill" and savings. Values come from
// the `tokens` CLI command (which reads the auditable log), with no new counters or writes.
let statusItem: vscode.StatusBarItem | undefined;

function kfmt(n: number): string {
  if (n >= 1000) return (n / 1000).toFixed(n >= 10000 ? 0 : 1).replace(/\.0$/, "") + "k";
  return String(n);
}

async function refreshValue(): Promise<void> {
  if (!statusItem) return;
  const t = hostMessages(vscode.env.language);
  try {
    const s = (JSON.parse(await run(["tokens"])).summary) || {};
    const saved = Number(s.saved_by_budget || 0);
    if (saved > 0 || Number(s.injections || 0) > 0) {
      statusItem.text = `$(database) ${t.statusValue(kfmt(saved))}`;
      statusItem.tooltip = t.valueTooltip(Number(s.injections || 0), Number(s.total || 0),
        saved, Number(s.today || 0));
    } else {
      statusItem.text = "$(database) Hipercampo";
      statusItem.tooltip = t.statusTooltip;
    }
  } catch {
    // Without the CLI or log, keep a quiet, simple status marker.
    statusItem.text = "$(database) Hipercampo";
    statusItem.tooltip = t.statusTooltip;
  }
}

async function fetchGraph(): Promise<{ memories: Memory[]; edges: any[]; scope: string; db?: string; paused?: boolean }> {
  // The viewer ALWAYS fetches every context; the chips select one or all client-side.
  // Consequently, clearing "all contexts" never empties the screen by fetching a
  // namespace that may not exist.
  const path = projectPath();
  const out = await run(path ? ["graph", "--all-namespaces", "--project", path]
                              : ["graph", "--all-namespaces"]);
  const data = JSON.parse(out);
  const scope = hostMessages(vscode.env.language).allContexts;
  return { memories: data.nodes || [], edges: data.edges || [], scope, db: data.db, paused: !!data.paused };
}

// Search "like the agent": recall (direct and able to abstain) or muse (creative,
// including associated and dormant memories—the "eureka" path). Both use the
// environment's namespace.
async function agentSearch(query: string, mode: "recall" | "recall-auto" | "recall-nav" | "muse"): Promise<Memory[]> {
  const args = mode === "recall-nav" ? ["recall", "--nav", query]
    : mode === "recall-auto" ? ["recall", "--nav-auto", query]
    : [mode, query];
  const out = await run(args);
  const hits = JSON.parse(out);
  return Array.isArray(hits) ? hits : [];
}

// Health status for the CLI, database, MCP server, and log: whether the engine is
// alive, not merely what it stores.
// --- per-project opt-in ---------------------------------------------------------
// hipercampo starts switched off in a project until someone says yes. The path is
// passed EXPLICITLY on every call: `run()` uses execFile without `cwd`, so the CLI
// inherits the extension host's working directory, which is not the workspace. A
// bare `hipercampo enable` from here would register the wrong directory.
function projectPath(): string | undefined {
  return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath;
}

async function fetchProject(): Promise<any> {
  const path = projectPath();
  if (!path) return { none: true };          // no folder open: nothing to enable
  return JSON.parse(await run(["projects", "--json", path]));
}

async function fetchStatus(): Promise<any> {
  const path = projectPath();
  const out = await run(path ? ["status", "--project", path] : ["status"]);
  return JSON.parse(out);
}

// Structured decision log (recall/remember/sleep/forget/tokens, etc.).
async function fetchLog(): Promise<any> {
  const out = await run(["log", "-n", "300", "--json"]);
  return JSON.parse(out);
}

// A short tail for the ambient activity footer: cheap enough to fetch on every
// reload (debounced by the watcher already), unlike the full 300-entry Log tab.
async function fetchActivityTail(): Promise<any[]> {
  const out = await run(["log", "-n", "20", "--json"]);
  const data = JSON.parse(out);
  return data.entries || [];
}

// The token bill: aggregate plus time series, making this defining feature visible.
async function fetchTokens(): Promise<any> {
  const out = await run(["tokens"]);
  return JSON.parse(out);
}

// Ideas: BRIDGES proposed by dreaming between distant memories with a common associate
// (hypotheses, not evidence). A dry run by design: displayed but never stored.
async function fetchIdeas(): Promise<any> {
  const out = await run(["dream", "--json", "--max", "12", "--all-namespaces"]);
  return JSON.parse(out);
}

// Structured facts (role records): the VSA differentiator, across every context.
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

// --- editing the REAL MCP server config (not just this extension's own setting) ----
// hipercampo.linked only steers the viewer's own CLI calls. The thing Armando actually
// asked for is editing HIPERCAMPO_LINKED where it really lives: the mcpServers entries
// in the workspace .mcp.json and the global ~/.claude.json that Claude itself reads.

interface LinkedTarget { file: string; server: string; }

/** A server counts as "hipercampo" when its env carries one of our variables — this
 * avoids guessing from `command`, which users are free to alias or wrap. */
function isHipercampoEnv(env: any): boolean {
  return !!env && ("HIPERCAMPO_NAMESPACE" in env || "HIPERCAMPO_LINKED" in env || "HIPERCAMPO_DB" in env);
}

function collectServers(servers: any, file: string, out: LinkedTarget[]): void {
  if (!servers || typeof servers !== "object") return;
  for (const name of Object.keys(servers)) {
    if (isHipercampoEnv(servers[name]?.env)) out.push({ file, server: name });
  }
}

/** Every hipercampo MCP server this machine knows about: the project's .mcp.json and
 * the global ~/.claude.json (both its top-level mcpServers and, for older layouts,
 * the per-project mcpServers under projects[cwd]). Files that don't exist or don't
 * parse are skipped silently — a missing .mcp.json is normal, not an error. */
function findLinkedTargets(): LinkedTarget[] {
  const out: LinkedTarget[] = [];
  const wsFolder = projectPath();
  const candidateFiles = [
    wsFolder ? path.join(wsFolder, ".mcp.json") : undefined,
    path.join(os.homedir(), ".claude.json"),
  ].filter((f): f is string => !!f);
  for (const file of candidateFiles) {
    try {
      const data = JSON.parse(fs.readFileSync(file, "utf8"));
      collectServers(data.mcpServers, file, out);
      if (wsFolder) collectServers(data.projects?.[wsFolder]?.mcpServers, file, out);
    } catch { /* No file, or not JSON we understand: nothing to offer for it. */ }
  }
  return out;
}

function readLinkedValue(target: LinkedTarget): string {
  try {
    const data = JSON.parse(fs.readFileSync(target.file, "utf8"));
    const env = data.mcpServers?.[target.server]?.env
      ?? data.projects?.[projectPath() || ""]?.mcpServers?.[target.server]?.env;
    return env?.HIPERCAMPO_LINKED || "";
  } catch { return ""; }
}

/** Detect the file's own indent so a rewrite doesn't turn a two-space file into a
 * four-space diff noise-fest; JSON.stringify needs a width, not the original text. */
function detectIndent(raw: string): number {
  const m = raw.match(/\n( +)"/);
  return m ? m[1].length : 2;
}

/** Write HIPERCAMPO_LINKED into one server's env, in place. A timestamped backup is
 * written first because ~/.claude.json is Claude's own config, not ours: if something
 * about this rewrite is wrong, the fix is "restore the backup", not "lose settings". */
function writeLinkedValue(target: LinkedTarget, value: string): void {
  const raw = fs.readFileSync(target.file, "utf8");
  const data = JSON.parse(raw);
  const apply = (servers: any): boolean => {
    if (!servers?.[target.server]) return false;
    const server = servers[target.server];
    server.env = server.env || {};
    if (value) server.env.HIPERCAMPO_LINKED = value;
    else delete server.env.HIPERCAMPO_LINKED;
    return true;
  };
  const wsFolder = projectPath();
  const done = apply(data.mcpServers)
    || (wsFolder ? apply(data.projects?.[wsFolder]?.mcpServers) : false);
  if (!done) throw new Error(`Server "${target.server}" not found in ${target.file}`);
  fs.writeFileSync(`${target.file}.bak-hipercampo`, raw, "utf8");
  const indent = detectIndent(raw);
  fs.writeFileSync(target.file, JSON.stringify(data, null, indent) + "\n", "utf8");
}

/** Edit HIPERCAMPO_LINKED where it actually lives: the real MCP server configs
 * (.mcp.json / ~/.claude.json), not a copy inside this extension's own settings. */
async function editLinked(): Promise<boolean> {
  const text = hostMessages(vscode.env.language);
  const targets = findLinkedTargets();

  if (!targets.length) {
    // No known hipercampo MCP server on this machine/workspace: fall back to the
    // viewer's own setting so the CLI calls it makes are still consistent.
    const current = cfg().get<string>("linked") || "";
    const value = await vscode.window.showInputBox({
      prompt: text.editLinkedPrompt, placeHolder: text.editLinkedPlaceholder, value: current,
    });
    if (value === undefined) return false;
    const trimmed = value.trim();
    await cfg().update("linked", trimmed, vscode.ConfigurationTarget.Global);
    vscode.window.showInformationMessage(text.linkedUpdated(trimmed));
    return true;
  }

  let picks = targets;
  if (targets.length > 1) {
    const items = targets.map((t) => ({
      label: t.server, description: t.file, picked: true, target: t,
    }));
    const selected = await vscode.window.showQuickPick(items,
      { canPickMany: true, placeHolder: text.chooseServers });
    if (!selected?.length) return false;
    picks = selected.map((s) => s.target);
  }

  const current = readLinkedValue(picks[0]);
  const value = await vscode.window.showInputBox({
    prompt: text.editLinkedPrompt, placeHolder: text.editLinkedPlaceholder, value: current,
  });
  if (value === undefined) return false;
  const trimmed = value.trim();

  const failed: string[] = [];
  for (const t of picks) {
    try { writeLinkedValue(t, trimmed); } catch (e: any) { failed.push(`${t.server}: ${e.message || e}`); }
  }
  if (failed.length) vscode.window.showErrorMessage(text.linkedWriteError(failed.join("; ")));
  const ok = picks.length - failed.length;
  if (ok > 0) vscode.window.showInformationMessage(text.linkedUpdatedFiles(trimmed, ok));
  return ok > 0;
}
/** Move a memory to another context (curation). Ask for an existing or new destination.
 * The operation is reversible, so it does not require a modal confirmation. */
async function reclassify(id: number, namespace: string | undefined): Promise<boolean> {
  const source = namespace || "default";
  let nss: string[] = [];
  try {
    const data = JSON.parse(await run(["graph", "--all-namespaces"]));
    nss = [...new Set((data.nodes || []).map((n: any) => n.namespace))]
      .filter((n): n is string => typeof n === "string" && n !== source).sort();
  } catch { /* A new context can still be entered when the list is unavailable. */ }
  const text = hostMessages(vscode.env.language);
  const NEW_CONTEXT = text.newContext;
  const pick = await vscode.window.showQuickPick([...nss, NEW_CONTEXT], {
    placeHolder: text.moveFrom(source),
  });
  if (!pick) return false;
  let destination: string | undefined = pick;
  if (pick === NEW_CONTEXT) {
    destination = (await vscode.window.showInputBox({
      prompt: text.targetContextName,
    }))?.trim();
  }
  if (!destination) return false;
  await run(["reclassify", "--ids", String(id), "--to", destination, "--namespace", source]);
  return true;
}

/** Put a memory to sleep, wake it, or purge it after confirmation. Return true on change. */
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
  // Purging is physical and irreversible: require MODAL confirmation first.
  const text = hostMessages(vscode.env.language);
  const ok = await vscode.window.showWarningMessage(
    text.purgePrompt(id), { modal: true }, text.purgeAction);
  if (ok !== text.purgeAction) return false;
  await run(["purge", "--ids", String(id), "--yes", ...nsArgs]);
  return true;
}

/** Shared logic for BOTH viewer surfaces (the editor panel and Activity Bar view):
 * render HTML, handle webview messages, and refresh automatically when the .db file
 * changes so users do not need to close and reopen it. */
class Controller {
  private db: string | undefined;
  private watcher: fs.FSWatcher | undefined;
  private pend: NodeJS.Timeout | undefined;
  private quietUntil = 0;   // Ignore watcher events until this time (see below).
  private readonly disposables: vscode.Disposable[] = [];
  // Ambient activity footer: `undefined` means "not baselined yet" (the first
  // load sets it silently, so opening the viewer doesn't dump the whole recent
  // history into the footer at once).
  private lastActivityRaw: string | undefined | null = undefined;

  constructor(private readonly webview: vscode.Webview,
              private readonly ctx: vscode.ExtensionContext) {
    webview.options = { enableScripts: true };
    webview.html = html(webview, ctx);
    this.disposables.push(webview.onDidReceiveMessage((m) => this.onMessage(m)));
  }

  private post(m: any) { this.webview.postMessage(m); }

  // Critical CPU-loop guard: every viewer command opens the database in WAL mode,
  // touching -wal/-shm. The watcher would see that as a change and trigger another
  // reload forever. Mute it briefly after each operation so it reacts only to EXTERNAL
  // changes (the agent or another session), not to our own reads.
  private muteWatcher() { this.quietUntil = Date.now() + 1500; }

  private async onMessage(msg: any) {
    this.muteWatcher();
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
        const path = projectPath();
        const cmd = msg.value ? "pause" : "resume";
        await run(path ? [cmd, path] : [cmd]);
        await this.load();
      } else if (msg.type === "setProjectEnabled") {
        const path = projectPath();
        if (!path) {
          vscode.window.showInformationMessage(
            hostMessages(vscode.env.language).noFolderOpen);
        } else {
          await run([msg.value ? "enable" : "disable", path]);
          this.post({ type: "project", data: await fetchProject() });
        }
      } else if (msg.type === "backup") {
        const out = (await run(["backup"])).trim();
        vscode.window.showInformationMessage(out || hostMessages(vscode.env.language).backupCreated);
        this.post({ type: "status", data: await fetchStatus() });   // Refresh sizes.
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
        this.post({ type: "status", data: await fetchStatus() });   // Refresh the list.
      } else if (msg.type === "set-budget") {
        await run(msg.reset ? ["budget", "--reset"] : ["budget", "--set", String(msg.value)]);
        this.post({ type: "tokens", data: await fetchTokens() });
      } else if (msg.type === "reindex") {
        const out = JSON.parse(await run(["reindex", "--neighbors", "4", "--all-namespaces"]));
        vscode.window.showInformationMessage(
          hostMessages(vscode.env.language).graphWoven(out.links_woven ?? 0));
        await this.load();                              // Refresh the now-dense map.
      }
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    }
  }

  async load() {
    this.muteWatcher();
    try {
      // One fetch: `graph` returns nodes, edges, and the .db PATH to watch.
      const { memories, edges, scope, db, paused } = await fetchGraph();
      this.post({ type: "data", memories, edges, scope, paused });
      // Opt-in state travels with every load: whether hipercampo is even acting
      // here is the first thing someone opening the viewer needs to know.
      this.post({ type: "project", data: await fetchProject() });
      if (db && db !== this.db) { this.db = db; this.watchDatabase(db); }
      void refreshValue();   // Fresh data also updates the status-bar value.
      void this.postActivity();
    } catch (e: any) {
      this.post({ type: "error", message: e.message || String(e) });
    } finally {
      this.muteWatcher();   // The read touched -wal/-shm; do not trigger on it again.
    }
  }

  // Pushes only NEW log entries since the last load, for the ambient footer.
  // Cosmetic: a failure here must never surface as a viewer error.
  private async postActivity(): Promise<void> {
    try {
      const entries = await fetchActivityTail();
      if (!entries.length) return;
      if (this.lastActivityRaw === undefined) {
        this.lastActivityRaw = entries[entries.length - 1].raw;   // baseline only
        return;
      }
      const idx = this.lastActivityRaw === null ? -1
        : entries.findIndex((e: any) => e.raw === this.lastActivityRaw);
      // Not found (log rotated, or baseline was "empty"): still new, but capped
      // so a rotation cannot dump a burst of stale-looking entries at once.
      const fresh = (idx >= 0 ? entries.slice(idx + 1) : entries).slice(-5);
      this.lastActivityRaw = entries[entries.length - 1].raw;
      if (fresh.length) this.post({ type: "activity", entries: fresh });
    } catch { /* no-op: the footer is decoration, not a source of errors */ }
  }

  // Watch the .db file and reload when the agent or another session changes it.
  // Debounce because one SQLite WAL write emits several events.
  private watchDatabase(db: string) {
    this.watcher?.close();
    try {
      const dir = path.dirname(db);
      // The extensionless stem covers .db, .db-wal, .db-shm, AND .log in the same
      // directory, so the live log refreshes too.
      const stem = path.basename(db).replace(/\.db$/, "");
      this.watcher = fs.watch(dir, (_ev, fn) => {
        if (!fn || !fn.startsWith(stem)) return;
        if (Date.now() < this.quietUntil) return;   // Ignore our own read.
        clearTimeout(this.pend);
        this.pend = setTimeout(() => { if (Date.now() >= this.quietUntil) this.load(); }, 700);
      });
    } catch { /* The ↻ button remains available when watching is unavailable. */ }
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
  // Viewer language follows VS Code (es/en). This bilingual community defaults to
  // English and uses Spanish when VS Code does. The webview reads the document lang.
  const lang = vscode.env.language.toLowerCase().startsWith("es") ? "es" : "en";
  let page = fs.readFileSync(path.join(ctx.extensionPath, "media", "viewer.html"), "utf8");
  return page
    .replace(/%CSP%/g, csp)
    .replace(/%NONCE%/g, nonce)
    .replace(/%LANG%/g, lang)
    .replace(/%SCRIPT%/g, String(uri("viewer.js")))
    .replace(/%STYLE%/g, String(uri("viewer.css")));
}

/** The wide panel beside the editor, well suited to the map. */
class Panel {
  private static current: { ctrl: Controller; panel: vscode.WebviewPanel } | undefined;

  static show(ctx: vscode.ExtensionContext) {
    if (Panel.current) { Panel.current.panel.reveal(); Panel.current.ctrl.load(); return; }
    const panel = vscode.window.createWebviewPanel(
      "hipercampoViewer", hostMessages(vscode.env.language).panelTitle, vscode.ViewColumn.Beside,
      { enableScripts: true, retainContextWhenHidden: true });
    const ctrl = new Controller(panel.webview, ctx);
    Panel.current = { ctrl, panel };
    // Refresh on refocus in case something changed while the panel was hidden.
    panel.onDidChangeViewState((e) => { if (e.webviewPanel.visible) ctrl.load(); });
    panel.onDidDispose(() => { ctrl.dispose(); Panel.current = undefined; });
  }

  static refresh() { Panel.current?.ctrl.load(); }
}

/** The SAME memory inside the Activity Bar (left strip): its icon opens the complete
 * viewer there, rather than a message containing a button. */
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
  // The always-visible bottom status-bar button opens the wide panel. Its text makes
  // the VALUE (how much memory saved) visible without pop-ups.
  statusItem = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
  statusItem.text = "$(database) Hipercampo";
  statusItem.tooltip = hostMessages(vscode.env.language).statusTooltip;
  statusItem.command = "hipercampo.showMemories";
  statusItem.show();
  void refreshValue();                               // At startup.
  const valueTimer = setInterval(() => void refreshValue(), 60000);   // Live, without noise.

  context.subscriptions.push(
    statusItem,
    new vscode.Disposable(() => clearInterval(valueTimer)),
    vscode.window.registerWebviewViewProvider("hipercampo.home", new SidebarProvider(context),
      { webviewOptions: { retainContextWhenHidden: true } }),
    vscode.commands.registerCommand("hipercampo.showMemories", () => Panel.show(context)),
    vscode.commands.registerCommand("hipercampo.refresh", () => Panel.refresh()),
    vscode.commands.registerCommand("hipercampo.editLinked", async () => {
      if (await editLinked()) { resolved = undefined; Panel.refresh(); }
    }),
  );
}

export function deactivate() { /* No global cleanup: each viewer releases its resources. */ }
