"""Azure App Service host; only explicitly public assets are served."""

from datetime import datetime, timezone
import json
import logging
import os
from pathlib import Path
import subprocess
import sys
import threading

from flask import Flask, jsonify, send_from_directory

ROOT = Path(__file__).resolve().parent
PUBLIC_FILES = {"index.html", "styles.css", "theme.js", "app.mjs", "news-core.mjs", "i18n.mjs", "favicon.svg"}
LOG = logging.getLogger("mynews")


def create_app(data_path=None):
    app = Flask(__name__, static_folder=None)
    app.config["NEWS_DATA_PATH"] = Path(data_path or os.environ.get(
        "NEWS_DATA_PATH", "/home/mynews/news.json" if os.environ.get("WEBSITE_SITE_NAME") else ROOT / ".cache/news.json"))
    app.config["LAST_UPDATE_FAILED"] = False

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' https:; "
            "connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'; form-action 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        return response

    @app.get("/")
    def index():
        return send_from_directory(ROOT, "index.html")

    @app.get("/<filename>")
    def public_file(filename):
        if filename not in PUBLIC_FILES:
            return jsonify(error="Not found"), 404
        return send_from_directory(ROOT, filename)

    def edition_path():
        path = app.config["NEWS_DATA_PATH"]
        return path if path.exists() else ROOT / "data/news.json"

    @app.get("/data/news.json")
    @app.get("/api/news")
    def news():
        path = edition_path()
        response = send_from_directory(path.parent, path.name, mimetype="application/json")
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/healthz")
    def health():
        return jsonify(status="ok")

    @app.get("/readyz")
    def ready():
        try:
            data = json.loads(edition_path().read_text(encoding="utf-8"))
            generated = datetime.fromisoformat(data["generated_at"].replace("Z", "+00:00"))
            age = (datetime.now(timezone.utc) - generated).total_seconds()
            healthy = (-300 <= age <= 5400 and not app.config["LAST_UPDATE_FAILED"]
                       and any(source["status"] in ("ok", "partial") for source in data["sources"]))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            LOG.warning("Readiness check: no valid published edition.")
            healthy = False
        response = jsonify(status="ready" if healthy else "waiting_or_degraded")
        response.headers["Cache-Control"] = "no-store"
        return response, 200 if healthy else 503

    return app


def start_scheduler(app):
    if os.environ.get("NEWS_AUTO_UPDATE", "1") == "0":
        LOG.info("Automatic RSS collection is disabled.")
        return
    interval = int(os.environ.get("NEWS_UPDATE_MINUTES", "15"))
    if not 5 <= interval <= 120:
        raise ValueError("NEWS_UPDATE_MINUTES must be between 5 and 120.")
    if app.extensions.get("news_scheduler"):
        return
    path = app.config["NEWS_DATA_PATH"]

    def update_loop():
        while True:
            try:
                subprocess.run(
                    [sys.executable, "-m", "scripts.aggregate", "--previous", str(path), "--output", str(path)],
                    cwd=ROOT, check=True, timeout=900,
                )
                app.config["LAST_UPDATE_FAILED"] = False
            except (subprocess.SubprocessError, OSError):
                app.config["LAST_UPDATE_FAILED"] = True
                LOG.exception("News update failed; the previous edition remains published.")
            threading.Event().wait(interval * 60)

    thread = threading.Thread(target=update_loop, name="news-updater", daemon=True)
    app.extensions["news_scheduler"] = thread
    thread.start()


app = create_app()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    start_scheduler(app)
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")), threaded=True)
