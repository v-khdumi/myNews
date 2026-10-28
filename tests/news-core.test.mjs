import assert from "node:assert/strict";
import test from "node:test";
import { currentArticles, DAY_MS, normalizeSearch, relativeTime, selectArticles, validArticle } from "../news-core.mjs";

const now = Date.parse("2026-10-28T22:30:00Z");
function article(hours, overrides = {}) {
  return {
    id: `${hours}`, source: "hotnews", title: "Știri din România",
    url: `https://hotnews.ro/article-${hours}`,
    published_at: new Date(now - hours * 3600000).toISOString(),
    ...overrides,
  };
}

test("exact rolling 24-hour boundary, excludes old and future articles", () => {
  const articles = [article(0), article(24), article(24.001), article(-0.001)];
  assert.deepEqual(currentArticles(articles, now), articles.slice(0, 2));
  assert.equal(DAY_MS, 86400000);
});

test("articles expire as the client clock advances", () => {
  assert.equal(currentArticles([article(23.99)], now).length, 1);
  assert.equal(currentArticles([article(23.99)], now + 60000).length, 0);
});

test("source, search, case and diacritics work together", () => {
  const articles = [article(1), article(2, { title: "Economia", source: "digi24", url: "https://www.digi24.ro/article" })];
  assert.equal(selectArticles(articles, { source: "hotnews", query: " STIRI ", now }).length, 1);
  assert.equal(selectArticles(articles, { source: "digi24", query: "stiri", now }).length, 0);
  assert.equal(normalizeSearch("ȘȚĂÂÎ şţ"), "staai st");
});

test("sorts by publication date in either direction without mutating input", () => {
  const articles = [article(5), article(1), article(3)];
  assert.deepEqual(selectArticles(articles, { now }).map((entry) => entry.id), ["1", "3", "5"]);
  assert.deepEqual(selectArticles(articles, { sort: "oldest", now }).map((entry) => entry.id), ["5", "3", "1"]);
  assert.equal(articles[0].id, "5");
});

test("invalid dates, URLs, source IDs and empty titles are rejected", () => {
  for (const overrides of [
    { published_at: "invalid" }, { published_at: 4 }, { source: "unknown" }, { title: "" },
    { url: "javascript:alert(1)" }, { url: "https://hotnews.ro.evil.test/" },
    { url: "https://user:password@hotnews.ro/" }, { url: "https://digi24.ro/wrong-source" },
    { url: "http://hotnews.ro/insecure" },
  ]) {
    assert.equal(validArticle(article(1, overrides)), false, JSON.stringify(overrides));
  }
  assert.equal(validArticle(null), false);
  assert.equal(validArticle(article(1)), true);
});

test("relative time labels", () => {
  assert.equal(relativeTime(article(0).published_at, now), "chiar acum");
  assert.equal(relativeTime(article(0.5).published_at, now), "acum 30 min");
  assert.equal(relativeTime(article(3).published_at, now), "acum 3 h");
});

test("markup in a title remains data", () => {
  assert.equal(validArticle(article(1, { title: "<img src=x onerror=alert(1)>" })), true);
});
