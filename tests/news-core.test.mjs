import assert from "node:assert/strict";
import test from "node:test";
import { currentArticles, DAY_MS, normalizeSearch, relativeTime, safeImageUrl, selectArticles, SOURCES, validArticle, validateEdition } from "../news-core.mjs";

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

test("images accept HTTPS CDN URLs without allowing unsafe schemes or credentials", () => {
  assert.equal(safeImageUrl("https://cdn.example.com/image.jpg"), "https://cdn.example.com/image.jpg");
  for (const url of [null, undefined, "", 42, "not a URL", "javascript:alert(1)",
    "data:image/svg+xml,test", "http://cdn.example.com/a",
    "https://user:pass@cdn.example.com/a", "https://cdn.example.com:9000/a"]) {
    assert.equal(safeImageUrl(url), null);
  }
});

test("old editions without image and excerpt fields remain compatible", () => {
  assert.equal(validArticle(article(1)), true);
  assert.equal(currentArticles([article(1)], now).length, 1);
  assert.equal(safeImageUrl(article(1).image_url), null);
});

test("all nine sources accept their own links and are individually filterable", () => {
  assert.deepEqual(SOURCES.map((source) => source.id), [
    "hotnews", "g4media", "mediafax", "digi24", "descopera", "biziday", "zonait", "go4it", "stiripesurse",
  ]);
  const articles = SOURCES.map((source) => article(1, {
    source: source.id, url: `${source.homepage}/article`,
  }));
  for (const source of SOURCES) {
    const result = selectArticles(articles, { source: source.id, now });
    assert.equal(result.length, 1);
    assert.equal(result[0].source, source.id);
    assert.equal(validArticle(article(1, { source: source.id, url: "https://unrelated.example/article" })), false);
  }
});

test("replacement publisher accepts both hostnames and removed publisher is rejected", () => {
  for (const hostname of ["stiripesurse.ro", "www.stiripesurse.ro"]) {
    assert.equal(validArticle(article(1, { source: "stiripesurse", url: `https://${hostname}/stire` })), true);
  }
  assert.equal(validArticle(article(1, { source: "playtech", url: "https://playtech.ro/stire" })), false);
});

test("Google News links require explicit provenance and the selected publisher", () => {
  const syndicated = article(1, {
    source: "stiripesurse", via: "google_news", url: "https://news.google.com/rss/articles/test-token?oc=5",
  });
  assert.equal(validArticle(syndicated), true);
  assert.equal(currentArticles([syndicated], now).length, 1);
  assert.equal(validArticle({ ...syndicated, via: undefined }), false);
  assert.equal(validArticle({ ...syndicated, source: "hotnews" }), false);
  for (const url of ["https://news.google.com/other", "https://evil.example/rss/articles/token",
    "https://news.google.com.evil.example/rss/articles/token", "http://news.google.com/rss/articles/token",
    "https://news.google.com:9000/rss/articles/token"]) {
    assert.equal(validArticle({ ...syndicated, url }), false);
  }
  assert.equal(validateEdition({
    generated_at: new Date(now).toISOString(),
    articles: [syndicated], sources: SOURCES.map(({ id }) => ({ id, status: "ok" })),
  }).articles[0].via, "google_news");
});

test("old four-source editions retain news and show new sources as pending", () => {
  const old = {
    generated_at: new Date(now).toISOString(),
    articles: [article(1)],
    sources: SOURCES.slice(0, 4).map(({ id }) => ({ id, status: "ok" })),
  };
  const edition = validateEdition(old);
  assert.equal(edition.sources.length, 9);
  assert.equal(edition.sources.filter(({ status }) => status === "pending").length, 5);
  assert.deepEqual(edition.articles, old.articles);
  assert.equal(old.sources.length, 4);
});

test("invalid editions still fail explicitly", () => {
  const base = {
    generated_at: null, articles: [], sources: SOURCES.map(({ id }) => ({ id, status: "pending" })),
  };
  assert.equal(validateEdition(base).sources.length, 9);
  for (const overrides of [
    { sources: [] }, { sources: [null] },
    { sources: [{ id: "hotnews", status: "ok" }, { id: "hotnews", status: "ok" }] },
    { sources: [{ id: "unknown", status: "ok" }] },
    { sources: [{ id: "hotnews", status: "wrong" }] },
    { articles: [article(1, { url: "javascript:alert(1)" })] }, { generated_at: "invalid" },
  ]) {
    assert.throws(() => validateEdition({ ...base, ...overrides }), /Formatul ediției/);
  }
});
