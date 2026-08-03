#!/usr/bin/env python3
"""Exercise the real collector/MLflow path and verify the task contract."""

from __future__ import annotations

import json
import os
import secrets
import time
import urllib.request

import mlflow
from mlflow import MlflowClient

import deployment_env


deployment_env.load()


def attr(key: str, value: str) -> dict[str, object]:
    return {"key": key, "value": {"stringValue": value}}


trace_hex = secrets.token_hex(16)
root_id = secrets.token_hex(8)
child_id = secrets.token_hex(8)
started = time.time_ns()
canary = "privacy-canary-" + secrets.token_hex(8)
payload = {"resourceSpans": [{
    "resource": {"attributes": [
        attr("service.name", "ai-observability-conformance"),
        attr("app.agent.trace.kind", "development"),
    ]},
    "scopeSpans": [{"scope": {"name": "conformance", "version": "1.2.0"}, "spans": [
        {
            "traceId": trace_hex, "spanId": root_id, "name": "agent.task", "kind": 1,
            "startTimeUnixNano": str(started), "endTimeUnixNano": str(started + 1_000_000),
            "attributes": [
                attr("session.id", "conformance-session"),
                attr("app.agent.task.id", "conformance-task"),
                attr("app.agent.content.capture", "off"),
                attr("gen_ai.input.messages", canary),
                attr("user.email", "privacy-canary@example.invalid"),
            ],
            "status": {"code": 1},
        },
        {
            "traceId": trace_hex, "spanId": child_id, "parentSpanId": root_id,
            "name": "agent.final", "kind": 1,
            "startTimeUnixNano": str(started + 500_000),
            "endTimeUnixNano": str(started + 1_000_000),
            "attributes": [attr("app.agent.final.status", "completed")],
            "status": {"code": 1},
        },
    ]}],
}]}
request = urllib.request.Request(
    "http://otel-collector:4318/v1/traces",
    data=json.dumps(payload).encode(), headers={"content-type": "application/json"}, method="POST",
)
with urllib.request.urlopen(request, timeout=10) as response:
    if response.status >= 300:
        raise SystemExit(f"collector returned {response.status}")

os.environ["MLFLOW_TRACKING_URI"] = "http://mlflow:5000"
os.environ["MLFLOW_TRACKING_USERNAME"] = os.environ["MLFLOW_AUTH_ADMIN_USERNAME"]
os.environ["MLFLOW_TRACKING_PASSWORD"] = os.environ["MLFLOW_AUTH_ADMIN_PASSWORD"]
mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
client = MlflowClient()
experiment = client.get_experiment_by_name("agent-development")
if experiment is None:
    raise SystemExit("development experiment is missing")
trace_id = f"tr-{trace_hex}"
found = []
for _ in range(30):
    found = client.search_traces(
        locations=[experiment.experiment_id],
        filter_string=f"request_id = '{trace_id}'", max_results=2,
    )
    if found:
        break
    time.sleep(2)
if len(found) != 1:
    raise SystemExit(f"expected one routed trace, found {len(found)}")
trace = client.get_trace(trace_id)
spans = trace.data.spans
roots = [span for span in spans if span.parent_id is None]
if len(roots) != 1 or roots[0].name != "agent.task":
    raise SystemExit("trace does not have exactly one agent.task root")
serialized = json.dumps(trace.to_dict())
if canary in serialized or "privacy-canary@example.invalid" in serialized:
    raise SystemExit("privacy transform leaked rich content or identity")
session = json.loads(trace.info.trace_metadata.get("mlflow.trace.session", "null"))
if session != "conformance-session":
    raise SystemExit("session.id was not mapped to mlflow.trace.session")
print(json.dumps({"status": "pass", "trace_id": trace_id, "experiment_id": experiment.experiment_id}))
