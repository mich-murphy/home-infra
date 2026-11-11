# Isolated data and identity proof

## Acceptance status

**Implementation and offline checks only; no live deployment or functional proof yet.**
The parent has not granted a resource lease/kubeconfig. Do not interpret manifest
probes, rendered objects, or the executable functional test plans as passed tests.
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
| Immich + ML + PG + Valkey |1600|
| Miniflux + PG + fixture |448|
| Wallabag + MariaDB + Redis + fixture |896|
| CouchDB |256|
| Pocket-ID |192|

The actual node is only2560MiB. Heavy groups may **not fit**, even sequentially,
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
| Miniflux | category/feed CRUD; fetch synthetic RSS fixture via allowed network flow; entry read-state update; PG replacement; full PG dump/independent restore | all live pending; external feed fetching intentionally forbidden |
| Wallabag | rotate image default password; CLI v2 synthetic entry import with content update disabled; JSON export exact title/content; MariaDB replacement/export | all live pending; OAuth/browser login, article scraping, MariaDB backup restore |
| CouchDB | authenticated database/document create/read exact marker; pod replacement/read; database deletion | all live pending; replication, multi-node recovery, logical backup restore |
| Immich | synthetic PNG generated in memory; fresh admin signup/login; asset upload/original download byte equality; server replacement/download; full vector PG dump/restore; ML ping | all live pending; ML inference/model download, thumbnails/job completeness, GPU/video, external OIDC |
| Pocket-ID | isolated OIDC discovery issuer/endpoints; public signing JWKS; pod replacement/discovery | all live pending; interactive admin/passkey enrollment, user persistence, authorization-code/token flow, human browser ceremony |

The PNG and RSS/article content are synthetic. Dumps contain only new proof data
and remain0600 outside git. The restore target is a separate `proof_restore`
database, not an overwrite of the running app database. PG dumps are hashed for
reproducibility, but a hash is not a backup-durability claim. Pod replacement uses
the same local PVC/node; it does not prove VM loss, disk loss, HA, remote recovery
or node-reboot survival. Parent platform negative isolation and gateway evidence
must be combined with these functional checks for integration acceptance.

## Offline verification

```sh
kubectl kustomize kubernetes/apps/data | python3 tests/kubernetes-proof.py
python3 tests/talos-proof-data_test.py
```

The24 offline tests cover parent safety validation, exact boundaries, current
Compose image membership, Immich/PG18 paths, default-deny presence, group-budget
accounting, no committed Secret manifests, fresh/private credential behavior,
repository-state refusal, no implicit kubeconfig, expired leases, exact endpoint/TLS/node UID enforcement, symlink/ancestor
refusal, mutation reauthorization, frontend-only reserved ingress ports, and stale
or insufficient memory rejection. These are not live assertions. Static result and
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
