import json
from pathlib import Path
import unittest


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
        self.assertEqual(config["appCommandLine"], "gunicorn --config gunicorn.conf.py server:app")
        self.assertEqual(config["healthCheckPath"], "/healthz")
        for filename in ("requirements.txt", "gunicorn.conf.py", "server.py", "data/news.json"):
            with self.subTest(filename=filename):
                self.assertTrue((ROOT / filename).is_file())
