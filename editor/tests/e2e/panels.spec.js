"use strict";

// Regression tests for the three bugs that actually SHIPPED through the viewer.
//
// All three were the same shape: the Python CLI emits JSON, the viewer reads it in
// JavaScript, and a renamed key breaks a panel SILENTLY — no exception, no failing
// test, just a value that renders empty or wrong.
//
// tests/contracts/test_viewer_json.py (Python side) checks the key NAMES line up.
// These check the other half: that the panel actually puts the value on screen. A
// contract test would not have caught a panel that reads the right key and then
// renders nothing.

const { test, expect, openViewer, send } = require("./fixture");

test("the token panel shows the counting method, not an empty hint", async ({ page }) => {
  // The bug: the CLI renamed `metodo` to `method` and the viewer kept reading
  // `s.metodo`, so this line rendered blank. Nothing failed; the note just vanished.
  const errors = await openViewer(page, { view: "tokens" });
  await send(page, {
    type: "tokens",
    data: {
      summary: {
        total: 65451, today: 890, injections: 160, saved_by_budget: 5929,
        avg_per_injection: 409, hook_budget: 350, identity_budget: 500,
        estimated: true, method: "estimated at 3.7 characters per token",
      },
      series: [{ ts: "2026-08-10 12:00:00", tok: 120, etiqueta: "injected" }],
    },
  });
  const hint = page.locator("#view-tokens .hint").last();
  await expect(hint).toContainText("3.7 characters per token");
  await expect(page.locator("#view-tokens")).toContainText("65451");
  expect(errors).toEqual([]);
});

test("the opt-in banner reflects the project state instead of always saying off",
  async ({ page }) => {
    // The bug (caught before shipping): the viewer read `PROJECT.enabled` while the
    // CLI emits `enabled_here`, so the banner would have claimed every project was
    // off, forever — with no error anywhere.
    const errors = await openViewer(page);
    const banner = page.locator("#optin-banner");

    await send(page, { type: "project",
                       data: { here: "/tmp/p", enabled_here: false, opt_in_adopted: true } });
    await expect(banner).toBeVisible();
    await expect(page.locator("#optin-enable")).toHaveText(/Enable here/i);

    // Enabled AND configured: nothing to say, so no permanent banner.
    await send(page, { type: "project",
                       data: { here: "/tmp/p", enabled_here: true, opt_in_adopted: true } });
    await expect(banner).toBeHidden();

    // Enabled but NOT yet adopted is a THIRD state and must not look like the
    // second one: the user needs to know opt-in is available but unconfigured.
    await send(page, { type: "project",
                       data: { here: "/tmp/p", enabled_here: true, opt_in_adopted: false } });
    await expect(banner).toBeVisible();
    expect(errors).toEqual([]);
  });

test("log rows show their action instead of a question mark", async ({ page }) => {
  // The bug: an unescaped newline in a remembered text split a log entry in two,
  // and the orphaned half had no timestamp and no action — which this panel renders
  // as "?". Reported by a human as "the logs don't show, it shows ?".
  const errors = await openViewer(page, { view: "log" });
  await send(page, {
    type: "log",
    data: {
      path: "/tmp/hipercampo.log",
      entries: [
        { ts: "2026-08-10 12:00:00", action: "recall", message: "2 result(s)", raw: "" },
        { ts: "2026-08-10 12:00:01", action: "remember", message: "stored id=7", raw: "" },
      ],
    },
  });
  const acciones = page.locator("#view-log .lact");
  await expect(acciones).toHaveCount(2);
  // NEWEST FIRST — the panel reverses the CLI's chronological order on purpose.
  // Pinned here because the first version of this test assumed the opposite and
  // failed: the ordering is a decision, so it should break loudly if it changes.
  await expect(acciones.first()).toHaveText("remember");
  await expect(acciones.nth(1)).toHaveText("recall");
  await expect(page.locator("#view-log")).not.toContainText("?");
  expect(errors).toEqual([]);
});

test("a log entry with no action degrades visibly rather than silently",
  async ({ page }) => {
    // The complement: an orphan line is now filtered when READ, but if one ever
    // reaches the panel it must be obvious, not invisible. "?" is the honest
    // rendering — this pins that behaviour so it is a decision, not an accident.
    const errors = await openViewer(page, { view: "log" });
    await send(page, {
      type: "log",
      data: { path: "/tmp/x.log", entries: [{ ts: "", action: "", message: "", raw: "" }] },
    });
    await expect(page.locator("#view-log .lact")).toHaveText("?");
    expect(errors).toEqual([]);
  });

test("the facts panel renders the role triple and marks closed facts",
  async ({ page }) => {
    // Facts are the VSA differentiator and the least exercised panel. It binds
    // `fields`, `current`, `context` and `id`; `current` in particular decides
    // whether a fact reads as history or as truth.
    const errors = await openViewer(page, { view: "facts" });
    await send(page, {
      type: "facts",
      data: {
        count: 2, namespace: "test",
        facts: [
          { id: 1, fields: { subject: "the dog", predicate: "bites", object: "the man" },
            current: true, context: "test" },
          { id: 2, fields: { subject: "the server", predicate: "lives in", object: "Frankfurt" },
            current: false, context: "test" },
        ],
      },
    });
    const fichas = page.locator("#view-facts .fact");
    await expect(fichas).toHaveCount(2);
    await expect(fichas.first()).toContainText("bites");
    await expect(fichas.first()).toContainText("the man");
    // The closed one must be visibly different, or history reads as current truth.
    await expect(fichas.nth(1)).toHaveClass(/cerrado/);
    expect(errors).toEqual([]);
  });
