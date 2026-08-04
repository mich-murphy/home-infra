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


RETENTION_DAYS = {
    "__OPERATIONAL_ID__": 90,
    "__DEVELOPMENT_ID__": 90,
    "__EVALUATION_ID__": 365,
}


def iter_runs(client: object, experiment_id: str):
    """Yield the complete MLflow run inventory, following opaque page tokens."""
    token = None
    while True:
        page = client.search_runs(
            [experiment_id], max_results=1000, page_token=token
        )
        yield from page
        next_token = getattr(page, "token", None)
        if not next_token:
            return
        if next_token == token:
            raise RuntimeError("MLflow run pagination returned a repeated token")
        token = next_token


def iter_traces(client: object, experiment_id: str):
    """Yield the complete MLflow trace inventory within MLflow's page limit."""
    token = None
    while True:
        page = client.search_traces(
            locations=[experiment_id], max_results=500, page_token=token
        )
        yield from page
        next_token = getattr(page, "token", None)
        if not next_token:
            return
        if next_token == token:
            raise RuntimeError("MLflow trace pagination returned a repeated token")
        token = next_token


def _timestamp(value: object, field: str, trace_id: str) -> dt.datetime:
    if not isinstance(value, str):
        raise ValueError(f"{trace_id}: invalid {field}")
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{trace_id}: invalid {field}") from error
    if parsed.tzinfo is None:
        raise ValueError(f"{trace_id}: invalid {field}")
    return parsed.astimezone(dt.timezone.utc)


def protection_from_tags(tags: dict[str, str]) -> dict[str, object]:
    """Preserve absent protection metadata so selection can fail closed."""
    superseded_at = tags.get("app.agent.eval.superseded_at")
    return {
        "state": tags.get("app.agent.eval.protection"),
        "decision": tags.get("app.agent.eval.owner_decision"),
        "superseded_by": tags.get("app.agent.eval.superseded_by") or None,
        "superseded_at": superseded_at if superseded_at else None,
        "grace_days": tags.get("app.agent.eval.grace_days"),
    }


def resolve_supersession_references(
    protections: dict[str, list[dict[str, object]]],
) -> None:
    """Validate each supersession chain through one active same-skill release."""
    def valid_chain(origin: str, expected_skill: str) -> bool:
        current = origin
        visited: set[str] = set()
        while True:
            if current in visited:
                return False
            visited.add(current)
            summaries = protections.get(current, [])
            if len(summaries) != 1:
                return False
            summary = summaries[0]
            if (
                summary.get("identity") != current
                or summary.get("skill") != expected_skill
                or summary.get("summary_complete") is not True
                or summary.get("state") != "protected"
                or summary.get("decision") not in {"adopt", "restrict"}
                or summary.get("grace_days") != "365"
            ):
                return False
            successor = summary.get("superseded_by")
            superseded_at = summary.get("superseded_at")
            if (successor is None) != (superseded_at is None):
                return False
            if successor is None:
                return True
            if not isinstance(successor, str) or not successor:
                return False
            current = successor

    for identity, candidates in protections.items():
        for protection in candidates:
            successor_identity = protection.get("superseded_by")
            if successor_identity is None:
                protection["successor_valid"] = None
                continue
            skill = protection.get("skill")
            protection["successor_valid"] = bool(
                isinstance(skill, str)
                and skill
                and valid_chain(identity, skill)
            )


def select_expired_evidence(
    records: list[dict[str, object]],
    *,
    now: dt.datetime | None = None,
) -> dict[str, list[str]]:
    """Select deletable evaluation evidence, failing safe on any ambiguity."""
    current = (now or dt.datetime.now(dt.timezone.utc)).astimezone(dt.timezone.utc)
    cutoff = current - dt.timedelta(days=RETENTION_DAYS["__EVALUATION_ID__"])
    selected: list[str] = []
    protected: list[str] = []
    blocked: list[str] = []
    for record in records:
        trace_id = record.get("trace_id")
        if not isinstance(trace_id, str) or not trace_id:
            blocked.append("unknown: invalid trace_id")
            continue
        try:
            created_at = _timestamp(record.get("created_at"), "created_at", trace_id)
        except ValueError as error:
            blocked.append(str(error))
            continue
        protection = record.get("protection")
        if not isinstance(protection, dict):
            blocked.append(f"{trace_id}: invalid protection")
            continue
        state = protection.get("state")
        if state == "ordinary":
            if (
                protection.get("decision") != "defer"
                or protection.get("superseded_by") is not None
                or protection.get("superseded_at") is not None
                or protection.get("grace_days") != "365"
            ):
                blocked.append(f"{trace_id}: invalid protection")
                continue
            if created_at <= cutoff:
                selected.append(trace_id)
            continue
        if (
            state != "protected"
            or protection.get("decision") not in {"adopt", "restrict"}
            or protection.get("grace_days") != "365"
        ):
            blocked.append(f"{trace_id}: invalid protection")
            continue
        superseded_at = protection.get("superseded_at")
        superseded_by = protection.get("superseded_by")
        if (superseded_at is None) != (superseded_by is None):
            blocked.append(f"{trace_id}: invalid protection")
            continue
        if superseded_at is None:
            protected.append(trace_id)
            continue
        if protection.get("successor_valid") is not True:
            blocked.append(f"{trace_id}: invalid protection")
            continue
        try:
            superseded = _timestamp(superseded_at, "superseded_at", trace_id)
        except ValueError as error:
            blocked.append(str(error))
            continue
        if created_at <= cutoff and superseded <= cutoff:
            selected.append(trace_id)
        else:
            protected.append(trace_id)
    if blocked:
        selected = []
    return {
        "selected": sorted(selected),
        "protected": sorted(protected),
        "blocked": sorted(blocked),
    }


def delete_expired() -> None:
    deployment_env.load()
    experiments = json.loads(Path("/generated/experiments.json").read_text())
    environment = os.environ.copy()
    environment["MLFLOW_TRACKING_URI"] = "http://mlflow:5000"
    environment["MLFLOW_TRACKING_USERNAME"] = environment["MLFLOW_AUTH_ADMIN_USERNAME"]
    environment["MLFLOW_TRACKING_PASSWORD"] = environment["MLFLOW_AUTH_ADMIN_PASSWORD"]
    deletion_enabled = os.environ.get("MLFLOW_RETENTION_DELETE_ENABLED", "false").casefold() == "true"
    for marker, days in RETENTION_DAYS.items():
        if marker == "__EVALUATION_ID__":
            continue
        cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
        if deletion_enabled:
            subprocess.run([
                "mlflow", "traces", "delete",
                "--experiment-id", str(experiments[marker]),
                "--max-timestamp-millis", str(int(cutoff.timestamp() * 1000)),
                "--max-traces", "1000",
            ], env=environment, check=True)

    import mlflow
    from mlflow import MlflowClient

    os.environ.update({
        "MLFLOW_TRACKING_URI": environment["MLFLOW_TRACKING_URI"],
        "MLFLOW_TRACKING_USERNAME": environment["MLFLOW_TRACKING_USERNAME"],
        "MLFLOW_TRACKING_PASSWORD": environment["MLFLOW_TRACKING_PASSWORD"],
    })
    mlflow.set_tracking_uri(environment["MLFLOW_TRACKING_URI"])
    client = MlflowClient()
    evaluation_id = str(experiments["__EVALUATION_ID__"])
    summaries = iter_runs(client, evaluation_id)
    protections: dict[str, list[dict[str, object]]] = {}
    for run in summaries:
        tags = run.data.tags
        identity = tags.get("app.agent.eval.identity")
        if not identity:
            continue
        protection = protection_from_tags(tags)
        protection.update({
            "identity": identity,
            "skill": tags.get("app.agent.eval.skill"),
            "summary_complete": tags.get("app.agent.eval.summary_complete") == "true",
        })
        protections.setdefault(identity, []).append(protection)
    resolve_supersession_references(protections)
    records: list[dict[str, object]] = []
    traces = iter_traces(client, evaluation_id)
    for trace in traces:
        trace_id = getattr(trace.info, "trace_id", None) or getattr(trace.info, "request_id", None)
        timestamp_ms = getattr(trace.info, "timestamp_ms", None) or getattr(trace.info, "request_time", None)
        detailed = client.get_trace(trace_id)
        roots = [span for span in detailed.data.spans if span.parent_id is None]
        identity = roots[0].attributes.get("app.agent.eval.identity") if len(roots) == 1 else None
        candidates = protections.get(identity, []) if identity else []
        protection = candidates[0] if len(candidates) == 1 else None
        created_at = (
            dt.datetime.fromtimestamp(float(timestamp_ms) / 1000, tz=dt.timezone.utc).isoformat()
            if timestamp_ms is not None
            else None
        )
        records.append({
            "trace_id": trace_id,
            "created_at": created_at,
            "protection": protection,
        })
    selection = select_expired_evidence(records)
    print(json.dumps({
        "mode": "delete" if deletion_enabled else "dry-run",
        "experiment_id": evaluation_id,
        **selection,
    }, sort_keys=True), flush=True)
    if deletion_enabled and not selection["blocked"] and selection["selected"]:
        client.delete_traces(evaluation_id, trace_ids=selection["selected"])


def main() -> None:
    while True:
        delete_expired()
        time.sleep(int(os.environ.get("MLFLOW_RETENTION_INTERVAL_SECONDS", "86400")))


if __name__ == "__main__":
    main()
