"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { hostMessages } = require("../out/i18n.js");

const root = path.resolve(__dirname, "..");
const manifest = require(path.join(root, "package.json"));
const lock = require(path.join(root, "package-lock.json"));
const english = require(path.join(root, "package.nls.json"));
const spanish = require(path.join(root, "package.nls.es.json"));

assert.deepEqual(Object.keys(spanish).sort(), Object.keys(english).sort(),
  "package metadata must expose the same keys in English and Spanish");
assert.deepEqual(Object.keys(hostMessages("es")).sort(), Object.keys(hostMessages("en")).sort(),
  "host dialogs must expose the same keys in English and Spanish");
assert.equal(hostMessages("en").panelTitle, "Hipercampo — memory");
assert.equal(hostMessages("es-ES").panelTitle, "Hipercampo — memoria");
assert.equal(hostMessages("fr").panelTitle, hostMessages("en").panelTitle,
  "unsupported locales must fall back to English");
assert.match(hostMessages("en").purgePrompt(7), /irreversible/);
assert.match(hostMessages("es").purgePrompt(7), /irreversible/);

assert.equal(lock.version, manifest.version);
assert.equal(lock.packages[""].version, manifest.version);
assert.equal(manifest.icon, "media/icon.png");

const icon = fs.readFileSync(path.join(root, manifest.icon));
assert.equal(icon.subarray(1, 4).toString("ascii"), "PNG");
assert.equal(icon.readUInt32BE(16), 128);
assert.equal(icon.readUInt32BE(20), 128);

const html = fs.readFileSync(path.join(root, "media", "viewer.html"), "utf8");
assert.match(html, /Filter by text/);
assert.doesNotMatch(html, /Filtrar por texto|Nada que mostrar|todos los contextos/);

console.log("extension i18n + icon contract OK");
