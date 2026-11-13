# Guarded serial native Nextcloud cron — OFFLINE implementation

**No live grant, cluster/VM/API/image/runtime execution, or new functional PASS.**
The legacy lastcron-only lifecycle remains hard-blocked. This supersedes the
ff667cea draft checkpoint, not the retained application evidence or readiness gates.
Actual image/config/retained-state/Redis preflight requires a **new parent grant**.

## Source and resource contract

Core v35.0.2 commit `ba900af933e61ffa005315b09d6454bfbbcbcc81` and Docker commit
`7e9e152f77372845195ed28dc65569df74f582ff` remain immutable. The original
[27-file index](evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json)
is unchanged. [Docker configuration supplement](evidence/talos-data/nextcloud-cron-docker-config-source.json)
records ten additional immutable public configuration files, hashes and sizes.
Source is **not** image attestation. Runtime parity mismatch blocks.

Exact CLI image:
`nextcloud:35.0.2-apache@sha256:786c102155d2717ba0f53a62b3fdd7a1354edc48e800b94dbe32294d9a5752a2`.
Budget unchanged: PG384 + Redis64 + **one** CLI/Cron192 + reserve192 = **832MiB**.
No Apache, frontend, Office, Immich, ML, media, sidecar or observer interpreter.
No resource shrink, production import, credential generation/rotation, upgrade,
clean-slate retry or retained-content chown/delete.

## Entry points and future receipt (not permission to run now)

- `scripts/talos-proof-nextcloud-cron.py compile`: private offline bundle only;
  its `run` action still blocks. Never manually apply compiled documents.
- `scripts/talos-proof-nextcloud-cron-supervisor.py`: concrete guarded supervisor.
  Future actions `run`, `stop`, `cleanup` require `--state` and parent-known
  canonical v4 `--run-id`. No VM start, receipt issuance or lease refresh exists.
- `scripts/talos-proof-nextcloud-cron.php`: native PHP payload, not a standalone
  authorization boundary. Invoking it manually bypasses the supervisor contract
  and is forbidden.

A new private0600 `TALOS_PROOF_DATA_LEASE` must contain existing data-lease
context/endpoint/node UID/expiry fields and these exact bindings (including a
parent-recorded `namespace_uid` for proof-nextcloud):

- group `nextcloud`, stage `cron`, canonical run_id, canonical outside-Git
  state_dir (the **same existing private data state directory**, never a fresh
  directory to evade pending cleanup);
- phases `preflight`, `install-or-verify`, `fixture`, `before`, `cron`,
  `assert-restore`, in that order;
- budget_mib832, synthetic_age true, cleanup_authorized true;
- sorted selected_controllers: cronjob/nextcloud-cron, deployment/postgres,
  deployment/redis;
- object_uids mapping exact kind/name to original UID: application PVC, Secret,
  live Nextcloud Deployment, both backend Deployments, suspended CronJob,
  **every desired backend PVC and every associated PV**;
- html_claim bound to the current `/var/www/html` mapping in **both** the live
  Deployment and CronJob; no implicit `nextcloud-data` fallback after restore;
- backend_images mapping postgres and redis to exact parent-reviewed image
  references; these are compared to Deployments and actual pod specifications;
- `network_policy_uids`: an exact six-entry mapping from **unqualified policy
  name** to parent-observed UID: `default-deny`, `dns`,
  `nextcloud-to-postgres-ingress`, `nextcloud-to-postgres-egress`,
  `nextcloud-to-redis-ingress`, `nextcloud-to-redis-egress`. Native activation
  requires each live policy's exact UID, namespace `proof-nextcloud`, name,
  networking.k8s.io/v1 kind and full spec matching its existing declaration in
  `kubernetes/apps/data/nextcloud/networkpolicy.yaml`. Missing/terminating
  policies, broader rules, DNS/default-deny drift and unknown spec fields reject.
  No receipt field or activation check creates/repairs policies.

The immutable receipt must cover the entire serial sequence plus cleanup window;
start requires at least six240second phase allowances plus300seconds. This is a
minimum authorization window, not a guarantee that API operations finish in it.
Local receipt rejection occurs before API work. Every operation revalidates the
existing data lease, context, exact loopback endpoint and target node UID. Receipt
changes or expiry block, including recovery; only a new parent grant can recover.

## Implemented execution path

1. Lock the private journal directory (one supervisor). Scan append-only UUID
   journals; unresolved pending runs block activation. Export parent-known UUID
   and exact candidate/control names to fsynced off-pod intent **before mutation**.
   All new supervisor artifacts are UUID/O_EXCL0600, parent directory0700.
2. Before any scale/fixture/install mutation, validate retained Kubernetes
   identities, every desired PVC/PV UID, Bound/proof-local and exact claimRef
   namespace/name/UID. Validate the entire CronJob pod security/resource/init/
   execution template against the reviewed manifest (only enumerated API
   defaults allowed), not only at the cron phase. Backend templates and actual
   Pods must match their full approved ceilings, including CPU, memory,
   overhead, pod-level resources and init shape. Require all
   other proof app/helper controllers zero and every proof schedule suspended.
   All proof Job pods block, even completed/failed/terminating/unlabelled; other
   proof pods, including validation/gateway helpers, block. No parallel helper.
3. Independently observe kubelet availableBytes (timestamp at most30seconds old)
   and explicit-endpoint Talos `/proc/meminfo` MemAvailable. Both must meet832MiB;
   receipt-reported memory cannot substitute. Recheck helper absence. Start only
   the two receipt-bound backend Deployments, wait, and re-admit.
4. Create payload ConfigMap and exactly one UUID-named phase Job at a time.
   Each phase repeats identities/helper barriers and fresh dual memory checks.
   Jobs have backoffLimit0, deadline180seconds, UID/GID33, no SA token, no init/
   sidecar, RuntimeDefault and dropALL. Cron phase derives from the actual
   suspended CronJob template; the full envelope was already validated before
   backend activation and is revalidated at each admission.
5. Preflight compares reviewed packaged core and all Docker config hashes;
   recursively inventories retained types/symlinks/UID33 ownership and allowed
   root entries; connects to PG with read-only transactions and authenticated
   Redis PING only. Empty PVC requires an empty designated database (relations,
   routines and extra namespaces). Nonempty PVC must bootstrap/verify the
   retained native install, exact version/config/backend/user/Redis and no
   upgrade. Unknown config fragments and ambiguous partial installations block.
   Read-only PVC is used for preflight: any native bootstrap write requirement
   fails, rather than silently relaxing read-only inspection.
6. Install-or-verify repeats preflight. Only jointly proven empty PVC+DB gets
   rsync from packaged code **without --delete**, then one native
   `maintenance:install`. Secrets are read inside the pod, never Job arguments
   or manifests. Native output is stored privately; failure preserves partial
   state and cannot earn retry permission. Retained installation is verified,
   never overwritten/reset. Actual permissions, CLI extensions/config and
   migration fit remain runtime measurements, not asserted passes.
7. Fixture uses native provider generation with **NULL password**, fresh random
   raw values, parent-known UUID names and exact IDs saved privately. No global
   session TTL change. PublicKeyToken's documented `setLastActivity` plus native
   PublicKeyTokenMapper's inherited entity update changes only the just-created
   owned candidate. **SYNTHETIC AGE, NOT REAL ELAPSED EXPIRY.** The remembered live
   control is untouched. No SQL insert/update or job completion spoof.
8. Fresh `before` process physically reads both owned rows and due metadata.
   Refuse any out-of-scope token eligible within the bounded run horizon across
   session, remembered, wipe and permanent retention. Unknown classes block.
   TokenCleanupJob must be uniquely registered, unreserved and strictly more
   than86400seconds since last_run. Class filtering does not bypass daily due.
9. Run actual `php -f /var/www/html/cron.php --
   'OC\Authentication\Token\TokenCleanupJob'` from the charged PHP payload.
   PHP reads native cgroup current/peak/events/stat for the same pod, including
   its child CLI. Missing measurements/OOM block; no extra Python container.
10. Capture all raw pod JSON/state/lastState/current and applicable previous
    logs **before** parsing JSON, interpreting BLOCKED, or validating OOM. A
    current-log failure still attempts previous logs and captures raw private
    error output. A gap fails acceptance. If fresh pod-state API capture works,
    retire the own helper even when a waiting/failed container has no logs. An
    unreachable API leaves pending/unconfirmed cleanup; never bypass guards.
    Ordinary payload/JSON/OOM failures do not skip deletion. Delete only the exact run/phase Job with its observed-create or
    parent-bound UID as an API DeleteOptions precondition. Verify both Job and
    pod absence before the next phase or returning a handled failure. Fresh final process requires physical candidate
    absence, exact unchanged live control, same job ID with native advanced
    scheduling metadata and lastcron corroboration. Lastcron or exit0 alone is
    insufficient. Only after observations, invalidate exact owned fixtures and
    verify absence, restore backgroundjobs_mode exact presence/value, verify
    unchanged typed global TTL. Failure assertions still attempt owned cleanup.
11. Stop backend Deployments and confirm pod absence. Only a verified end records
    `clean`. Exceptions record pending cleanup and attempt guarded stop; no guard
    bypass or automatic VM/backend restart. Existing lifecycle apply/activate/
    run/test also refuses pending journals in the shared private state directory.
    Stop/deactivate is not blocked by its own pending journal.

## Failure and recovery boundaries

No physical cleanup/restore is guaranteed if Node/API/guard is unreachable.
Preserve the VM stopped; do not start around the guard. The supervisor never
starts a VM. Parent/operator must keep/return the VM stopped when guarded stop
cannot be confirmed. A new exact parent recovery receipt is necessary after
expiry. `stop` does not inspect pending activation policy and accepts either
valid run or cleanup receipt scope; it scales backends to zero, captures/retires
only its UID-bound helper, then waits for namespace pod absence.

`cleanup` requires a **new** `action: cleanup` receipt with `phases: [cleanup]`,
the original pending run_id/intent, exact retained UIDs/images/HTML alias,
the same six-entry `network_policy_uids` prerequisite for backend activation,
budget832 and at least780seconds remaining. It never changes an old receipt or
expiry. It prevalidates identities/stopped controllers, captures and deletes
only the own prior UID-bound Job, performs fresh dual832 admission, starts
**only** PG/Redis, runs one192MiB cleanup CLI, captures/deletes it, and stops
all backends. No preflight/install/fixture/main cron rerun. The original payload
ConfigMap and native fixture journal must exist; no reconstruction or adoption.
It uses only names/UID/type/remember from the immutable intent and native journal
and cannot earn cron acceptance. If fixture mutation never
started, missing journal blocks rather than guessing success. A crash after
insert but before ID export is recoverable by the pre-exported exact UUID name.

No existing users, credentials, archives or partial installs are erased. This
path does not touch Pocket-ID34ef3547, Wallabag5622c159, private WOPI artifacts,
eight preserved WOPI failures, or offline-only ordered UI/native Save67 work.
No full Nextcloud/HTTP/WebDAV/Redis reconnect/capacity/durability claim follows.

## Offline validation

`python3 tests/talos-proof-nextcloud-cron_test.py` (8),
`python3 tests/talos-proof-nextcloud-cron-supervisor_test.py` (23), and
`python3 tests/talos-proof-data_test.py` (42) passed: **73 mocked/offline tests**.
`nix shell nixpkgs#php --command php -l scripts/talos-proof-nextcloud-cron.php`
passed with workstation PHP8.5.12. This is syntax only, not pinned-image runtime
compatibility. No unit command may reach Kubernetes/Talos/VM/image/runtime.

Remaining grant-bound measurements: actual source/config parity, UID33 inventory
and copy permission, retained DB/PVC state, actual native Redis config/access,
CLI bootstrap writes/extensions, due-job state, migration duration, real native
side effects and192MiB fit. Every unavailable measurement fails closed.


## Canonical shared journal and replay boundary

Both the legacy data CLI and supervisor require the one existing canonical
`$HOME/.local/state/talos-data-proof` directory (0700, outside Git, no symlinks).
No alternate `--state` or receipt `state_dir` can hide pending cleanup. Only
canonical UUID.json journals are parsed; credentials and prefixed forensic JSON
are not journals. Malformed/private-mode-invalid UUID journals fail closed.
Pending and clean event counts are shared across both entry points; duplicate
pending for a reused run remains blocked rather than being masked by an older
clean event. Full `run` refuses **any** prior journal event for that run UUID
before mutation, including after clean. Stop remains available. Initialization
must not migrate/overwrite existing private state to evade these rules.

## Separate stopped-object / read-only binding initializer — OFFLINE, no grant

Parent read-only discovery reported **zero PVC objects** in proof-nextcloud.
Prior eight native WOPI failures applied only CODE/fixture, not application/PG/
Redis storage. The UID-bound full runner still cannot initialize this state.

`scripts/talos-proof-nextcloud-initialize.py initialize --state <canonical-state>
--run-id <new-parent-known-v4-UUID>` is a **separate receipt scope**, not a cron
phase. No runtime call was made in implementing or testing it. Do not run it
without a NEW exact parent initialization grant. It never applies kustomize,
patches/replaces/adopts objects, generates credentials, starts web/PG/Redis,
installs Nextcloud, changes storage/host/lifecycle policy, or issues a full-run
receipt. Existing CODE/WOPI/Secrets/archives and PVCs remain untouched.

### Exact initialization receipt

Private0600 `TALOS_PROOF_DATA_LEASE` retains the ordinary data lease's context,
exact loopback endpoint, node_uid and expires fields, with:

- `action: initialize`, `group: nextcloud`, `stage: cron`, `namespace:
  proof-nextcloud`, exact `namespace_uid`, canonical parent-known v4 `run_id`,
  canonical existing shared `state_dir`;
- `phases: [stopped-objects, readonly-binding]`, `budget_mib: 832`,
  `cleanup_authorized: true`, `storage_device: /dev/sdb1`, and parent-measured
  `storage_device_id` (canonical block-device major:minor, no inferred value);
- the same sorted selected_controllers list as the cron receipt;
- explicit `html_claim` (no guessed alias); sorted unique
  `allowed_missing_resources` in lowercase kind/name notation, restricted to
  declarations from nextcloud.yaml, postgres.yaml, redis.yaml, cronjob.yaml;
- `document_sha256`: mapping of **every canonical intended declaration** kind/name
  to its SHA-256. Canonicalization is UTF-8 `json.dumps(document, sort_keys=True,
  separators=(',', ':'), ensure_ascii=True)` after explicit HTML alias and
  proof-nextcloud namespace substitution (`document_hashes(declarations(alias))`).
  This binds actual intended content, not merely HEAD: dirty-file drift rejects
  before API authorization and again before each create. Parent must independently
  review those exact documents/hashes; this helper issues no grant;
- `existing_uids`: **every** declaration not in the missing allowlist plus the
  already-existing `secret/proof-credentials`. No UID is guessed/enrolled.

The namespace and Secret must already exist. At least900seconds of authorization
must remain at start. Receipt bytes cannot change/refresh during an invocation.
Unknown missing resources, missing credential keys, mismatched existing specs,
images, UIDs, security, metadata or unknown API defaults block before creation.
An existing stopped web declaration is validated with its current HTML alias;
when explicitly absent, the receipt may permit creating its reviewed replicas0
declaration. Only explicitly absent PVCs, replicas0 Deployments, suspended
CronJob, Services and necessary ConfigMap are create-only candidates. Secrets
are never candidates. The current narrow binding path requires **all three
claims newly missing**, not a mixture of new/retained/partially Bound claims.
Such mixed state requires parent review, not adoption or a clean-slate retry.

### Admission, creation and binding

Before creation: validate existing objects, namespace/node identities, storage
configuration and every proof controller/schedule. Reject **every** proof pod,
including completed/failed/terminating/unlabelled pods. Reject storage helpers;
only the reviewed provisioner controller pod, bound through ReplicaSet and
Deployment UIDs with explicitly checked API defaults/SA projection, is exempt.
A fresh independent kubelet availableBytes observation (at most30seconds old)
and explicit-endpoint Talos MemAvailable must **both meet832MiB**. Repeat barriers
and dual memory admission before each create and the one binding Job.

Actual bounded binding envelope is **one64MiB busybox helper + at most three
32MiB automatic local-path helpers + reserve192 = 352MiB**. Requiring **832MiB**
for this path is an intentional conservative overestimate, **not arithmetic
error or gate lowering**. Validate live proof-local as
`rancher.io/local-path / Retain / WaitForFirstConsumer`, and the existing reviewed
local-path configuration, dedicated-XFS setup and32MiB helper limit against
`kubernetes/platform/storage/storage.yaml`. No policy modification is attempted.

Export UUID/O_EXCL0600 fsynced intent to the existing outside-Git0700 state
before each create, then append observed returned UIDs. Create races fail; never
apply-overwrite or recreate. Recheck every created/existing UID and stopped
specification before binding. Newly created PVCs must still be Pending with no
volumeName; unexpected partial binding blocks without mounting or modifying it.

One UUID Job, backoffLimit0/deadline180, uses the **exact pinned busybox image
from the reviewed storage helper**, CPU100m/memory64Mi limit, no token/init/
sidecar/fsGroup, dropALL/RuntimeDefault/no escalation/read-only root filesystem.
Its native shell mounts **only those three new PVCs READONLY**. It checks each
mountinfo root against that new PVC UID's deterministic local-path directory,
exact XFS source `/dev/sdb1` and parent-bound major:minor device identity,
read-only mount options and actual emptiness
(including hidden entries). Errors/unknown data block. It does not chown, write,
install, boot a database, or execute an extra Python interpreter. UID0 here is
only for read-only empty-directory inspection without ownership changes.

Capture owned helper raw states, current/applicable previous logs and native
cgroup current/peak/events/stat before UID-precondition deletion. Bad logs,
nonempty directories, nonzero exit/OOM or missing measurements cannot earn a
binding observation. Reachable capture failures still allow retiring the owned
helper; unreachable API leaves pending/unconfirmed cleanup. Capture observed
automatic provisioner states/logs; **automatic deletion can race observation, so
complete provisioner lifetime logs/cgroup forensics are NOT claimed**. These gaps
are explicitly journaled, never hidden as a PASS.

After helper deletion, require Job/pod absence, Bound/proof-local and exact
PVC/PV claimRef UID/namespace/name, Retain, expected path/capacity/RWO/node
identity, all declarations still stopped/suspended, and **all** proof/storage
helper absence. Retain all PVCs/PVs and every partially created object. No
application install, cron completion or live acceptance follows.

### Stop, cleanup and handoff

Pending shared journals block initialization and native activation; reused UUIDs
block even after clean. `stop` can retire only the recorded owned binding Job
under the original unexpired initialization receipt despite a pending journal.
`cleanup` needs a **NEW** `action: initialization-cleanup` receipt with
`phases: [initialization-cleanup]`, the original run/intent and same exact target/
allowlist/identity fields. It captures/deletes only the journal UID-bound helper,
checks absence and preserves all created objects. Neither path creates, scales,
installs, invokes native cleanup PHP, or reruns initialization/main cron. An
unrecorded create UID or unreachable/expired target requires explicit parent
recovery, never implicit enrollment. No automatic VM start exists.

Only the parent may issue a **NEW post-binding full832 UID receipt**, using
observed Deployment/CronJob/Secret/current HTML PVC/all backend PVC and PV UIDs,
after reviewing stopped state, absence and provisioning forensic gaps. The
initializer does not edit a receipt, enroll identities into the native runner,
or refresh authorization. Full native cron remains **unrun**.

### Offline validation / canonical resource correction

Kubernetes canonically serializes CPU1000m as1. The full backend/actual-Pod/
CronJob envelope oracle now compares CPU/memory quantities as exact rational
values (also the Cron-derived phase resource check). Exact keys, reviewed
ceilings, image/security envelopes and enumerated defaults remain mandatory;
actual changed limits and unknown API defaults still reject. No media paths
were edited or imported. The PHP payload is unchanged: NULL-password native
owned token, synthetic age, unchanged global/default TTL, real due job and
physical deletion/live-control assertions remain mandatory.

Offline tests: initializer16, supervisor24, compiler8, data42 = **90 tests**.
Every unit test forbids or mocks subprocess runtime calls. Workstation PHP lint
is syntax-only, never pinned-image runtime evidence. No generated manifests or
results are stored in Git. Parent review of14199547/b4acdca9 and this checkpoint
is not live acceptance; static67ad's353 methods/443 resources and the prepared
67 correction remain unrun. All eight WOPI failures remain retained.


## Bounded offline correction after read-only review 5526425f

This checkpoint follows b4acdca9/237ea686 and parent base64215964. Parent
acceptance was held for six concrete static gaps. These local changes are **not
live-ready acceptance** and do not authorize initialization, native install,
PG/Redis/web/CODE start, API/host/production calls or lease issuance. The parent
reports all proof applications released and Nextcloud PVC count0; neither was
queried here. A NEW initialization receipt and, separately, NEW post-binding full
UID handoff remain mandatory. Parent-owned root docs, gates, platform manifests,
old archives/credentials/STOP/history and all eight WOPI failures are unchanged.

Corrections implemented and exercised offline:

1. Full pod comparison normalizes only enumerated exact core/v1 defaults on
   **both sides**, including probe initialDelay0/timeout1/period10/success1/failure3,
   HTTP schemeHTTP, volume defaultMode420 and fieldRef apiVersionv1 (env and
   downward API, including projected sources). Regular and explicitly approved
   init containers use the same normalization and exact quantity comparison.
   Unknown fields, HTTPS/nondefault probe changes, security and limit changes
   still reject. API-shaped provisioner/web/backend fixtures cover these fields;
   the complete mocked initializer now executes the real `storage()` validator,
   not a stub. The default definitions are documented in the Kubernetes
   [Pod core/v1 API reference](https://kubernetes.io/docs/reference/kubernetes-api/workload-resources/pod-v1/);
   no live schema/default query was made.
2. Receipt `document_sha256` binds the canonical intended documents, including
   dirty files. Independently of the hashes, creation enforces the fixed reviewed
   kind/name set and namespace, Deployment replicas **explicit integer0**, CronJob
   suspend **true** and no Secret candidate. At the create boundary the submitted
   document must exactly equal the authorized missing declaration. The generated
   binding Job must equal its single pre-exported own-run intent. Create-only API
   semantics still reject existing-object races; no apply/overwrite/repair path
   was added.
3. Legacy data CLI and native supervisor/initializer use the same stable directory
   inode OS flock. Legacy holds it across pending-check through mutation/failure;
   supervisor remains fail-fast while legacy waits. No lock inode is unlinked;
   process death releases the OS lock. Two real bounded workstation child-process
   tests exercise both orderings (legacy waiting sees initializer PENDING before
   credentials/mutation; legacy holding after check excludes a supervisor).
   Pending state does not block exact owned-helper cleanup. Expiry/receipt/target
   identity checks remain mandatory.
4. Initialization cleanup records auxiliary provisioner-list failure, then still
   captures the owned binding pod/logs and deletes with the exact Job UID API
   precondition if its API is reachable. The real retirement sequence is tested,
   rather than stubbing the retirement method. Such a gap raises failure and
   leaves PENDING; it never records clean or deletes a foreign helper.
5. Native receipts now require parent `namespace_uid`; activation identities and
   mutation boundaries recheck it. PG/Redis changes use atomic JSON Patch UID
   `test` followed by replicas `replace`, rather than scale-by-name. Native stop
   deliberately does **not** require the activation/resource envelope, so an own
   UID with a bad spec can be stopped, while a replacement namespace or backend
   UID is rejected. A full stop-path test covers this narrow cleanup boundary.
   Namespace checks are fresh API reads, not a cross-resource transaction; the
   Deployment UID test is atomic at the actual patch operation.
6. Failed real `CompletedProcess` results through `life.kube()` now raise a fixed
   public-message exception carrying private stdout/stderr, never argv. Forensics
   retains these payloads in UUID/O_EXCL0600 fsynced captures. Tests exercise the
   real kube-to-forensics path, safe str/repr/args, private modes and overwrite
   rejection; no injected CalledProcessError shortcut is relied on for this gap.

**Resource contract unchanged:** actual binding64 + three automatic32 helpers +
reserve192 = **352MiB**, still requiring conservative fresh independent **832MiB**
dual minimum. No budgets/limits were reduced. Binding stays read-only; no native
application operation occurred.

Validation at this checkpoint: initializer20, supervisor29 (including two real
workstation serialization tests), compiler8, data42, data-WOPI14 and
workflows20 = **133 passing tests**. All cluster/host/runtime work was forbidden
or mocked; real subprocesses in serialization tests execute only local Python.
`git diff --check` passed. PHP is unchanged and no fresh PHP/runtime claim is made.
The parent's64215964 root gate (395 methods /443 renders, no skips, actionlint)
is historical base evidence, **not validation of these changes**. Full root CI,
new parent read-only acceptance and every grant-bound measurement remain pending.

## Exact service-account alias repair after actual API discovery

Read-only evidence at `4507fd70` found one remaining real provisioner Deployment
PodTemplate mismatch: API `serviceAccount` equals explicit
`serviceAccountName: local-path-provisioner-service-account`, while the manifest
only declares the canonical name. The shared pure envelope now removes the legacy
alias **only when both explicit fields exist and equal each other**. The canonical
name remains subject to the existing approved-name comparison/default policy;
conflicts, jointly wrong identities and unknown fields still reject. The old
provisioner-Pod-specific alias removal is removed, so it cannot independently
bypass that comparison. Alias-only `serviceAccount: default` is no longer ignored.
No security, image, resource or other default policy was loosened.

Focused OFFLINE tests: supervisor30, initializer21, compiler8, data42 = **101
passing tests**. Custom matching aliases pass for templates and Pods; mismatched
aliases, both-wrong custom/default identities, alias without canonical name and
unknown fields reject. The API-shaped provisioner fixture now includes the real
legacy alias. An independent pure-validator replay against the privately captured
actual Deployment and Pod (with cached ReplicaSet/Deployment UID chain) passes;
four identity/unknown-field negative variants reject for each. Runtime subprocess
calls were forbidden during replay; inputs were verified unchanged. No live API
query, constructor, initialize/main invocation, receipt or activation was needed.

Parent explicitly chose **desired new** HTML claim name `nextcloud-data` only
after discovery found no native web/backend/CronJob declarations, Nextcloud PVCs
or Nextcloud PV claimRefs. It is **not** a discovered/restored alias or adoption.
Pure `declarations('nextcloud-data')`, stopped-document validation and canonical
hashes for all eleven documents were compiled under that explicit choice.
Private0700 artifacts, each UUID/O_EXCL0600, are in:
`$HOME/.local/state/initialization-candidate-3c27eca2-a31d-4c8e-b62c-c7c6e25aad6f/`.
The complete private candidate identity/hash plan is
`candidate-identity-plan-14a104ad-0070-4dda-98d3-3ed37e4010f8.json`; its referenced
exact declarations and captured-validator results are in the same directory.
It records source-file hashes and historical captured identities, **not a receipt,
grant, authority or fresh admission result**.

Parent will create the fresh canonical0700 journal directory; completion was not
assumed or performed here. Old `STATE/data` remains untouched, with no credential
copy/generation, state migration or adoption. Parent independent source/document/
identity review and fresh target/storage/quiescence/dual-memory measurements are
still required, followed by a **NEW initialize-only receipt before create/bind**.
The gate remains832MiB; actual binding64+3×32+192 remains352MiB. No main cron,
web/backend/helper start or additional concrete compatibility blocker was observed
in this bounded offline replay. Postbinding native cron requires separate new
UID-bound authority and is not authorized by the candidate plan.


## Post-create binding continuation — OFFLINE, NEW authority required

The single initializer run `34a6bc9c-7a6a-46b3-ac59-528c84233bca` created
all eleven declarations but stopped before binding; see
[evidence](evidence/talos-data/initialization-live-34a6bc9c-7a6a-46b3-ac59-528c84233bca.md).
Its receipt was released, its three PVCs remain Pending and its original pending
journal remains. This section is implementation, **not a live grant or retry**.

Two exact empty-serialization corrections now compare container `env: []` with
absence (on both sides) and CronJob `jobTemplate.metadata: {}` with absence.
Nonempty env/metadata, malformed env types, unknown fields, image/security/limit
changes remain rejected. All eleven privately captured actual objects pass the
real corrected readback validators in an offline replay; this is historical
snapshot compatibility, not fresh runtime admission.

### New receipt schema (parent only)

CLI: `scripts/talos-proof-nextcloud-initialize.py bind-created --state
<canonical-shared-state> --run-id 34a6bc9c-7a6a-46b3-ac59-528c84233bca`.
No alternate state, generated receipt, VM start or legacy CLI is involved.
`TALOS_PROOF_DATA_LEASE` must name a NEW private0600 immutable receipt with:

- `action: bind-created`, `phases: [readonly-binding]`, original canonical v4
  `run_id`, **new** canonical v4 `authorization_id`, numeric finite Unix `issued`
  and `expires`. Issuance must follow original issuance and not be in the future;
  expiry must leave at least900seconds at invocation. The old expiry is inert
  provenance, never authority. Bytes remain immutable through stop.
- Exact unchanged original `group: nextcloud`, `stage: cron`, canonical
  `state_dir`, `budget_mib: 832`, `cleanup_authorized: true`, sorted
  `selected_controllers: [cronjob/nextcloud-cron, deployment/postgres,
  deployment/redis]`, `namespace: proof-nextcloud`, `namespace_uid`, `context`,
  loopback `endpoint`, `node_uid`, `html_claim: nextcloud-data`,
  `storage_device: /dev/sdb1`, `storage_device_id: "8:17"` and all eleven
  canonical `document_sha256` bindings.
- `allowed_missing_resources: []`; `existing_uids` maps **all eleven** original
  declaration keys plus `secret/proof-credentials` to exact original UIDs.
- `origin_created_uids`: all eleven exact declaration-key→created-UID bindings,
  matching `existing_uids` minus Secret. Canonical unique UIDs required.
- `origin_receipt_path`: private outside-Git path of the immutable **issued**
  original initialize receipt; `origin_receipt_sha256`: its exact SHA256.
- `origin_journal_sha256`: exact original UUID.json basename→SHA256 map in the
  canonical shared journal root. Referenced bytes/modes/names/run IDs are checked
  on each authorization. Original hashes do not freeze future own append-only
  observations. The parent must independently review this original history.

The original receipt must bind this same target/documents, all eleven originally
missing objects and only the existing Secret. Referenced history must contain
one original initialize pending event, eleven unique exact document-create
intents and eleven unique exact UID create observations. No arbitrary retained
PVC or guessed UID can be enrolled. Unreferenced original create/intents/pending
history rejects. The sole pending run must be the original run; clean history,
foreign pending, any prior binding intent/create, or reused authorization ID
rejects entry. Original `initialize` still rejects partial/retained/reused state.

### Bounded execution and failure semantics

After purely local provenance verification, a fsynced UUID/O_EXCL0600
`initialization-continuation` event consumes the new authorization ID **before
any runtime query**, without a second pending event. An unreachable first
admission still consumes this ID. Every subsequent authorization checks this
single consumed event plus the immutable original provenance/new receipt.
No existing binding intent can earn another continuation, even under a new ID.

Before the one generated helper: recheck exact Node/namespace/Secret and all
created identities, full corrected stopped declarations, every PVC Pending
with no volumeName, and absence of PV claimRefs for these UIDs (also any
Nextcloud namespace claimRef). Reuse the reviewed storage/provisioner checks,
all-proof Pod/controller barriers and fresh independent dual832 memory gate.
Repeat created-object/PVC/PV checks immediately before entering shared binding.
No declaration creation, patch/replacement/deletion, credentials, backend,
web/CODE, native install or cron operation exists in this scope. The mutation
boundary explicitly rejects **every non-Job create**.

The existing generated read-only64MiB Job, exact original-run helper name,
three32MiB automatic helper ceiling, emptiness/XFS/device/path checks,
capture-before-UID-delete, helper absence and Bound/Retain/path/capacity/claimRef
oracle are shared unchanged with initialization. Successful observations append
one original-run clean event only after final stopped/absence checks. No native
acceptance or full-run receipt is produced. Automatic provisioner lifetime
log/cgroup capture gaps remain explicit, not hidden as acceptance.

Failure preserves original pending state and all declarations/PVCs. `stop` under
the unexpired **new bind-created receipt** can capture/retire only the exact
journal UID-bound original-run binding helper; the expired original receipt is
not consulted for permission. Otherwise the existing separate NEW
`initialization-cleanup` receipt is required. No unknown UID adoption, wider
cleanup or automatic restart exists. A native post-binding grant remains a
separate parent decision after actual binding evidence.

### Offline validation and private candidate

Focused tests: initializer35 + supervisor30 + compiler8 + data42 = **115**.
New coverage includes empty serialization positives/nonempty/malformed/unknown
negatives, provenance/hash/target/UID/name/namespace drift, retained/Bound PVCs,
PV claimRefs, foreign pending, prior binding, replay, non-Job mutation rejection,
unreachable admission consuming authority, full mocked Bound handoff and
capture-before-exact-UID retirement. All runtime subprocess calls are forbidden
or mocked; no cluster/Talos/VM/image/native query occurred in this correction.

Private candidate (NOT a receipt, authority, or fresh admission result):
`$HOME/.local/state/home-infra/talos-proof/diagnostics/bind-created-offline-candidate-plan-35e212e0-cec4-4f53-98d5-19ba8869f589.json`.
It includes exact eleven UIDs, original issued receipt hash/path, all36 original
journal hashes and intended document hashes. New authorization ID/time fields
are **placeholders for the parent**, not issued values. Its referenced historical
all-eleven-object replay is recorded separately. Parent must review current
source hashes and independently perform fresh measurements before issuing any
authorization. Original state/history/receipt/credentials remain unchanged.

Additional offline regressions: data-WOPI14 and data-workflows20 also pass,
for **149 total passing tests**. Final source-hash-matched replay/candidate paths
and all-eleven resource keys are indexed in
[evidence](evidence/talos-data/bind-created-offline-34a6bc9c-7a6a-46b3-ac59-528c84233bca.json).
`git diff --check` passed. No root gate/CI/live acceptance is claimed.


## Native backend NetworkPolicy prerequisite — OFFLINE checkpoint

Parent read-only discovery reports the four declared backend policies absent
while seven existing WOPI/default-deny/DNS policies are retained. That is parent
context, not a query made by this correction. No policy/runtime/host call or
creation occurred here. Parent alone may separately authorize bounded create-only
creation of the four declared backend policies; this supervisor cannot create,
replace, delete or broaden them. No manifest was edited.

The new native receipt field `network_policy_uids` (documented above) binds the
six prerequisite names. Native admission checks exact declared specs/identities
before phase execution; positive backend scaling rechecks this prerequisite
before any PG/Redis patch. Cleanup therefore requires it when activating
backends too. An unavailable or mismatched policy cannot become a silent DB
connection timeout followed by application mutation.

Stop, replicas0 patches and exact-owned-helper retirement deliberately do **not**
require this activation field or policy availability/specification. Cleanup may
capture/retire its prior UID-bound helper before failing activation admission.
Existing seven policies are neither enumerated as an exact namespace inventory
nor altered: only the six receipt-bound prerequisites are checked. This does not
assert the absence of additional additive policies or prove live connectivity.

Offline tests: supervisor40 + initializer35 + compiler8 + data42 = **125 passing**.
Coverage includes exact declared positives before backend patches, missing UID
bindings/live policy, UID/name/namespace drift, broader backend/DNS rules,
default-deny changes, unknown spec fields, terminating policies, cleanup
admission before activation and policy-independent stop/helper retirement.
All cluster/Talos/VM/image/native calls were forbidden or mocked; existing
serialization tests use local Python processes only. `git diff --check` passed.

Current supervisor SHA256: `ee48fca44047135bd614c73fd56e6220a01b6893a2299d9aa5824f178791e56b`.
Parent must review this updated source hash before a separate new native grant.
No credential/backend/native install/cron action, retry or functional/capacity
acceptance occurred. Budgets/limits/ini remain unchanged;192MiB is still a
bounded trial constraint, not Nextcloud capacity assurance. Parent-owned root
docs/gates/integrity review and all retained binding/history remain untouched.


## Sequential heavy PHP children in cron phase — OFFLINE checkpoint

The cron phase previously loaded full Nextcloud core in its wrapper and kept
that runtime alive while launching another full PHP cron runtime. Both were
inside the same192MiB cgroup, but that was needless heavy-runtime overlap, not
one single PHP process. The corrected process model is a **lightweight PHP
parent plus one heavy child at a time**, sequentially:

1. Parent `cron` case invokes this same payload as internal `cron-precheck`,
   writing a fresh exclusive0600 `$journal/cron-precheck.log`.
2. Only that child performs `nativeContext(); due(cleanupRow())`; the strict
   >86400seconds daily due/unreserved predicate is unchanged. Parent waits via
   synchronous `proc_close`; nonzero exit throws and prevents the next command.
3. After successful child completion/private-log fsync, parent launches actual
   `php -f /var/www/html/cron.php -- CLEANUP_CLASS` using the existing private
   exclusive `cron.log`. No parent core bootstrap occurs in the cron case.

`cron-precheck` is internal dispatch only and requires inherited PROOF_PHASE
`cron`. It is **not** added to public PHASES, compiled Jobs, supervisor actions or
receipt phases. This environment check is not independent authorization:
manual/direct payload invocation remains forbidden. The unchanged supervisor
still requires a new parent-known run UUID and blocks replay; future phase logs
are exclusive in that new run's private journal. No old run/log/history was
modified or a new live run journal created by this offline correction.

All children inherit the same existing pod cgroup. Actual kernel
current/peak/events/stat reads remain unchanged and encompass child processes;
no fake observations, extra container or budget exemption exists. The parent
itself is still PHP and consumes memory: this is **not a single-PHP-process
claim**. The lightweight parent plus rsync/native-install sequence is otherwise
unchanged. No force, last_run manipulation, global/default TTL alteration,
retry, ini/resource/gate change or weakening of physical candidate deletion,
control survival or native scheduling assertions occurred.192MiB and832MiB
remain fixed. Supplied official Nextcloud35 documentation context is128MB
minimum/512MB recommended per process and PHP memory_limit512MB recommended;
that is not an actual measurement, and this bounded trial is not capacity
assurance.

Offline contract tests pin precheck-before-cron ordering, absence of parent
bootstrap, synchronous throwing failure propagation before the second command,
private exclusive logging and rejection of public precheck phase admission.
Compiler11 + supervisor40 + initializer35 + data42 = **128 passing tests**.
`nix shell nixpkgs#php` workstation PHP8.5.12 reports no syntax errors: syntax
only, not pinned-image/native runtime validation. `git diff --check` passed.
Upstream core/config hash indexes and manifests were not changed.

Updated native PHP SHA256: `9da32b07324986684c54bc16f934d5745f52bb5f7d6f47a23da7cc32107e0b8e`.
The supervisor's policy/cgroup admission checks are unchanged. Parent must use
the updated payload hash when reviewing/issuing a separate new native grant.
No runtime query, grant, application execution, install/cron result, functional
PASS, capacity/durability or production-readiness claim follows. Parent-owned
root docs/gates/integrity review and released policy/binding history are intact.
