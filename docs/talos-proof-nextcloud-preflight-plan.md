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

These remain **four direct artifacts**, not five: the fixed parent acceptance
record `docs/evidence/talos-acceptance/nextcloud-public-image-review-a8a4347c61c34638a3b4946fb331c769.json`
is a **transitive** bridge binding. Every compiler bridge validation checks that
exact permitted path and its recorded SHA256; authorization invokes it before
consumption and on later operations, before any runtime operation. A missing or
changed parent review rejects. Source5/artifact4/document bindings remain separate.

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
  Exact multiplicities are one each of pending, backend-start-intent, phase-intent,
  phase-created, pods, private-log, blocked-pending-cleanup, stop-intent and
  stop-pods, plus **three memory events**. Missing/extra events reject even when
  the remaining files and map are rehashed.
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
mandatory, not an invented historical event. Raw snapshot controller entries must
carry kind/name/namespace/UID/spec, include every retained Deployment/CronJob
(including frontend, both backends and the suspended cron schedule), match retained
UIDs and explicitly show stopped replica state. Empty/sparse controller lists do
not prove absence. For the known original run, snapshot hash and failed Job/Pod
UIDs must also match the independently accepted public native-failure review
320eb83b; this is provenance binding, not a new attestation. Fresh runtime checks
remain independent of this snapshot.

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
Jobs, arbitrary patches/deletes, generic exec and main phases reject. The sole
backend cgroup-reader exception is specified below.

Reuse fresh dual832 admission, native identities/envelopes, all retained UIDs,
six policies and global proof barriers before starting only PG384/Redis64 and
before the one192MiB helper. Diagnostic-specific admission additionally rejects
every global proof Job/DaemonSet object, including suspended, terminal and Podless
objects. Before startup no proof Pod is allowed; after startup only full-envelope
backend Pods with exact ReplicaSet UID and retained Deployment ownership pass.
The original main Supervisor and lifecycle semantics are unchanged. PHP `preflight(true)` requires HTML empty **before
PDO/cache checks**; on nonempty HTML it never calls nativeContext/loads core.
PDO uses session default_transaction_read_only; Redis only connects/AUTH/PING.
No install, token generation/aging, job execution, TTL/last_run change or native
fixture cleanup is authorized. Source/config parity remains strict, with only
the exact artifact bridge below. Success additionally requires explicit empty
HTML, zero application DB objects and authenticated Redis result fields.

Capture all helper raw state/current/applicable previous logs and actual kernel
counters before interpretation/deletion; validate namespace/owner UID/full Pod
envelope. Retire only the observed recorded UID using existing exact Job deletion
and Pod absence checks. Always attempt guarded backend stop, including on failure. Diagnostic-only stop
independently attempts each backend UID-tested zero-replica patch and recorded
helper capture/UID retirement, accumulating failures rather than aborting the
chain. Helper capture must precede deletion; incomplete capture prevents deletion.
No unknown UID is adopted and no failed helper cleanup is automatically retried
by the final stop in the same invocation. Target, namespace, receipt expiry and
UID guards remain mandatory for each operation. Any cleanup uncertainty keeps
final confirmation failed/PENDING even if later absence reads appear stopped.
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

## Focused HOLD remediation — offline only

The positive synthetic release fixture now contains all12 required events (including
three memory observations) and actual retained stopped controller objects. New
regressions remove a memory event entirely, remove retained controllers, and
rehash empty/sparse/changed snapshots; each rejects. Diagnostic admission and stop
regressions exercise the actual validators/cleanup chain (API responses and the
external memory probe are mocked, not the entire admission/stop method). They
cover global Podless/suspended/terminal Jobs/DaemonSets, startup/owned-backend
boundaries, first/second backend patch failures, capture failure and UID retirement
failure, with no clean on uncertainty. Missing/changed transitive parent review
also rejects before authorization consumption or runtime work.

This correction did not read private historical proof state or perform another
historical replay. The earlier replay/static-gate reports above are prior evidence,
not fresh attestation. No historical file, receipt, immutable public image/source
artifact, parent acceptance record, grant, original PENDING event or RELEASED
receipt was changed. No live acceptance or pending release is claimed.

Fresh focused validation after this correction: recovery18 + compiler15 +
supervisor40 + initializer35 + data42 + WOPI14 + workflows20 = **184 Python tests
passing, no skips**; `git diff --check` passes. No PHP payload, browser, cluster,
Talos, VM, credentials, CI, or full static gate was run for this correction.

## Focused post-57af7334 follow-up — offline only

Post-start diagnostic admission requires exactly one PostgreSQL Pod and one Redis
Pod in each observed global Pod snapshot. Both must be Running and Ready, without
termination, restart, previous container-state/OOM evidence or missing/unknown
status; exact owner chains and actual Pod envelopes still apply. All observed
backend Pod memory limits are summed, then the unchanged192MiB helper and192MiB
reserve charged against832MiB. Duplicate valid Pods therefore cannot hide behind
Deployment counts. Before startup, zero proof Pods remains mandatory. Deployment
strategies, resource declarations and admission thresholds are unchanged.

Diagnostic STOP helper retirement requires complete raw capture followed by strict
namespace/recorded Job UID ownership and UID-preconditioned deletion, but no longer
requires the captured Pod's resources/image/spec to match a healthy activation
Pod. A drifted known-owned helper can be captured and retired without accepting
its evidence or clearing diagnostic failure. Unknown ownership or changed live Job
UID blocks retirement. Normal diagnostic activation/evidence envelopes remain
strict. Main Supervisor/lifecycle semantics, target/expiry guards and no-retry
behavior are unchanged.

Expanded actual-admission/STOP regressions cover duplicate valid PostgreSQL Pods,
terminating-plus-replacement Pods, terminal/unknown/Pending/unready/restarted/OOM
backends, the healthy two-Running-Pod positive, drifted-resource helper raw capture
and guarded retirement, and unknown-owner/live-UID retirement rejection. These are
synthetic offline fixtures, not live acceptance or a private historical replay.

## Projected metadata reader — offline correction after diagnostic43

Evidence-only commit `27607487` retains the one diagnostic43 failure and confirmed
stop separately from this source correction. The payload reported fixed gate
`reviewed packaged metadata drift`, expected bridge SHA25686a6…de32c and actual
hash unavailable for `/proof/packaged-metadata.json`. **Live file type was not
captured; the actual runtime reason for unavailable remains unknown.** This new
GateFailure does not recover the original run's RuntimeException cause. Neither
failure authorizes a retry or any further runtime operation.

Official Kubernetes research (repository search before fetching source):
- [AtomicWriter, Kubernetes v1.35.0, lines39–57](https://github.com/kubernetes/kubernetes/blob/v1.35.0/pkg/volume/util/atomic_writer.go#L39-L57)
  documents visible-file symlinks, hidden timestamp directories and atomic data-link
  replacement. [Lines458–481](https://github.com/kubernetes/kubernetes/blob/v1.35.0/pkg/volume/util/atomic_writer.go#L458-L481)
  show the visible `key -> ..data/key` links. This is an upstream layout reference,
  **not evidence of the failed live mount's layout**.
- The original ordinary-source `hashCheck()` requires `!is_link($path)`; real
  workstation PHP reproduces its rejection of a normal projected ConfigMap key.

`projectedMetadata()` is a separate no-path-arguments reader for **only** the
fixed `/proof/packaged-metadata.json` key. Existing receipt/document validation
still binds the exact read-only ConfigMap mount and helper scope. The reader
requires the exact relative key link, relative single-component AtomicWriter
numeric timestamp data link, real non-link mount/ancestors/timestamp directory,
and single-link regular target inside that mount. Absolute/escaping/nested or
alternate key links, extra target symlinks, hardlinks, special files and ordinary
file fallback reject. It caps metadata at8192bytes, opens the regular target,
checks descriptor/path identities and complete projection snapshots before and
after the bounded read, and requires the same exact bridge SHA25686a6…de32c.
The JSON parser consumes those already-hashed bytes, not a second path read.
Fixed private gates distinguish unavailable path, wrong type, unavailable read,
bounds, changed identity and hash mismatch without emitting contents/environment.
The read-only mount and immutable AtomicWriter timestamp files remain deployment
prerequisites; this is not a general hostile writable-filesystem reader.

Image and HTML/PVC `hashCheck()` and ancestor-link checks remain unchanged and
strict. Original source indexes, bridge bytes/hash, image override semantics,
PHASES, Job scope/resources,192MiB helper limit and832MiB gate remain unchanged.
Only the PHP reader and its tests/documentation change in this correction; new
source/document hashes must be independently reviewed for any future authority.

Mandatory regression entry point:
`TALOS_PROOF_TEST_PHP=/absolute/locked-Nix-PHP/bin/php python3 tests/talos-proof-nextcloud-projection_test.py`.
Missing/nonabsolute/non-Nix tools fail explicitly; no optional skips or automatic
tool discovery/build/network. Parent owns flake/devShell/CI/fullgate wiring.
The15 real-PHP filesystem tests run `php -n` with fresh private0700 HOME/temp,
0600 fixture files, minimal environment, disabled process/network functions and
5second per-process timeout. Only extracted production guard declarations run;
the literal mount is relocated solely in the test copy, with no production
path override. Deterministic namespaced I/O seams perform real filesystem swaps
at open/read boundaries; they are not callbacks in production. Coverage includes
normal projection, missing/escaping/alternate/special/corrupt/oversized targets,
ancestor links, hardlinks, same-target link replacement, target inode swaps,
read failure, and unchanged strict ordinary source/PVC symlink rejection.
No Nextcloud application, image, PVC or proof-state copy is executed or created.

This correction is **not a grant, live validation or native acceptance**. Diagnostic43
scope is RELEASED and its failed result remains failed. Parent review and a
separate NEW diagnostic authorization are required before any further runtime work.

Fresh focused validation:15 mandatory real-PHP filesystem tests passed using the
parent-wired project-lock PHP8.5.7 executable (`php -n`, not earlier8.5.12 and not
proof-image execution). Related compiler15 + recovery18 + supervisor40 +
initializer35 + data42 + WOPI14 + workflows20 also pass: **199 tests total, no
skips**. Full-payload syntax lint with the same locked PHP8.5.7 and fresh private
HOME passed; `git diff --check` passed. Parent owns the full static gate; no new
runtime, SSH, credential read, proof-data mutation, image or PHP application
execution occurred during this source correction.


## Diagnostic-only backend forensics — offline source correction

Historical source gap: parent reports that diagnostic43's4515 capture files
contain only two logs requests (both for its own PHP helper) and zero execs.
The old stop retained raw backend Pod state but did not request backend current/
previous logs or cgroup counters before scale-to-zero. Evidence27607487 and parent
review b47846fac38c4b8a899f090b6c0a66fc remain immutable. Backend OOM absence,
continuous zero events, and the original RuntimeException cause are **unknown**;
this correction cannot reconstruct them and has not read historical private state.

A NEW diagnostic receipt must additionally bind
`backend_forensics_profile: backend-cgroup-v2-timeout-cat-four-files-serial-v1`.
Missing/other profiles fail local authorization before API use; old receipts are
not reusable. Source5/artifact4/document bindings still apply. Release authority,
main PHASES, PHP payload (including projected reader), supervisor and lifecycle
are unchanged. No grant or diagnostic retry is issued by this source change.

Before EACH backend's UID-tested zero-replica patch, retain private raw namespace
Pod lists and each relevant Pod's complete metadata/spec/status (UID, containerID,
restartCount and lastState included). Resolve ReplicaSet ownership to the retained
Deployment UID, rather than trusting labels or RS name prefixes. Include known
lifetimes observed during admission, duplicates, terminating Pods and replacements;
missing lifetimes/cardinality changes fail acceptance. Refresh and retain the final
Pod list to expose replacement races. This is finite sampling, not a watch or a
claim to capture unobserved lifetimes between samples.

For each identity-confirmed owned backend, attempt explicit-container current logs
and previous logs when restartCount or lastState makes them applicable. For each
owned Running container, serially issue exactly four commands, one fixed path per
command: `timeout 2 cat /sys/fs/cgroup/memory.current`, then `memory.peak`,
`memory.events`, and `memory.stat`. Each uses namespace, recorded Pod name,
explicit container, `--request-timeout=5s`, and no stdin/TTY/shell. The command
allowlist rejects other paths/flags/programs; no shell input, environment dump,
credential lookup or generic exec is authorized. Missing image tools, inaccessible
cgroup paths, failed requests or malformed outputs are gaps, never synthetic zero.
The two-second in-container timeout bounds each reader; existing shared transport
limits and lease/target checks remain intact. Tool availability and image cgroup
layout remain unmeasured live prerequisites, not assumed passing evidence.

Exec pre/post checks bind namespace/Pod UID, node name/receipt node UID,
containerID/restart/state and RS→retained Deployment UID. Raw successful exec
output is saved privately before post-check interpretation, so post-read drift
still leaves the sample but fails acceptance. No shared guard bypass is used.
Memory current/peak must be positive integers within the unchanged backend limit;
events/stat require strict unique nonnegative integer fields. Missing counters,
OOM/oom_kill, max/high events, restarts/lastState or malformed output fail. Reads
are sequential: no peak>=current assertion or continuous-zero inference follows.

Resource drift does not prevent capturing an identity-confirmed owned Pod, but
fails acceptance. Capture and stop attempts are independent per backend: a PG
capture/control failure cannot suppress Redis capture/stop or legitimate helper
capture/retirement. Identity-only known-controller stop may proceed for safety;
unknown Pods are never deleted. Any capture/ownership/control uncertainty retains
PENDING and prevents clean even if later absence checks pass. Helper capture before
UID retirement and full namespace/target guards remain. No retry loop is added.

The small reader processes run serially inside the already charged backend
cgroups, consume sampling CPU/memory and can themselves affect sampled peaks.
No helper resources, tuning or budget relaxation: PG384 + Redis64 + CLI192 +
reserve192 =832MiB remains fixed. This is diagnostic sampling, **not** capacity,
full forensics, native acceptance, or retrospective backend OOM0 evidence.

Fresh offline validation: recovery25 actual-method tests and all15 mandatory real
PHP projection tests pass with project-lock PHP8.5.7 (`php -n`). The PHP code and
projection tests are unchanged. No cluster/runtime/SSH/proof-state/credential/
receipt access, image execution, CI or push occurred. Parent owns fullgate,
independent review and any separate new authority.
