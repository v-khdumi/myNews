import assert from "node:assert/strict";
import test from "node:test";
import { paginateText } from "../reader.mjs";

test("short stories stay on one page", () => {
  const text = "O știre cu detalii și sursa la vedere.";
  assert.deepEqual(paginateText(text, () => true), [{ text, start: 0, end: Array.from(text).length }]);
});

test("pagination retains every word, paragraphs and readable page boundaries", () => {
  const text = "Primul paragraf prezintă faptele confirmate și persoanele implicate.\n\n"
    + "Al doilea paragraf explică detaliile disponibile, fără informații inventate. ".repeat(20);
  const pages = paginateText(text, (candidate) => candidate.length <= 180);
  assert.ok(pages.length > 5);
  assert.equal(pages.map((page) => page.text).join(" ").replace(/\s+/gu, " "), text.trim().replace(/\s+/gu, " "));
  assert.ok(pages.every((page) => page.text.length <= 180 && page.end > page.start));
  assert.ok(pages[0].text.includes("\n\n"));
});

test("unbroken tokens and Unicode are not dropped or split into invalid code points", () => {
  const text = "ș🙂".repeat(120);
  const pages = paginateText(text, (candidate) => Array.from(candidate).length <= 17);
  assert.equal(pages.map((page) => page.text).join(""), text);
  assert.ok(pages.every((page) => !page.text.includes("\uFFFD")));
});

test("combining marks and joined emoji stay attached across page boundaries", () => {
  const text = "s\u0326👩‍💻".repeat(40);
  const pages = paginateText(text, (candidate) => Array.from(candidate).length <= 17);
  assert.equal(pages.map((page) => page.text).join(""), text);
  assert.ok(pages.every((page) => !/^\p{M}|^\u200d|\u200d$/u.test(page.text)));
  assert.ok(pages.every((page) => !page.text.endsWith("s")));
});
test("repagination keeps the current reading position in a containing page", () => {
  const text = "Informații verificate, cu sursa originală. ".repeat(40);
  const initial = paginateText(text, (candidate) => candidate.length <= 160);
  const anchor = initial[3].start;
  const resized = paginateText(text, (candidate) => candidate.length <= 95);
  const page = resized.find((entry) => entry.end > anchor);
  assert.ok(page.start <= anchor && page.end > anchor);
});

test("an unreadable viewport is reported rather than silently discarding text", () => {
  assert.throws(() => paginateText("Știre", () => false), RangeError);
  assert.deepEqual(paginateText("  ", () => false), []);
});
