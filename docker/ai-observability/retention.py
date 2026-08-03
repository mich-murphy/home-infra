#!/usr/bin/env python3
"""Delete traces after the experiment-specific retention window."""

from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import time
from pathlib import Path

import deployment_env


deployment_env.load()


RETENTION_DAYS = {
    "__OPERATIONAL_ID__": 90,
    "__DEVELOPMENT_ID__": 90,
    "__EVALUATION_ID__": 365,
}


def delete_expired() -> None:
    experiments = json.loads(Path("/generated/experiments.json").read_text())
    environment = os.environ.copy()
    environment["MLFLOW_TRACKING_URI"] = "http://mlflow:5000"
    environment["MLFLOW_TRACKING_USERNAME"] = environment["MLFLOW_AUTH_ADMIN_USERNAME"]
    environment["MLFLOW_TRACKING_PASSWORD"] = environment["MLFLOW_AUTH_ADMIN_PASSWORD"]
    for marker, days in RETENTION_DAYS.items():
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        subprocess.run([
            "mlflow", "traces", "delete",
            "--experiment-id", str(experiments[marker]),
            "--max-timestamp-millis", str(int(cutoff.timestamp() * 1000)),
            "--max-traces", "1000",
        ], env=environment, check=True)


while True:
    delete_expired()
    time.sleep(int(os.environ.get("MLFLOW_RETENTION_INTERVAL_SECONDS", "86400")))
