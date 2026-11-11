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


## WOPI live failure checkpoint and additional offline preparation

An explicit parent lease authorized **only CODE + WOPI fixture**, not Nextcloud,
PG, Redis or ML. Fresh minimum availability1133MiB passed704+192 admission. Both
components became Ready with0 restarts. Real public verified-TLS discovery offered
editable txt; the corrected pinned browser reached rendered CODE canvas and real
WSS. **Editing/save FAILED:** input dispatch did not independently demonstrate
PutFile bytes containing the unique marker. No full Nextcloud Office claim follows.

All four attempts and diagnostic gaps are preserved in `wopi-live-attempt-*.json`
and `wopi-live-checkpoint.json`: host-page form error, click timeout, an intervening
browser syntax regression, then dispatch without saved-marker proof. A negative
exec timed out; it is NOT a negative-auth/lock PASS. Host rejection/reopen remain
untested. Fixture callback event/content details were not retained on the failed
path before emptyDir deletion: that is an explicit evidence gap, not an absence
of callbacks claim. Subsequent code must preserve fixture evidence even on failure.

CODE has no shell. Instead of weakening the image/capabilities, exact container
cgroupfs files were read via authenticated Talos under
`/sys/fs/cgroup/kubepods/burstable/pod<UID>/<container-id>/`. CODE peaked at its full
671088640-byte640MiB limit, latest511934464bytes, memory.events max10, oom0 and
 oom_kill0. These are NOT safe peak-headroom figures. Fixture latest kernel peak
50954240bytes; earlier in-container observations are retained separately. No
limit raise, SYS_ADMIN/privileged container, global policy or host/cache tuning
was used. After a diagnostic timeout interrupted its cleanup sequence, an
immediate separate guarded cleanup successfully scaled only the leased controllers
to0, waited pod deletion and independently found **global labelled pod count0**.
The live window is released; no receipt authority is assumed beyond that window.

Before the lease arrived, additional **offline-only, unexecuted** code was prepared:

- ML: locally rehashed all nine existing pinned artifacts; added red/blue image–text
  positive-vs-negative cosine checks, model-cold/warm timing and repeated-vector
  tolerance, persistent-cache hash verification and inference after pod replacement
  with **no re-preload**.1024+192=1216MiB still requires fresh conservative admission;
  this code is not a live inference/score/cache result. No blind resource change.
- `scripts/talos-proof-data-memory.py` verifies the existing exact stage receipt
  and refreshes **only** actual kubelet/Talos memory observations and timestamp,
  preserving group/stage/controllers/expiry/identity. It never grants a lease.
- Office: public richdocuments12.0.2 package14642847bytes downloaded privately and
  verified SHA256 `5deacee4fa1bb8eb7068e86c6dadbdaf0e44f8c79df0298a2254f562e3ed949b`.
  A full-stage-only guarded preload validates archive paths/type and NC35 metadata,
  enables the app and supported internal/public/callback URL options, scopes
  `wopi_allowlist` to the actual current CODE pod IP and never disables HTTPS
  certificate verification. Packaged CachedRequestService/RemoteOptionsService
  already permit app-scoped local-address discovery; no global SSRF exception.
  Existing exact80/9980 policies suffice; CODE aliasgroup3 is exactly
  `http://nextcloud:80`. No full-stage activation or app preload occurred.
- Actual Office browser scaffolding uses Nextcloud login and the packaged supported
  `richdocuments/index?fileId=...` route, a generated valid ODT, marker-in-content.xml
  save checks, close/reopen/web+CODE replacement, actual versions and paired clean
  volume recovery. It is not a functional PASS and inherits unresolved browser
  input/save behavior from this failed component window.
- Nextcloud DAV scaffolding now uses exact35.0.2 files_versions/files_trashbin Sabre
  RestoreFolder APIs: overwrite→enumerate real versions→MOVE original version into
  restore; rename→delete→DAV trash restore; compare DAV file ID/size to PG filecache
  and actual configured datadirectory file SHA256; require version hashes/file IDs
  and share ACLs after coordinated DB+HTML/files recovery. All remain live untested.

Immich album/share/metadata/video and coordinated `/data` recovery code is **not
finished** in this checkpoint. Existing own-worker/full-stage vector search code
remains capacity-blocked and unrun. No source-only feature-complete assertion is
made. User/tenant tests use synthetic local accounts, not production/cloud accounts.


## Renewed WOPI-only768MiB window: two attempts consumed, released

Parent explicitly approved **CODE768MiB only** after the recorded640MiB limit
saturation, retaining fixture64MiB and192MiB reserve. The declarative limits and
stage accounting now match: WOPI832+192=1024MiB; standalone CODE768+192=960MiB;
full original Nextcloud services1856+192=2048MiB. All-declarations Nextcloud budget
is1920MiB including the otherwise-off64MiB fixture. Earlier budgets/evidence above
are historical, not permission to use the old ceiling or optimistic memory signal.
No other limit/capability, reserve, platform/global policy, host/VM or source Docker
setting was changed.

The parent issued a **new** retry receipt (`data-nextcloud-wopi-retry.json`) with
new lease_id, max_attempts2 and exact approved_controller_limits_mib; the old released
receipt was explicitly revoked and never reused for activation. The new bounded
runner `scripts/talos-proof-data-wopi-run.py` requires these fields and exact768/64,
consumes a private unique per-lease attempt marker before mutation, refuses repeats
or a third attempt, refreshes only measured memory fields and requires fresh
min(kubelet,Talos)>=1024 before activation. It applies only selected component
resources and the scoped existing policies/route, not Nextcloud/DB/Redis/cron.
Both attempts are now consumed. **Live window released; no more activation.**

### Fixture hardening and checks

The earlier synchronous HTTP fixture was a plausible stall hazard, not a proven
root cause. It is now HTTP/1.1 with at most8 concurrent request handlers,5s socket
read timeout,32 requests per persistent connection, bounded1MiB body parsing,
correct `Expect: 100-continue` handshake, explicit rejection of unsupported transfer
encoding, body draining before reuse and RLock-protected state/atomic updates.
A stalled body is read outside the state lock. Sanitized callback event/status/
response-byte counts and file SHA/size are persisted to `/data/evidence.json` after
each response—never token/lock values or raw file bytes. Twelve offline protocol
regressions cover persistence,100-continue, a stalled client not blocking others,
lock conflicts, wrong tokens, expiry/relock, bounds and durable sanitized evidence.
This is still a narrow single-text-file fixture, not general WOPI conformance.

### Actual768MiB results: partial protocol proof, NOT edit/save

Both attempts started only CODE+fixture after fresh conservative admission, and
both ended with selected replicas0, pod deletion complete and **global labelled pod
count0**. See `wopi-768-live-attempt-{1,2}.json` and `wopi-768-live-summary.json`.
No Nextcloud/PG/Redis/ML was activated and neither receipt was extended.

- Attempt1 reached a genuinely loaded document but runtime permission was readonly;
  editor-only screenshot exposed the version-tour overlay and Viewing selector.
  Diagnostic Python exec could not read callback state, and fixture kernel data
  became unavailable. Extra Python in a64MiB Python fixture is a resource hazard,
  but no exact termination/OOM evidence was captured; **cause remains unproved**.
- Attempt2 switched diagnostics to a lean `cat` of persisted callback JSON and
  Mac-side API port-forward HTTP, avoiding a second guest Python interpreter.
  Captured real CODE callbacks: CheckFileInfo200, GetFile200/30bytes and LOCK200.
  The known `welcome-close` control was found and the version tour was dismissed.
  The real Viewing menu opened; the subsequent selector requested `Editing`, but
  the actual observed menu text is **`Editing Mode`**. That click timed out before
  input/Save. The cropped editor-only image `wopi-768-attempt2-editor.png` contains
  only the synthetic document/UI, no URL/token/credentials. The selector was fixed
  **offline after both attempts**, not retried live.
- Actual negative tests through the API tunnel returned bad-token401 and wrong-lock
  PutFile409. Independently reviewed persisted SHA and30-byte size were unchanged;
  no accepted PutFile event exists. No test-client successful PutFile was used to
  manufacture browser editing acceptance.
- **No marker edit, accepted PutFile save, saved-document close/reopen or explicit
  wrong-host live denial passed.** The corresponding code is not evidence. Full
  Nextcloud Office remains distinct and unproved.

The browser now records actual map document-loaded/edit permission, bounded
structural input/save-control IDs, dismisses only the observed known tour, selects
Editing Mode via real UI, checks editor clipboard focus and clicks the actual Save
button. An OS browser Save shortcut is no longer the save mechanism. Real saved
bytes/marker and PutFile callbacks remain mandatory. The prior corrected synthetic
parent HTML only hosts the iframe in the local browser; all CODE rendering, WSS and
WOPI reads/locks remain real. This is not the Nextcloud Office client route.

### Resource qualification

Both CODE containers peaked804855808bytes =767.5703125MiB under768MiB, leaving only
450560bytes (~0.43MiB) at the observed peak. Latest memory.events max0/oom0/oom_kill0
is retained, not treated as headroom. **Read-only document loading already nearly
exhausted the approved limit; editing and production capacity are unproved.**
Attempt2 fixture peaked53903360bytes (~51.4MiB), max/oom/oom_kill0. Kernel
memory.current/peak/events/stat, pod/container/image IDs and restart counts are in
both attempt records. Attempt1 fixture kernel gap is explicit. Prior640MiB failure
history/max10 and every768MiB failure are preserved unchanged. No cache-drop,
pressure trick, SYS_ADMIN/privileged container, sysctl or guard bypass was used.

Diagnostic capture now cannot skip guarded cleanup: exceptions are isolated and
callback JSON, negative outcomes and kernel samples are saved progressively before
an unconditional nested-finally scale0/delete wait. Both live cleanup records are
actual observations, not promises. Parent may revoke the released retry receipt;
no further app mutation is authorized by this checkpoint.

Offline verification:39 data contract tests,12 local WOPI protocol tests, rendered
app safety, Python compilation, browser syntax and diff checks pass. The new HTTP
and UI code is not complete Nextcloud/Immich functional acceptance. Deferred Office,
ML, database/files restore, tenant and media criteria remain as previously recorded.

## Offline ownership checkpoint: CouchDB and Miniflux acceptance expansion

**No live lease or controller activation occurred in this checkpoint.** Existing
results above remain authoritative; newly prepared code is not a new pass.
Acceptance was checked against the inventory and parent readiness matrix, not
inferred from the earlier green suites. Wallabag recovery remains **MariaDB**,
not PostgreSQL.

### Prepared light-data checks (not run live)

- **CouchDB3.5.3:** fresh proof users and two proof databases only; authorized
  revision update, actual stale-revision409, executable design view with exact
  marker/value, authorized tenant access and other authenticated tenant read/write
 403. One-shot replication uses explicit same-pod `127.0.0.1:5984` source/target
  URLs with member credentials and bounded `doc_ids`; no external endpoint,
  continuous job, automatic target creation or production checkpoint is used.
  A second replication must propagate an actual document deletion to404.
- CouchDB backup reads the **actual** `_security`, live documents (including the
  design doc) and necessary proof `_users` records (server-generated password
  hashes/salts, not just freshly constructed user definitions). Recovery reads
  the persisted SHA-verified archive, restores those records and security onto a
  distinct clean PVC, and revalidates allowed member, denied tenant read/write,
  exact documents and an executing design view. Member/denied checks repeat after
  replacement. This is **not** revision-tree, tombstone, shard, replication-
  checkpoint, CORS, multi-node or historical dataset recovery.
- **Miniflux2.3.5:** exactly one fixture entry with expected title/body; actual
  bookmark toggle and read state; changed valid `dark_serif`/`light_serif` theme
  and page-size preferences; assertions after PG replacement and clean-PVC PG
  restore. Successful source cleanup restores original preferences. Still unrun.

API contracts were checked against exact upstream tags:
[CouchDB3.5.3 security](https://github.com/apache/couchdb/blob/3.5.3/src/docs/src/api/database/security.rst),
[CouchDB3.5.3 replication](https://github.com/apache/couchdb/blob/3.5.3/src/docs/src/api/server/common.rst),
[Miniflux2.3.5 routes](https://github.com/miniflux/v2/blob/2.3.5/internal/api/api.go),
[user fields](https://github.com/miniflux/v2/blob/2.3.5/internal/model/user.go),
[theme enum](https://github.com/miniflux/v2/blob/2.3.5/internal/model/theme.go), and
[validation](https://github.com/miniflux/v2/blob/2.3.5/internal/validator/user.go).
Offline fake HTTP checks validate harness behavior, not application compatibility.

### Archive preservation and next runnable windows

New PostgreSQL/MariaDB/Pocket-ID/Nextcloud archives and CouchDB logical bundles
use UUID-suffixed filenames and exclusive0600 creation in the existing0700
outside-Git private state. **No old archive is renamed, deleted or overwritten.**
Results now append only `<group>-<stage-or-group>-<time_ns>-result.json`; old
fixed-name `<group>-result.json` observations remain untouched and therefore do
**not** identify a new run. CouchDB records its new private archive basename and
SHA256 in its result. Other existing backup hashes remain in their result.

After media release and **only with a new parent-issued exact group lease**, the
existing entry points are runnable serially (the parent supplies STATE, CA,
kubeconfig and selected-controller receipt/lease, never credentials in output):

```sh
python3 scripts/talos-proof-data.py run --group couchdb --state "$STATE"
# Different explicit lease, not part of the CouchDB lease:
python3 scripts/talos-proof-data.py run --group miniflux --state "$STATE"
```

Remaining light-data gaps: Pocket-ID actual wrong redirect/code replay/wrong PKCE
negatives; Wallabag actual extracted image retrieval, supported async queue worker
and Redis reconnect. They were not broadened into new partial frameworks here.

**Next focused implementation is Immich core**, whose current code only prepares
PNG upload/original checksum, thumbnail, pod replacement and **PG-only** clean-PVC
restore while retaining `/data`. Album/member/public-share ACL, metadata/EXIF,
video playback and coordinated fresh-`/data` + fresh-PG restore are still absent.
Standalone `--stage ml` real inference/comparison/hash/timing is prepared but unrun;
`--stage full` must observe Immich's own worker embedding/search, never inject
vectors. Neither stage is implicitly authorized or resource-approved. Nextcloud
web/cron/version/trash/share/coordinated recovery and richdocuments remain unrun;
CODE save/edit/reopen/host denial remain failed or unproved as recorded above.
No limit, cache, host, source Docker, guest or global-policy changes were made.

## Expanded CouchDB → Miniflux live checkpoint (2026-11-11 17:03–17:08 UTC)

**Both expanded suites passed their named functional checks on the first live
suite attempt.** This supersedes only the corresponding “prepared/unrun” checks
in the preceding offline checkpoint. It is not full-service or capacity acceptance.
Parent explicitly granted separate private CouchDB and Miniflux leases, in that
order. No Immich/ML/Nextcloud/Office/other data controller was activated.

### CouchDB: expanded bounded pass

[Immutable expanded result](evidence/talos-data/couchdb-expanded-live-result.json)
records36 checks: real update/stale-revision409, exact executable design view,
member allow/other authenticated tenant read+write403, same-pod member-authenticated
one-shot replication, replica exact document/revision and deletion propagation404.
Recovery read a SHA-verified private archive containing actual `_security`, the
actual design/live documents and two server-hashed `_users` records. Distinct
fresh PVC `687843e6-a262-48d4-8371-6afd48b121d7` restored those records, not new
user/password definitions; allowed/denied tenants and view execution passed there,
and permissions passed again after replacement. Source PVC UID remains
`2ec59c23-2b17-4b50-8f02-d84acbd6cd56`. Synthetic source databases/users were cleaned.

The immutable result retains an obsolete limitation sentence saying these checks
were “unrun until explicitly leased”; the recorded positive checks actually ran
under the newly granted lease. That sentence is corrected in future code, not
rewritten in the historical result. Shards/full revision trees/tombstones,
replication checkpoints, CORS, multi-node and historical-data recovery remain
outside this proof. Four observed pod UIDs had restartCount0; the final reattached
source container was not cgroup-sampled before deletion (an explicit measurement
gap, not an inferred zero). [CouchDB release](evidence/talos-data/expanded-couchdb-release.json)
records all proof pods absent and CouchDB receipt removal **before** Miniflux.

### Miniflux: star/preferences and PG recovery bounded pass

[Immutable expanded result](evidence/talos-data/miniflux-expanded-live-result.json)
records18 checks: exactly one fixture article with expected title/content, actual
bookmark toggle, read state and changed valid theme/page-size preferences. State
survived PostgreSQL replacement and a fresh-PVC logical restore validated through
real authenticated Miniflux HTTP. Restored PG UID
`1dc45c7d-0aa1-46da-a634-d46036993b3c` differs from source
`04d80385-d11a-481e-b666-81162c795a0a`. Source feed/category were removed and original
preferences restored.

**Transient failures remain visible:** one post-PG-replacement401 recovered after
one second; the first Miniflux pod had restartCount2, whereas restored/final app
pods had0. [Retained events](evidence/talos-data/miniflux-expanded-pod-events.json)
show initial BackOffs at17:05:40–47 and readiness/liveness503 during the PG restart.
Deleted container exit states/logs were not captured, so exact restart causes are
**not established**. One cgroup snapshot failed while a repeated scale0 targeted
an already-stopped app; other source/restored/final snapshots remain. Do not turn
this bounded functional pass into restart-free or soak acceptance.

### Resources, preservation and release

Fresh dual-memory minima at admission were1182MiB for CouchDB (kubelet1265,
Talos1182) and1111MiB for Miniflux (kubelet1169, Talos1111). Only actual measured
memory fields were refreshed; lease expiry/identity/group were unchanged. A new
explicit helper-deletion barrier waits for every remaining proof Job pod before
app activation, including restored app activation;41 offline contracts include
wait-before-scale and fail-closed-on-wait-timeout checks.

| Container | Maximum observed cgroup peak | Limit | Observed max/oom/oom_kill |
|---|---:|---:|---|
| CouchDB |193.8515625MiB|256MiB|0/0/0|
| Miniflux |36.46875MiB|128MiB|0/0/0|
| Miniflux PostgreSQL |139.51171875MiB|256MiB|0/0/0|
| Miniflux fixture |63.9921875MiB|64MiB|0/0/0|

**Fixture peak leaves only8192bytes (8KiB) below its limit.** At that observation,
current memory was60.63671875MiB, anon9.09375MiB and file49.515625MiB. Those are
current samples, not an exact decomposition of the earlier peak; inclusive
cgroup/file-cache peak is not synonymous with anonymous pressure. No capacity
headroom, zero-restart, representative concurrency or production-load claim is
made; no limits/cache/host settings were altered.

[Archive preservation](evidence/talos-data/expanded-archive-preservation.json)
recomputes all **four previous parent-crosschecked archive hashes** unchanged,
with original0600 modes. The new1087-byte CouchDB bundle and51495-byte Miniflux
PG dump have distinct UUID paths,0600 modes and recorded SHA256; private state is
0700. The CouchDB bundle contains two salted/derived-key records and no plaintext
password field. No secret/archive payload was committed or printed.

[Final release](evidence/talos-data/expanded-data-release.json) independently records
all proof Deployment/StatefulSet replicas0, all proof pods absent and both expanded
lease files removed. Separate checks found all proof CronJobs suspended and no
active proof Jobs. No further live grant remains. The host guard/baseline was not
reset or modified; no host execution, source data/credentials, production DNS,
storage, GPU or other guest change was performed. Remaining priorities are the
light-data negatives/Wallabag image+queue gaps, then Immich core as listed above.

## Offline checkpoint after expanded data release: Immich core and forensics

**No live lease, API/cluster read, controller mutation or host execution occurred
in this checkpoint.** Ordinary public upstream research and local/offline tests
only. All new sequencing and Immich acceptance assertions remain **LIVE UNTESTED**.
No readiness/root acceptance document is changed by this data-owned checkpoint.

### Concrete Immich3.3.6 workflow prepared

The app/full stages now prepare a real224px red PNG carrying TIFF EXIF make/model
and original date (independently parsed offline with ExifTool), plus a one-second
160×120 H.264 MP4 generated by the pinned server's existing FFmpeg. The multipart
upload uses the pinned v3 fields, **not** removed `deviceId/deviceAssetId` fields.
Assertions cover original bytes/SHA1 asset checksum, actual worker-extracted EXIF,
image/video dimensions and duration, timeline month/IDs, generated thumbnails,
and downloaded authenticated playback decoded into actual video frames. Synthetic
fixture generation/decoding is bounded, not a codec/GPU/performance survey.

Real HTTP operations create an album with both assets, invite a fresh viewer and
create a separate outsider. Viewer album/original reads must pass; outsider
album/original access and viewer asset removal must fail with the pinned API's
actual400 (not guessed403). Public album share keys must resolve the expected
album and thumbnail, enforce download-denied400, permit exact original download
after policy change, return to denied policy, reject wrong keys401 and reject a
revoked key401. Share keys/passwords are never added to public evidence; query
strings are excluded from failure-stage metadata. Proof account secrets are saved
only in fresh0600 private files; synthetic users/album/assets are retained for
audit. No existing user data or external libraries are used.

All these positive/negative assertions repeat after app replacement and after
**both fresh `/data` and fresh PostgreSQL PVCs** have been populated. For the
coordinated backup the app and its in-process workers are stopped, the same
pinned container temporarily sleeps on its source PVC, and `/data` tar + logical
PG dump are taken with no application writer active. No helper Pod is introduced.
The source runtime is returned to replicas0 before recovery. Clean PG restores
first; clean data PVC starts with sleeping bootstrap and must be empty, then
receives the SHA-verified file archive. Only then may the real app start and
freshly authenticate the recovered owner/viewer/outsider. Nested recovery contexts
use `resume=False` so neither starts a mixed old/new state on rollback. Original
volume bindings **and container specs** must match before the original PG then
app may restart; a mismatch fails closed. Source/restored claims remain retained.

`--stage full` additionally waits for Immich's **own worker** to persist a512D
embedding in `smart_search`, then runs a real red-image text search, including
after coordinated restore. Harness SQL is read-only; no embedding injection.
Standalone ML comparison/hash/timing remains prepared and unrun. App-only does
**not** claim ML inference/search. No resource limits were reduced or expanded;
no stage is implicitly authorized merely because implementation exists.

Contracts were checked against exact upstream
[v3.3.6 OpenAPI](https://github.com/immich-app/immich/blob/v3.3.6/open-api/immich-openapi-specs.json),
[access rules](https://github.com/immich-app/immich/blob/v3.3.6/server/src/utils/access.ts),
[album service](https://github.com/immich-app/immich/blob/v3.3.6/server/src/services/album.service.ts),
[media service](https://github.com/immich-app/immich/blob/v3.3.6/server/src/services/asset-media.service.ts),
[shared links](https://github.com/immich-app/immich/blob/v3.3.6/server/src/services/shared-link.service.ts),
and [vector schema](https://github.com/immich-app/immich/blob/v3.3.6/server/src/schema/tables/smart-search.table.ts).
These confirm API intent, not live compatibility. Redis/Valkey forced reconnect,
production-sized recovery/concurrency and general semantic quality remain gaps.

### Before-deletion forensic preparation (unrun live)

Lifecycle/suite destructive operations now first attempt an **off-node API** Pod
snapshot of regular/init container `state` and `lastState`, retaining safe
exitCode/reason/signal/timestamps but **not raw termination messages**. On restart,
previous container logs are fetched through the Kubernetes logs API (bounded to
1MiB/container and30seconds), stored exclusively in new0600 private files and
hashed. Safe state manifests are likewise fresh0600 private files; suite public
metadata contains only phase/hash. Failures are recorded as gaps and cannot
prevent guarded cleanup. No interpreter/agent is injected into a fixture, no
observer resource allowance is added, and no raw log/credential output is printed.
This cannot retrospectively recover either deleted Miniflux container's cause.

Existing cgroup peaks include any in-container exec diagnostics/fixture workload
where applicable; future captures must retain that qualification. CODE sampled
anon272MiB/file251MiB/inactive_file245MiB is not its767.57MiB peak decomposition,
nor proof against OOM or proof of editing headroom. The six failed CODE attempts
remain immutable. Their source was30-byte `proof.txt`, **not** ODT-format proof.
Nextcloud's separately prepared `.odt` path checks saved ZIP MIME/content text,
changed bytes, real version and the expected DAV file ID after save and reopen;
that workflow remains unrun and earns no standalone-WOPI format claim. The retry
runner now reads append-only stage result files rather than stale fixed names.

### Miniflux cold-start barrier (unrun live)

A bounded sequential `pg_isready` init container uses the **same exact PG18
image+digest** as proof PostgreSQL, explicit proof host/user/database and at most90
attempts with2second connect timeout/delay. Init memory128MiB and CPU limit match,
not exceed, the main Miniflux container. Kubernetes sequential-init effective
resource accounting therefore leaves the448MiB group limit unchanged; it is not a
concurrent sidecar. This addresses a plausible cold-DB startup race, **not a
conclusive cause of the historical two restarts**, and does not protect against
later DB outages. Existing restart/401 evidence is untouched.

Offline validation:42 data contracts,11 workflow tests (including actual EXIF
parsing, quiescence ordering, PG→files→runtime recovery, no mixed-pair rollback
startup, private log redaction/modes),12 WOPI protocol tests, compilation and diff
checks. These are regression/contract tests, not new live service passes.

## Offline light-data protocol/image/queue checkpoint

**No live lease, cluster/API observation, controller activation or host/source
mutation occurred.** Public exact-version source research and local/offline tests
only. All newly implemented negatives/image/queue sequencing below is **unrun
live**, not acceptance evidence. Existing expanded CouchDB/Miniflux results and
all old archives/observations remain unchanged.

### Pocket-ID2.19.2 real protocol negatives prepared

The existing real browser/WebAuthn/OIDC suite now prepares these actual requests,
not merely claim-validation mocks:

1. Redeem a real browser-issued authorization code successfully; validate signed
   claims and userinfo first. Then replay the **same redeemed code** with its
   correct verifier/redirect, requiring400 `invalid_grant` and no returned tokens.
   Userinfo precedes replay because providers may revoke tokens on code reuse.
2. Obtain a **different fresh real browser-issued code** and send a syntactically
   valid43-character but incorrect S256 verifier. Require400 `invalid_grant` with
   no access/ID/refresh token; unknown-client/malformed-request/500/transport
   failures do not count as PKCE denial.
3. Send a real authorization request with an unregistered same-proof-origin
   callback. Require the issuer's `/interaction/error` response with a
   redirect-specific error, no authorization code and **zero callback requests**.
   The forbidden callback is intercepted, never forwarded externally. A generic
   successful page or unrelated error is not accepted as redirect validation.

Negative outcomes are recorded progressively using only safe HTTP/error enums,
phase/path and a token-presence boolean—not tokens, codes, verifier values,
redirect queries or error bodies. Authenticator histories and browser results now
use exclusive UUID-named0600 files; the old fixed-name files are untouched. The
newest validated authenticator history supplies future login, including restored
passkeys. Public-key signature/audience/nonce/subject checks remain mandatory.

Contracts checked against Pocket-ID's exact
[v2.19.2 authorization handler](https://github.com/pocket-id/pocket-id/blob/v2.19.2/backend/internal/oidc/authorization_handler.go),
[token handler](https://github.com/pocket-id/pocket-id/blob/v2.19.2/backend/internal/oidc/token_handler.go)
and [route module](https://github.com/pocket-id/pocket-id/blob/v2.19.2/backend/internal/oidc/module.go).
No live negative protocol pass is claimed by the pure response-classifier tests.

### Wallabag image and actual Redis import worker prepared

The pinned Docker wrapper2.6.15.1 explicitly bundles application2.6.15
([Dockerfile](https://github.com/wallabag/docker/blob/2.6.15.1/Dockerfile)). The
fixture article now includes one harmless SVG at the already-authorized exact
fixture FQDN. A proof-instance-only Craue setting enables supported image
capture; the successful suite restores its original value. A real article save
must rewrite the image to the Wallabag `/assets/images/` origin. HTTP readback
must parse the known16×16 red SVG, record its SHA256, and retain that same hash
with the article after MariaDB replacement and distinct fresh-MariaDB restore.
**Image storage PVC is retained**, so this is not clean image-volume recovery.
There is no binary/base64 fixture, additional observer process or resource increase.

Source research confirms image downloading is **synchronous**. Redis queues are
for imports, not image downloads. The prepared async check uses the actual
`WallabagV2Import` with its supported `setProducer` method and the actual
`wallabag_import.producer.redis.wallabag_v2` service. It asserts one queued/zero
synchronously imported entry; real Redis pending depth1 and no visible API
article before running the real `wallabag:import:redis-worker wallabag_v2
--maxIterations=1`. A45second process timeout bounds the worker. Afterwards,
source/processing/failed/error depths must all be0 and authenticated HTTP must
show the exact imported URL/body/read/star state. A unique **supported tag
filter**, not an unsupported guessed title filter, isolates the synthetic item.
No harness `LPUSH`, direct SQL insertion or fake consumer substitutes for this.

After draining the first synthetic job, Redis is replaced and the same workflow
runs again using new real producer/worker connections. This proves only bounded
**connection reestablishment by fresh processes** if it passes—not a surviving
worker's transparent reconnect, queued-message persistence during restart,
in-flight delivery or exactly-once semantics. Those remain gaps; no unsupported
queue semantics are fabricated. Worker output remains in append-only0600 private
logs, and synthetic queue-created articles are deleted through the app API.

Exact sources:
[image subscriber](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/CoreBundle/Event/Subscriber/DownloadImagesSubscriber.php),
[image helper](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/CoreBundle/Helper/DownloadImages.php),
[Redis services](https://github.com/wallabag/wallabag/blob/2.6.15/app/config/services_redis.yml),
[importer](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/ImportBundle/Import/WallabagImport.php),
[producer](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/ImportBundle/Redis/Producer.php),
[consumer](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/ImportBundle/Consumer/AbstractConsumer.php),
[worker command](https://github.com/wallabag/wallabag/blob/2.6.15/src/Wallabag/ImportBundle/Command/RedisWorkerCommand.php).
`composer.lock` pins Simpleue2.1.0 (`b12ccea…`) and Craue2.7.0 (`5bf3673…`);
their real queue suffixes, worker iteration bound and setting persistence were
checked against those exact sources, not inferred from Redis PING.

### Runtime wording correction (historical JSON preserved)

The historical expanded CouchDB JSON still contains its old pre-run “prepared…
unrun” limitation sentence, despite its recorded live positive checks. The prior
expanded checkpoint explains that discrepancy; **the JSON is not rewritten**.
The current CouchDB generator already uses bounded-recovery-only wording; a new
regression test guards against reintroducing “prepared/unrun” there. Successful
future suites additionally emit
`workflow_execution: completed-under-validated-live-lease`; offline preparation
remains described in this runbook, not misreported in successful runtime results.
Equivalent stale preparation wording was removed from Immich's runtime limitation.

### Read-only Immich role-sequencing proposal—not implemented or admitted

Pinned Immich3.3.6 supports `IMMICH_WORKERS_INCLUDE=api` and
`IMMICH_WORKERS_INCLUDE=microservices`; its default includes both. These create
**genuinely different process roles**, unlike simply reducing an unchanged full
container limit. The old `start.sh microservices` entrypoint is explicitly
rejected by the pinned server, so that is not a supported proposal.

A future separately reviewed experiment could upload through API-only, stop that
role, run microservices-only against the **same** fresh data/PG/Valkey plus real ML
for own-worker indexing, then stop workers and use API-only + real ML for actual
text queries. It must prove queue completion, association and access across
transitions without embedding injection. Microservices-only does not serve the
existing2283 API health probe; supported readiness/shutdown must be designed and
measured rather than silently reusing an always-failing probe or a fake ping.

**No feasibility or smaller reservation is established.** Keeping all existing
limits unchanged, API-only+PG+Valkey still reserves1216MiB plus192MiB headroom
(minimum1408). Either role with ML still reserves2240+192=2432MiB. Standalone ML
requires1216MiB and Nextcloud web1280MiB. Parent-reported1069MiB guest minimum
admits none of these, including API-only. Role separation might change actual
memory behavior, but it does not currently change the admission result; it needs
fresh measurements and explicit leases before implementation/activation. Full
profile and all resource limits remain unchanged.

Source: [environment configuration](https://github.com/immich-app/immich/blob/v3.3.6/server/src/repositories/config.repository.ts),
[process supervisor](https://github.com/immich-app/immich/blob/v3.3.6/server/src/main.ts),
and [microservices bootstrap](https://github.com/immich-app/immich/blob/v3.3.6/server/src/workers/microservices.ts).

Offline validation:42 data contracts,14 workflow tests,13 strict audience cases,
18 negative-response classifier cases,12 WOPI protocol tests, syntax/compilation
and diff checks. None is new live Pocket-ID/Wallabag/Immich evidence.

## Pocket-ID protocol-negative live checkpoint (2026-11-11 18:54–18:57 UTC)

**Bounded functional pass on the first suite attempt.** Parent granted only
Pocket-ID, after independently observing all previous app/helper pods absent.
No Wallabag, ML, Immich, Nextcloud, Office or media controller was activated. The
new WebSocket boundary and actual-leaf SPKI extraction were installed/tested
before activation; no global TLS bypass or application Internet allowance was used.

[Immutable live result](evidence/talos-data/pocket-id-negatives-live-result.json)
records three complete browser runs: existing source state, pod replacement and
logical import into distinct fresh PVC. **Every run** passed actual positive
browser authorization/code redemption200, signed ID-token checks and userinfo,
then:

- Replayed that successfully redeemed code with correct original parameters:
  **400 `invalid_grant`, no access/ID/refresh token**.
- Obtained a different genuine browser-authorized code and supplied a valid-format
  wrong S256 verifier: **400 `invalid_grant`, no tokens**.
- Submitted an unregistered redirect: issuer `/interaction/error` response200,
  redirect-specific error assertion passed, no code and **zero forbidden callback
  requests**. The200 is the issuer error-page status, not a successful grant.
- Existing unknown-client credential denial still passed.

### Existing passkey—not silent replacement

Before activation, the original0600 `pocket-virtual-authenticator.json` existed
with one registered credential. The run explicitly required existing-credential
mode; a missing history would fail before signup/registration. All three browser
runs report **`registered_new_credential: false`**, the same existing user ID and
credential-ID fingerprint, independently matched to the pre-run baseline. Each
login started with cleared cookies and used `navigator.credentials.get` with the
saved virtual key. No `navigator.credentials.create` fallback was used.

This verifies the retained proof passkey/user in the current post-cold-start state
(parent reports the intervening VM cold start), after app replacement and after
clean-PVC import. It is **not** an independent VM cold-boot procedure or physical
passkey/device-recovery test. The browser description's “fresh CDP authenticator”
means a fresh browser emulator instance **loaded with that old credential**, not a
newly registered key. Original authenticator bytes are unchanged; advancing
virtual-authenticator counters are in new exclusive0600 history files.

Source PVC UID `090ae00b-e1ca-4e40-9f2a-2007d9869620` differs from restored
`a17b20a3-9b0d-4c11-953a-0bc5c89f4ec1`. The new logical export is UUID-named,
SHA-verified and private; the original245497-byte export remains unchanged. All
three flows use application2.19.2; this is not source2.19.1 upgrade acceptance.

### TLS, browser boundary and deletion forensics

Python performed a fresh hostname/CA-verified handshake to the actual Pocket-ID
Gateway leaf and derived **that leaf's** public-key SPKI for Chrome. Verified leaf
SHA256 is in the result. This no longer assumes the CA certificate itself is the
served leaf. HTTP routes permit only the exact issuer origin; all WebSockets are
blocked and service workers disabled **before first navigation**. Pocket-ID needs
no WebSocket, so this records the installed deny rule, not a useful WSS session.

[Forensic capture index](evidence/talos-data/pocket-id-negatives-forensics.json)
contains only hashes/phases for11 immutable0600 private state manifests, including
suite transitions and final lifecycle cleanup. Six live Pod-state snapshots were
captured before deletion/replacement; regular/init state and lastState were
retained without raw termination messages. All observed restart counters were0,
so previous-container-log capture was not applicable. No raw private logs, keys or
termination messages were published, no observer interpreter was injected into a
fixture, and no historical exit cause is inferred.

Maximum observed Pocket-ID cgroup peak was108515328bytes =103.48828125MiB under
192MiB; observed max/oom/oom_kill were0. Four cgroup-sampled Pod UIDs had
restartCount0. At the largest-peak sample, current anon was15.95703125MiB and file
82.2578125MiB; these samples are not a decomposition of the earlier peak. Inclusive
peaks include in-container exec diagnostics and import/export work where present.
This is not a production load, capacity/headroom or no-OOM-risk claim.

### Release, preservation and next decision

[Release/preservation record](evidence/talos-data/pocket-id-negatives-release.json)
independently records all proof app/helper pods absent, all proof controller
replicas0, receipt archived0600 then removed, and eight old files hash-unchanged:
the four original application archives plus original authenticator, credentials,
legacy Pocket-ID browser result and legacy suite result. No immutable historical
JSON or archive was rewritten. Synthetic newly-created OIDC clients were deleted
by each successful browser flow. Source PVC was rebound before cleanup.

Fresh admission minimum was1163MiB (kubelet1196/Talos1163). After deletion, the
exact fresh sample at Unix1794423428.4132 was **kubelet1195MiB / Talos1099MiB /
minimum1099MiB**. WOPI's unchanged768+64+192=1024MiB requirement is numerically
below that observation; Wallabag's576+192=768MiB is also below it. Neither is
activated or authorized, and this now-historical sample is **not** a fresh guard
receipt for either. Parent must choose/grant any next window and obtain new dual
measurements. ML1216/web1280/Immich-app1408 minima were still unmet by this sample.
The host guard/baseline was untouched; no host or source mutation occurred.

Post-run validation:42 data contracts,16 workflow/boundary tests,13 audience cases,
18 negative-response cases,12 WOPI protocol tests, syntax/compilation and diff
checks. Wallabag image/queue and every heavy/Office workflow remain unrun as
previously recorded. No live Pocket-ID receipt remains.
