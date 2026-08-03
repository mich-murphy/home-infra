#!/usr/bin/env python3
"""Start MLflow with persistent basic-auth state and trace archival."""

from __future__ import annotations

import os
from pathlib import Path


def required(name: str) -> str:
    value = os.environ.get(name, "")
    if not value or "\n" in value:
        raise SystemExit(f"{name} must be set to a non-empty single-line value")
    return value


username = required("MLFLOW_AUTH_ADMIN_USERNAME")
password = required("MLFLOW_AUTH_ADMIN_PASSWORD")
config_username = username.replace("%", "%%")
config_password = password.replace("%", "%%")
config = Path("/tmp/mlflow-auth.ini")
config.write_text(
    "[mlflow]\n"
    "database_uri = sqlite:////mlflow/auth.db\n"
    "default_permission = NO_PERMISSIONS\n"
    f"admin_username = {config_username}\n"
    f"admin_password = {config_password}\n"
)
config.chmod(0o600)
os.environ["MLFLOW_AUTH_CONFIG_PATH"] = str(config)
os.execvp("mlflow", [
    "mlflow", "server", "--app-name", "basic-auth",
    "--host", "0.0.0.0", "--port", "5000",
    "--workers", "1",
    "--backend-store-uri", "sqlite:////mlflow/mlflow.db",
    "--artifacts-destination", "file:///mlflow/artifacts",
    "--allowed-hosts", "mlflow.local.elmurphy.com,mlflow:5000,localhost:*,127.0.0.1:*",
    "--cors-allowed-origins", "https://mlflow.local.elmurphy.com",
])
