"use strict";

// Aggregates the V8 coverage the e2e run collected and reports how much of
// viewer.js it executed.
//
//   npm run coverage        (runs the suite with collection on, then reports)
//
// It reports LINES, not V8's byte ranges: bytes flatter the number, because a long
// untouched line counts the same as a short one. Lines are what a reader assumes
// when they see a percentage.

const fs = require("fs");
const path = require("path");

const TMP = path.join(__dirname, "..", "coverage-tmp");
const FLOOR = Number(process.env.VIEWER_COVERAGE_FLOOR || 0);

function uncoveredOffsets(entries) {
  /**
   * Byte ranges that did NOT run, intersected across every test.
   *
   * V8 reports the whole script as one executed range and nests the parts that did
   * NOT run inside it with `count: 0`. Collecting the `count > 0` ranges therefore
   * marks the entire file as covered — the first version of this script reported a
   * perfect 100%, which is how the mistake was noticed.
   *
   * A byte is uncovered only if EVERY test left it uncovered, so the runs add up
   * instead of each one capping the total.
   */
  let shared = null;
  for (const entry of entries) {
    const zero = [];
    for (const fn of entry.functions || []) {
      for (const r of fn.ranges || []) {
        if (r.count === 0) zero.push([r.startOffset, r.endOffset]);
      }
    }
    const asSet = (rs) => {
      const s = new Set();
      for (const [a, b] of rs) for (let i = a; i < b; i++) s.add(i);
      return s;
    };
    const here = asSet(zero);
    if (shared === null) shared = here;
    else for (const b of [...shared]) if (!here.has(b)) shared.delete(b);
  }
  return shared || new Set();
}

function lineCoverage(source, uncovered) {
  /** A line counts as covered when any byte of it ran in at least one test. */
  const lines = source.split("\n");
  let offset = 0, total = 0, done = 0;
  for (const line of lines) {
    const start = offset;
    offset += line.length + 1;
    const t = line.trim();
    // Blank lines and pure comments are not executable and would only pad the number.
    if (!t || t.startsWith("//") || t.startsWith("*") || t.startsWith("/*")) continue;
    total++;
    let ran = false;
    for (let i = start; i < start + line.length; i++) {
      if (!uncovered.has(i)) { ran = true; break; }
    }
    if (ran) done++;
  }
  return { total, done };
}

function main() {
  if (!fs.existsSync(TMP)) {
    console.error("No coverage collected. Run: npm run coverage");
    process.exit(1);
  }
  const files = fs.readdirSync(TMP).filter((f) => f.endsWith(".json"));
  if (!files.length) {
    console.error("No coverage collected. Run: npm run coverage");
    process.exit(1);
  }
  const entries = files.flatMap((f) => JSON.parse(fs.readFileSync(path.join(TMP, f), "utf8")));
  const source = entries[0].source;
  const { total, done } = lineCoverage(source, uncoveredOffsets(entries));
  const pct = total ? (100 * done / total) : 0;
  console.log(`viewer.js  ${done}/${total} executable lines  ${pct.toFixed(1)}%`);
  console.log(`(from ${files.length} test runs)`);
  // Written for scripts/badges.py, so the badge is generated from a measurement
  // rather than typed by hand.
  fs.writeFileSync(path.join(TMP, "summary.json"),
    JSON.stringify({ pct: Number(pct.toFixed(1)), covered: done, total }, null, 2) + "\n");
  if (FLOOR && pct < FLOOR) {
    console.error(`::error::viewer coverage ${pct.toFixed(1)}% is below the floor of ${FLOOR}%`);
    process.exit(1);
  }
}

main();
