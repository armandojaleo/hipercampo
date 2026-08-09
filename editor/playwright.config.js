"use strict";

const { defineConfig } = require("@playwright/test");
const { findBrowser } = require("./tools/preview");

const systemBrowser = findBrowser();

module.exports = defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? "github" : "list",
  use: {
    browserName: "chromium",
    headless: true,
    launchOptions: systemBrowser ? { executablePath: systemBrowser } : {},
    trace: "retain-on-failure",
  },
});
