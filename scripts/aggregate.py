#!/usr/bin/env python3
"""Collect RSS headlines, short previews and publisher-hosted image references."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import hashlib
import html
from html.parser import HTMLParser
import json
import logging
from pathlib import Path
import re
import time
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET

UTC = timezone.utc
MAX_FEED_BYTES = 8 * 1024 * 1024
MAX_PAGES = 40
TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
LOG = logging.getLogger("mynews")


@dataclass(frozen=True)
class Source:
    id: str
    name: str
    domain: str
    feeds: tuple[str, ...]
    paginated: bool = True


SOURCES = (
    Source("hotnews", "HotNews", "hotnews.ro", ("https://hotnews.ro/feed", "https://hotnews.ro/rss")),
    Source("g4media", "G4Media", "g4media.ro", ("https://www.g4media.ro/feed",)),
    Source("mediafax", "Mediafax", "mediafax.ro", ("https://www.mediafax.ro/rss", "https://www.mediafax.ro/feed")),
    Source("digi24", "Digi24", "digi24.ro", ("https://www.digi24.ro/rss",), paginated=False),
)


class FeedError(Exception):
    pass


class TitleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


class PreviewParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.images = []
        self.ignored = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "iframe", "noscript", "svg"}:
            self.ignored += 1
        if self.ignored:
            return
        if tag in {"p", "br", "div", "li"}:
            self.parts.append(" ")
        if tag == "img":
            attributes = dict(attrs)
            self.images.append(attributes.get("data-src") or attributes.get("src") or "")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "iframe", "noscript", "svg"}:
            self.ignored = max(0, self.ignored - 1)
        if not self.ignored and tag in {"p", "div", "li"}:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.ignored:
            self.parts.append(data)


def clean_title(value):
    parser = TitleParser()
    parser.feed(value)
    return " ".join(html.unescape("".join(parser.parts)).split())


def short_excerpt(value):
    parser = PreviewParser()
    parser.feed(value)
    text = " ".join("".join(parser.parts).split())
    truncated = text.endswith("…")
    if truncated:
        text = text[:-1]
    words = text.split()
    clipped = " ".join(words[:45])
    if len(clipped) > 280:
        clipped = clipped[:281].rsplit(" ", 1)[0][:280]
    return clipped + ("…" if truncated or len(clipped) < len(text) else "")


def image_url(value, base):
    if not value:
        return None
    try:
        url = urlsplit(urljoin(base, value.strip()))
        if url.scheme != "https" or not url.hostname or url.username or url.password or url.port not in {None, 443}:
            return None
        return urlunsplit(url._replace(fragment=""))
    except ValueError:
        return None


def preview_metadata(item, base):
    candidates = []
    credit = ""
    for node in item.iter():
        name = local_name(node.tag)
        media = node.tag.startswith("{http://search.yahoo.com/mrss/}")
        if media and name in {"credit", "copyright"} and node.text and not credit:
            credit = clean_title(node.text)[:200]
        if ((media and name in {"thumbnail", "content"}
             and (name == "thumbnail" or node.attrib.get("medium") == "image"
                  or node.attrib.get("type", "").startswith("image/")
                  or ("medium" not in node.attrib and "type" not in node.attrib)))
                or (name == "enclosure" and node.attrib.get("type", "").startswith("image/"))
                or (name == "link" and node.attrib.get("rel") == "enclosure"
                    and node.attrib.get("type", "").startswith("image/"))):
            candidates.append(node.attrib.get("url") or node.attrib.get("href") or "")
    for node in item:
        if local_name(node.tag) in {"description", "summary", "encoded"} and node.text:
            parser = PreviewParser()
            parser.feed(node.text)
            candidates.extend(parser.images)
    image = next((url for candidate in candidates if (url := image_url(candidate, base))), None)
    return {
        "excerpt": short_excerpt(child_text(item, ("description", "summary"))),
        "image_url": image,
        "image_credit": credit if image else "",
    }


def iso_date(value):
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def parse_date(value):
    if not value:
        return None
    try:
        result = parsedate_to_datetime(value.strip())
    except (ValueError, TypeError, OverflowError):
        try:
            result = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=UTC)
    return result.astimezone(UTC)


def publisher_url(value, source, base=None):
    if not value:
        return None
    try:
        url = urlsplit(urljoin(base or source.feeds[0], value.strip()))
        if url.scheme not in {"https", "http"} or url.username or url.password or url.port not in {None, 80, 443}:
            return None
        if url.hostname not in {source.domain, f"www.{source.domain}"}:
            return None
        params = [(key, val) for key, val in parse_qsl(url.query, keep_blank_values=True)
                  if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS]
        return urlunsplit(("https", url.hostname, url.path or "/", urlencode(params), ""))
    except ValueError:
        return None


def local_name(tag):
    return tag.rsplit("}", 1)[-1]


def child_text(node, names):
    for name in names:
        for child in node:
            if local_name(child.tag) == name and child.text:
                return child.text.strip()
    return ""


def parse_feed(body, source, base_url):
    if re.search(br"<!\s*(DOCTYPE|ENTITY)\b", body, re.IGNORECASE):
        raise FeedError("Fluxul conține declarații XML nesigure.")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as error:
        raise FeedError("Răspunsul nu este un flux XML valid.") from error
    if local_name(root.tag) not in {"rss", "feed", "RDF"}:
        raise FeedError("Răspunsul nu este un flux RSS sau Atom.")
    articles = []
    dates = []
    invalid = 0
    entries = [node for node in root.iter() if local_name(node.tag) in {"item", "entry"}]
    for item in entries:
        title = clean_title(child_text(item, ("title",)))
        published = parse_date(child_text(item, ("pubDate", "published", "date", "updated")))
        link = ""
        for node in item:
            if local_name(node.tag) == "link" and node.attrib.get("rel", "alternate") == "alternate":
                link = node.attrib.get("href") or node.text or ""
                if link.strip():
                    break
        url = publisher_url(link, source, base_url)
        if published:
            dates.append(published)
        if not title or not published or not url:
            invalid += 1
            continue
        articles.append({
            "id": hashlib.sha256(url.encode()).hexdigest()[:24],
            "source": source.id,
            "title": title,
            "url": url,
            "published_at": iso_date(published),
            **preview_metadata(item, url),
        })
    next_url = None
    # Only feed-level links can paginate; article-level "next" links cannot.
    containers = [root] + [node for node in root if local_name(node.tag) == "channel"]
    for container in containers:
        for node in container:
            if local_name(node.tag) == "link" and node.attrib.get("rel") == "next":
                next_url = publisher_url(node.attrib.get("href"), source, base_url)
    if entries and not articles:
        raise FeedError("Fluxul nu conține articole cu titlu, link și dată valide.")
    return articles, dates, next_url, invalid


def fetch_feed(url, source):
    request = Request(url, headers={
        "User-Agent": "myNews-RSS/1.0 (GitHub Pages headline aggregator)",
        "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9",
    })
    for attempt in range(2):
        try:
            with urlopen(request, timeout=25) as response:
                if not publisher_url(response.url, source):
                    raise FeedError("Redirecționare în afara publicației.")
                data = response.read(MAX_FEED_BYTES + 1)
                if len(data) > MAX_FEED_BYTES:
                    raise FeedError("Fluxul depășește limita de 8 MB.")
                return data
        except (URLError, TimeoutError, OSError) as error:
            if attempt:
                raise FeedError(f"Flux RSS inaccesibil: {error}") from error
            time.sleep(1)


def page_url(base, page):
    url = urlsplit(base)
    query = [(key, value) for key, value in parse_qsl(url.query) if key != "paged"]
    return urlunsplit(url._replace(query=urlencode(query + [("paged", str(page))])))


def collect_source(source, now, fetcher=fetch_feed):
    cutoff = now - timedelta(hours=24)
    articles = {}
    seen_pages = set()
    warnings = []
    base_url = None
    parsed = None
    failures = []
    for candidate in source.feeds:
        try:
            parsed = parse_feed(fetcher(candidate, source), source, candidate)
            base_url = candidate
            break
        except FeedError as error:
            failures.append(str(error))
            LOG.warning("%s (%s): %s", source.name, candidate, error)
    if parsed is None:
        raise FeedError("; ".join(failures))
    visited_urls = {base_url}
    for page in range(1, MAX_PAGES + 1):
        items, dates, next_url, invalid = parsed
        fingerprint = tuple(sorted(item["id"] for item in items))
        if fingerprint in seen_pages and items:
            warnings.append("Fluxul nu permite continuarea paginării; unele articole pot lipsi.")
            break
        seen_pages.add(fingerprint)
        if invalid:
            warnings.append(f"{invalid} articole fără titlu, link sau dată valide au fost omise.")
        for article in items:
            published = parse_date(article["published_at"])
            if cutoff <= published <= now:
                articles[article["id"]] = article
        if not items or (dates and min(dates) < cutoff):
            break
        if not next_url and not source.paginated:
            warnings.append("Fluxul publică un număr limitat de articole, fără paginare.")
            break
        if page == MAX_PAGES:
            warnings.append("S-a atins limita de paginare; unele articole pot lipsi.")
            break
        next_url = next_url or page_url(base_url, page + 1)
        if next_url in visited_urls:
            warnings.append("Fluxul repetă pagina următoare; unele articole pot lipsi.")
            break
        visited_urls.add(next_url)
        try:
            parsed = parse_feed(fetcher(next_url, source), source, next_url)
        except FeedError as error:
            LOG.warning("%s, pagina %s: %s", source.name, page + 1, error)
            warnings.append("Paginarea nu a putut fi finalizată; unele articole pot lipsi.")
            break
    error = " ".join(dict.fromkeys(warnings)) or None
    return list(articles.values()), {
        "id": source.id,
        "status": "partial" if error else "ok",
        "error": error,
        "last_success_at": iso_date(now),
    }


def aggregate(now, previous=None, fetcher=fetch_feed):
    previous = previous or {}
    old_articles = previous.get("articles", [])
    old_sources = {source["id"]: source for source in previous.get("sources", [])}
    cutoff = now - timedelta(hours=24)

    def collect(source):
        try:
            return collect_source(source, now, fetcher)
        except FeedError as error:
            LOG.error("%s: %s", source.name, error)
            return [], {
                "id": source.id,
                "status": "error",
                "error": "La ultima încercare, fluxul RSS nu a putut fi citit.",
                "last_success_at": old_sources.get(source.id, {}).get("last_success_at"),
            }

    articles = {}
    # Keep earlier RSS entries even after they disappear from a publisher's feed.
    for article in old_articles:
        source = next((entry for entry in SOURCES if entry.id == article.get("source")), None)
        published = parse_date(article.get("published_at"))
        if source and published and cutoff <= published <= now and article.get("title"):
            url = publisher_url(article.get("url"), source)
            if url:
                image = image_url(article.get("image_url"), url)
                article = {
                    **article, "url": url, "id": hashlib.sha256(url.encode()).hexdigest()[:24],
                    "excerpt": short_excerpt(article.get("excerpt") or ""),
                    "image_url": image,
                    "image_credit": clean_title(article.get("image_credit") or "")[:200] if image else "",
                }
                articles[article["id"]] = article
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        results = list(pool.map(collect, SOURCES))
    statuses = []
    for fresh, status in results:
        statuses.append(status)
        articles.update((article["id"], article) for article in fresh)
    return {
        "generated_at": iso_date(now),
        "window_hours": 24,
        "sources": statuses,
        "articles": sorted(articles.values(), key=lambda article: article["published_at"], reverse=True),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("data/news.json"))
    parser.add_argument("--previous", type=Path, help="Reuse a previous edition for the rolling 24-hour window.")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    previous = None
    if args.previous and args.previous.exists():
        try:
            previous = json.loads(args.previous.read_text(encoding="utf-8"))
            if not isinstance(previous, dict) or not isinstance(previous.get("articles"), list) or not isinstance(previous.get("sources"), list):
                raise ValueError("Format de cache invalid")
        except (ValueError, OSError) as error:
            LOG.error("Ediția precedentă nu poate fi citită: %s", error)
            raise SystemExit(1) from error
    data = aggregate(datetime.now(UTC), previous)
    if all(source["status"] == "error" for source in data["sources"]) and not data["articles"]:
        LOG.error("Nicio sursă nu este disponibilă și nu există articole recente în cache; publicarea este oprită.")
        raise SystemExit(1)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(args.output)
    LOG.info("%s articole publicate în %s", len(data["articles"]), args.output)


if __name__ == "__main__":
    main()
