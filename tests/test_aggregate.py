from datetime import datetime, timedelta, timezone
from email.utils import format_datetime
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from xml.sax.saxutils import escape

from scripts.aggregate import (
    aggregate, clean_title, collect_source, FeedError, iso_date, main,
    image_url, MAX_PAGES, page_url, parse_date, parse_feed, publisher_url,
    short_excerpt, SOURCES,
)

NOW = datetime(2026, 10, 28, 22, 30, tzinfo=timezone.utc)
SOURCE = SOURCES[0]


def rss(items, next_url=None):
    entries = []
    for title, url, date in items:
        entries.append(f"<item><title>{escape(title)}</title><link>{escape(url)}</link>"
                       f"<pubDate>{escape(date or '')}</pubDate></item>")
    next_link = f'<atom:link rel="next" href="{escape(next_url)}"/>' if next_url else ""
    return ('<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom"><channel>'
            + next_link + "".join(entries) + "</channel></rss>").encode()


def item(hours=1, title="Titlu de test", slug="stire", domain="hotnews.ro"):
    return title, f"https://{domain}/{slug}", format_datetime(NOW - timedelta(hours=hours))


class FeedParsingTests(unittest.TestCase):
    def test_rss_dates_titles_and_tracking_links(self):
        body = rss([item(title="<b>Știre</b> &amp; analiză", slug="stire?utm_source=rss&id=7#top")])
        articles, dates, next_url, invalid = parse_feed(body, SOURCE, SOURCE.feeds[0])
        self.assertEqual(articles[0]["title"], "Știre & analiză")
        self.assertEqual(articles[0]["url"], "https://hotnews.ro/stire?id=7")
        self.assertEqual(dates, [NOW - timedelta(hours=1)])
        self.assertIsNone(next_url)
        self.assertEqual(invalid, 0)

    def test_atom_prefers_publication_not_update(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom">
          <link rel="next" href="/feed?page=2"/>
          <entry><title>Atom headline</title><link href="/article"/>
            <updated>2026-10-28T22:00:00Z</updated>
            <published>2026-10-27T20:00:00Z</published></entry></feed>'''
        articles, _, next_url, _ = parse_feed(body, SOURCE, SOURCE.feeds[0])
        self.assertEqual(articles[0]["published_at"], "2026-10-27T20:00:00Z")
        self.assertEqual(next_url, "https://hotnews.ro/feed?page=2")

    def test_dublin_core_date(self):
        body = b'''<rss xmlns:dc="http://purl.org/dc/elements/1.1/"><channel><item>
          <title>Date test</title><link>https://hotnews.ro/date</link>
          <dc:date>2026-10-29T00:30:00+02:00</dc:date>
          </item></channel></rss>'''
        self.assertEqual(parse_feed(body, SOURCE, SOURCE.feeds[0])[0][0]["published_at"], iso_date(NOW))

    def test_article_next_links_do_not_paginate_feed(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Headline</title><link href="/article"/>
          <link rel="next" href="/wrong"/><published>2026-10-28T22:00:00Z</published>
          </entry></feed>'''
        self.assertIsNone(parse_feed(body, SOURCE, SOURCE.feeds[0])[2])

    def test_invalid_entries_are_counted(self):
        body = rss([item(), ("No date", "https://hotnews.ro/missing", "")])
        articles, _, _, invalid = parse_feed(body, SOURCE, SOURCE.feeds[0])
        self.assertEqual(len(articles), 1)
        self.assertEqual(invalid, 1)

    def test_all_invalid_entries_are_an_error(self):
        with self.assertRaises(FeedError):
            parse_feed(rss([("Missing date", "https://hotnews.ro/no-date", "")]), SOURCE, SOURCE.feeds[0])

    def test_rejects_html_broken_xml_and_entities(self):
        for body in (b"<html></html>", b"<rss>", b'<!DOCTYPE rss [<!ENTITY x "x">]><rss/>'):
            with self.subTest(body=body), self.assertRaises(FeedError):
                parse_feed(body, SOURCE, SOURCE.feeds[0])

    def test_empty_feed_is_valid(self):
        self.assertEqual(parse_feed(rss([]), SOURCE, SOURCE.feeds[0])[0], [])

    def test_safe_urls_only(self):
        for value in ("javascript:alert(1)", "https://evil.test/article",
                      "https://hotnews.ro.evil.test/", "https://user:pass@hotnews.ro/",
                      "https://hotnews.ro:9000/", "https://hotnews.ro:bad/"):
            with self.subTest(value=value):
                self.assertIsNone(publisher_url(value, SOURCE))
        self.assertEqual(publisher_url("http://www.hotnews.ro/a?fbclid=x", SOURCE), "https://www.hotnews.ro/a")

    def test_date_formats_and_timezone(self):
        self.assertEqual(parse_date("2026-10-29T00:30:00+02:00"), NOW)
        self.assertEqual(parse_date(format_datetime(NOW)), NOW)
        self.assertEqual(parse_date("2026-10-28T22:30:00"), NOW)
        self.assertIsNone(parse_date("not a date"))
        self.assertIsNone(parse_date(""))

    def test_plain_title_preserves_comparison(self):
        self.assertEqual(clean_title("  A < B &amp; C  "), "A < B & C")

    def test_page_url_preserves_existing_query(self):
        self.assertEqual(page_url("https://hotnews.ro/feed?x=1&paged=1", 2),
                         "https://hotnews.ro/feed?x=1&paged=2")


class PreviewTests(unittest.TestCase):
    def parse(self, metadata):
        body = rss([item()]).decode().replace(
            "<channel>",
            '<channel xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/">',
        ).replace("</item>", metadata + "</item>")
        return parse_feed(body.encode(), SOURCE, SOURCE.feeds[0])[0][0]

    def test_extracts_media_thumbnail_and_credit(self):
        article = self.parse(
            '<media:thumbnail url="https://cdn.example.com/photo.jpg"/>'
            '<media:credit><![CDATA[Foto: <b>Redacție</b>]]></media:credit>'
            '<description><![CDATA[<p>Scurt <b>rezumat</b>.</p>]]></description>'
        )
        self.assertEqual(article["image_url"], "https://cdn.example.com/photo.jpg")
        self.assertEqual(article["image_credit"], "Foto: Redacție")
        self.assertEqual(article["excerpt"], "Scurt rezumat.")

    def test_media_content_and_image_enclosures(self):
        for metadata in (
            '<media:content medium="image" url="https://cdn.example.com/photo.jpg"/>',
            '<media:content type="image/jpeg" url="https://cdn.example.com/photo.jpg"/>',
            '<enclosure type="image/jpeg" url="https://cdn.example.com/photo.jpg"/>',
            '<link rel="enclosure" type="image/jpeg" href="https://cdn.example.com/photo.jpg"/>',
        ):
            with self.subTest(metadata=metadata):
                self.assertEqual(self.parse(metadata)["image_url"], "https://cdn.example.com/photo.jpg")

    def test_html_image_fallback_and_relative_url(self):
        article = self.parse(
            '<description><![CDATA[<p>Rezumat</p>'
            '<img src="/images/photo.jpg" onerror="alert(1)">]]></description>'
        )
        self.assertEqual(article["image_url"], "https://hotnews.ro/images/photo.jpg")
        self.assertEqual(article["excerpt"], "Rezumat")

    def test_lazy_image_and_encoded_content_do_not_copy_body(self):
        article = self.parse(
            '<content:encoded><![CDATA[<img src="data:image/gif;base64,abc" '
            'data-src="https://cdn.example.com/photo.jpg"><p>Text integral neimportat</p>]]></content:encoded>'
        )
        self.assertEqual(article["image_url"], "https://cdn.example.com/photo.jpg")
        self.assertEqual(article["excerpt"], "")

    def test_video_is_not_an_image_and_unsafe_candidate_is_skipped(self):
        article = self.parse(
            '<media:content medium="video" url="https://cdn.example.com/movie.mp4"/>'
            '<enclosure type="audio/mpeg" url="https://cdn.example.com/audio.mp3"/>'
            '<media:thumbnail url="javascript:alert(1)"/>'
            '<description><![CDATA[<img src="https://cdn.example.com/photo.jpg">]]></description>'
        )
        self.assertEqual(article["image_url"], "https://cdn.example.com/photo.jpg")

    def test_missing_optional_metadata_does_not_remove_article(self):
        article = self.parse("")
        self.assertIsNone(article["image_url"])
        self.assertEqual(article["image_credit"], "")
        self.assertEqual(article["excerpt"], "")

    def test_atom_summary(self):
        body = b'''<feed xmlns="http://www.w3.org/2005/Atom"><entry>
          <title>Atom</title><link href="https://hotnews.ro/atom"/>
          <published>2026-10-28T22:00:00Z</published>
          <summary type="html">&lt;p&gt;Short preview&lt;/p&gt;</summary>
          </entry></feed>'''
        self.assertEqual(parse_feed(body, SOURCE, SOURCE.feeds[0])[0][0]["excerpt"], "Short preview")

    def test_excerpt_removes_active_content_and_preserves_spacing(self):
        self.assertEqual(short_excerpt(
            "<p>Primul &amp; text</p><p>Al doilea</p><script>alert(1)</script>"
            "<style>body{}</style><iframe>Nu se importă</iframe><noscript>Ascuns</noscript>"
        ), "Primul & text Al doilea")

    def test_excerpt_is_bounded_and_cache_reprocessing_is_stable(self):
        for text in ("cuvânt " * 100, "cuvânt-lung " * 100, "x" * 400):
            with self.subTest(text=text[:20]):
                result = short_excerpt(text)
                self.assertLessEqual(len(result), 281)
                self.assertLessEqual(len(result.split()), 45)
                self.assertTrue(result.endswith("…"))
                self.assertEqual(short_excerpt(result), result)

    def test_image_url_validation_and_cdn_support(self):
        for value in ("javascript:alert(1)", "data:image/svg+xml,test", "http://cdn.example.com/a",
                      "https://user:pass@cdn.example.com/a", "https://cdn.example.com:9000/a",
                      "https://cdn.example.com:bad/a", ""):
            with self.subTest(value=value):
                self.assertIsNone(image_url(value, SOURCE.feeds[0]))
        self.assertEqual(image_url("//cdn.example.com/photo.jpg#fragment", SOURCE.feeds[0]),
                         "https://cdn.example.com/photo.jpg")


class CollectionTests(unittest.TestCase):
    def test_all_nine_publishers_are_configured_and_collected(self):
        self.assertEqual({source.id for source in SOURCES}, {
            "hotnews", "g4media", "mediafax", "digi24", "descopera",
            "biziday", "zonait", "go4it", "stiripesurse",
        })
        for source in SOURCES:
            with self.subTest(source=source.id):
                for feed in source.feeds:
                    self.assertIsNotNone(publisher_url(feed, source))
                articles, status = collect_source(source, NOW, lambda url, selected: rss([
                    item(1, domain=selected.domain), item(25, slug="old", domain=selected.domain),
                ]))
                self.assertEqual(len(articles), 1)
                self.assertEqual(articles[0]["source"], source.id)
                self.assertEqual(status["status"], "ok")

    def test_exact_24_hour_window_no_future_or_old(self):
        body = rss([item(0, slug="now"), item(24, slug="boundary"),
                    item(24.001, slug="old"), item(-0.001, slug="future")])
        articles, status = collect_source(SOURCE, NOW, lambda *_: body)
        self.assertEqual({article["url"] for article in articles},
                         {"https://hotnews.ro/now", "https://hotnews.ro/boundary"})
        self.assertEqual(status["status"], "ok")

    def test_paginates_until_older_than_window(self):
        pages = [rss([item(1, slug="first")]),
                 rss([item(4, slug="second"), item(25, slug="old")])]
        calls = []

        def fetch(url, source):
            calls.append(url)
            return pages[len(calls) - 1]

        articles, status = collect_source(SOURCE, NOW, fetch)
        self.assertEqual(len(articles), 2)
        self.assertEqual(calls, ["https://hotnews.ro/feed", "https://hotnews.ro/feed?paged=2"])
        self.assertEqual(status["status"], "ok")

    def test_follows_explicit_next_even_for_non_paginated_source(self):
        source = next(source for source in SOURCES if source.id == "digi24")
        pages = [
            rss([item(1, domain=source.domain)], next_url="https://www.digi24.ro/rss?cursor=2"),
            rss([item(25, domain=source.domain, slug="old")]),
        ]
        calls = []

        def fetch(url, selected):
            calls.append(url)
            return pages[len(calls) - 1]

        articles, status = collect_source(source, NOW, fetch)
        self.assertEqual(len(articles), 1)
        self.assertEqual(calls[-1], "https://www.digi24.ro/rss?cursor=2")
        self.assertEqual(status["status"], "ok")

    def test_repeated_page_stops_without_duplicate_articles(self):
        articles, status = collect_source(SOURCE, NOW, lambda *_: rss([item()]))
        self.assertEqual(len(articles), 1)
        self.assertEqual(status["status"], "partial")

    def test_feed_fallback(self):
        def fetch(url, source):
            if url == source.feeds[0]:
                raise FeedError("Unavailable")
            return rss([item(25)])

        with self.assertLogs("mynews", level="WARNING"):
            articles, status = collect_source(SOURCE, NOW, fetch)
        self.assertEqual(articles, [])
        self.assertEqual(status["status"], "ok")

    def test_partial_pagination_failure_keeps_first_page(self):
        def fetch(url, source):
            if "paged" in url:
                raise FeedError("Down")
            return rss([item()])

        with self.assertLogs("mynews", level="WARNING"):
            articles, status = collect_source(SOURCE, NOW, fetch)
        self.assertEqual(len(articles), 1)
        self.assertEqual(status["status"], "partial")

    def test_page_limit_is_reported(self):
        def fetch(url, source):
            return rss([item(slug=url.split("?")[-1])])

        articles, status = collect_source(SOURCE, NOW, fetch)
        self.assertEqual(len(articles), MAX_PAGES)
        self.assertEqual(status["status"], "partial")
        self.assertIn("limita", status["error"])

    def test_non_paginated_feed_reports_limited_coverage(self):
        for source in (source for source in SOURCES if source.id in {"digi24", "stiripesurse"}):
            with self.subTest(source=source.id):
                calls = []

                def fetch(url, selected):
                    calls.append(url)
                    return rss([item(domain=selected.domain)])

                _, status = collect_source(source, NOW, fetch)
                self.assertEqual(status["status"], "partial")
                self.assertEqual(calls, [source.feeds[0]])

    def test_invalid_items_reported(self):
        _, status = collect_source(SOURCE, NOW, lambda *_: rss([item(25), ("Bad", "", "")]))
        self.assertEqual(status["status"], "partial")
        self.assertIn("omise", status["error"])

    def test_deduplicates_tracking_links(self):
        body = rss([item(slug="same?utm_source=rss"), item(slug="same?fbclid=x"), item(25)])
        articles, _ = collect_source(SOURCE, NOW, lambda *_: body)
        self.assertEqual(len(articles), 1)


class AggregationTests(unittest.TestCase):
    def article(self, hours, slug):
        return {
            "id": slug, "source": SOURCE.id, "title": f"Titlu {slug}",
            "url": f"https://hotnews.ro/{slug}",
            "published_at": iso_date(NOW - timedelta(hours=hours)),
        }

    def test_cache_survives_outage_but_expires(self):
        previous = {
            "sources": [{"id": SOURCE.id, "last_success_at": iso_date(NOW - timedelta(hours=1))}],
            "articles": [self.article(3, "cached"), self.article(25, "expired"), self.article(-1, "future")],
        }

        def fail(*_):
            raise FeedError("Unavailable")

        with self.assertLogs("mynews"):
            data = aggregate(NOW, previous, fail)
        self.assertEqual([article["url"] for article in data["articles"]], ["https://hotnews.ro/cached"])
        self.assertTrue(all(source["status"] == "error" for source in data["sources"]))
        self.assertEqual(data["sources"][0]["last_success_at"], previous["sources"][0]["last_success_at"])

    def test_removed_publisher_is_not_retained_from_cache(self):
        previous = {
            "sources": [{"id": "playtech", "last_success_at": iso_date(NOW)}],
            "articles": [{
                **self.article(1, "removed"),
                "source": "playtech", "url": "https://playtech.ro/removed",
            }],
        }
        data = aggregate(NOW, previous, lambda url, source: rss([
            item(1, domain=source.domain), item(25, domain=source.domain),
        ]))
        self.assertNotIn("playtech", {source["id"] for source in data["sources"]})
        self.assertEqual({article["source"] for article in data["articles"]},
                         {source.id for source in SOURCES})

    def test_cached_articles_survive_feed_rotation_and_are_deduplicated(self):
        previous = {"sources": [], "articles": [self.article(3, "cached"), self.article(2, "fresh")]}

        def fetch(url, source):
            return rss([item(2, title="Titlu actualizat", slug="fresh", domain=source.domain),
                        item(25, domain=source.domain)])

        data = aggregate(NOW, previous, fetch)
        self.assertEqual(len(data["articles"]), len(SOURCES) + 1)
        fresh = next(article for article in data["articles"] if article["url"] == "https://hotnews.ro/fresh")
        self.assertEqual(fresh["title"], "Titlu actualizat")
        self.assertEqual(len(data["sources"]), len(SOURCES))
        self.assertTrue(all(source["status"] == "ok" for source in data["sources"]))

    def test_partial_source_failure_does_not_hide_healthy_sources(self):
        def fetch(url, source):
            if source.id == "mediafax":
                raise FeedError("Down")
            return rss([item(domain=source.domain), item(25, domain=source.domain)])

        with self.assertLogs("mynews"):
            data = aggregate(NOW, fetcher=fetch)
        self.assertEqual(len(data["articles"]), len(SOURCES) - 1)
        self.assertEqual(data["sources"][2]["status"], "error")

    def test_cached_preview_metadata_survives_outage(self):
        cached = {
            **self.article(3, "cached"),
            "excerpt": short_excerpt("cuvânt " * 100),
            "image_url": "https://cdn.example.com/photo.jpg",
            "image_credit": "Foto: Redacție",
        }

        def fail(*_):
            raise FeedError("Unavailable")

        with self.assertLogs("mynews"):
            result = aggregate(NOW, {"sources": [], "articles": [cached]}, fail)["articles"][0]
        for key in ("excerpt", "image_url", "image_credit"):
            self.assertEqual(result[key], cached[key])

    def test_all_failed_does_not_overwrite_existing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "news.json"
            output.write_text("existing edition")
            with patch("sys.argv", ["aggregate.py", "--output", str(output)]), \
                    patch("scripts.aggregate.aggregate", return_value={
                        "sources": [{"status": "error"} for _ in SOURCES], "articles": [],
                    }), self.assertLogs("mynews"), self.assertRaises(SystemExit) as context:
                main()
            self.assertEqual(context.exception.code, 1)
            self.assertEqual(output.read_text(), "existing edition")

    def test_cli_writes_valid_json(self):
        data = {
            "generated_at": iso_date(NOW), "window_hours": 24,
            "sources": [{"status": "ok"}], "articles": [self.article(1, "recent")],
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "data" / "news.json"
            with patch("sys.argv", ["aggregate.py", "--output", str(output)]), \
                    patch("scripts.aggregate.aggregate", return_value=data):
                main()
            self.assertEqual(json.loads(output.read_text()), data)
            self.assertFalse(output.with_suffix(".tmp").exists())


if __name__ == "__main__":
    unittest.main()
