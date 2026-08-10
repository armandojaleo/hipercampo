"use strict";

// Shared harness for the viewer end-to-end tests, plus the coverage measurement.
//
// WHY THE PAGE IS LOADED FROM A FILE. The obvious approach, `page.setContent` with
// viewer.js inlined, works for assertions but reports ZERO coverage entries: V8
// does not instrument scripts injected that way. Written to a file and loaded over
// file:// with `<script src="viewer.js">`, the script has a URL and is measured —
// and it is also closer to how the real webview loads it.
//
// No new dependency: Chromium's V8 coverage already ships with Playwright, so
// nothing like c8 or nyc joins a project that counts its dependencies one by one.
//
// Coverage is collected DURING THE REAL TEST RUN, not by a separate script driving
// the viewer. A script's number would say what the script touched, not what the
// tests actually check — the kind of figure this project has been burned by.
//
// Enabled with VIEWER_COVERAGE=1; off by default so the normal run stays fast.

const fs = require("fs");
const path = require("path");
const base = require("@playwright/test");
const { SAMPLE, buildStandalone } = require("../../tools/preview");

const ON = process.env.VIEWER_COVERAGE === "1";
const MEDIA = path.join(__dirname, "..", "..", "media");
const OUT = path.join(__dirname, "..", "..", "coverage-tmp");
// Appears in viewer.js and nowhere else on the page, so the measured script can be
// told apart from the vscode-api stub and the data-feed snippet.
const MARKER = "function renderLog(";

/** Write the standalone page next to media/ so `src="viewer.js"` resolves. */
function writePage(language, view, data, theme) {
  const js = fs.readFileSync(path.join(MEDIA, "viewer.js"), "utf8");
  const html = buildStandalone(language, view, data, theme)
    .replace("<script>" + js + "</script>", '<script src="viewer.js"></script>');
  // Unique per worker: the suite runs fullyParallel, and a shared name would have
  // one test reading the file another was still writing.
  const file = path.join(MEDIA, `__e2e-${process.pid}-${Math.random().toString(36).slice(2)}.html`);
  fs.writeFileSync(file, html, "utf8");
  return file;
}

const test = base.test.extend({
  page: async ({ page }, use) => {
    if (ON) await page.coverage.startJSCoverage({ resetOnNavigation: false });
    await use(page);
    if (!ON) return;
    let entries = [];
    try {
      entries = await page.coverage.stopJSCoverage();
    } catch {
      return;                       // a closed page has nothing to report
    }
    const viewer = entries.filter((e) => (e.source || "").includes(MARKER));
    if (!viewer.length) return;
    fs.mkdirSync(OUT, { recursive: true });
    const name = `cov-${process.pid}-${Date.now()}-${Math.random().toString(36).slice(2)}.json`;
    fs.writeFileSync(path.join(OUT, name),
      JSON.stringify(viewer.map((e) => ({ source: e.source, functions: e.functions }))));
  },
});

/**
 * Open the real webview and return an array collecting any page error.
 * The temp file is removed once loaded; the browser already holds the content.
 */
async function openViewer(page, { language = "en", view = "list", data = SAMPLE } = {}) {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  const file = writePage(language, view, data, "dark");
  try {
    await page.goto("file:///" + path.resolve(file).split(path.sep).join("/"),
                    { waitUntil: "load" });
  } finally {
    fs.rmSync(file, { force: true });
  }
  return errors;
}

/** Push a host message in, exactly as the extension does. */
async function send(page, message) {
  await page.evaluate((m) => {
    window.dispatchEvent(new MessageEvent("message", { data: m }));
  }, message);
}

module.exports = { test, expect: base.expect, openViewer, send, SAMPLE };
