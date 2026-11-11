# Pinchflat provider-only 384 MiB experiment — OFFLINE preparation

Parent explicitly approved preparation, NOT activation or a lease. This is ready
for parent review of **one 704 MiB bounded live window**, conditional on fresh
parent admission and the runtime preflight below. It is not a capacity, provider,
download, recovery or binary-compatibility pass. All prior receipts remain revoked.
No proof-runtime, production or host call was made. Public source HTTPS research
and workstation-only tests were used; no image or runtime binary was executed.

## Unchanged failures and scope

[Prior exact-source followup](native-auth-rpc-source-followup.md) and its private
kernel SHA75e20244e98d1d189ab8a0eee13acd33d00eab1e4d5f8f4c04dae33c85d91348
remain authoritative. Three same-Pinchflat-pod memcg OOMs include a third event
with only one BEAM plus yt-dlp/python; extra RPC BEAM is NOT the sole proven cause.
No earlier evidence, limits, credentials or recovery archives were rewritten.
Jellyfin's actual anonymous120214-byte leak and Plex browser Origin/Referer401
remain blocked, not targets for activation, LAN/proxy changes or auth bypass.
Indexer fixture socket contracts are not reviewed Prowlarr public compatibility
and do not authorize arr/indexer wiring or any other live group.

## Exact new profile and receipt

Ordinary `pinchflat/resources.yaml` remains256 MiB main. Only optional
`pinchflat-rss/provider.yaml` raises main memory limit to384 MiB; main request128,
CPU1000m, fixture128, all other resources and VM sizing stay unchanged.
Full admission: **384 main +128 fixture +192 reserve =704 MiB**.
Both receipt fields are mandatory, with exact integer type for the new field:

```json
{"provider_fixture":"pinchflat-rss","pinchflat_main_memory_mib":384}
```

These are additional fields on a genuine parent-issued lease, not a lease
example or permission to mint one. Old576 receipts never expand implicitly.
PodTemplate annotations must be exactly `provider-fixture: pinchflat-rss` and
`pinchflat-main-memory-mib: "384"` under `talos-proof.home/`.

Admission inspects the actual retained selected Deployment PodTemplate even at
replicas0, plus app Pod specs, before scale/rollout. Plain `batch activate`
therefore charges512+192, not the base256+192. Missing/wrong markers, changed
requests/limits/CPU, unknown containers, unsupported pod-level resources, and
unapproved init containers fail closed before a mutating subprocess. Capacity
operations additionally read the exact selected Deployment, so absence is not
interpreted as a base template. The pure exact resource oracle extracted from
b476f7ab's tests accounts for all regular containers, cumulative restartable
init sidecars and sequential-init peaks, with no circular safety import.
The explicit approved profile has no init containers: adding one is drift,
even if its effective ceiling would otherwise fit.

`provider prepare` upgrades the STOPPED retained Deployment, not a base reapply.
It requires all namespace pods absent and replicas0, builds and validates the
prospective complete spec and704 admission BEFORE any ConfigMap/Secret/patch
mutation, then JSON-patches using test(original spec)/replace(expected spec).
The merge preserves restored PVC claims, bootstrap Secret refs, env credentials,
images, other volumes and all nonprofile fields; post-read requires exact spec
agreement. Original archives are neither read nor changed. The legacy256 RSS
profile can only be upgraded through this stopped prospective validation;
ordinary activation rejects its missing384 marker rather than inferring approval.
No offline patch command was executed against the proof cluster.

## Exact public-source update review

Web search preceded public source fetch. Reviewed pinned Pinchflat
[`076f2fe78b32f5f0a4997639c89601774d34016b`](https://github.com/kieraneglin/pinchflat/tree/076f2fe78b32f5f0a4997639c89601774d34016b)
(v2025.6.6), specifically:

- [`config/runtime.exs`](https://github.com/kieraneglin/pinchflat/blob/076f2fe78b32f5f0a4997639c89601774d34016b/config/runtime.exs):
  YT_DLP_WORKER_CONCURRENCY applies separately to four extractor queues, NOT a
  global concurrency cap. `local_data` remains separate. Cron schedules updater.
- [`lib/pinchflat/yt_dlp/update_worker.ex`](https://github.com/kieraneglin/pinchflat/blob/076f2fe78b32f5f0a4997639c89601774d34016b/lib/pinchflat/yt_dlp/update_worker.ex):
  documentation explicitly says boot and cron; perform unconditionally calls
  runner.update, then version and Settings.set. There is no disable/immutable
  environment branch in this worker.
- [`lib/pinchflat/yt_dlp/command_runner.ex`](https://github.com/kieraneglin/pinchflat/blob/076f2fe78b32f5f0a4997639c89601774d34016b/lib/pinchflat/yt_dlp/command_runner.ex):
  update invokes configured executable with `["--update"]` directly; errors are
  returned. Download-only extra configuration is not an update-disable contract.
- Also reviewed config/config.exs, application.ex, yt_dlp_command_runner.ex and
  docker/selfhosted.Dockerfile. No supported native immutable-downloader or
  update-disable switch was established in these exact reviewed paths.

Therefore NO guessed environment toggle, arbitrary process kill, hidden global
concurrency change, worker replacement, downloader replacement or read-only
binary mount is introduced. Existing network denial stays authoritative for
external update attempts; it is not proof that the updater consumes no memory,
never ran, or cannot alter the binary by some unobserved mechanism. Actual
stock path/version/hash before AND after, and native updater job states/logs,
remain required runtime gates. Public source text was retained in a unique
private workstation directory with exclusive0600 files, not raw binary stdout.

## One future window procedure and stop gates — UNEXECUTED

Only AFTER explicit parent grant with both fields, exact target identity and fresh
704-or-greater available-memory receipt:

1. Run stopped `provider prepare` with the exact existing120214-byte fixture;
   preserve existing credentials/config/download PVCs. Never use base `start`
   to install this profile and never regenerate the fixture.
2. One `batch activate pinchflat STATE`. Startup checks Pod termination/restart
   status every second before rollout acceptance. First observed termination,
   OOM/restart or timeout captures observations then scales0 and waits deletion.
3. Guarded `provider exercise` first validates actual bundled ELF erl_call path,
   SHA, running release node/cookie compatibility and native stdout. There is NO
   extra-BEAM fallback and no automatic remote-expression retry on timeout.
   Native command boundaries check restart/termination before and after exec;
   failure retains private evidence and attempts observation→scale0→pod deletion.
   No second exercise/activation after a known OOM is authorized. Kubelet can
   restart between samples; these checks are fail-stop detection, NOT a claim
   Kubernetes restartPolicy prevents an instantaneous first restart. Parent must
   observe throughout and revoke the window on the first OOM; cleanup failure
   requires parent action, never retry.
4. Measure actual cgroup/process overhead and retain all failures. Boot updater
   overlap is still possible before native queue pause. Check real stock yt-dlp
   identity, independent metadata, native Source/index/download job relationships,
   unique download-phase byte coverage and actual output hash. Missing runtime
   ELF, unsupported transport/schema/extractor or immutable identity fails closed.
   No binary replacement, source/output preseed or external allowance fallback.
5. Stop/delete all app/helper pods and release/revoke receipt. Additional
   replacement/recovery activations are NOT included in this one-activation
   experiment; parent must separately approve them later.

Offline evidence: all23 media test files passed, including transferred indexer
socket tests (not compatibility review); the new budget suite has6 methods.
Root and optional RSS static Kustomize safety renders pass; whitespace passes.
Tests cover retained-profile704 admission/703 and old576 denial, exact receipt
type/markers, resource and init drift, no mutating subprocess on bad activation,
stopped prospective admission, atomic full-spec/PVC/Secret preservation, no
known termination retry, and the inherited sequential/restartable-init oracle.
Actual native ELF/stock yt-dlp identity and measured384 MiB behavior remain
UNTESTED. Parent retains brief/readiness/root gates and acceptance.
