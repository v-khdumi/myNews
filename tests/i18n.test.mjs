import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { messages } from "../i18n.mjs";
import { CATEGORIES } from "../news-core.mjs";

test("both interface languages cover all strings and categories", () => {
  assert.deepEqual(Object.keys(messages.ro).sort(), Object.keys(messages.en).sort());
  for (const language of ["ro", "en"]) {
    for (const category of ["all", ...CATEGORIES]) assert.ok(messages[language].categories[category]);
    const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
    for (const match of html.matchAll(/data-i18n(?:-aria)?="([^"]+)"/g)) {
      assert.equal(typeof messages[language][match[1]], "string", `${language}.${match[1]}`);
    }
  }
});
