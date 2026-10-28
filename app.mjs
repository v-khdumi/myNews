import { currentArticles, relativeTime, safeImageUrl, selectArticles, SOURCES, validArticle } from "./news-core.mjs";

const $ = (selector) => document.querySelector(selector);
const pageSize = 24;
const state = { data: null, source: "all", query: "", sort: "newest", limit: pageSize, loading: false, error: "" };
const fullDate = new Intl.DateTimeFormat("ro-RO", { dateStyle: "long", timeStyle: "short", timeZone: "Europe/Bucharest" });
const shortDate = new Intl.DateTimeFormat("ro-RO", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit", timeZone: "Europe/Bucharest" });
let readerArticleUrl = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function articleImage(article, { thumbnail = false } = {}) {
  const url = safeImageUrl(article.image_url);
  if (!url) return null;
  const container = element("div", "article-image");
  const image = element("img");
  image.alt = "";
  image.loading = thumbnail ? "lazy" : "eager";
  image.decoding = "async";
  image.referrerPolicy = "no-referrer";
  const fallback = element("span", "image-unavailable", "Imagine indisponibilă");
  fallback.hidden = true;
  image.addEventListener("error", () => {
    console.warn("Imaginea știrii nu a putut fi încărcată:", url);
    image.hidden = true;
    fallback.hidden = false;
  }, { once: true });
  image.src = url;
  container.append(image, fallback);
  return container;
}

function openArticle(article) {
  const source = SOURCES.find((entry) => entry.id === article.source);
  readerArticleUrl = article.url;
  $("#reader-title").textContent = article.title;
  $("#reader-meta").textContent = `${source.name} · ${fullDate.format(new Date(article.published_at))}`;
  $("#reader-excerpt").textContent = typeof article.excerpt === "string" && article.excerpt.trim()
    ? article.excerpt
    : "Sursa nu oferă un extras în fluxul RSS pentru această știre. Poți citi articolul complet folosind linkul de mai jos.";
  const image = articleImage(article);
  $("#reader-image").replaceChildren();
  if (image) {
    const figure = element("figure");
    const credit = typeof article.image_credit === "string" && article.image_credit.trim()
      ? `Credit imagine (RSS): ${article.image_credit}`
      : `Imagine asociată în fluxul RSS ${source.name}.`;
    figure.append(image, element("figcaption", "", credit));
    $("#reader-image").append(figure);
  }
  $("#reader-source").href = article.url;
  $("#reader-source").textContent = `Citește articolul integral la ${source.name} ↗`;
  $("#reader-source").setAttribute("aria-label", `Citește articolul integral la ${source.name} (filă nouă)`);
  document.documentElement.classList.add("reader-open");
  if (!$("#article-reader").open) $("#article-reader").showModal();
  $("#article-reader").scrollTop = 0;
  $("#close-reader").focus({ preventScroll: true });
}

function articleCard(article, now) {
  const source = SOURCES.find((entry) => entry.id === article.source);
  const card = element("article", `news-card ${source.id}`);
  card.dataset.url = article.url;
  card.addEventListener("click", (event) => {
    if (event.target.closest("a")) return;
    openArticle(article);
  });
  const image = articleImage(article, { thumbnail: true });
  if (image) {
    card.classList.add("has-image");
    const imageButton = element("button", "card-image-button");
    imageButton.type = "button";
    imageButton.setAttribute("aria-label", `Previzualizează: ${article.title}`);
    imageButton.setAttribute("aria-haspopup", "dialog");
    imageButton.append(image);
    card.append(imageButton);
  }
  const meta = element("div", "card-meta");
  const publisher = element("span", "publisher");
  const dot = element("span", "source-dot");
  dot.setAttribute("aria-hidden", "true");
  publisher.append(dot, source.name);
  const time = element("time", "", relativeTime(article.published_at, now));
  time.dateTime = article.published_at;
  time.title = fullDate.format(new Date(article.published_at));
  meta.append(publisher, time);

  const heading = element("h3");
  const title = element("button", "article-title", article.title);
  title.type = "button";
  title.setAttribute("aria-haspopup", "dialog");
  heading.append(title);
  const bottom = element("div", "card-bottom");
  const date = element("span", "", shortDate.format(new Date(article.published_at)));
  const link = element("a", "read-link", "Citește la sursă");
  link.href = article.url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.setAttribute("aria-label", `Citește la ${source.name}: ${article.title} (filă nouă)`);
  const arrow = element("b", "", "↗");
  arrow.setAttribute("aria-hidden", "true");
  link.append(arrow);
  bottom.append(date, link);
  card.append(meta, heading, bottom);
  return card;
}

function renderSources() {
  $("#source-status").replaceChildren(...SOURCES.map((source) => {
    const status = state.data?.sources.find((entry) => entry.id === source.id);
    const item = element("li");
    const link = element("a", "", source.name);
    link.href = source.homepage;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    let text = "în așteptarea primei actualizări";
    if (status?.status === "ok") text = "actualizat";
    if (status?.status === "partial") text = `acoperire limitată — ${status.error}`;
    if (status?.status === "error") text = `indisponibil temporar — ${status.error}`;
    if (status?.last_success_at && Number.isFinite(Date.parse(status.last_success_at))) {
      text += `; ultima preluare reușită: ${fullDate.format(new Date(status.last_success_at))}`;
    }
    item.append(link, `: ${text}.`);
    return item;
  }));
}

function render() {
  const now = Date.now();
  const articles = currentArticles(state.data?.articles ?? [], now);
  const selected = selectArticles(articles, { ...state, now });
  const shown = selected.slice(0, state.limit);
  const focusedArticle = document.activeElement?.closest(".news-card");
  const focusedUrl = focusedArticle?.dataset.url;
  const focusedClass = focusedArticle ? document.activeElement.className : null;
  $("#news").replaceChildren(...shown.map((article) => articleCard(article, now)));
  if (focusedUrl) {
    const card = Array.from($("#news").children).find((entry) => entry.dataset.url === focusedUrl);
    Array.from(card?.querySelectorAll("button, a") ?? []).find((entry) => entry.className === focusedClass)?.focus({ preventScroll: true });
  }
  $("#news").setAttribute("aria-busy", String(state.loading));
  $("#result-count").textContent = `${selected.length} ${selected.length === 1 ? "știre" : "știri"}`;
  document.querySelectorAll("[data-count]").forEach((counter) => {
    counter.textContent = counter.dataset.count === "all"
      ? articles.length
      : articles.filter((article) => article.source === counter.dataset.count).length;
  });
  document.querySelectorAll("[data-source]").forEach((button) => {
    const active = button.dataset.source === state.source;
    button.classList.toggle("active", active);
    button.setAttribute("aria-pressed", String(active));
  });
  $("#load-more").hidden = state.limit >= selected.length;
  $("#empty").hidden = selected.length > 0;
  const filtered = state.source !== "all" || state.query.trim();
  $("#reset-filters").hidden = !filtered;
  let title = "Nicio știre în ultimele 24 de ore";
  let description = "Momentan nu sunt articole recente disponibile. Următoarea actualizare poate aduce știri noi.";
  if (state.loading && !state.data) {
    title = "Se încarcă știrile";
    description = "Citim cea mai recentă ediție.";
  } else if (state.error && !state.data) {
    title = "Nu am putut încărca ediția";
    description = "Verifică conexiunea și apasă „Reîncarcă”. Dacă problema persistă, verifică publicarea din GitHub Actions.";
  } else if (!state.data?.generated_at) {
    title = "Prima ediție este în pregătire";
    description = "Știrile vor apărea după prima rulare reușită a workflow-ului „Actualizează și publică știrile” din GitHub Actions.";
  } else if (filtered) {
    title = "Nicio știre pentru aceste filtre";
    description = "Încearcă alt cuvânt sau alege toate sursele. Căutarea funcționează și fără diacritice.";
  }
  $("#empty-title").textContent = title;
  $("#empty-description").textContent = description;

  const notices = [];
  if (state.error) notices.push(state.error);
  if (state.data?.generated_at) {
    const generated = Date.parse(state.data.generated_at);
    $("#update-status").textContent = `Ediție actualizată: ${shortDate.format(new Date(generated))}`;
    if (now - generated > 90 * 60000) notices.push("Actualizarea automată întârzie. Sunt afișate doar știrile care încă se încadrează în ultimele 24 de ore.");
    if (generated > now + 5 * 60000) notices.push("Ora dispozitivului pare diferită de ora ediției. Verifică data și ora dispozitivului.");
  } else {
    $("#update-status").textContent = state.loading ? "Se încarcă știrile…" : "În așteptarea primei actualizări";
  }
  const unavailable = state.data?.sources.filter((source) => source.status === "error") ?? [];
  const partial = state.data?.sources.filter((source) => source.status === "partial") ?? [];
  if (unavailable.length) notices.push(`Surse indisponibile temporar: ${unavailable.map((source) => SOURCES.find((entry) => entry.id === source.id)?.name).join(", ")}. Păstrăm articolele preluate anterior, numai dacă au mai puțin de 24 de ore.`);
  if (partial.length) notices.push(`Acoperire limitată pentru ${partial.map((source) => SOURCES.find((entry) => entry.id === source.id)?.name).join(", ")}. Vezi detaliile surselor de mai jos.`);
  $("#notice").hidden = notices.length === 0;
  $("#notice").textContent = notices.join(" ");
  $("#notice").classList.toggle("error", Boolean(state.error));
  $("#refresh").disabled = state.loading;
  renderSources();
}

function validateData(data) {
  const statuses = new Set(["ok", "partial", "error", "pending"]);
  if (!data || !Array.isArray(data.articles) || !Array.isArray(data.sources)
    || data.sources.length !== SOURCES.length
    || !SOURCES.every((source) => data.sources.some((entry) => entry.id === source.id && statuses.has(entry.status)))
    || !data.articles.every(validArticle)
    || (data.generated_at !== null && (typeof data.generated_at !== "string" || !Number.isFinite(Date.parse(data.generated_at))))) {
    throw new Error("Formatul ediției nu este valid.");
  }
  return data;
}

async function loadNews() {
  if (state.loading) return;
  state.loading = true;
  render();
  try {
    const response = await fetch(new URL("data/news.json", import.meta.url), {
      cache: "no-store",
      signal: AbortSignal.timeout(20000),
    });
    if (!response.ok) throw new Error(`Serverul a răspuns cu HTTP ${response.status}.`);
    state.data = validateData(await response.json());
    state.error = "";
  } catch (error) {
    console.error("Încărcarea știrilor a eșuat:", error);
    state.error = "Nu am putut prelua ultima ediție. Reîncearcă folosind butonul „Reîncarcă”.";
  } finally {
    state.loading = false;
    render();
  }
}

document.querySelectorAll("[data-source]").forEach((button) => {
  button.addEventListener("click", () => {
    state.source = button.dataset.source;
    state.limit = pageSize;
    render();
  });
});
$("#search").addEventListener("input", (event) => {
  state.query = event.target.value;
  state.limit = pageSize;
  render();
});
$("#sort").addEventListener("change", (event) => {
  state.sort = event.target.value;
  state.limit = pageSize;
  render();
});
$("#load-more").addEventListener("click", () => {
  const previous = state.limit;
  state.limit += pageSize;
  render();
  $("#news").children[previous]?.querySelector(".article-title")?.focus({ preventScroll: true });
});
$("#reset-filters").addEventListener("click", () => {
  state.source = "all";
  state.query = "";
  state.limit = pageSize;
  $("#search").value = "";
  render();
  $("#search").focus();
});
$("#refresh").addEventListener("click", loadNews);
$("#close-reader").addEventListener("click", () => $("#article-reader").close());
$("#article-reader").addEventListener("keydown", (event) => {
  if (event.key !== "Tab") return;
  const first = $("#close-reader");
  const last = $("#reader-source");
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
});
$("#article-reader").addEventListener("click", (event) => {
  if (event.target !== $("#article-reader")) return;
  const bounds = event.target.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) {
    $("#article-reader").close();
  }
});
$("#article-reader").addEventListener("close", () => {
  document.documentElement.classList.remove("reader-open");
  const card = Array.from($("#news").children).find((entry) => entry.dataset.url === readerArticleUrl);
  (card?.querySelector(".article-title") ?? $("#news")).focus({ preventScroll: true });
  readerArticleUrl = null;
});
setInterval(() => { if (!document.hidden) render(); }, 60000);
setInterval(() => { if (!document.hidden) loadNews(); }, 5 * 60000);
document.addEventListener("visibilitychange", () => { if (!document.hidden) loadNews(); });
loadNews();
