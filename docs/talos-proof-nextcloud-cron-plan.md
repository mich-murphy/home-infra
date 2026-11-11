# Native Nextcloud CLI/bootstrap + cron: offline preparation only

**No live grant. No cluster/host/image execution was performed for this review.**
This is a source-backed staged procedure, not a runnable admission bypass or a
claim that installation fits. Existing `nextcloud/cron` tests check lastcron only;
they do not implement this bootstrap/side-effect contract. Do not run that stage
and label it the stronger proof described here.

## Immutable source review and scope

Image remains exactly:
`nextcloud:35.0.2-apache@sha256:786c102155d2717ba0f53a62b3fdd7a1354edc48e800b94dbe32294d9a5752a2`.

[Reviewed source index](evidence/talos-data/nextcloud-cron-source-review-97384394-9c9c-47d4-8d17-50e63b9b62fd.json)
contains immutable URLs, byte sizes and SHA256 for 27 public files. Core tag
v35.0.2 resolves to server commit `ba900af933e61ffa005315b09d6454bfbbcbcc81`.
Core version.php reports internal35.0.2.2 / public35.0.2. Docker source commit
`7e9e152f77372845195ed28dc65569df74f582ff` supplies the reviewed35/apache build
and entrypoint. **Public source is not digest/image attestation.** Future admission
must compare actual in-image sources/versions with this review; discrepancies
block, rather than running a guessed private API. No image was pulled or run here.

Scope: own synthetic Nextcloud PVC, existing unchanged proof credentials, native
PostgreSQL and authenticated Redis, PHP CLI installation and real native cron
side effect only. No HTTP, Apache, WebDAV, Office, richdocuments or full Nextcloud
acceptance. No production/source imports, token/authenticator regeneration,
credential rotation, DNS/global-policy changes or other applications.

## Budget and serial execution

| Component | unchanged limit MiB |
|---|---:|
| PostgreSQL |384|
| Redis |64|
| One CLI bootstrap/setup/assertion OR CronJob pod |192|
| Admission reserve |192|
| Total admission requirement |832|

The current web stage still requires1280MiB including reserve and is not admitted.
Do not shrink its limits or run Apache as a192MiB helper. Use the same pinned
image but **override command/entrypoint explicitly** with CLI-only processes.
Do not use `NEXTCLOUD_UPDATE=1` to sneak through normal entrypoint initialization:
that path includes rsync --delete, automatic installation retries and upgrades.

Only one Job pod, including Pending/Running/Terminating/Completed pods and any
init containers, may exist at a time. `concurrencyPolicy: Forbid` alone does not
serialize manually created Jobs. Future supervisor must refuse any existing
CLI/cron pod, create one UUID-named Job, collect logs/state/cgroups, delete the Job
and confirm its pod absent before creating the next. backoffLimit0, no automatic
retry, bounded activeDeadlineSeconds, SA automount false, RuntimeDefault,
capabilities dropALL, UID/GID33, existing PVC mounted, unchanged192MiB limit.
No sidecar, parallel helper, observer interpreter or Apache. Instrument from off
node; if a short process escapes peak observation, preserve that gap.

The existing180second CronJob deadline bounds execution but **bootstrap migrations
have not been demonstrated within180seconds or192MiB**. A timeout/OOM is failure,
not permission to raise limits, drop reserve, resume partial install or add retries.
A future receipt must explicitly authorize the serial bootstrap and cron Jobs,
not merely the two backend Deployments. Existing guard semantics need review for
serial helper identity and all-app/helper exclusion before executable integration.

## Phase A: read-only inventory, then install OR verify (one CLI Job)

Future admission must obtain genuine fresh kubelet + explicit-endpoint Talos
observations and verify all unrelated app/helper pods absent. These are not part
of this offline review. Do not refresh a revoked lease or make a new one.

1. Verify exact PVC UID/source attachment, proof ownership, Secret identity and
   backend volume state. Do not call `prepare`, generate credentials, rewrite
   config, delete PVC contents or assume the PVC is empty.
2. Inventory actual source/config/data paths privately before writes, rejecting
   symlinks, unknown files, unexpected ownership and version mismatches. If
   installed, verify config owner33, installed:true, DB host/name/user, data path,
   version35.0.2.2, maintenance:false and no pending upgrade using native status.
   Verify original proof user exists. Do **not** reinstall/upgrade/reset passwords.
3. An incomplete/ambiguous install blocks. In particular, code files without a
   valid installed config, nonempty application DB without installed config,
   unexpected data directory, wrong backend or partial migrations must not be
   repaired automatically.
4. Only a proven empty own PVC **and** empty designated application database can
   enter fresh bootstrap. Copy packaged `/usr/src/nextcloud/` to the empty own
   `/var/www/html/` as33 using the packaged rsync tool, without --delete or running
   the image entrypoint. Verify source tree identity first. Missing write
   permission/packaged tools blocks; no recursive chown of retained contents.
5. Run the supported native installer exactly once, noninteractively:

   ```text
   php /var/www/html/occ maintenance:install --no-interaction
     --database=pgsql --database-host=postgres --database-name=nextcloud
     --database-user=nextcloud --database-pass=<existing private proof DB secret>
     --admin-user=proof --admin-pass=<existing private proof admin secret>
     --data-dir=/var/www/html/data
   ```

   These are descriptive placeholders, not shell commands to paste. Future runner
   must source existing Secret values inside the pod, never render them into Job
   arguments/manifests, stdout or committed logs. Native installation creates its
   own initial instance secret/salt only on a genuinely new instance; it must not
   regenerate any preexisting private identity. Disable shell tracing, store raw
   installer output0600 and publish only sanitized assertions.
6. Native `occ status --output=json` must verify installation/version/maintenance
   and upgrade status. Verify configuration and existing proof-user/backend
   access without password reset. Docker-specific cache config must be evaluated:
   PHP CLI bypasses entrypoint and does not automatically inherit its configuration
   copying/session setup. Inventory packaged config fragments and validate actual
   authenticated Redis configuration from the same native bootstrap. Do not
   silently overwrite config.php or add an unreviewed Redis workaround.
7. Capture current/previous logs where applicable, state/lastState and cgroups;
   delete Job and confirm pod absence before phase B.

**Open bootstrap gaps:** actual PVC/DB contents are intentionally unobserved in
this offline phase; UID33 copy permissions, packaged config fragments, native
Redis integration, migrations, first-install background-job registration,
process duration and cgroup fit require future bounded evidence. No executable
bootstrap was added while these are unresolved.

## Phase B: native token fixture and before-state (one CLI Job)

Source chain:
`OC\Setup::installBackgroundJobs()` registers
`OC\Authentication\Token\TokenCleanupJob`; that TimedJob calls
`OC\Authentication\Token\IProvider::invalidateOldTokens()` through Manager and
PublicKeyTokenProvider. `PublicKeyTokenMapper::invalidateOld()` deletes tokens
whose actual `last_activity` is **strictly less than** current time minus the
appropriate configured retention. Explicit `expires` is not the retention test.
The public OCP IProvider does not expose generateToken: this is a **version-bound
internal API fixture**, not a stable public app API or supported auth CLI command.
`maintenance:install` and `cron.php` themselves are native supported entrypoints.

Proposed reviewed calls in a PHP CLI script, after native lib/base.php bootstrap:

- Resolve `OCP\Server::get(OC\Authentication\Token\IProvider::class)` and
  `OCP\IConfig`; verify actual methods/constants/version before mutation.
- Verify installed proof user and absence of all preexisting non-proof token
  state that could be aged by lowering global session retention. A nonempty or
  ambiguous retained auth state blocks this proof. Never age/delete old tokens
  to make the fixture convenient.
- Snapshot both **presence and exact typed value** of `session_lifetime` plus
  `core/backgroundjobs_mode` for later restoration in durable private UUID state.
  Snapshot before changing anything. The relevant supported TTL is a **system**
  setting, not an invented app-specific token TTL. Do not change remember TTL.
- Verify existing `remember_login_cookie_lifetime` exceeds the entire bounded
  run by a safe margin (e.g.3600seconds); otherwise block, not change it.
- Set supported system `session_lifetime` to5seconds for this isolated proof via
  native IConfig (or native occ config:system:set --type=integer). Preserve exact
  old presence/type. Do not alter token timestamps or SQL rows.
- Create two fresh random synthetic session tokens with distinct UUID names via
  `generateToken(raw, 'proof', 'proof', null, name, TEMPORARY_TOKEN, remember)`.
  One uses DO_NOT_REMEMBER and the live control uses REMEMBER. **Password is null**:
  a non-null password can invoke updatePasswords on existing user tokens. Never
  pass an old credential to trigger that path. Raw synthetic token values stay
  private0600, never stdout; they do not replace existing credentials.
- Wait on genuine elapsed application time until the unremembered token's actual
  last_activity is strictly more than5seconds old, with a bounded10second timeout.
  Do not backdate, inject a fake clock, set expires in the past or update rows.
- Verify both rows present through native provider enumeration and a fresh
  process/read-only DB observation, recording IDs/types/remember flags and age
  only. Check the expired candidate is past threshold and remembered control
  remains within its **own** retention. Do not use provider getters alone as proof
  of physical row absence because token caches may survive process boundaries.
- Verify the registered TokenCleanupJob actually exists, is due (last_run0 on
  genuine fresh install, or naturally >86400seconds old) and unreserved. If not
  due, **block**. Do not delete/re-add it, clear reservation, change last_run or
  call its protected run/provider invalidateOldTokens directly.
- Capture forensic observations, delete phase-B Job and confirm pod absence.

## Phase C: actual native cron (one CronJob-derived Job)

Run the real native entrypoint, using its documented class filter:

```text
php -f /var/www/html/cron.php -- 'OC\Authentication\Token\TokenCleanupJob'
```

Retain the original suspended CronJob (no schedule activation); future scoped
runner may derive a UUID Job with this argument list and unchanged192MiB limit.
The class filter bypasses the maintenance-window restriction but **does not bypass
TimedJob's24hour interval**. Require an actually due registered job beforehand.
No custom fake cron, direct provider cleanup call, completed-row inserts or
reconstruction of native completion records. Capture original job identity,
native logs, before/after native scheduling metadata, cgroups and process exit.
Native job exceptions can be swallowed by the framework, so exit0 and updated
`lastcron` are **insufficient**. Phase D's side effect is mandatory.

Delete Job and confirm pod absent before phase D. No web or second CLI helper
runs alongside it. Redis and PG retain their actual unchanged limits.

## Phase D: fresh-process assertions and restoration (one CLI Job)

- In a new native process, assert candidate token ID physically absent and live
  remembered control physically present with exact original UID/type/name/flags.
  Use read-only native/DB evidence in addition to provider lookup to avoid cache
  ambiguity. A getter throwing alone is not physical deletion evidence.
- Require native TokenCleanupJob execution metadata advanced within the observed
  interval, and lastcron corroborates. Correlate actual side effect and process
  bounds. Do not insert/update job completion rows to supply evidence.
- Remove **only the surviving new synthetic control** using native
  invalidateTokenById('proof', controlId), after verifying UUID name/ownership;
  record that harness cleanup is after the acceptance observation. Failure-path
  cleanup may also remove the new candidate, but that must never earn cron PASS.
- Restore session_lifetime exact previous type/value, or delete it if originally
  absent. Restore backgroundjobs_mode exact old presence/value through native
  config API because cron may switch ajax to cron. Verify restoration. This is a
  proof-setting restore, never credential/authenticator/config identity rotation.
- Capture forensics, delete Job and confirm absence; stop backend Deployments,
  confirm all apps/helpers/controllers0 and CronJobs suspended, archive/revoke
  any future receipt before checkpoint. A restoration failure remains an
  explicit failure requiring new parent direction, not automatic reactivation.

A killed/expired supervisor cannot guarantee phase-D restoration. A future grant
must reserve a bounded restoration/cleanup window and persist a private recovery
journal before the TTL mutation. If admission does not authorize that entire
sequence, **do not mutate the setting**. No live receipt currently exists.

## Acceptance boundaries

Even a future pass proves only native install/verified retained state and one
native token-retention cron side effect with a live control on synthetic storage.
It does not prove general cron scheduling, all jobs, WebDAV, HTTP, Office,
transparent Redis reconnect, logical restore, production capacity or durability.
Current status remains **OFFLINE PREPARED / EXECUTABLE INTEGRATION BLOCKED** by
image-source parity, retained-state inspection, Redis config verification,
serial-helper lease/guard integration, due-job state and restoration safety.


## Offline executable payload checkpoint

No live grant or native execution. The integration remains **BLOCKED**, not PASS.
The previous `tests/talos-proof-data-live.py` nextcloud/cron branch could succeed
with lastcron alone; that acceptance path is removed. The lifecycle also refuses
cron activate/run/test before credentials, API calls or mutations. Backend and
legacy cleanup/deactivate paths are unchanged.

Owned additions:

- `scripts/talos-proof-nextcloud-cron.py`: offline-only private UUID/O_EXCL0600
  bundle compiler, five serial phase documents,192MiB one-container security
  envelope, explicit384+64+192+192=832 budget, strict daily due predicate and
  all-proof-Job-pod barrier (including completed/failed/terminating/unlabelled).
  No command execution is implemented here; `run` always blocks. Never apply
  this bundle manually: the documents are not an admitted orchestration path.
- `scripts/talos-proof-nextcloud-cron.php`: read-only packaged-core hash comparison
  and shallow PVC-root inventory. This intentionally does NOT execute retained
  config or claim full inventory/Redis parity. Native fixture/assert/restore
  functions are drafts behind `MUTATION_INTEGRATION_READY = false`; compiled
  non-preflight phases cannot run. The source includes null-password creation,
  genuine session aging, physical row assertions, actual daily due check,
  exact synthetic cleanup and typed setting snapshot/restore. No fake cron,
  timestamp/SQL writes or completion-row synthesis. Cgroups are read by PHP
  itself from the charged container, with explicit unavailable gaps.
- Generic private forensics now captures raw pod JSON (including lastState),
  current logs for terminated pods as well as running pods, and previous logs
  on restart before deletion. Artifact files use UUID/O_EXCL0600. The existing
  lifecycle may still report a forensic gap and continue cleanup; a future cron
  supervisor must instead require successful capture before phase deletion.

**Exact critical integration gate:** implement/review a serial supervisor binding
EVERY operation to exact nextcloud/cron receipt, context/endpoint/node UID and
lease expiry, independently fresh dual-memory minimum and all-helper barriers.
Receipt must authorize full sequence and bounded restore window. Implement real
PVC/Secret/backend UID binding, complete read-only retained inventory, packaged
Docker/config parity and native authenticated Redis preflight BEFORE install or
fixture writes. Prove own PVC AND designated PG DB empty before native one-shot
maintenance:install; otherwise verify installed native status without repair.
Partial install blocks and is preserved. These are deliberately not implemented
as guessed passing flags or caller-supplied boolean attestations.

Then implement durable private journal directory creation, off-pod journal export
and failure recovery (including death between token insert and ID observation),
fresh-process before observation, actual CronJob-derived native cron invocation
with documented class filter and end-of-phase cgroups/log capture, serialized
absence checks, and finally restore even when acceptance assertion fails. Native
fixture functions alone do not provide these guarantees. The cron phase document
currently blocks, rather than invoking an unguarded cleanup job. The suspended
CronJob remains untouched; no schedule, web resources, identities or archives
changed. A missing local PHP interpreter means syntax/API/runtime validation of
the draft payload remains outstanding; Python tests are not that evidence.

No actual image source parity, retained state, Redis connectivity, native install,
native token generation/deletion, cgroup fit or restore success has been observed.
This checkpoint does not change any Couch/Miniflux/Pocket-ID/Wallabag/media/WOPI
acceptance boundaries or authorize WOPI, web, ML, heavy or media activation.
