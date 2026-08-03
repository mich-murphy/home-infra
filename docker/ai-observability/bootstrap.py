#!/usr/bin/env python3
"""Create trace experiments and render collector configuration with their IDs."""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


MLFLOW = "http://mlflow:5000"
EXPERIMENTS = {
    "__OPERATIONAL_ID__": "agent-operational",
    "__DEVELOPMENT_ID__": "agent-development",
    "__EVALUATION_ID__": "skill-evaluations",
}


def credentials() -> tuple[str, str]:
    username = os.environ.get("MLFLOW_AUTH_ADMIN_USERNAME", "")
    password = os.environ.get("MLFLOW_AUTH_ADMIN_PASSWORD", "")
    if not username or not password:
        raise SystemExit("MLflow bootstrap credentials are required")
    return username, password


def request(path: str, *, body: dict[str, str] | None = None) -> dict[str, object]:
    username, password = credentials()
    headers = {
        "authorization": "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode(),
        "content-type": "application/json",
    }
    data = json.dumps(body).encode() if body is not None else None
    with urllib.request.urlopen(
        urllib.request.Request(MLFLOW + path, data=data, headers=headers, method="POST" if data else "GET"),
        timeout=10,
    ) as response:
        return json.load(response)


def experiment_id(name: str) -> str:
    path = "/api/2.0/mlflow/experiments/get-by-name?" + urllib.parse.urlencode({"experiment_name": name})
    try:
        document = request(path)
        return str(document["experiment"]["experiment_id"])
    except urllib.error.HTTPError as error:
        if error.code != 404:
            raise
    return str(request("/api/2.0/mlflow/experiments/create", body={"name": name})["experiment_id"])


def main() -> int:
    for attempt in range(30):
        try:
            replacements = {marker: experiment_id(name) for marker, name in EXPERIMENTS.items()}
            break
        except (OSError, KeyError, urllib.error.HTTPError):
            if attempt == 29:
                raise
            time.sleep(2)
    username, password = credentials()
    experiment_ids = dict(replacements)
    replacements["__AUTHORIZATION__"] = "Basic " + base64.b64encode(f"{username}:{password}".encode()).decode()
    rendered = Path("/templates/collector.yaml").read_text()
    for marker, value in replacements.items():
        rendered = rendered.replace(marker, value)
    # The collector image seeds this volume with its example config.yaml; replace
    # that exact entrypoint file so the service cannot silently load the example.
    target = Path("/generated/config.yaml")
    temporary = target.with_suffix(".tmp")
    temporary.write_text(rendered)
    temporary.chmod(0o444)
    temporary.replace(target)
    Path("/generated/experiments.json").write_text(json.dumps(experiment_ids, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
