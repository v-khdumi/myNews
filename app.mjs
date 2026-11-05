import { articleText, categoryOf, CATEGORIES, currentArticles, relativeTime, safeImageUrl, selectArticles, SOURCES, validateEdition } from "./news-core.mjs";
import { messages } from "./i18n.mjs";
import { paginateText } from "./reader.mjs";

const $ = (selector) => document.querySelector(selector);
const pageSize = 12;
let language = "ro";
try {
  if (localStorage.getItem("mynews-language") === "en") language = "en";
} catch (error) {
  console.warn("Language preference could not be read:", error);
}
const state = { data: null, source: "all", query: "", sort: "newest", region: "all", category: "all", aiOnly: false, language, limit: pageSize, loading: false, error: false };
let readerArticle = null;
let returnFocus = null;
let readerText = "";
let readerPages = [];
let readerPage = 0;
let readerLayoutFrame = 0;
const t = () => messages[state.language];
const date = (value, full = false) => new Intl.DateTimeFormat(state.language === "ro" ? "ro-RO" : "en-GB", {
  dateStyle: full ? "long" : "medium", timeStyle: "short", timeZone: "Europe/Bucharest",
}).format(new Date(value));

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function imageFor(article, thumbnail = false) {
  const url = safeImageUrl(article.image_url);
  if (!url) return null;
  const container = element("div", "article-image");
  const image = element("img");
  image.alt = "";
  image.loading = thumbnail ? "lazy" : "eager";
  image.decoding = "async";
  image.referrerPolicy = "no-referrer";
  const fallback = element("span", "image-unavailable", t().unavailableImage);
  fallback.hidden = true;
  image.addEventListener("error", () => {
    console.warn("Publisher image unavailable:", url);
    image.hidden = true;
    fallback.hidden = false;
  }, { once: true });
  image.src = url;
  container.append(image, fallback);
  return container;
}

function renderReaderText(text) {
  $("#reader-excerpt").replaceChildren(...text.split(/\n\s*\n/u).map((paragraph) => element("p", "", paragraph)));
}

function renderReader() {
  const article = readerArticle;
  if (!article) return;
  const source = SOURCES.find((entry) => entry.id === article.source);
  const text = articleText(article, state.language);
  $("#reader-kind").textContent = `${t().readerKind} · ${t().categories[categoryOf(article)]}`;
  $("#reader-title").textContent = text.title;
  $("#reader-title").lang = text.language;
  $("#reader-meta").textContent = `${source.name} · ${date(article.published_at, true)}`;
  readerText = text.summary || t().noExcerpt;
  readerPages = [];
  readerPage = 0;
  renderReaderText(readerText);
  $("#reader-excerpt").lang = text.summary ? text.language : state.language;
  $("#reader-image").replaceChildren();
  const image = imageFor(article);
  if (image) {
    const figure = element("figure");
    const credit = article.image_credit ? `${t().imageCredit}: ${article.image_credit}` : `${t().imageFrom} ${source.name}.`;
    figure.append(image, element("figcaption", "", credit));
    $("#reader-image").append(figure);
  }
  $(".reader-body").classList.toggle("has-image", Boolean(image));
  $("#reader-note").textContent = text.ai ? t().aiNote : t().rssNote;
  $("#reader-source").href = article.url;
  $("#reader-source").textContent = `${t().readerSource} ↗`;
  $("#reader-source").setAttribute("aria-label", `${t().readSource}: ${source.name} (${t().newTab})`);
  if ($("#article-reader").open) layoutReader();
}

function showReaderPage(index) {
  if (!readerPages.length) return;
  readerPage = Math.max(0, Math.min(index, readerPages.length - 1));
  renderReaderText(readerPages[readerPage].text);
  $("#reader-page").textContent = `${readerPage + 1} / ${readerPages.length}`;
  $("#reader-page").setAttribute("aria-label", `${t().page} ${readerPage + 1} ${t().of} ${readerPages.length}`);
  $("#reader-previous").disabled = readerPage === 0;
  $("#reader-next").disabled = readerPage === readerPages.length - 1;
}

function layoutReader() {
  const dialog = $("#article-reader");
  if (!dialog.open) return;
  const anchor = readerPages[readerPage]?.start ?? 0;
  const excerpt = $("#reader-excerpt");
  dialog.classList.remove("reader-scroll", "reader-text-first");
  $(".reader-pagination").hidden = false;
  const fits = (candidate) => {
    renderReaderText(candidate);
    return excerpt.scrollHeight <= excerpt.clientHeight && excerpt.scrollWidth <= excerpt.clientWidth;
  };
  try {
    readerPages = paginateText(readerText, fits);
    if (readerPages.length > 1 && getComputedStyle($("#reader-image")).display !== "none") {
      dialog.classList.add("reader-text-first");
      readerPages = paginateText(readerText, fits);
    }
    const index = readerPages.findIndex((page) => page.end > anchor);
    showReaderPage(Math.max(0, index));
  } catch (error) {
    if (!(error instanceof RangeError)) throw error;
    console.warn("Reader viewport is too small; enabling accessible scrolling:", error);
    dialog.classList.add("reader-scroll");
    renderReaderText(readerText);
    $(".reader-pagination").hidden = true;
  }
}

function scheduleReaderLayout() {
  cancelAnimationFrame(readerLayoutFrame);
  readerLayoutFrame = requestAnimationFrame(layoutReader);
}

function openArticle(article) {
  returnFocus = document.activeElement;
  readerArticle = article;
  renderReader();
  document.documentElement.classList.add("reader-open");
  $("#article-reader").showModal();
  layoutReader();
  $("#close-reader").focus({ preventScroll: true });
}

function articleCard(article, now, index) {
  const source = SOURCES.find((entry) => entry.id === article.source);
  const text = articleText(article, state.language);
  const card = element("article", `news-card${index === 0 ? " lead-card" : ""}`);
  card.dataset.url = article.url;
  const image = imageFor(article, index !== 0);
  const media = element("button", `card-media${image ? "" : " no-image"}`);
  media.type = "button";
  media.setAttribute("aria-label", `${t().preview}: ${text.title}`);
  media.setAttribute("aria-haspopup", "dialog");
  if (image) media.append(image);
  else {
    media.append(element("span", "placeholder-category", t().categories[categoryOf(article)]),
      element("span", "placeholder-mark", source.name), element("span", "placeholder-arrow", "↗"));
  }
  media.addEventListener("click", () => openArticle(article));
  const body = element("div", "card-body");
  const meta = element("div", "card-meta");
  meta.append(element("span", "category-label", t().categories[categoryOf(article)]),
    element("span", text.ai ? "ai-badge" : "rss-badge", text.ai ? t().aiBadge : `${t().originalLanguage} · ${text.language.toUpperCase()}`));
  const heading = element("h3");
  const title = element("button", "article-title", text.title);
  title.lang = text.language;
  title.type = "button";
  title.setAttribute("aria-haspopup", "dialog");
  title.addEventListener("click", () => openArticle(article));
  heading.append(title);
  const excerpt = element("p", "card-excerpt", text.summary || t().noExcerpt);
  excerpt.lang = text.summary ? text.language : state.language;
  const bottom = element("div", "card-bottom");
  const publisher = element("span", "publisher", source.name);
  const time = element("time", "", relativeTime(article.published_at, now, state.language));
  time.dateTime = article.published_at;
  time.title = date(article.published_at);
  const link = element("a", "source-link", "↗");
  link.href = article.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `${t().readSource}: ${source.name} (${t().newTab})`);
  bottom.append(publisher, time, link);
  body.append(meta, heading, excerpt, bottom);
  card.append(media, body);
  return card;
}

function localize() {
  document.documentElement.lang = state.language;
  document.title = `myNews — ${t().heroAccent}`;
  document.querySelectorAll("[data-i18n]").forEach((node) => { node.textContent = t()[node.dataset.i18n]; });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => { node.setAttribute("aria-label", t()[node.dataset.i18nAria]); });
  $("#search").placeholder = t().searchPlaceholder;
  $("#theme-toggle").setAttribute("aria-label", t().darkTheme);
  $("#theme-toggle").title = t().darkTheme;
  document.querySelectorAll("[data-language]").forEach((node) => {
    node.setAttribute("aria-pressed", String(node.dataset.language === state.language));
  });
  $("#source").replaceChildren(...[{ id: "all", name: t().allSources }, ...SOURCES].map((source) => {
    const option = element("option", "", source.name);
    option.value = source.id;
    return option;
  }));
  $("#source").value = state.source;
  $("#category-filters").replaceChildren(...["all", ...CATEGORIES].map((category) => {
    const button = element("button", "category-filter", t().categories[category]);
    button.type = "button";
    button.dataset.category = category;
    button.addEventListener("click", () => {
      state.category = category;
      state.limit = pageSize;
      render();
    });
    return button;
  }));
  renderReader();
}

function renderSources() {
  $("#source-status").replaceChildren(...SOURCES.map((source) => {
    const status = state.data?.sources.find((entry) => entry.id === source.id);
    const item = element("li");
    const link = element("a", "", source.name);
    link.href = source.homepage;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    const label = element("span", `status-${status?.status || "pending"}`, t().sourceStates[status?.status || "pending"]);
    item.append(link, label);
    if (status?.last_success_at && Number.isFinite(Date.parse(status.last_success_at))) {
      item.append(element("small", "", date(status.last_success_at)));
    }
    // Technical source diagnostics are preserved verbatim from the collector.
    if (status?.error) item.append(element("small", "source-diagnostic", status.error));
    return item;
  }));
}

function render() {
  const now = Date.now();
  const articles = currentArticles(state.data?.articles ?? [], now);
  const selected = selectArticles(articles, { ...state, now });
  const active = document.activeElement;
  const focusedUrl = active?.closest(".news-card")?.dataset.url;
  const focusedClass = active?.className;
  $("#news").replaceChildren(...selected.slice(0, state.limit).map((article, index) => articleCard(article, now, index)));
  if (focusedUrl) {
    const card = Array.from($("#news").children).find((entry) => entry.dataset.url === focusedUrl);
    (Array.from(card?.querySelectorAll("button, a") ?? []).find((node) => node.className === focusedClass) ?? $("#news")).focus({ preventScroll: true });
  }
  $("#news").setAttribute("aria-busy", String(state.loading));
  $("#result-count").textContent = `${selected.length} ${selected.length === 1 ? t().story : t().stories}`;
  $("#total-count").textContent = articles.length;
  $("#source-count").textContent = SOURCES.length;
  $("#today").textContent = new Intl.DateTimeFormat(state.language === "ro" ? "ro-RO" : "en-GB", {
    weekday: "long", day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Bucharest",
  }).format(now);
  document.querySelectorAll("[data-count]").forEach((node) => {
    node.textContent = articles.filter((article) => node.dataset.count === "all"
      || (SOURCES.find((entry) => entry.id === article.source)?.region || "romania") === node.dataset.count).length;
  });
  for (const key of ["region", "category"]) {
    document.querySelectorAll(`[data-${key}]`).forEach((button) => {
      const selected = button.dataset[key] === state[key];
      button.classList.toggle("active", selected);
      button.setAttribute("aria-pressed", String(selected));
    });
  }
  $("#load-more").hidden = state.limit >= selected.length;
  $("#empty").hidden = selected.length > 0;
  const filtered = state.source !== "all" || state.region !== "all" || state.category !== "all" || state.aiOnly || state.query.trim();
  $("#reset-filters").hidden = !filtered;
  const emptyKey = state.loading && !state.data ? "loading" : state.error && !state.data ? "loadError"
    : !state.data?.generated_at ? "first" : filtered ? "noMatch" : "empty";
  $("#empty-title").textContent = t()[emptyKey];
  $("#empty-description").textContent = t()[`${emptyKey}Description`];
  const notices = [];
  if (state.error) notices.push(t().fetchError);
  if (state.data?.generated_at) {
    const generated = Date.parse(state.data.generated_at);
    $("#update-status").textContent = `${t().updated}: ${date(generated)}`;
    if (now - generated > 90 * 60000) notices.push(t().stale);
    if (generated > now + 5 * 60000) notices.push(t().clock);
  } else $("#update-status").textContent = state.loading ? t().loading : t().waiting;
  if (state.data?.sources.some((source) => ["error", "partial"].includes(source.status))) notices.push(t().sourceWarning);
  if (state.data?.ai?.status === "degraded") notices.push(t().aiDegraded);
  $("#notice").hidden = !notices.length;
  $("#notice").textContent = notices.join(" ");
  $("#notice").classList.toggle("error", state.error);
  $("#refresh").disabled = state.loading;
  const ready = articles.filter((article) => articleText(article, state.language).ai).length;
  const aiCounts = `${ready} ${t().aiReady} · ${articles.length - ready} ${t().aiPending}`;
  $("#ai-status").textContent = state.data?.ai?.status === "disabled" || !state.data?.ai
    ? ready ? `${t().aiPaused} ${aiCounts}` : t().aiDisabled
    : aiCounts;
  $("#radar").replaceChildren(...articles.slice(0, 4).map((article, index) => {
    const row = element("li");
    const text = articleText(article, state.language);
    const body = element("div");
    const button = element("button", "", text.title);
    button.lang = text.language;
    button.type = "button";
    button.setAttribute("aria-haspopup", "dialog");
    button.addEventListener("click", () => openArticle(article));
    body.append(element("span", "", relativeTime(article.published_at, now, state.language)), button);
    row.append(element("span", "radar-number", String(index + 1).padStart(2, "0")), body);
    return row;
  }));
  if (!articles.length) $("#radar").append(element("li", "radar-empty", t().noRadar));
  renderSources();
}

async function loadNews() {
  if (state.loading) return;
  state.loading = true;
  render();
  try {
    const response = await fetch(new URL("data/news.json", import.meta.url), {
      cache: "no-store", signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.data = validateEdition(await response.json());
    state.error = false;
  } catch (error) {
    console.error("News edition could not be loaded:", error);
    state.error = true;
  } finally {
    state.loading = false;
    render();
  }
}

document.querySelectorAll("[data-language]").forEach((button) => {
  button.addEventListener("click", () => {
    state.language = button.dataset.language;
    try { localStorage.setItem("mynews-language", state.language); }
    catch (error) { console.warn("Language preference could not be saved:", error); }
    localize();
    render();
  });
});
document.querySelectorAll("[data-region]").forEach((button) => {
  button.addEventListener("click", () => {
    state.region = button.dataset.region;
    state.limit = pageSize;
    render();
  });
});
for (const [selector, key, event] of [["#search", "query", "input"], ["#source", "source", "change"], ["#sort", "sort", "change"], ["#ai-only", "aiOnly", "change"]]) {
  $(selector).addEventListener(event, (event) => {
    state[key] = key === "aiOnly" ? event.target.checked : event.target.value;
    state.limit = pageSize;
    render();
  });
}
$("#load-more").addEventListener("click", () => {
  const previous = state.limit;
  state.limit += pageSize;
  render();
  $("#news").children[previous]?.querySelector(".article-title")?.focus({ preventScroll: true });
});
$("#reset-filters").addEventListener("click", () => {
  Object.assign(state, { source: "all", region: "all", category: "all", query: "", aiOnly: false, limit: pageSize });
  $("#search").value = "";
  $("#source").value = "all";
  $("#ai-only").checked = false;
  render();
  $("#search").focus();
});
$("#refresh").addEventListener("click", loadNews);
$("#close-reader").addEventListener("click", () => $("#article-reader").close());
$("#reader-previous").addEventListener("click", () => showReaderPage(readerPage - 1));
$("#reader-next").addEventListener("click", () => showReaderPage(readerPage + 1));
$("#article-reader").addEventListener("keydown", (event) => {
  if (event.altKey || event.ctrlKey || event.metaKey || event.shiftKey) return;
  const direction = { ArrowLeft: -1, PageUp: -1, ArrowRight: 1, PageDown: 1 }[event.key];
  if (direction) {
    event.preventDefault();
    showReaderPage(readerPage + direction);
  }
});
window.addEventListener("resize", scheduleReaderLayout);
window.visualViewport?.addEventListener("resize", scheduleReaderLayout);
document.fonts.ready.then(scheduleReaderLayout);
document.fonts.addEventListener("loadingdone", scheduleReaderLayout);
new ResizeObserver(() => {
  if (!$("#article-reader").classList.contains("reader-scroll")) scheduleReaderLayout();
}).observe($("#reader-excerpt"));
$("#article-reader").addEventListener("click", (event) => {
  if (event.target !== $("#article-reader")) return;
  const bounds = event.target.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) $("#article-reader").close();
});
$("#article-reader").addEventListener("close", () => {
  document.documentElement.classList.remove("reader-open");
  const card = Array.from($("#news").children).find((entry) => entry.dataset.url === readerArticle?.url);
  (returnFocus?.isConnected ? returnFocus : card?.querySelector(".article-title") ?? $("#news")).focus({ preventScroll: true });
  readerArticle = null;
  returnFocus = null;
});
setInterval(() => { if (!document.hidden) render(); }, 60000);
setInterval(() => { if (!document.hidden) loadNews(); }, 5 * 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadNews(); });
localize();
loadNews();
