# AI observability

This stack accepts metadata-first application-agent traces over OTLP/HTTP and
routes them into `agent-operational`, `agent-development`, or
`skill-evaluations` MLflow experiments. MLflow basic authentication protects
the application boundary; Traefik/Tailscale remains the network boundary.

## Required configuration

The Docker Ansible role creates `/etc/ai-observability/mlflow.env` mode `0600`
with a generated admin password and a separate Flask signing key. For a
non-Ansible deployment, create that file outside Git with:

```sh
export MLFLOW_AUTH_ADMIN_USERNAME=admin
export MLFLOW_AUTH_ADMIN_PASSWORD='use-a-password-manager-generated-value'
export MLFLOW_FLASK_SERVER_SECRET_KEY='use-a-separate-long-random-value'
```

The admin username/password seed a new auth database; changing the environment
later does not rotate an existing account. Rotate it through MLflow's auth API
and update the collector/deployment secret together.

Run the media Ansible role before deploying so `/mnt/data` is backed by the
TrueNAS NFS export and `/mnt/data/backups/mlflow` exists. Then deploy normally.
The bootstrap job creates the three
experiments and writes an authenticated collector configuration before the
collector starts.

Before the first rollout, or before changing the pinned MLflow version, stop
MLflow and take an offline copy of the existing `mlflow-data` volume. The
scheduled backup service starts only after the upgraded server is healthy, so
it is not a substitute for a pre-migration snapshot.

Codex hook commands must be reviewed once through `/hooks` after the Nix
configuration is activated. Claude hooks take effect from the generated
settings. Both native trace exporters are disabled because their low-level
spans cannot be parented into the application task trace.

## Verification

Run a real privacy, routing, session, and task-boundary check:

```sh
docker compose --profile conformance run --rm conformance
```

The check sends canary identities and prompts through both development and
evaluation routes, confirms they were removed, and verifies exactly one
`agent.task` root in each destination experiment.

Evaluation result files are linked to traces automatically. Use the repository
central evaluator's `publish` or `retry` command to reconcile the MLflow
dataset, named assessments, and one identity-keyed summary run with
`MLFLOW_TRACKING_URI`, `MLFLOW_TRACKING_USERNAME`, and
`MLFLOW_TRACKING_PASSWORD` set.

## Data lifecycle and recovery

- Agent traces are metadata-only unless an explicitly approved resource marks
  rich capture. Identity fields and unapproved content fields are removed in
  the collector.
- Operational sampling is explicitly configured and defaults to 100%. Change
  `APP_AGENT_OPERATIONAL_SAMPLING_PERCENTAGE` only with a documented reason.
- Span payloads move to the MLflow trace archive after 30 days. Operational
  and development traces are eligible after 90 days. Ordinary evaluation
  evidence is eligible after 365 days; adopted or restricted evidence remains
  protected until superseded and then receives another 365-day grace period.
  Missing, duplicate, or malformed protection references cancel the evaluation
  deletion selection.
- `mlflow-backup` takes a consistent SQLite backup plus artifacts/archive every
  24 hours to `/mnt/data/backups/mlflow` on TrueNAS and retains daily snapshots
  for 14 days.

Retention starts in dry-run mode. Review its structured selection output after
backup and conformance checks, then set
`MLFLOW_RETENTION_DELETE_ENABLED=true` separately when deletion is authorized.

To restore, stop MLflow, copy a chosen snapshot's `mlflow.db` and `auth.db`
into the `mlflow-data` volume, extract `files.tar.gz` there, then start MLflow
and run the conformance profile. Preserve the pre-restore volume until the
integrity and conformance checks pass.

Existing pre-policy traces may contain rich content. After taking and testing
a backup, delete those traces or retain their database only in access-restricted
offline storage; collector policy cannot retroactively redact stored spans.
