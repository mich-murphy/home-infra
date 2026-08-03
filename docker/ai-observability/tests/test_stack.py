from __future__ import annotations

import re
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]


class StackPolicyTests(unittest.TestCase):
    @staticmethod
    def collector_config() -> str:
        compose = (ROOT / "compose.yml").read_text()
        marker = "\nconfigs:\n  otel-collector-config:\n    content: |-\n"
        content = compose.split(marker, 1)[1]
        return textwrap.dedent(content)

    def test_collector_is_metadata_only_and_retries_asynchronously(self) -> None:
        config = self.collector_config()
        for forbidden in (
            "prompt",
            "source",
            "diff",
            "command",
            "path",
            "payload",
            "authorization",
            "secret",
        ):
            self.assertIn(forbidden, config)
            self.assertNotIn(f"- app.agent.{forbidden}\n", config)
        for required in (
            "memory_limiter",
            "batch",
            "retry_on_failure",
            "sending_queue",
        ):
            self.assertIn(required, config)
        self.assertIn("max_elapsed_time: 0s", config)
        self.assertNotIn("tail_sampling", config)
        self.assertNotIn("Authorization:", config)

    def test_collector_config_is_inline(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        collector = compose.split("  otel-collector:\n", 1)[1].split(
            "\nvolumes:\n", 1
        )[0]
        self.assertFalse((ROOT / "collector.yml").exists())
        self.assertIn("source: otel-collector-config", compose)
        self.assertIn("content: |-", compose)
        self.assertNotIn("./collector.yml", compose)
        self.assertIn("$${env:APP_AGENT_SCHEMA_VERSION}", compose)
        self.assertNotIn("read_only: true", collector)

    def test_mlflow_has_one_data_volume_and_no_application_secrets(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        for removed_secret in (
            "MLFLOW_ADMIN_PASSWORD",
            "MLFLOW_FLASK_SERVER_SECRET_KEY",
            "MLFLOW_OTLP_AUTH_HEADER",
        ):
            self.assertNotIn(removed_secret, compose)
        self.assertIn("sqlite:////mlflow/mlflow.db", compose)
        self.assertEqual(compose.count("name: mlflow-data"), 1)
        self.assertNotIn("mlflow-auth", compose)
        self.assertNotIn("volume-init", compose)
        self.assertNotIn("mlflow-bootstrap", compose)

    def test_only_mlflow_and_collector_are_defined(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        service_block = compose.split("services:\n", 1)[1].split("\nvolumes:\n", 1)[0]
        services = re.findall(r"^  ([a-z0-9-]+):$", service_block, re.MULTILINE)
        self.assertEqual(services, ["mlflow", "otel-collector"])
        self.assertNotIn("/opt/ai-observability", compose)

    def test_otlp_is_not_allowed_on_the_external_interface(self) -> None:
        compose = (ROOT / "compose.yml").read_text()
        defaults = (
            REPOSITORY
            / "ansible"
            / "roles"
            / "firewall"
            / "defaults"
            / "main.yaml"
        ).read_text()
        group_vars = (
            REPOSITORY / "ansible" / "group_vars" / "docker.yaml"
        ).read_text()
        self.assertIn('"4318:4318"', compose)
        self.assertNotIn("port: 4318", defaults)
        self.assertNotIn("port: 4318", group_vars)

if __name__ == "__main__":
    unittest.main()
