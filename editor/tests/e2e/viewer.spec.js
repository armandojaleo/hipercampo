"use strict";

const { test, expect, openViewer, SAMPLE } = require("./fixture");

test("renders, filters, sorts, and localizes the real webview", async ({ page }) => {
  const errors = await openViewer(page);

  // Atom targets remain searchable but are hidden in the browsing list.
  await expect(page.locator("#view-list .card")).toHaveCount(16);
  await expect(page.locator("#count")).toHaveText("16 of 18");

  await page.locator("#q").fill("Frankfurt");
  await expect(page.locator("#view-list .card")).toHaveCount(1);
  await expect(page.locator("#view-list .text")).toContainText("Frankfurt");

  await page.locator("#q").fill("");
  await page.locator("#kind").selectOption("semantic");
  await expect(page.locator("#view-list .card")).toHaveCount(6);

  await page.locator("#kind").selectOption("atom");
  await expect(page.locator("#view-list .card")).toHaveCount(2);
  await expect(page.locator("#count")).toHaveText("2 of 18");

  await openViewer(page, { language: "es" });
  await expect(page.locator('[data-view="graph"]')).toHaveText("Mapa");
  await expect(page.locator("#q")).toHaveAttribute("placeholder", "Filtrar por texto…");
  expect(errors).toEqual([]);
});

test("renders the map and preserves the VS Code message contract", async ({ page }) => {
  const errors = await openViewer(page, { view: "graph" });

  await expect(page.locator("#view-graph")).toHaveClass(/active/);
  await expect(page.locator("#graph-legend .k")).not.toHaveCount(0);

  await page.locator('[data-view="status"]').click();
  await page.locator("#refresh").click();
  await page.locator("#pause").click();
  const messages = await page.evaluate(() => window.__vscodeMessages);
  expect(messages).toContainEqual({ type: "ready" });
  expect(messages).toContainEqual({ type: "status-request" });
  expect(messages).toContainEqual({ type: "refresh" });
  expect(messages).toContainEqual({ type: "setPaused", value: true });
  expect(errors).toEqual([]);
});

test("escapes memory content instead of executing stored markup", async ({ page }) => {
  const malicious = '<img id="owned" src=x onerror="window.__xss = true">';
  const data = { nodes: [{ ...SAMPLE.nodes[0], text: malicious }], edges: [] };
  const errors = await openViewer(page, { data });

  await expect(page.locator("#view-list .text")).toHaveText(malicious);
  await expect(page.locator("#owned")).toHaveCount(0);
  expect(await page.evaluate(() => window.__xss || false)).toBe(false);
  expect(errors).toEqual([]);
});
