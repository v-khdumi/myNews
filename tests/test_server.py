from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import create_app, start_scheduler


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "news.json"
        self.app = create_app(self.path)
        self.client = self.app.test_client()

    def test_public_assets_and_liveness(self):
        for path in ("/", "/app.mjs", "/i18n.mjs", "/reader.mjs", "/styles.css", "/healthz"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
                response.close()

    def test_source_code_credentials_and_arbitrary_paths_are_not_public(self):
        for path in ("/server.py", "/.env", "/requirements.txt", "/scripts/aggregate.py",
                     "/.git/config", "/../server.py", "/data/../server.py"):
            with self.subTest(path=path):
                self.assertEqual(self.client.get(path).status_code, 404)

    def test_first_edition_is_honest_and_not_ready(self):
        response = self.client.get("/data/news.json")
        self.assertIsNone(response.json["generated_at"])
        response.close()
        self.assertEqual(self.client.get("/readyz").status_code, 503)

    def test_persistent_edition_and_health(self):
        data = {"generated_at": datetime.now(timezone.utc).isoformat(),
                "sources": [{"id": "guardian", "status": "ok"}], "articles": []}
        self.path.write_text(json.dumps(data))
        response = self.client.get("/api/news")
        self.assertEqual(response.json, data)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        response.close()
        self.assertEqual(self.client.get("/readyz").status_code, 200)
        self.app.config["LAST_UPDATE_FAILED"] = True
        self.assertEqual(self.client.get("/readyz").status_code, 503)
        self.assertEqual(self.client.get("/healthz").status_code, 200)

    def test_stale_failed_and_invalid_editions_are_not_ready(self):
        for data in (
            {"generated_at": "2020-01-01T00:00:00Z", "sources": [{"status": "ok"}]},
            {"generated_at": datetime.now(timezone.utc).isoformat(), "sources": [{"status": "error"}]},
            {"generated_at": "not-a-date"},
        ):
            self.path.write_text(json.dumps(data))
            self.assertEqual(self.client.get("/readyz").status_code, 503)

    def test_scheduler_can_be_disabled_and_checks_interval(self):
        with patch.dict("os.environ", {"NEWS_AUTO_UPDATE": "0"}):
            start_scheduler(self.app)
        self.assertNotIn("news_scheduler", self.app.extensions)
        with patch.dict("os.environ", {"NEWS_AUTO_UPDATE": "1", "NEWS_UPDATE_MINUTES": "0"}):
            with self.assertRaises(ValueError):
                start_scheduler(self.app)
