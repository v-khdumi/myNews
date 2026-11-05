import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.deploy_azure import APP_FILES, STARTUP_COMMAND, build_package, deploy


ROOT = Path(__file__).resolve().parents[1]


class DeploymentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template = json.loads((ROOT / "infra/azuredeploy.json").read_text(encoding="utf-8"))

    def resource(self, resource_type):
        resources = [resource for resource in self.template["resources"]
                     if resource["type"] == resource_type]
        self.assertEqual(len(resources), 1)
        return resources[0]

    def test_portal_deployment_publishes_application_after_creating_web_app(self):
        source = self.resource("Microsoft.Web/sites/sourcecontrols")
        self.assertEqual(source["properties"]["repoUrl"], "https://github.com/v-khdumi/myNews")
        self.assertEqual(source["properties"]["branch"], "main")
        self.assertIs(source["properties"]["isManualIntegration"], True)
        self.assertIn("[resourceId('Microsoft.Web/sites', parameters('appName'))]", source["dependsOn"])

    def test_python_build_startup_and_liveness_are_configured(self):
        config = self.resource("Microsoft.Web/sites")["properties"]["siteConfig"]
        settings = {setting["name"]: setting["value"] for setting in config["appSettings"]}
        self.assertEqual(settings["SCM_DO_BUILD_DURING_DEPLOYMENT"], "true")
        self.assertEqual(config["linuxFxVersion"], "PYTHON|3.12")
        self.assertEqual(config["appCommandLine"], STARTUP_COMMAND)
        self.assertEqual(config["healthCheckPath"], "/healthz")
        for filename in ("requirements.txt", "gunicorn.conf.py", "server.py", "reader.mjs", "data/news.json"):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file())

    def test_package_contains_startup_files_at_root_without_private_or_stale_files(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "app.zip"
            with ZipFile(package, "w") as archive:
                archive.writestr("stale-secret.env", "must not survive repackaging")
            build_package(package)
            with ZipFile(package) as archive:
                expected = set(APP_FILES) | {
                    str(path.relative_to(ROOT)) for path in (ROOT / "scripts").glob("*.py")
                }
                self.assertEqual(set(archive.namelist()), expected)
                for filename in expected:
                    self.assertEqual(archive.read(filename), (ROOT / filename).read_bytes())

    def test_missing_gunicorn_config_prevents_creating_a_broken_package(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in APP_FILES:
                if name != "gunicorn.conf.py":
                    path = root / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("fixture")
            package = root / "app.zip"
            with patch("scripts.deploy_azure.ROOT", root):
                with self.assertRaisesRegex(FileNotFoundError, "gunicorn.conf.py"):
                    build_package(package)
            self.assertFalse(package.exists())

    def test_recovery_builds_deploys_and_verifies_the_actual_azure_hostname(self):
        calls = []
        hostname = "mynews-unique.westeurope-01.azurewebsites.net"

        def run(command, **kwargs):
            self.assertTrue(kwargs["check"])
            calls.append(command)
            if command[:3] == ["az", "webapp", "deploy"]:
                with ZipFile(command[command.index("--src-path") + 1]) as archive:
                    self.assertIn("gunicorn.conf.py", archive.namelist())
                    self.assertIn("server.py", archive.namelist())
            if command[0] == "curl" and f"https://{hostname}/healthz" in command:
                Path(command[command.index("--output") + 1]).write_text('{"status":"ok"}')
            return subprocess.CompletedProcess(command, 0, stdout=hostname)

        with patch("scripts.deploy_azure.shutil.which", return_value="/usr/bin/tool"), \
                patch("scripts.deploy_azure.subprocess.run", side_effect=run), \
                patch("builtins.print") as output:
            deploy("existing-rg", "existing-app")
        output.assert_called_once_with(f"Application startup verified: https://{hostname}")
        az_commands = [command for command in calls if command[0] == "az"]
        self.assertEqual(az_commands[0], ["az", "account", "show", "--output", "none"])
        for command in az_commands[1:]:
            self.assertEqual(command[command.index("--resource-group") + 1], "existing-rg")
            self.assertEqual(command[command.index("--name") + 1], "existing-app")
        self.assertIn("SCM_DO_BUILD_DURING_DEPLOYMENT=true", calls[1])
        self.assertIn("WEBSITE_RUN_FROM_PACKAGE", calls[2])
        self.assertIn(STARTUP_COMMAND, calls[3])
        self.assertEqual(calls[4][:3], ["az", "webapp", "deploy"])
        self.assertIn("--track-status", calls[4])
        self.assertIn(f"https://{hostname}/healthz", calls[6])
        self.assertIn(f"https://{hostname}/", calls[7])

    def test_failed_azure_build_is_not_reported_as_success(self):
        def run(command, **kwargs):
            if command[:3] == ["az", "webapp", "deploy"]:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        with patch("scripts.deploy_azure.shutil.which", return_value="/usr/bin/tool"), \
                patch("scripts.deploy_azure.subprocess.run", side_effect=run) as runner:
            with self.assertRaises(subprocess.CalledProcessError):
                deploy("existing-rg", "existing-app")
        self.assertFalse(any(call.args[0][0] == "curl" for call in runner.call_args_list))

    def test_missing_azure_cli_fails_before_changing_the_app(self):
        with patch("scripts.deploy_azure.shutil.which", return_value=None), \
                patch("scripts.deploy_azure.subprocess.run") as runner:
            with self.assertRaisesRegex(RuntimeError, "Required command not found: az"):
                deploy("existing-rg", "existing-app")
        runner.assert_not_called()

    def test_unhealthy_deployment_is_not_reported_as_success(self):
        for payload in ('{"status":"waiting_or_degraded"}', "not-json"):
            with self.subTest(payload=payload):
                def run(command, **kwargs):
                    if command[0] == "curl":
                        Path(command[command.index("--output") + 1]).write_text(payload)
                    return subprocess.CompletedProcess(command, 0, stdout="mynews.azurewebsites.net")

                with patch("scripts.deploy_azure.shutil.which", return_value="/usr/bin/tool"), \
                        patch("scripts.deploy_azure.subprocess.run", side_effect=run) as runner, \
                        patch("builtins.print") as output:
                    with self.assertRaises((RuntimeError, json.JSONDecodeError)):
                        deploy("existing-rg", "existing-app")
                output.assert_not_called()
                curl_calls = [call for call in runner.call_args_list if call.args[0][0] == "curl"]
                self.assertEqual(len(curl_calls), 1)
