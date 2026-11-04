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
  { id: "stiripesurse", name: "Știripesurse.ro", domain: "stiripesurse.ro", homepage: "https://www.stiripesurse.ro" },
  { id: "guardian", name: "The Guardian", domain: "theguardian.com", homepage: "https://www.theguardian.com", region: "world", language: "en" },
  { id: "france24", name: "France 24", domain: "france24.com", homepage: "https://www.france24.com", region: "world", language: "en" },
  { id: "aljazeera", name: "Al Jazeera", domain: "aljazeera.com", homepage: "https://www.aljazeera.com", region: "world", language: "en" },
];

export const CATEGORIES = ["general", "politics", "business", "technology", "science", "sport", "culture"];

export function articleText(article, language = "ro") {
  const synthesis = article.synthesis;
  const edition = synthesis?.[language];
  const valid = synthesis?.source_url === article.url
    && typeof synthesis.model === "string" && synthesis.model.trim()
    && typeof synthesis.generated_at === "string" && Number.isFinite(Date.parse(synthesis.generated_at))
    && typeof edition?.title === "string" && edition.title.trim() && edition.title.length <= 180
    && typeof edition?.summary === "string" && edition.summary.trim() && edition.summary.length <= 1200;
  return valid
    ? { title: edition.title, summary: edition.summary, ai: true, language }
    : { title: article.title, summary: article.excerpt || "", ai: false,
      language: SOURCES.find((source) => source.id === article.source)?.language || "ro" };
}

export function categoryOf(article) {
  const category = articleText(article).ai ? article.synthesis.category : article.category;
  return CATEGORIES.includes(category) ? category : "general";
}

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
    return url.protocol === "https:" && !url.username && !url.password && !url.port
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

export function selectArticles(articles, {
  source = "all", query = "", sort = "newest", region = "all", category = "all",
  language = "ro", aiOnly = false, now = Date.now(),
} = {}) {
  const needle = normalizeSearch(query.trim());
  return currentArticles(articles, now)
    .filter((article) => {
      const text = articleText(article, language);
      const area = SOURCES.find((entry) => entry.id === article.source)?.region || "romania";
      return (source === "all" || article.source === source)
        && (region === "all" || area === region)
        && (category === "all" || categoryOf(article) === category)
        && (!aiOnly || text.ai)
        && normalizeSearch(`${text.title} ${text.summary} ${article.title}`).includes(needle);
    })
    .sort((a, b) => sort === "oldest"
      ? Date.parse(a.published_at) - Date.parse(b.published_at)
      : Date.parse(b.published_at) - Date.parse(a.published_at));
}

export function relativeTime(value, now = Date.now(), language = "ro") {
  const minutes = Math.max(0, Math.floor((now - Date.parse(value)) / 60000));
  if (minutes < 1) return language === "en" ? "just now" : "chiar acum";
  if (language === "en") return minutes < 60 ? `${minutes} min ago` : `${Math.floor(minutes / 60)} h ago`;
  if (minutes < 60) return `acum ${minutes} min`;
  return `acum ${Math.floor(minutes / 60)} h`;
}
