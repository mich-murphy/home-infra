# Failed-preflight release and read-only diagnosis — OFFLINE, no grant

These are separate scopes, not a full-run retry or extensions to the native six
PHASES. Original run `33d6df9f-c2a8-459f-8eef-bc5fc3bfbdc1` remains PENDING;
its receipt is released. Its exact historical RuntimeException gate is **lost**.
All original journals, receipts, indexes and data remain untouched. Backend
startup may have written PostgreSQL/Redis volumes; there is no renewed backend
volume-emptiness claim. Parent owns root gates, independent acceptance and every
future authority. No runtime query/activation/release occurred in this work.

Entry point: `python3 scripts/talos-proof-nextcloud-preflight.py ACTION --state
$HOME/.local/state/talos-data-proof --run-id PARENT_KNOWN_V4_UUID`.
Actions are only `release-preflight`, `diagnose-preflight`, and diagnostic `stop`.
No legacy CLI, credentials generation, VM start or authority issuance exists.

## Bounded private error evidence

PHP gate failures now retain a bounded private message (1024 bytes), source-file
basename/line, and bounded structured context. Parity failures report the source
root/relative path, expected SHA256 and actual SHA256 (or explicitly unavailable).
Known credential environment **values** and long opaque token-like strings are
redacted from messages; no environment dump, argv, full trace or trace arguments
are emitted. CLI public errors remain fixed class-only messages. These detailed
records belong only in privately captured Pod output, never raw public evidence.

`nativeCommand()` waits for the child, then flushes/fsyncs its exclusive0600 log
**before** raising a nonzero-exit failure. Private failure context retains bounded
log location and exit code, never the command arguments. Failing child logs and
partial state are retained. Cgroup observations still read actual kernel files;
no fabricated counters or weakened counter validation was introduced. Historical
class-only failure output cannot be retroactively expanded into an exact cause.

## Common NEW receipt fields

A parent-issued immutable0600 `TALOS_PROOF_DATA_LEASE` must contain:

- `action` equal to the exact action, `phases: [action]`, canonical v4 `run_id`;
  **new** canonical v4 `authorization_id`, distinct from run_id and never consumed
  in any shared journal; finite numeric Unix `issued` and `expires`.
- `group: nextcloud`, `stage: cron`, `namespace: proof-nextcloud`, existing
  canonical `state_dir`, exact `context`, loopback `endpoint`, `node_uid`,
  `namespace_uid`, `html_claim`, complete retained `object_uids`,
  `backend_images`, and exact six-name `network_policy_uids` from the native
  receipt. No fresh directory or guessed/adopted identity can hide pending work.
- `budget_mib: 832`, `synthetic_age: false`, `cleanup_authorized: true`, sorted
  `selected_controllers: [cronjob/nextcloud-cron, deployment/postgres,
  deployment/redis]`. Cleanup here means guarded stop/owned helper retirement,
  **not** authorization for native fixture cleanup or another main run.
- `reviewed_source_sha256`: exact path→SHA256 map of all **five current** files:
  compiler `scripts/talos-proof-nextcloud-cron.py`, payload
  `scripts/talos-proof-nextcloud-cron.php`, supervisor
  `scripts/talos-proof-nextcloud-cron-supervisor.py`, lifecycle
  `scripts/talos-proof-data.py`, recovery `scripts/talos-proof-nextcloud-preflight.py`.
- `reviewed_artifact_sha256`: exact path→SHA256 map of all **four current** files:
  `docs/evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json`,
  `docs/evidence/talos-data/nextcloud-cron-docker-config-source.json`,
  `docs/evidence/talos-data/nextcloud-packaged-metadata-bridge-49e437a1-23fe-491f-92e9-541137daaa6a.json`,
  `docs/evidence/talos-data/nextcloud-public-image-parity-412faf37-f124-44b2-b52a-418ad71f9cd0.json`.

Both maps are checked locally by authorization, including on later operations;
missing/extra/changed bindings reject before API work. Compiler code determines
Job and payload, while packaged metadata and indexes determine effective parity:
none may float under a diagnostic receipt. These **current-authority** bindings
are separate from the original receipt/source provenance described below.
Receipt bytes cannot change. A durable exclusive UUID `preflight-authorized`
event consumes the new authorization before the first runtime query. New events
never overwrite referenced history. Same-ID invocation replay rejects.

## `release-preflight`: original run, GET-only runtime

Additional exact bindings:

- `origin_receipt_path`, `origin_receipt_sha256`: immutable issued original native
  receipt; its expiry is inert provenance, not permission to act.
- `origin_source_sha256`: exact original `reviewed_source_sha256` map from that
  receipt. **Do not substitute current hashes into this original map.**
- `origin_journal_sha256`: original-run canonical UUID.json basename→SHA256 map,
  covering all12 original-run events, not unrelated credentials/forensic files.
- `origin_preflight_document_sha256`: canonical JSON SHA256 of the exact original
  Job document (`json.dumps(..., sort_keys=True, separators=(',', ':'))`).
- `preflight_job_uid`: exact original observed Job UID;
  `payload_configmap_uid`: exact retained original payload ConfigMap UID.
- `origin_stop_snapshot_path`, `origin_stop_snapshot_sha256`: immutable original
  post-failure stopped API snapshot. Its timestamp must follow the failed Pod's
  termination and precede new issuance; namespace/Node UIDs and global proof
  absence/stopped/suspended state must match.

At least300seconds must remain. Local proof requires the sole pending original
transaction, exact main-run receipt/intent, exactly one original preflight
phase-intent/create, original fixed RO HTML/env/command Job document, failed Pod
owner UID/full envelope/nonzero exit/restart0, original private payload failure,
blocked/retired-helper state and stop records. Missing/changed/duplicate/unknown
history, stop-unconfirmed, foreign pending, clean, cleanup or any later-phase
intent/create rejects. The original runner had no final stop-confirmed journal
event: the separately hash-bound post-failure stopped snapshot is therefore
mandatory, not an invented historical event.

Runtime operations are **GET-only** (trusted lifecycle target validation also
reads local kube config). No Kubernetes mutation, backend/helper activation,
Pod exec, application command or deletion is possible through this scope.
Fresh native identity/spec readback, **every retained UID/name/namespace**, six
policy specs, all stopped controllers/suspended schedules and all global proof
Pod/Job/DaemonSet absence are required. The retained original ConfigMap must
match its original UID and **original PHP SHA256**, not the updated payload.
The unchanged exact Job-shape oracle plus original canonical-document binding
remain valid despite the compiler's new packaged-metadata bridge; no original
compiler/source hash is rewritten or falsely compared with current code.

Only after proof and final absence checks append `preflight-release-observation`
(`historical_failure_gate: unknown`, `native_acceptance: false`) and one clean.
The original pending event stays. Failures append a blocked observation, never
clean. No parity/DB/Redis/emptiness/install/native acceptance follows. Original
full-run failure behavior and UUID-reuse rejection are unchanged.

## `diagnose-preflight`: separate new run, one read-only helper

Requires a **different unused parent-known run UUID**, no pending transaction,
at least900seconds remaining, and additional `document_sha256` bindings for the
exact generated `configmap/nextcloud-cron-payload-<newrun>` and
`job/nc-preflight-<newrun>` documents, canonically hashed as above. This scope
cannot reuse an original main receipt or hide pending state in another directory.

The generated helper derives from the unchanged bounded preflight Job, with
only fixed PROOF_PHASE `diagnose-preflight`, explicit current HTML alias and
readOnlyRootFilesystem true. HTML and payload mounts are read-only;192MiB,
UID/GID33, no token/init/sidecar, backoff0 and180second deadline remain. Fixture
intent JSON is removed from its ConfigMap. The public compiler/main PHASES and
supervisor actions are **not widened**. Only this separate guarded entry point
can authorize its exact documents; non-Job/declaration/Secret changes, alternate
Jobs, arbitrary patches/deletes, exec and main phases reject.

Reuse fresh dual832 admission, native identities/envelopes, all retained UIDs,
six policies and global proof barriers before starting only PG384/Redis64 and
before the one192MiB helper. PHP `preflight(true)` requires HTML empty **before
PDO/cache checks**; on nonempty HTML it never calls nativeContext/loads core.
PDO uses session default_transaction_read_only; Redis only connects/AUTH/PING.
No install, token generation/aging, job execution, TTL/last_run change or native
fixture cleanup is authorized. Source/config parity remains strict, with only
the exact artifact bridge below. Success additionally requires explicit empty
HTML, zero application DB objects and authenticated Redis result fields.

Capture all helper raw state/current/applicable previous logs and actual kernel
counters before interpretation/deletion; validate namespace/owner UID/full Pod
envelope. Retire only the observed recorded UID using existing exact Job deletion
and Pod absence checks. Always attempt guarded backend stop, including on failure.
Only confirmed final backend/helper/global proof absence plus stopped controllers
permits `diagnostic-result` and one clean, even if the diagnostic failed: no
fixture was authorized. Failure status remains and CLI still exits1. This narrow
rule does **not** clean a main-run pending journal. Unreachable/unknown/unconfirmed
cleanup keeps PENDING. Unexpired diagnostic `stop` can retire only recorded own
helpers and stop exact backends; it is not activation or an expiry refresh.

## Strict packaged `version.php` bridge

The original Git source index remains byte-for-byte unchanged. New record
`nextcloud-packaged-metadata-bridge-49e437a1-23fe-491f-92e9-541137daaa6a.json`
binds current image index786c…752a2, linux/amd64 manifest3139…3ef3, configb5cf…0f5a,
public inspection/parent-review identities, original Git version.php hash
`0c5e1bfe12870e43d2a9965063d97dd261a351e96d6d81f854b29857ceac5e25` (870bytes)
and packaged hash `91f47176c67a94f3e33e4fcee8f272cfc72210614b25906fa228cc27c72b07ea`
(446bytes). Compiler pins the complete bridge's SHA256 and its evidence/index
hashes, requires exact image/platform and **only version.php**, and produces
24 unchanged Git core hashes plus this exact packaged hash. All10 Docker config
hashes remain unchanged. PHP checks the exact bridge bytes/platform and each
actual source hash; no binary is replaced, no hash is skipped and no blanket
metadata/version equivalence is asserted. Channel/build/edition/format differences
remain documented in the public inspection record. This proves a current strict
Git-only guard would reject the reviewed public artifact, **not** the exact
historical failing gate. No image/layer download or runtime inspection occurred
in this correction.

## Validation / private candidate (not authority)

Focused: recovery14 + compiler15 + supervisor40 + initializer35 + data42 = **146**
passing tests. WOPI14 + workflows20 also pass: **180 total**. Coverage includes
original proof/hash/UID/policy/namespace/RO/env/command/history/timestamp rejection,
GET-only release, diagnostic one-shot/cross-use/replay boundaries, actual Pod
owner/envelope/counter/result validation, capture-before-UID-retirement and failed
diagnosis versus confirmed/unconfirmed stop. PHP error/log/diagnostic constraints
are source-contract tests; no PHP application was executed. Workstation Nix
PHP8.5.12 syntax lint and `git diff --check` pass. Cluster/Talos/VM/image/app calls
were forbidden or mocked; existing serialization tests use isolated local Python.
No root CI/gate or runtime acceptance is claimed.

Historical offline replay passes against all12 original-run events, the original
stopped snapshot, all15 retained UIDs and six policies; original-vs-current PHP
hash distinction is verified. No authority was consumed, release performed or
canonical state file changed. Private candidate schemas include explicit parent
placeholders for authorization/issued/expires and cannot act as receipts. Parent
must independently review current source/artifact/document hashes and fresh
runtime conditions before separately granting release, then diagnosis.

The192MiB trial/832MiB gate/ini are unchanged. Nextcloud35's128MB minimum and512MB
recommended per-process/PHP memory_limit context is not actual measurement or
capacity acceptance. No native install/cron/functionality/durability claim follows.

Final private candidate (NOT receipt/authority):
`$HOME/.local/state/home-infra/talos-proof/diagnostics/preflight-recovery-offline-candidate-730f543b-6268-42dc-a615-51489b6c282e.json`.
It binds all five current source files, all four current artifacts, original
provenance and separate diagnostic documents. New authorization/time fields are
parent placeholders. Fresh parent review, separate grants, runtime admission and
pinned-image behavior remain unmeasured; original PENDING has not been released.
