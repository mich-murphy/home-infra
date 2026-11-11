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
  both backend Deployments, suspended CronJob, **every backend PVC and every
  associated PV**, including nextcloud-data's PV;
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
2. Validate retained Kubernetes identities and PV claim attachments. Require all
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
   suspended CronJob template and validates its security/resource envelope.
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
10. Capture private pod JSON/state/lastState/current/previous logs before delete;
    capture gaps preserve the Job and block another phase. Delete and confirm
    pod absence before the next. Fresh final process requires physical candidate
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
expiry. `stop` does not inspect pending activation policy. `cleanup` serially
uses only names/UID/type/remember from the immutable intent and native journal;
it cannot earn cron acceptance. If a failed/retained helper exists, first obtain
parent direction to preserve/export forensics and remove that exact helper;
cleanup deliberately refuses to run alongside it. If fixture mutation never
started, missing journal blocks rather than guessing success. A crash after
insert but before ID export is recoverable by the pre-exported exact UUID name.

No existing users, credentials, archives or partial installs are erased. This
path does not touch Pocket-ID34ef3547, Wallabag5622c159, private WOPI artifacts,
eight preserved WOPI failures, or offline-only ordered UI/native Save67 work.
No full Nextcloud/HTTP/WebDAV/Redis reconnect/capacity/durability claim follows.

## Offline validation

`python3 tests/talos-proof-nextcloud-cron_test.py` (8),
`python3 tests/talos-proof-nextcloud-cron-supervisor_test.py` (8), and
`python3 tests/talos-proof-data_test.py` (42) passed: **58 mocked/offline tests**.
`nix shell nixpkgs#php --command php -l scripts/talos-proof-nextcloud-cron.php`
passed with workstation PHP8.5.12. This is syntax only, not pinned-image runtime
compatibility. No unit command may reach Kubernetes/Talos/VM/image/runtime.

Remaining grant-bound measurements: actual source/config parity, UID33 inventory
and copy permission, retained DB/PVC state, actual native Redis config/access,
CLI bootstrap writes/extensions, due-job state, migration duration, real native
side effects and192MiB fit. Every unavailable measurement fails closed.
