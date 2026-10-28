import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { runInNewContext } from "node:vm";

const script = readFileSync(new URL("../theme.js", import.meta.url), "utf8");

function setup({ saved = null, blocked = false } = {}) {
  const events = {};
  const attributes = {};
  const warnings = [];
  const root = { dataset: {} };
  const meta = {};
  const button = {
    disabled: true,
    setAttribute: (name, value) => { attributes[name] = value; },
    addEventListener: (name, callback) => { events[name] = callback; },
  };
  const storage = new Map(saved === null ? [] : [["mynews-theme", saved]]);
  runInNewContext(script, {
    document: {
      documentElement: root,
      querySelector: (selector) => selector === "#theme-toggle" ? button : meta,
      addEventListener: (name, callback) => { events[name] = callback; },
    },
    localStorage: {
      getItem: (key) => { if (blocked) throw new Error("blocked"); return storage.get(key) ?? null; },
      setItem: (key, value) => { if (blocked) throw new Error("blocked"); storage.set(key, value); },
    },
    console: { warn: (...args) => warnings.push(args) },
  });
  return { events, attributes, root, meta, button, storage, warnings };
}

test("night is the default and is applied before DOMContentLoaded", () => {
  const env = setup();
  assert.equal(env.root.dataset.theme, "night");
  assert.equal(env.meta.content, "#0c1015");
  env.events.DOMContentLoaded();
  assert.equal(env.attributes["aria-pressed"], "true");
  assert.equal(env.button.disabled, false);
});

test("day and night toggle, persist and restore", () => {
  const env = setup();
  env.events.DOMContentLoaded();
  env.events.click();
  assert.equal(env.root.dataset.theme, "day");
  assert.equal(env.button.textContent, "Zi");
  assert.equal(env.attributes["aria-pressed"], "false");
  assert.equal(env.storage.get("mynews-theme"), "day");
  assert.equal(env.meta.content, "#f4f6f8");
  assert.equal(setup({ saved: "day" }).root.dataset.theme, "day");
  env.events.click();
  assert.equal(env.root.dataset.theme, "night");
  assert.equal(env.storage.get("mynews-theme"), "night");
});

test("invalid preferences use night", () => {
  assert.equal(setup({ saved: "invalid" }).root.dataset.theme, "night");
});

test("blocked storage is reported and does not disable the theme toggle", () => {
  const env = setup({ blocked: true });
  env.events.DOMContentLoaded();
  env.events.click();
  assert.equal(env.root.dataset.theme, "day");
  assert.equal(env.warnings.length, 2);
});
