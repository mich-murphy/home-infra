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
context/endpoint/node UID/expiry fields and these exact bindings:

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
  references; these are compared to Deployments and actual pod specifications.

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
