"use strict";

// Runs the e2e suite with V8 coverage collection on, then reports it.
// A script rather than an inline `npm` one-liner: the inline version needed shell
// quoting that behaved differently on Windows, which is exactly the platform this
// project keeps finding bugs on.

const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const ROOT = path.join(__dirname, "..");

// The Playwright CLI is invoked through node directly, not npx: Node 20+ refuses
// to spawn a .cmd without `shell: true` (EINVAL on Windows), and turning the shell
// on brings back quoting problems. This path works the same everywhere.
const CLI = path.join(ROOT, "node_modules", "@playwright", "test", "cli.js");

fs.rmSync(path.join(ROOT, "coverage-tmp"), { recursive: true, force: true });

execFileSync(process.execPath, [CLI, "test"], {
  cwd: ROOT, stdio: "inherit",
  env: { ...process.env, VIEWER_COVERAGE: "1" },
});

execFileSync(process.execPath, [path.join(__dirname, "coverage.js")], {
  cwd: ROOT, stdio: "inherit", env: process.env,
});
