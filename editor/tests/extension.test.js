"use strict";

// Contract test for the extension HOST (src/extension.ts), which had no coverage at
// all: everything it does is shell out to the `hipercampo` CLI via `execFile`, which
// runs WITHOUT `cwd` (see the comment at extension.ts's `projectPath()`). That already
// bit `enable`/`disable` once, and bit `pause`/`resume` a second time (2026-08-13):
// every command whose effect is scoped to a project must pass that project's path
// EXPLICITLY as an argument, or it silently affects every project sharing the DB.
//
// This test does not launch real VS Code. It mocks the `vscode` module (only the
// surface extension.ts actually touches) and `child_process.execFile`, then drives
// the sidebar webview provider exactly as VS Code would: resolve the view, feed it
// messages, and inspect which CLI argv each message produced.

const assert = require("node:assert/strict");
const Module = require("node:module");
const path = require("node:path");
const cp = require("node:child_process");

const PROJECT = process.platform === "win32" ? "C:\\work\\myproject" : "/work/myproject";

// --- capture every execFile call instead of spawning a real process ---------------
const calls = [];
/** Queue of canned responses; each command pops the next one (default: "{}"). */
const responses = [];
cp.execFile = function execFile(exe, args, _opts, cb) {
  calls.push({ exe, args });
  const next = responses.length ? responses.shift() : { out: "{}" };
  process.nextTick(() => {
    if (next.err) return cb(next.err, "", next.err.message);
    cb(null, next.out, "");
  });
};

// --- minimal vscode mock: only what extension.ts references -----------------------
const registered = { providers: {}, commands: {} };
let workspaceFolders;
const vscodeMock = {
  workspace: {
    getConfiguration: () => ({ get: () => undefined, update: async () => {} }),
    get workspaceFolders() { return workspaceFolders; },
    openTextDocument: async () => ({}),
  },
  window: {
    registerWebviewViewProvider: (id, provider) => { registered.providers[id] = provider; return { dispose() {} }; },
    createStatusBarItem: () => ({ show() {}, hide() {}, dispose() {} }),
    createWebviewPanel: () => ({
      webview: { onDidReceiveMessage() {}, postMessage: async () => true, options: {}, html: "" },
      onDidDispose() {}, onDidChangeViewState() {}, reveal() {},
    }),
    showErrorMessage: async () => undefined,
    showInformationMessage: async () => undefined,
    showWarningMessage: async () => undefined,
    showInputBox: async () => undefined,
    showOpenDialog: async () => undefined,
    showQuickPick: async () => undefined,
    showTextDocument: async () => undefined,
  },
  commands: { registerCommand: (id, fn) => { registered.commands[id] = fn; return { dispose() {} }; } },
  env: { language: "en", openExternal: async () => true },
  Uri: { file: (p) => ({ fsPath: p }), parse: (s) => ({ toString: () => s }) },
  ViewColumn: { Beside: 2 },
  StatusBarAlignment: { Left: 1 },
  ConfigurationTarget: { Global: 1 },
  Disposable: class Disposable { constructor(fn) { this._fn = fn; } dispose() { this._fn?.(); } },
};

const originalLoad = Module._load;
Module._load = function (request, parent, isMain) {
  if (request === "vscode") return vscodeMock;
  return originalLoad.call(this, request, parent, isMain);
};
let ext;
try {
  ext = require("../out/extension.js");
} finally {
  Module._load = originalLoad;   // only the load of extension.js (and its requires) needs the mock
}

// --- activate, exactly like VS Code would ------------------------------------------
const context = { subscriptions: [], extensionPath: path.join(__dirname, ".."), extensionUri: { fsPath: path.join(__dirname, "..") } };
ext.activate(context);

const provider = registered.providers["hipercampo.home"];
assert.ok(provider, "the sidebar webview provider must be registered as hipercampo.home");

function makeView() {
  let handler;
  const webview = {
    options: undefined,
    html: undefined,
    asWebviewUri: (u) => u,
    cspSource: "",
    onDidReceiveMessage(fn) { handler = fn; return { dispose() {} }; },
    postMessage: async () => true,
  };
  const view = { webview, onDidChangeVisibility() {}, onDidDispose() {}, visible: true };
  provider.resolveWebviewView(view, {}, undefined);
  return { send: (m) => handler(m) };
}

function lastCallArgs(command) {
  const hit = [...calls].reverse().find((c) => c.args[0] === command);
  return hit && hit.args;
}

async function run() {
  // --- with a workspace folder open, project-scoped commands must carry its path ---
  workspaceFolders = [{ uri: { fsPath: PROJECT } }];
  calls.length = 0;
  const { send } = makeView();

  responses.push({ out: JSON.stringify({ nodes: [], edges: [], paused: false }) }); // graph
  responses.push({ out: JSON.stringify({}) });                                     // project
  await send({ type: "ready" });
  const graphArgs = lastCallArgs("graph");
  assert.ok(graphArgs, "load() must call the graph command");
  assert.ok(graphArgs.includes("--project") && graphArgs.includes(PROJECT),
    `graph must pass --project ${PROJECT}, got ${JSON.stringify(graphArgs)}`);

  calls.length = 0;
  responses.push({ out: JSON.stringify({}) });                                     // status
  await send({ type: "status-request" });
  const statusArgs = lastCallArgs("status");
  assert.ok(statusArgs, "status-request must call the status command");
  assert.ok(statusArgs.includes("--project") && statusArgs.includes(PROJECT),
    `status must pass --project ${PROJECT}, got ${JSON.stringify(statusArgs)}`);

  calls.length = 0;
  responses.push({ out: "{}" });                                                   // pause
  responses.push({ out: JSON.stringify({ nodes: [], edges: [], paused: true }) }); // graph (reload)
  responses.push({ out: JSON.stringify({}) });                                     // project (reload)
  await send({ type: "setPaused", value: true });
  const pauseArgs = lastCallArgs("pause");
  assert.ok(pauseArgs, "setPaused(true) must call the pause command");
  assert.ok(pauseArgs.includes(PROJECT),
    `pause must pass the project path explicitly, got ${JSON.stringify(pauseArgs)}`);

  calls.length = 0;
  responses.push({ out: "{}" });                                                   // resume
  responses.push({ out: JSON.stringify({ nodes: [], edges: [], paused: false }) }); // graph (reload)
  responses.push({ out: JSON.stringify({}) });                                     // project (reload)
  await send({ type: "setPaused", value: false });
  const resumeArgs = lastCallArgs("resume");
  assert.ok(resumeArgs, "setPaused(false) must call the resume command");
  assert.ok(resumeArgs.includes(PROJECT),
    `resume must pass the project path explicitly, got ${JSON.stringify(resumeArgs)}`);

  calls.length = 0;
  responses.push({ out: "{}" });                                                   // enable
  responses.push({ out: JSON.stringify({}) });                                     // project (reload)
  await send({ type: "setProjectEnabled", value: true });
  const enableArgs = lastCallArgs("enable");
  assert.ok(enableArgs && enableArgs.includes(PROJECT),
    `enable must pass the project path, got ${JSON.stringify(enableArgs)}`);

  // --- with NO workspace folder open, nothing must silently target the wrong dir ---
  workspaceFolders = undefined;
  calls.length = 0;
  const { send: send2 } = makeView();
  responses.push({ out: "{}" });
  await send2({ type: "setPaused", value: true });
  const noWsPauseArgs = lastCallArgs("pause");
  assert.ok(noWsPauseArgs, "pause must still run without a workspace (global CLI cwd)");
  assert.equal(noWsPauseArgs.length, 1,
    "with no workspace open, pause must not invent a path argument");

  console.log("extension host contract OK: pause/resume/graph/status/enable all pass the project path explicitly");
}

// activate() starts a 60s status-bar refresh timer that would otherwise keep this
// script (and `npm test`) alive; the test doesn't need it running.
run()
  .catch((e) => { console.error(e); process.exitCode = 1; })
  .finally(() => { context.subscriptions.forEach((d) => d.dispose?.()); });
