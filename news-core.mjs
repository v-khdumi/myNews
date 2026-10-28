export const DAY_MS = 24 * 60 * 60 * 1000;
export const SOURCES = [
  { id: "hotnews", name: "HotNews", domain: "hotnews.ro", homepage: "https://hotnews.ro" },
  { id: "g4media", name: "G4Media", domain: "g4media.ro", homepage: "https://www.g4media.ro" },
  { id: "mediafax", name: "Mediafax", domain: "mediafax.ro", homepage: "https://www.mediafax.ro" },
  { id: "digi24", name: "Digi24", domain: "digi24.ro", homepage: "https://www.digi24.ro" },
  { id: "descopera", name: "Descoperă", domain: "descopera.ro", homepage: "https://www.descopera.ro" },
  { id: "biziday", name: "Biziday", domain: "biziday.ro", homepage: "https://www.biziday.ro" },
  { id: "zonait", name: "Zona IT", domain: "zonait.ro", homepage: "https://zonait.ro" },
  { id: "go4it", name: "Go4it", domain: "go4it.ro", homepage: "https://www.go4it.ro" },
  { id: "playtech", name: "Playtech", domain: "playtech.ro", homepage: "https://playtech.ro" },
];

export function validateEdition(data) {
  const statuses = new Set(["ok", "partial", "error", "pending"]);
  if (!data || !Array.isArray(data.articles) || !Array.isArray(data.sources)
    || data.sources.length === 0
    || new Set(data.sources.map((entry) => entry?.id)).size !== data.sources.length
    || !data.sources.every((entry) => entry && SOURCES.some((source) => source.id === entry.id) && statuses.has(entry.status))
    || !data.articles.every(validArticle)
    || (data.generated_at !== null && (typeof data.generated_at !== "string" || !Number.isFinite(Date.parse(data.generated_at))))) {
    throw new Error("Formatul ediției nu este valid.");
  }
  return {
    ...data,
    sources: SOURCES.map((source) => data.sources.find((entry) => entry.id === source.id)
      ?? { id: source.id, status: "pending", last_success_at: null, error: null }),
  };
}

export function safeImageUrl(value) {
  if (typeof value !== "string" || !value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" && !url.username && !url.password && !url.port ? url.href : null;
  } catch {
    return null;
  }
}

export function validArticle(article) {
  const source = SOURCES.find((entry) => entry.id === article?.source);
  if (!source || typeof article.title !== "string" || !article.title.trim()) return false;
  if (typeof article.published_at !== "string" || !Number.isFinite(Date.parse(article.published_at))) return false;
  try {
    const url = new URL(article.url);
    return url.protocol === "https:" && !url.username && !url.password
      && (url.hostname === source.domain || url.hostname === `www.${source.domain}`);
  } catch {
    return false;
  }
}

export function normalizeSearch(value) {
  return value.normalize("NFD").replace(/\p{Diacritic}/gu, "").toLocaleLowerCase("ro");
}

export function currentArticles(articles, now = Date.now()) {
  return articles.filter((article) => {
    const date = Date.parse(article.published_at);
    return validArticle(article) && date >= now - DAY_MS && date <= now;
  });
}

export function selectArticles(articles, { source = "all", query = "", sort = "newest", now = Date.now() } = {}) {
  const needle = normalizeSearch(query.trim());
  return currentArticles(articles, now)
    .filter((article) => (source === "all" || article.source === source)
      && normalizeSearch(article.title).includes(needle))
    .sort((a, b) => sort === "oldest"
      ? Date.parse(a.published_at) - Date.parse(b.published_at)
      : Date.parse(b.published_at) - Date.parse(a.published_at));
}

export function relativeTime(value, now = Date.now()) {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60000));
  if (minutes < 1) return "chiar acum";
  if (minutes < 60) return `acum ${minutes} min`;
  return `acum ${Math.floor(minutes / 60)} h`;
}
