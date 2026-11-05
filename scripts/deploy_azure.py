"""Package the application or recover an existing Azure Web App deployment."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parents[1]
APP_FILES = (
    "index.html", "styles.css", "theme.js", "app.mjs", "news-core.mjs",
    "i18n.mjs", "reader.mjs", "favicon.svg", "data/news.json", "server.py",
    "gunicorn.conf.py", "requirements.txt",
)
STARTUP_COMMAND = "gunicorn --config gunicorn.conf.py server:app"


def build_package(destination):
    paths = [ROOT / name for name in APP_FILES]
    paths.extend(sorted((ROOT / "scripts").glob("*.py")))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(f"Required deployment file is missing: {path}")
    with ZipFile(destination, "w", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(path, path.relative_to(ROOT))


def deploy(resource_group, app_name):
    for command in ("az", "curl"):
        if shutil.which(command) is None:
            raise RuntimeError(f"Required command not found: {command}")
    subprocess.run(["az", "account", "show", "--output", "none"], check=True)
    target = ["--resource-group", resource_group, "--name", app_name]
    with tempfile.TemporaryDirectory(prefix="mynews-deploy-") as directory:
        package = Path(directory) / "app.zip"
        build_package(package)
        subprocess.run([
            "az", "webapp", "config", "appsettings", "set", *target,
            "--settings", "SCM_DO_BUILD_DURING_DEPLOYMENT=true", "--output", "none",
        ], check=True)
        # Python App Service needs an extracted deployment so Oryx can build it.
        subprocess.run([
            "az", "webapp", "config", "appsettings", "delete", *target,
            "--setting-names", "WEBSITE_RUN_FROM_PACKAGE", "--output", "none",
        ], check=True)
        subprocess.run([
            "az", "webapp", "config", "set", *target,
            "--startup-file", STARTUP_COMMAND, "--output", "none",
        ], check=True)
        subprocess.run([
            "az", "webapp", "deploy", *target, "--src-path", str(package),
            "--type", "zip", "--restart", "true", "--track-status", "true",
            "--timeout", "600000", "--output", "none",
        ], check=True)
        hostname = subprocess.run([
            "az", "webapp", "show", *target,
            "--query", "defaultHostName", "--output", "tsv",
        ], check=True, capture_output=True, text=True).stdout.strip()
        if not hostname:
            raise RuntimeError("Azure did not return the application's defaultHostName.")
        url = f"https://{hostname}"
        health = Path(directory) / "health.json"
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--retry", "12",
            "--retry-all-errors", "--retry-delay", "10", "--connect-timeout", "10",
            "--max-time", "20", f"{url}/healthz", "--output", str(health),
        ], check=True)
        if json.loads(health.read_text(encoding="utf-8")).get("status") != "ok":
            raise RuntimeError("The deployed application's /healthz did not report status=ok.")
        subprocess.run([
            "curl", "--fail", "--silent", "--show-error", "--connect-timeout", "10",
            "--max-time", "20", f"{url}/", "--output", os.devnull,
        ], check=True)
        print(f"Application startup verified: {url}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    package_parser = commands.add_parser("package", help="Build the deployable ZIP without Azure access.")
    package_parser.add_argument("--output", type=Path, default=Path("app.zip"))
    deploy_parser = commands.add_parser("deploy", help="Publish and verify an existing Azure Web App.")
    deploy_parser.add_argument("--resource-group", required=True)
    deploy_parser.add_argument("--name", required=True)
    args = parser.parse_args()
    if args.command == "package":
        build_package(args.output)
    else:
        deploy(args.resource_group, args.name)


if __name__ == "__main__":
    main()
