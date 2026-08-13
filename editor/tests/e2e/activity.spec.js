"use strict";

const { test, expect, openViewer, send } = require("./fixture");

// The ambient activity footer: no popups, just a short phrase in the footer
// telling what the memory is doing, sourced from decision-log entries the
// extension pushes as { type: "activity", entries: [...] }.

test("shows a phrase for a recall entry, then fades once idle", async ({ page }) => {
  await openViewer(page);
  const bar = page.locator("#activity-bar");
  await expect(bar).toHaveClass(/hidden/);

  await send(page, { type: "activity", entries: [
    { ts: "2026-08-13 12:00:00", action: "recall", message: "1 result(s)", raw: "r1" },
  ] });

  await expect(bar).toHaveClass(/visible/);
  await expect(page.locator("#activity-text")).not.toHaveText("");
});

test("an idea (bridge hypothesis) gets a clickable phrase that opens Ideas", async ({ page }) => {
  await openViewer(page);
  await send(page, { type: "activity", entries: [
    { ts: "2026-08-13 12:00:00", action: "dream", message: "2 hypothesis(es)", raw: "r2" },
  ] });

  const bar = page.locator("#activity-bar");
  await expect(bar).toHaveClass(/idea/);
  await bar.click();
  await expect(page.locator("#view-ideas")).toHaveClass(/active/);
});

test("a tokens entry with no savings produces no phrase (silent, no noise)", async ({ page }) => {
  await openViewer(page);
  await send(page, { type: "activity", entries: [
    { ts: "2026-08-13 12:00:00", action: "tokens", message: "identity 40 tok", raw: "r3" },
  ] });
  await page.waitForTimeout(200);
  await expect(page.locator("#activity-bar")).toHaveClass(/hidden/);
});
