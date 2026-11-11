# Isolated data and identity proof

## Acceptance status

**Bounded live workflow proofs passed for CouchDB create/read/recovery, Miniflux, Pocket-ID virtual WebAuthn/OIDC, and Wallabag HTTP extraction/CRUD/recovery.**
The exclusive CouchDB lease was used and released after scale0/pod deletion.
Wallabag passed with an explicit fixture-only extractor exception described below. Nextcloud/Immich remain untested live; overall integration/production-capacity acceptance is pending. Do not
interpret manifest probes or executable plans for those applications as passed tests.
This delivery needs parent integration acceptance. The source Docker host was not
changed or copied. All persistent data is newly generated synthetic proof data.

## Declarative layout and versions

`kubernetes/apps/data/kustomization.yaml` includes six independent, explicitly
maintained Kustomize directories. Each directory can be applied separately, and
all Deployments default to **zero replicas**. Nextcloud's five-minute CronJob is
**suspended**, has no retries and a 180-second deadline. No Helm/templating or
production overlays are required. Sources are CURRENT `docker/*/compose.yml`,
not the historical Kubernetes branch. Historical Pocket-ID was inspected only as
design reference; its old version/production issuer/secret were not copied.

| Boundary | Replicas represented (all initially off) | Current image versions |
|---|---|---|
| `proof-nextcloud` | Nextcloud, PostgreSQL, authenticated Redis, Collabora; suspended cron | Nextcloud35.0.2-apache, PG18.6, Redis8.10.3, CODE26.04.6.1.1 |
| `proof-immich` | Immich, ML, vector PostgreSQL, Valkey | Immich/ML3.3.6, PG14-vectorchord0.4.3-pgvectors0.2.0, Valkey9.0.1 |
| `proof-miniflux` | Miniflux, PG, synthetic HTTP fixture | Miniflux2.3.5, PG18 |
| `proof-wallabag` | Wallabag, MariaDB, Redis, synthetic HTTP fixture | Wallabag2.6.15.1, MariaDB13.0.2, Redis8.10.3-alpine |
| `proof-couchdb` | CouchDB single node | CouchDB3.5.3 |
| `proof-pocket-id` | Pocket-ID with fresh SQLite data | Pocket-ID2.19.2 |

Every image is pinned to its current Compose sha256 digest. Fixtures reuse the
same pinned Nextcloud image's PHP CLI server as an offline static RSS/article
server (nonroot, read-only root,64Mi limit); they do not run Apache/Nextcloud.
**ownCloud is obsolete and intentionally absent.**

Immich3 upload storage is mounted at **`/data`**, not the stale Compose
`/usr/src/app/upload`. Upstream release Compose evidence is recorded in
`docs/evidence/talos-data/immich-upstream-path.json`. No GPU/device mapping is
copied. PG18 PVCs mount `/var/lib/postgresql`, while Immich's PG14 uses
`/var/lib/postgresql/data`. Nextcloud HTML/config/apps/data share one new PVC;
cron mounts that same claim. No production NFS or existing directories are used.
All PVCs request `proof-local`; local-path requested sizes are not enforced quotas.

## Isolation and security

Each namespace and pod is labelled `app.kubernetes.io/part-of: talos-proof`.
Default-deny ingress AND egress applies in every app namespace. Only CoreDNS
UDP/TCP53 and explicit directional app-to-backend flows are allowed. Matching
backend ingress is present; there is no blanket same-namespace allow. Synthetic
fixture ingress is limited to its frontend. Frontend ingress permits the
`proof-validation` and `proof-gateway` namespaces. App-specific CiliumNetworkPolicies permit reserved `ingress` identity on only
each frontend port (never PostgreSQL/cache/backend ports); namespace-only matching cannot establish
Cilium native Gateway access. Verify real datapath tests and drop verdicts before
claiming isolation, rather than relying on policy YAML.

HTTPS HTTPRoutes attach to `proof-gateway/proof`, listener `https`, for
`nextcloud.proof.invalid`, `collabora.proof.invalid`, `immich.proof.invalid`,
`miniflux.proof.invalid`, `wallabag.proof.invalid`, `couchdb.proof.invalid`, and
`pocket-id.proof.invalid`. Nextcloud trusted domains and overwrite URL, Miniflux
base URL, Wallabag domain, Pocket-ID issuer and Collabora allowed WOPI origin use
these reserved proof origins. No production DNS, TLS issuer or OIDC integration
is referenced. HTTPS is verified against the private proof CA; no insecure TLS
flag is used. No HTTP redirect/exposure route is added.

Pods disable service-account token automount, set RuntimeDefault seccomp, drop
ALL capabilities before explicit image-init exceptions, and have startup,
readiness/liveness probes plus CPU/memory requests/limits. Image entrypoints
that initialize/chown storage retain the current Compose-required capabilities.
CouchDB runs5984 and fixtures run33; other upstream entrypoints may start root
and drop to their image account. Non-Collabora namespaces enforce baseline PSA,
with restricted audit/warn. This is not an assertion of restricted compliance.

**Collabora exception:** its setuid/file-capability startup requires privilege
escalation and a finite Compose-derived capability list (including SYS_CHROOT,
MKNOD, SETFCAP). The dedicated `proof-nextcloud` namespace therefore uses
privileged *PSA admission*, but containers are **not privileged**, have no host
mounts/devices/network, and still use seccomp/dropALL. This is broader admission
than ideal and must be accepted explicitly. Actual CODE startup, resource fit and
editing remain untested. Do not weaken global isolation to make it run.

No SMTP, production OIDC clients, analytics, remote storage, production accounts
or Internet egress are configured. Wallabag's initial image default account
password is changed to a generated proof password on activation; it is accessible
only through the isolated proof routes/validation boundary. Redis authentication
is retained where current Compose uses it (Nextcloud); other caches are private
backends with explicit ingress only.

## Private state and resource lease

Requirements: Python3, PyYAML (offline tests), `kubectl`, a parent-approved proof
kubeconfig, verified Gateway CA and a currently owned single resource lease.
No cluster command occurs during `prepare`.

```sh
umask 077
STATE="$HOME/.local/state/talos-data-proof"  # outside this checkout
python3 scripts/talos-proof-data.py prepare --state "$STATE"
# Parent supplies these paths; never paste their contents into logs:
export KUBECONFIG=/private/path/proof-kubeconfig
export TALOS_PROOF_DATA_LEASE=/private/path/data-lease.json
export TALOS_PROOF_GATEWAY_CA=/private/path/proof-ca.crt
export TALOS_PROOF_GATEWAY_PORT=18443
python3 scripts/talos-proof-data.py apply --group couchdb --state "$STATE"
python3 scripts/talos-proof-data.py run --group couchdb --state "$STATE"
```

State directory must be0700, credentials JSON0600 and outside git. Fresh random
per-boundary credentials are generated once and reused for that proof's PVCs.
The script submits Secret objects from memory to kubectl stdin, never renders or
prints credential values. Treat kubeconfig, dump files and result state as private.
Do not delete/regenerate credentials while retaining initialized database PVCs.

The parent-authored lease JSON contains `group`, exact kubectl `context`, Unix
`expires`, `endpoint: "https://127.0.0.1:64120"`, and recorded `node_uid`. Every
apply/scale/exec/patch/rollout revalidates the exact endpoint with TLS enabled and
the single node name/hostname `talos-proof` plus that UID, not just context.
Private state paths and existing ancestors/credential files reject symlinks using
lstat before resolution. An expired lease also blocks cleanup: parent must grant
a lease long enough for the bounded run and renew if an exceptional timeout occurs. Metrics API is preferred for memory observations. With the
intentional no-metrics-server platform, parent additionally provides guest
`available_mib` and Unix `measured_at`, at most120seconds old. This must measure
**guest available memory**, not Proxmox host free RAM. A missing/stale observation
fails closed. A lease is a coordinator receipt, not an authorization boundary
against a malicious cluster administrator.

The guard rejects another labelled proof workload outside the active boundary
(except validation/gateway); compare parent labels during integration. It requires
available memory >= summed group limits +192Mi reserve:

| Group | Sum of Deployment memory limits (MiB) |
|---|---:|
| Nextcloud + PG + Redis + Collabora |1728|
| Immich + ML + PG + Valkey |2240|
| Miniflux + PG + fixture |448|
| Wallabag + MariaDB + Redis + fixture |576|
| CouchDB |256|
| Pocket-ID |192|

The initial node was2560MiB; parent subsequently approved3072MiB for VM120 only
(actual guest total approximately2823MiB, available approximately1420MiB after stop).
Full heavy groups still **do not fit**, even sequentially,
after control plane/Cilium/system overhead. Do not bypass the guard, lower safety
reserve, resize existing VMs or claim complete proof on that basis. Parent must
coordinate an honest resource-safe plan (including potentially testing Collabora
or ML separately with acknowledged cross-service gaps). No such alternative
capacity plan is silently applied here.

`run` activates only one namespace, waits at most900seconds, executes the synthetic
suite at most1800seconds, and scales back to0 in `finally`, waiting180seconds for
pod deletion. Startup/test failure also triggers cleanup. Persistent PVCs remain.
`activate`, `test`, and `deactivate` are available for coordinated diagnosis;
standalone successful `activate` intentionally leaves pods running and requires
explicit `deactivate`. A process killed with SIGKILL cannot guarantee cleanup.
CronJobs stay suspended during every lifecycle action. No automatic production
backup/sync/job is enabled. Re-applying the zero-replica base will deactivate apps.

## Functional and recovery evidence contract

`tests/talos-proof-data-live.py` is executable proof, not readiness-only. Direct
invocation also checks the resource lease. Frontend HTTP requests use SNI and
verified TLS to their real `*.proof.invalid` Gateway routes through the parent's
loopback18443 forward; no public DNS is changed and proxies are disabled. Only
internal ML ping uses API port-forward. API exec handles database backup/import.
The suite writes sanitized per-group result JSON privately; secrets and raw HTTP
error bodies are never printed. Parent may copy reviewed result JSON into evidence.

| Service | Implemented assertions | Not yet demonstrated |
|---|---|---|
| Nextcloud | authenticated WebDAV PUT/GET byte equality, pod replacement/read, deletion; full PG dump and independent restore with exact SQL sentinel; PG pod replacement; bounded cron.php execution | **All live checks pending**; interactive WOPI editing/callback, richdocuments provisioning, browser UX |
| Collabora | real Gateway WOPI discovery action XML | startup/capability/resource fit; full interactive editor integration; no richdocuments Internet install attempted |
| Miniflux | **LIVE PASS:** authenticated category/feed CRUD, synthetic RSS fetch, read-state, PG replacement, distinct clean-PG-PVC logical restore with authenticated content SHA match | external feed fetching intentionally forbidden; whole-run resource peaks not captured |
| Wallabag | **LIVE PASS with fixture exception:** real OAuth password login; HTTP URL capture/extraction/read/update/archive/star/delete+404; export content SHA; MariaDB replacement; clean-PVC logical restore and existing-user OAuth relogin with same article SHA | browser UX, Redis async queue/import worker, production resource capacity; earlier replaced-container peaks unknown |
| CouchDB | **LIVE PASS:** trusted TLS Gateway auth denial401; authenticated document create/read and database deletion; pod replacement; logical JSON restore into distinct clean PVC; exact canonical SHA256; second replacement/read; source reattached and all pods deleted | replication, multi-node recovery, VM/disk loss |
| Immich | synthetic PNG generated in memory; fresh admin signup/login; asset upload/original download byte equality; server replacement/download; full vector PG dump/restore; ML ping | all live pending; ML inference/model download, thumbnails/job completeness, GPU/video, external OIDC |
| Pocket-ID | **LIVE PASS:** fresh virtual WebAuthn registration/login, PKCE code/state, signed ID token/JWKS/claims, userinfo, unknown client rejection; existing passkey/user after pod and distinct clean-PVC logical restore | physical authenticator UX/recovery, hardware attestation; replay/wrong-verifier negative tests not yet run; strict aud fix tested offline after live run |

The PNG and RSS/article content are synthetic. Dumps contain only new proof data
and remain0600 outside git. The initial generic PG sentinel helper uses a separate `proof_restore` database.
The actual Miniflux/Wallabag/Pocket-ID/CouchDB recovery suites additionally use
distinct newly provisioned PVCs/PVs, stop the old instance, restore logically,
validate existing application data/identity, and then reattach the retained source. PG dumps are hashed for
reproducibility, but a hash is not a backup-durability claim. Pod replacement uses
the same local PVC/node; it does not prove VM loss, disk loss, HA, remote recovery
or node-reboot survival. Parent platform negative isolation and gateway evidence
must be combined with these functional checks for integration acceptance.

## Offline verification

```sh
kubectl kustomize kubernetes/apps/data | python3 tests/kubernetes-proof.py
python3 tests/talos-proof-data_test.py
node tests/talos-proof-data-oidc_test.mjs
```

The37 offline tests cover parent safety validation, exact boundaries, current
Compose image membership, Immich/PG18 paths, default-deny presence, group-budget
accounting, no committed Secret manifests, fresh/private credential behavior,
repository-state refusal, no implicit kubeconfig, expired leases, exact endpoint/TLS/node UID enforcement, symlink/ancestor
refusal, mutation reauthorization, frontend-only reserved ingress ports, and stale
or insufficient memory rejection. Clean-PVC failure cleanup restores the source
claim, and restore refuses a nonempty target PostgreSQL cluster. These are not live assertions. Static result and
render hash are recorded under `docs/evidence/talos-data/`.

## Work in progress after safety review

The lower-resource suites now implement **separate newly provisioned clean-PVC**
restores, not only a second database on the same disk: CouchDB JSON documents,
Miniflux full PostgreSQL logical backup, and Wallabag MariaDB logical backup.
Source frontends/database are stopped before switching the Deployment claim;
source PVC remains retained and is reattached in finally. Evidence records distinct
source/restore PVC UIDs and PV names. The restored application validates original
content/checksum through its real TLS Gateway. These workflows remain **NOT RUN**
until the parent releases platform lease and grants the data lease.

Pocket-ID browser protocol experiments are implemented in
`tests/talos-proof-data-browser.mjs` using Mac-local Chrome and pinned
playwright-core1.58.2 outside git. Python independently verifies Gateway TLS using
the public self-signed certificate. Chrome uses that exact leaf SPKI pin rather
than broad ignoreHTTPSErrors or global keychain changes, and browser routing blocks
non-proof origins. Fresh CDP virtual CTAP2 keys are generated locally, registered
using navigator.credentials.create, then used with fresh cookies for actual
WebAuthn login. The harness creates an isolated PKCE client and checks authorization
code/state, token signature against JWKS, issuer/audience/nonce/sub/expiry and
userinfo identity. Keys remain0600 outside git; no fixed upstream fixture keys,
tokens or browser traces are printed/committed. This is not a physical passkey UX
claim. **The real browser flow remains untested pending lease**, although Chrome
launch/CDP availability has been verified locally. Set
`TALOS_PROOF_PLAYWRIGHT_MODULE` to the private installed playwright-core directory.

## Live CouchDB result

`docs/evidence/talos-data/couchdb-live-result.json` records the actual trusted TLS
Gateway functional run on node UID4845bfd5-3bdb-453d-8503-83b43edb7a1e through
18443→30310. Source claim UID2ec59c23-2b17-4b50-8f02-d84acbd6cd56 and restored
claim UID1635d436-9593-455c-b084-d545b7060e51 have distinct PVs. Restored content
canonical SHA256 matched the backup exactly. Fresh instance had no source database
before import. Auth denial401, authenticated read/write, original and restored pod
replacement persistence all passed. Image identities/restart counters and node/pod
memory are in adjacent evidence JSON. The first immediate post-rollout request
observed transient Gateway503; bounded idempotent retries were added and the full
suite rerun passed. No retry masks authentication errors or non-idempotent writes.
The source claim was rebound and **all CouchDB pods were deleted** at release.

Wallabag's offline prepared bounded profile is576MiB total, with explicit MariaDB
64MiB buffer pool/max12 connections/smaller engine caches, and PHP128MiB memory,
32MiB opcache and **one** on-demand PHP-FPM worker. Read-only source discovery
verified PHP8.2 and the exact config location/default five workers. This is a
resource-bounded synthetic workload experiment, not yet a successful runtime
capacity claim. The installer is allowed to create its own absent database; an
empty pre-created database would incorrectly skip schema installation.

Mac-side public ML artifacts are prepared and hashed: ViT-B-32__openai, commit
`a857c8de2c07bbcfa6646adfcf31b798845afa1e`, nine files610,837,857bytes. Canonical
URLs and SHA256 (verified against upstream LFS where available) are in
`ml-model-artifacts.json`. `scripts/talos-proof-data-models.py preload` requires
an actual Immich lease and copies only these files into the fresh proof cache.
Model revision and HF_HUB_OFFLINE are explicit; no cluster Internet widening is
needed. **No ML preload or inference has yet run.** Pocket-ID's built-in logical
export/import ZIP procedure is implemented for a separate clean PVC, with server
stopped during import; virtual WebAuthn/OIDC still awaits its live lease.

## Serial suite live checkpoint: Miniflux and Pocket-ID

**Miniflux PASS:** real CA-verified HTTPS Gateway, synthetic RSS/article fixture
fetch, authenticated category/feed CRUD, entry read-state update, PostgreSQL pod
replacement persistence, full logical dump restored into a distinct new PG PVC,
and authenticated restored entry/read-state/content SHA256 match. Source claim
UID04d80385-d11a-481e-b666-81162c795a0a, restore claim
UID2344508f-981b-484b-b450-52cbac4b25c6. Initial scheduler factor0 was invalid and
caused5 CrashLoop restarts; corrected to1. A PG replacement produced one transient
401 with valid credentials, recovering within1second. This is recorded as a
specific positive recovery observation; negative-auth tests are not globally
retried. Initial immediate non-idempotent POST503 prompted a preceding health GET
convergence check rather than blindly repeating the write. See adjacent live
result/runtime JSON for SHA256, image IDs, latest pod identities and memory.

**Pocket-ID PASS:** Mac Chrome157 and a fresh local virtual CTAP2 authenticator
performed real navigator.credentials.create registration, then fresh-cookie
passkey login. A proof-only PKCE OIDC client produced a matching state/code,
verified ID-token signature against JWKS, validated issuer/audience/nonce/subject/
expiry, matching userinfo, and rejection of unknown client credentials. The same
user993f20dc-ca5b-47b7-a36a-d176ff684b2f and **existing passkey** worked after pod
replacement and after built-in logical ZIP export/import into a distinct new PVC
(source090ae00b-e1ca-4e40-9f2a-2007d9869620, restore
93516455-e83f-4f71-8cba-917f992f3f97). No new account was created on restore.
Three complete signed OIDC browser flows passed. Initial registration/login had
already succeeded, but callback navigation raced token exchange; waiting for the
callback DOM fixed the race. Key material/tokens remain private0600 outside git.
This proves virtual WebAuthn protocol/crypto, not physical authenticator UX.

**Wallabag PARTIAL, not functional acceptance:** all four pods became Ready under
576MiB aggregate limits. Actual PHP128M/opcache32M and MariaDB64MiB buffer pool/
max12 connections were verified; per-pod working sets and cgroup memory.peak are
recorded. The proof account password was rotated. Console commands require
explicit --env=prod because dev dependencies are absent. Generic FOS create-client
is incompatible with Wallabag's Client(User) constructor; an owner-aware bootstrap
was implemented, then diagnosed as requiring an FQN under Doctrine persistence3.
That FQN correction is prepared but **not live rerun** at this checkpoint. Actual
OAuth token login, fixture URL extraction, HTTP read/update/archive/delete and
clean-MariaDB restore/relogin are executable in the suite but **NOT PASSED** yet.
CLI-only import/export is not frontend acceptance.

All groups were deactivated and pod deletion confirmed before switching groups.
At the final safe checkpoint the global talos-proof-labelled pod query found
**no resources**. No simultaneous groups or production copy were used. The early
CouchDB proof is bounded to document create/read, database deletion and logical
restore/restart—not document revision update/conflict/delete, CORS or replication.

## Completed Wallabag HTTP and clean-PVC recovery proof

The subsequent exclusive Wallabag run passed the actual real Gateway workflow:
OAuth password token login with the **fresh proof** account; POST a synthetic
article URL; real Graby extraction; GET; PATCH title/archive/star; export exact
content SHA256; MariaDB replacement/read; full logical dump and restore into a
distinct clean MariaDB PVC; **existing-user OAuth relogin**; read the same article,
archive state and content SHA256; DELETE and404; reattach the retained source and
clean up its test article through authenticated HTTP. Source PVC UID
6e8d81ac-4551-46be-9640-431ddbbd100c and restored UID
ad3caf6d-1fec-409e-9651-30900678e6f3 are distinct. Content SHA256 is
776281cc58d4ac7357609e41bdad7c083337751f9b8e0ae30c369aabf78df105.
A transient HTTP500 after database replacement recovered within1second and is
recorded, not discarded. Earlier bootstrap/fixture failures remain in evidence.

**Extractor exception, not an unchanged production security setting:** upstream
Graby only permits80/443/8080 and blocks private addresses. The isolated fixture
therefore uses8080 and a declarative, SHA-pinned proof adapter permits private-IP
resolution **only for `fixture.proof-wallabag.svc.cluster.local`**. Every other
Graby scheme/port/domain/IP check remains. The adapter refuses an unexpected
upstream source hash. It patches only the proof container's ephemeral layer,
never Docker-host or a production image/data volume. Cilium still allows only DNS
and exact backend/fixture pod flows; there is **no subnet/Internet/host allowance**.
This test-specific source/config delta is required by the synthetic private
fixture topology and must be retained in acceptance qualifications. No production
password was rotated: only `proof-wallabag`'s newly initialized account changed.
The sole Docker-host interaction was read-only version/config discovery.

Redis PING/memory and the actual PHP-FPM master+one worker were captured. Redis
asynchronous queue/import-worker integration was not exercised. All group pods
were deactivated, waited deleted, and the global talos-proof-labelled pod query
returned no resources before releasing the exclusive lease for ops/media.

### Resource qualification

`wallabag-live-runtime.json` includes each **latest surviving container's**
memory.current, memory.peak, memory.events and pod UID before final deactivation.
These are not whole-run peaks: earlier containers replaced during restore were
not sampled before deletion. Node available memory is a point-in-time observation,
not a minimum correlated with peak application memory. No extra resident monitor
or host changes were used. Latest sampled memory.events had oom/oom_kill/max0.
Nevertheless Wallabag's latest peak was201,289,728bytes against192MiB limit and
the fixture peak66,637,824bytes against64MiB—very near their cgroup limits, with
reclaimable cache included. Thus a successful synthetic workflow is **not** a
20–25% headroom or production-capacity acceptance. The192MiB guard reserve is only
an operating safety floor. Nextcloud/Immich/full simultaneous deployment remain
separate unproved resource gates. No limits were silently raised or OOMs hidden.

### OIDC audience validation follow-up

Parent review found generic `aud.includes(clientId)` would also match a substring
when aud is a string. The shared strict `audienceMatches` helper now requires
exact string equality, or an all-string array containing that exact client ID.
Thirteen pure negative/positive cases cover substring strings, mixed arrays,
null/object/number/empty inputs. The browser flow imports that helper. This fix
was offline tested after the successful Pocket-ID runs; no extra Pocket-ID
activation overlapped Wallabag. Authorization-code replay and wrong-PKCE-verifier
negative live tests remain untested and are not implied by unknown-client denial.


## Offline heavy-stage checkpoint (live lease NOT held)

Ownership of the stopped data scope was explicitly reassigned after Wallabag
commit `3b070339`. Existing completed evidence is retained unchanged. During this
checkpoint **no cluster commands, app mutations, credential regeneration, source
Docker calls or host/VM changes were performed**. OPS owns the exclusive live
lease; media precedes the next data window. Preparation is not a runtime PASS.

### Explicit stage admission

Heavy groups now require `--stage` on **every** lifecycle/test/preload invocation.
A private regular0600 parent receipt must match `group`, `stage` and the exact
sorted `selected_controllers` array, in addition to all previous context,
endpoint/TLS/UID/expiry checks. Example web selection:

```json
{
  "group": "nextcloud",
  "stage": "web",
  "selected_controllers": ["deployment/nextcloud", "deployment/postgres", "deployment/redis"]
}
```

This fragment is not a usable lease: parent still supplies context, endpoint,
node_uid, expires and fresh available_mib/measured_at privately. The CLI does not
write/renew the receipt or grant itself authority. An omitted stage must never
implicitly activate the full group. Only exact selected Deployment names are
scaled; tests also refuse unselected active controllers/pods, active Jobs and
unsuspended schedules in the same boundary. Other proof groups remain excluded.
Low-resource group behavior/receipts remain compatible except0600 is now enforced.

| Group/stage | Selected controllers | Limits MiB | With192 reserve | Next live purpose |
|---|---|---:|---:|---|
| nextcloud/web | nextcloud, postgres, redis |1088|1280|WebDAV bytes, replacement, full DB dump → distinct clean PostgreSQL PVC → existing-user WebDAV bytes; reattach source|
| nextcloud/cron | postgres, redis + cronjob/nextcloud-cron |640|832|One Job from suspended CronJob, web stopped; success + persistent lastcron timestamp|
| nextcloud/collabora | collabora |640|832|Startup/capabilities/discovery only; **NOT editing acceptance**|
| nextcloud/full | nextcloud, postgres, redis, collabora |1728|1920|Blocked at reported1420 available; no automatic fallback|
| immich/app | immich, postgres, valkey |1216|1408|Actual PNG upload/original bytes, replacement, generated thumbnail, clean vector-PG PVC application read|
| immich/ml | ml |1024|1216|Pinned model preload; real image + text CPU ONNX /predict,512 finite nonzero values each|
| immich/full | immich, ml, postgres, valkey |2240|2432|Blocked; integrated CLIP indexing + real /api/search/smart uploaded-asset result remains a separate gate|

Controller names in the table mean `deployment/<name>` except the named CronJob.
Cron's receipt includes `deployment/postgres`, `deployment/redis` and
`cronjob/nextcloud-cron`, sorted lexically. Its192MiB Job is included in the640MiB
budget, never added alongside the web stage. The recurring schedule stays suspended.
The test and lifecycle cleanup delete only the bounded `nextcloud-cron-proof` Job.

**Immich app margin is only12MiB over the admission floor** at the reported
1420MiB available. Re-measure immediately before activation; refuse if below1408.
The192MiB reserve is unchanged and is not a capacity/headroom claim. Fresh
measurement and parent approval are needed independently for every stage.

### Declarative single-user tuning and resource evidence

Nextcloud retains640MiB limit and PHP256MiB/64MiB opcache, with explicit Apache
prefork **one** worker. PG retains384MiB limit with64MiB shared_buffers,
16 connections,2MiB work_mem and32MiB maintenance_work_mem. Cron now explicitly
receives REDIS_HOST, matching the image's environment-derived Redis configuration.
These are untested single-user proof settings, not production recommendations.

ML's original384MiB limit was not a credible allocation for610,837,857 bytes of
model artifacts plus runtime/session/workspace. It is now declaratively1024MiB
for its isolated component stage; full group budget therefore increases to2240.
One worker, one request thread, one intra/inter-op thread, disabled ONNX arena,
10s TTL and2s TTL polling are configured. Visual and textual requests run
sequentially with15s idle expiry between them. Actual model/runtime fit remains
unknown until measured; OOM must remain a failure, not trigger a hidden limit bump.
No Internet egress is added; nine existing private artifacts are rehashed on preload.

Public upstream API/config inspected at immutable release tag `v3.3.6`:
`machine-learning/immich_ml/{main.py,pipeline.py,config.py,models/base.py,models/transforms.py,sessions/ort.py}`.
The real multipart `/predict` contract uses `entries.clip.visual/textual.modelName`;
its CLIP output is a JSON-serialized vector string, not a /ping response. App-only
checks do not invoke ML or claim text search. Component vectors are **not** a
substitute for app-side indexing/search. Current full-stage search code is prepared
but cannot be executed within the measured budget. Richdocuments/WOPI editing
is not implemented by this checkpoint and is not marked passed.

The heavy suites collect cgroup v2 memory.current, memory.peak, memory.events and
memory.stat before explicit replacement/scale0 and after inference/final checks,
with observed pod UIDs/image IDs/restart counts. Anonymous vs file cache can thus
be reviewed; available memory is still a separate parent guest observation.
Observed oom/oom_kill fails the result even after successful functional checks.
Snapshot failures are explicit evidence gaps. Unexpected deaths between samples
and the short completed cron Job can escape per-container peak capture; no
whole-run minimum/headroom or absence-of-OOM claim follows from missing data.
Each invocation saves an additional unique private result-history JSON, so reruns
cannot erase earlier failures. No private result/ONNX/dump contents enter git.

### WOPI routing prerequisite — proposal only, not a policy change

Source Gateway declarations use the native Cilium NodePort Gateway with HTTPS443.
Current data policy permits Nextcloud↔Collabora direct9980, not Collabora egress
to the public Nextcloud HTTPS origin. No cluster Gateway IP was queried in this
checkpoint. Before full WOPI work, parent must inspect the generated Gateway
Service/ClusterIP and actual Cilium identity/drop verdicts. A minimal proposal is
**pod-scoped** proof-only hostAliases for exactly nextcloud.proof.invalid and
collabora.proof.invalid to that verified Gateway address, verified proof CA trust,
and exact frontend-client egress to Gateway TCP443 with the matching native
Gateway client policy as determined by datapath evidence. No global CoreDNS
rewrite, production DNS, broad CIDR/world/cluster allow, TLS bypass or removal of
the global hard-deny is authorized. Parent owns any required platform policy.
If this cannot fit or be narrowly authorized, retain the integration blocker;
a future component WOPI fixture must explicitly disclose its narrower coverage.

### Validation at this checkpoint

`python3 tests/talos-proof-data_test.py`:37 offline tests pass, including stage
budgets vs rendered limits, exact stage/controller receipts, no implicit heavy
selection, selected-only scaling, same-boundary participant rejection,0600 leases,
reserve boundary and finite/nonzero embedding validation. Rendered app safety and
13 strict OIDC audience cases also pass. A first new-test run found a mocked
CronJob response mismatch after adding schedule checks; the fixture was corrected
and all tests rerun. This was offline test failure, not a hidden runtime failure.
No Nextcloud, cron, Collabora or Immich live result is claimed.


## Offline WOPI/integration checkpoint — supersedes optimistic admission above

**No data lease is held. All earlier data receipts are revoked. No live API calls,
app mutations, source Docker calls, secret regeneration or host/cache changes were
performed in this checkpoint.** Media has the exclusive live window. The previous
Talos-only approximately1420MiB estimate is NOT safe admission: parent measured
kubelet eviction availability642–688MiB while Talos reported approximately1403MiB.
`guard` now requires fresh numeric `kubelet_available_mib` AND
`talos_available_mib` in the private receipt and takes their **minimum**. Missing,
stale, NaN/bool or invalid signals fail closed; no RSS/working-set subtraction or
optimistic legacy `available_mib` fallback is accepted. Reserve stays192MiB.
Ordinary workload reclaim may alter future observations; no cache drop, pressure
trick or limit reduction is authorized. **Every heavy stage is currently blocked.**

### CODE editing/save fixture, not Nextcloud Office acceptance

New explicit `nextcloud/wopi` stage selects exactly `deployment/collabora` and
`deployment/wopi-fixture`:704MiB limits +192 reserve =896MiB. Its receipt must
name that stage and the sorted controller list. It is currently blocked at642–688.
The64MiB fixture reuses the immutable CPU ML image solely for Python stdlib,
nonroot/read-only root, token automount disabled, emptyDir capped2MiB. It does
not load ML or copy any Nextcloud/production data. All defaults remain replicas0.
All-declarations Nextcloud budget is now1792MiB (includes the otherwise-off fixture);
`nextcloud/full` still selects only the original1728MiB services, not the fixture.

The fixture implements single-file CheckFileInfo/GetFile/PutFile, LOCK,
REFRESH_LOCK, UNLOCK, GET_LOCK, old-lock relock,30-minute expiry,409 held-lock
responses, token enforcement and1MiB upload bound. It never logs token-bearing
requests. It exposes no public Gateway route. Exact directional pod policies only
allow Collabora→fixture TCP8082; DNS remains scoped. CODE aliasgroup2 names only
`http://wopi-fixture.proof-nextcloud.svc.cluster.local:8082`. Existing public
Nextcloud allowlist stays unchanged. CODE's existing `ssl.termination` option is
set true because the real public route terminates TLS at the proof Gateway;
internal listener TLS remains disabled by the existing architecture, **not**
certificate verification disabled on any HTTPS connection.

`tests/talos-proof-data-wopi.mjs` uses pinned Mac-local Chrome/playwright, the exact
independently CA-verified leaf SPKI, actual public CODE HTTPS origin and WSS.
HTTP and WebSocket routing aborts every other browser origin. Discovery must offer
a txt edit action with the correct public HTTPS origin; the test will not invent
an editor URL or silently rewrite HTTP discovery to HTTPS. The browser posts the
fresh proof token through the real editor form, waits for rendered document canvas,
types a unique marker and invokes save. Python independently requires real
CheckFileInfo/GetFile/LOCK/PutFile callbacks **and marker-containing saved bytes**,
recording checksum/events only. Browser input dispatch alone is not a PASS.
Canvas/keybinding compatibility, CODE startup, callback protocol and save are
**prepared, NOT LIVE TESTED**. No screenshots/DOM/tokens/raw URLs are emitted.

This is a faithful bounded text-document WOPI-host experiment, not full WOPI
conformance or Nextcloud richdocuments. It does not satisfy the inventory's ODT
via Nextcloud, close/reopen, wrong-host live denial or restart Office gates. Its
plain internal HTTP callback is intentionally isolated by exact pod policies;
public browser TLS remains verified. No global/platform/Gateway policy was edited.

### Supported Nextcloud35 Office options (research, not installation)

Public richdocuments **v12.0.2** `appinfo/info.xml` declares Nextcloud min35/max35
and PHP≥8.3. At that exact release, `lib/AppConfig.php` defines and consumes:

- `wopi_url`: Nextcloud's internal CODE URL;
- `public_wopi_url`: browser-facing CODE URL;
- `wopi_callback_url`: CODE's callback base to Nextcloud.

Source: `https://raw.githubusercontent.com/nextcloud/richdocuments/v12.0.2/lib/AppConfig.php`,
SHA256 `9820dab896d01a7352792e5a6f13fbea2a6eeb4b03bbf1c86e13281290b51ce3`.
Compatibility metadata: same release `appinfo/info.xml`. Supporting sources inspected:
`lib/Service/DiscoveryService.php` SHA256
`39725d7ff2733bfc52ed8f4ba7501d2ab2c5ba83b02c88a6338db172472aa317`,
and `lib/Service/CapabilitiesService.php` SHA256
`aef99d5d7ff423a39eb20167c0552dc67611151942b43ad53f4c06efa8f8829a`.
Several attempted guessed source paths returned404; the SDK web page returned an
anti-bot page, not API documentation. Neither is treated as supporting evidence.

A supported future topology can use `wopi_url=http://collabora:9980`,
`public_wopi_url=https://collabora.proof.invalid`, and
`wopi_callback_url=http://nextcloud` (already a proof trusted domain), with an
explicit exact CODE callback allowlist and matching pod ports. This avoids public
DNS/Gateway hairpin for service-to-service traffic while preserving real public
browser URLs. It must still be tested with a pinned, hashed complete app release
artifact and proof-only leased preload if not bundled. **That artifact/preload and
Nextcloud Office browser integration are not implemented by this checkpoint.**
Do not set `disable_certificate_verification`; no Gateway client policy is needed
for this proposed internal topology. If native Gateway callbacks are later chosen,
parent still owns inspection/authorization of exact platform policy.

### Inventory acceptance correction and expanded recovery scaffolding

The per-service table in `talos-proof-inventory.md` is the acceptance authority,
not the older basic-WebDAV table. Nextcloud's prepared web suite now creates two
additional synthetic proof users using OCS, grants one a read share, verifies its
exact DAV bytes, independently authenticates the third user and requires403/404
on both owner and incoming-file paths. Users/shares are checked again after the
coordinated restore; source users are removed after source fixture cleanup.
Passwords are private deterministic derivations of the existing fresh proof secret,
not production accounts or regenerated persistent administrator credentials.

Recovery is no longer presented as full app recovery from PG-only restoration:
the prepared suite enables maintenance (cron remains suspended), takes a logical
PG dump and complete HTML/config/apps/files archive at that quiescent synthetic
point, restores PG into one distinct clean PVC and the entire HTML/files tree into
a **second** distinct clean PVC, starts the restored runtime, exits maintenance,
then checks original bytes and second-/third-user share ACLs. Finally it reattaches
both retained source claims and exits source maintenance. Archives remain0600
outside git and contain fresh proof credentials; never publish them. These paths
are offline-prepared only; failure cleanup/consistency and actual resource demand
still need live validation. No production-data or VM/disk disaster recovery claim.

**Nextcloud still missing:** version restore and version/share continuity together,
rename/trash recovery, explicit file-record↔file identity checks, Redis lock
contention/reconnect, and actual Nextcloud Office ODT edit/reopen/restart. Basic DAV
or even the proposed paired restore must not mark the inventory row complete.

### Immich own-worker integration, not injected embeddings

Exact v3.3.6 OpenAPI and `SmartInfoService`/search schema were inspected. Prepared
suite now uses supported `/api/admin/config` GET/PUT with the complete returned
AdminConfigDto preserved, sets every job concurrency1, disables face/OCR/duplicate
work, map/reverse-geocoding/version checks and ML availability polling, and selects
only ViT-B-32__openai CLIP for the full stage. App-only stage disables ML explicitly
rather than emitting failed background inference requests. No unsupported env flag
or cluster Internet allowance is introduced.

The full stage preloads all pinned model artifacts, uploads the asset, requires
thumbnail bytes, waits for **Immich's own worker** to persist the asset UUID's
`smart_search` row, expires the visual model with the declared TTL, then invokes
real `/api/search/smart` and requires the uploaded asset. The harness makes only a
read-only SQL count; it never writes/injects embeddings or supplies a fake ML
response. It repeats association/search checks after clean vector-PG restore,
while retaining the original `/data` PVC (explicitly narrower than whole-app file
recovery). Source references at v3.3.6: `open-api/immich-openapi-specs.json`,
`server/src/services/smart-info.service.ts`, `server/src/services/search.service.ts`,
`server/src/schema/tables/smart-search.table.ts` and
`server/src/repositories/search.repository.ts`.

No legitimate sequential **component-only** arrangement has yet been shown to run
Immich's own indexing and search pipeline while server/DB/ML never overlap. The
full2240+192MiB allocation is blocked; app1216+192 and ML1024+192 are also blocked
against current eviction availability. No claim that separate CLIP vectors + upload
constitute integrated search. **Immich still missing:** album/share ACLs and a
second/third user, timeline/EXIF fixtures, video/playback, clean `/data`+DB recovery,
queue-once/reconnect assertions, cold/warm/cache-persistence measurements and any
actual live vector/search result. No human/cloud account is required for the
synthetic local cases; missing code and capacity, not account permission, block them.

### Offline verification only

39 data contract tests and8 local WOPI protocol tests pass; rendered app safety,
Python compilation and browser JS syntax checks pass. The local protocol tests
exercise both token denial and wrong-lock writes, expiry/relock/size bounds and
real saved bytes; they do NOT launch CODE. Two intermediate offline fixture-mock
failures after adding stricter admission were corrected, not runtime failures.
No new live functional/recovery/editing/inference PASS is recorded. Existing
CouchDB/Miniflux/Pocket-ID/Wallabag runtime failure history and evidence are intact.
