# Talos isolated proof delivery — coordinator brief

## Scope and checkout
- Dedicated worktree `/Users/mm/dev/home-infra-talos-proof`, branch `feat/talos-live-proof`, base `8de8c051` (`origin/main`), managed with `gh stack`.
- Draft PR **https://github.com/mich-murphy/home-infra/pull/2005**. Push with `gh stack submit --auto`; CI watch uses `gh run watch <id> --interval 60 --exit-status`, one watcher per session.
- Original `/Users/mm/dev/home-infra` has extensive pre-existing changes: never modify/stage/reset it. Historical `origin/feature/talos-kubernetes` is reference only; its Docker/GPU/network cutover is forbidden.
- Deliver maintainable declarative replicas and resource-safe, staged live functional/isolation/recovery evidence. **No migration approval or full-concurrency claim.**
- Never change/restart/stop Docker-host services or existing guests; no production storage, DNS/router changes, host ARC/sysctl tuning, GPU reassignment or production integrations. Read-only discovery permitted; mutate dedicated proof resources only.
- Fresh synthetic data/credentials; private material outside Git, directories0700/files0600, never stdout.
- Explicit new-VM membership safeguard: existing02:30 `backup-truenas-daily` all-guests job would include120 and write proof data to production NAS. Parent changed ONLY its exclusion list9001,9003→9001,9003,120; compared complete before/after objects, all other fields/existing-guest membership unchanged. No backup triggered. Receipt `docs/evidence/talos-acceptance/proof-backup-exclusion.json`; this limited existing-job configuration exception is disclosed, not hidden as 'no Proxmox changes'.

## Ownership and current leases (updated after 14:35 UTC)
Parent owns this brief, integration, root app Kustomization, CI/static gates, `talos/`, main platform/operator docs and final acceptance. Shared worktree: explicit-path commits only; do not edit active worker files.

Workers use `openai/gpt-6.1-sol`. Resumes requesting200turns still encounter a hard30turn/five-turn-warning cutoff: inspect actual state, preserve safe checkpoint, resume explicitly. Maximum3 active workers is the coordination target; stopped workers retain file ownership until reassigned.

| Worker | Ownership | Current state |
|---|---|---|
| `b3689397-1069-4a2` | inventory docs/evidence | COMPLETE9520a571;36 source containers; discovery IDs/starttimes/restarts/health unchanged. |
| `d03adc99-6042-4c0` | former node implementation | ABORTED/STOPPED; ownership reassigned. Do not resume without new scope. |
| `6befdde0-8478-4ba` | former platform/bootstrap owner | COMPLETEa0e27380; live storage/policy/Gateway proof; fixtures0; lease released; session expired. Bootstrap ownership explicitly reassigned below. |
| `72a968e4-2b56-467` | `kubernetes/bootstrap/`, related architecture/target-override evidence | COMPLETE4e2fd1a2: confirmed/fixed short/combined kubectl server flags, Helm/environment/proxy/preferences overrides;11 offline tests. Parent reviewed parser and ran full gate; no live mutation. |
| `0bd982bd-f35e-44e` | `infrastructure/proxmox-proof/`, `tests/talos-proof-host_test.py`, host-lifecycle doc/evidence | COMPLETE61a2fb1a+82e20ee0; actual crash/watchdog fail-closed proof passed; exclusive host outage lease RELEASED. No more host mutation planned. |
| `aded9180-673d-409` | former data owner | COMPLETE/STOPPED3b070339; four groups passed bounded live workflows/restores, all pods deleted, lease released. Ownership explicitly reassigned below. |
| `2fab86f6-2fc2-4ab` | `kubernetes/apps/data/`, data scripts/tests/doc/evidence | ACTIVE OFFLINE.560a5e11 adds explicit selected-controller stages, Nextcloud/cron and Immich/ML procedures;37 tests. Preparing actual WOPI and integrated ML/search, no live lease. |
| `3a63b030-2464-411` | former media owner | COMPLETE/STOPPEDfac87a05; no live tests. Ownership explicitly reassigned below, excluding reserved protocol paths. |
| `9a411d61-32dc-4b3` | media manifests/scripts/tests/docs/evidence, except reserved protocol paths | ACTIVE **EXCLUSIVE LIVE Pinchflat → Audiobookshelf → qBittorrent**.015a809c adds observations/durable qbit checks. Pinchflat profile/restart/fresh-PVC proof passed; cleanup/helper-wait correction underway; ABS/qbit pending. |
| `78bc6cb3-78bb-492` | ONLY new `media/fixtures/download-protocols/`, `scripts/talos-proof-media-protocol*.py`, `tests/talos-proof-media-protocol*`, protocol evidence | ACTIVE OFFLINE synthetic BEP3 tracker/seed and NNTP/yEnc/NZB fixture implementation; main media owner integrates later. No live lease. |
| `2f71adc3-4f23-46d` | former operations owner | COMPLETE/STOPPED2336d137; reassigned below. |
| `e5f5b3c8-110f-455` | `kubernetes/operations/`, operations scripts/tests/doc/evidence | COMPLETEacca13fc: live monitor/alerts/offnode file recovery/snapshot; Flux safely refused by unchanged gate. Zero ops/app pods; receipts archived/released14:17UTC. |

**Live resource owner is media9a411 only.** Receipts `$STATE/leases/media-{pinchflat,audiobookshelf,qbittorrent}.json` expire90minutes after~14:30UTC. Context `admin@talos-proof`, endpoint/UID below. Worker may refresh ONLY memory observation fields from **min(fresh kubelet availableBytes, fresh Talos MemAvailable)**, not expiry/group/identity. Initial conservative685MiB; isolated limits256+192, ABS seed additionally64; restore helper must be gone before app activation. No other groups/helpers/pipeline participants authorized by this lease.

Parent's later proof-only RAM window completed successfully in ONE start; lease released after API/node/guard/CA/nonce and existing-guest checks. All prior data receipts revoked. Operations receipts archived under `operations{,-flux}.released-20261111T141718Z.json`, active paths absent. A receipt is coordination, not a defense against a malicious administrator.

## Live platform and access
- Private `$STATE=$HOME/.local/state/home-infra/talos-proof`.
- `KUBECONFIG=$STATE/config/kubeconfig`; API **https://127.0.0.1:64120**.
- `TALOSCONFIG=$STATE/config/talosconfig`; matching binary `$STATE/bin/talosctl`1.14.5; endpoint127.0.0.1:50120, node172.31.250.10; SSH control socket `$STATE/ssh-control`.
- Sole node **talos-proof**, hostname same, UID **4845bfd5-3bdb-453d-8503-83b43edb7a1e**, Ready. Kubernetes1.36.5, Cilium1.20.4, GatewayAPI1.6.1, local-path0.0.37.
- VM120, UUID **555e8603-58e6-4fb6-a190-378a3f11c257**, **3072MiB now** (initial2560),2vCPU,x86-64-v2-AES,32GiB OS+64GiB data; noGPU/bridged NIC; QEMU slirp172.31.250.10/24.
- Dedicated XFS `/dev/sdb1` mounted `/var/mnt/proof`; `proof-local` Retain/WaitForFirstConsumer, cleanup disabled. Mayastor rejected on measured capacity/upstream engine minimums and lack of single-node replicated durability.
- Gateway namespace/name `proof-gateway/proof`; synthetic `*.proof.invalid`, public CA `$STATE/config/proof-gateway-ca.crt`.
- Current actual forwards: localhost18080→node30659, localhost18443→node30310,50120→50000,64120→6443. New Gateway may allocate new NodePorts; GatewayClassConfig cannot pin them. Only VM120 arguments changed.
- Supervised `talos-proof-guard.service` ACTIVE; start through guarded service/wrapper only, not `qm start`/`qm resume`. Enrollment bound to UUID/config and exact PID/starttime/boot incarnation; paused boot→isolation→READY→resume; pidfd cleanup. `onboot=0`.

## Measured capacity and experiments
- Host31834MiB; existing VM101 TrueNAS and VM102 Docker each10GiB, VM111 stopped.36 source Docker containers use3609.792MiB idle excluding cache/peaks: full concurrent replication cannot fit this proof VM.
- Initial fresh post-stop4546MiB failed3072+1536+384=4992MiB admission. Later independent host availability rose; after all apps stopped, parent re-tested: **fresh5168MiB passed4992**, changed ONLY VM120 to3072, re-enrolled exact config while preserving24KiB original swap baseline, and supervised one cold start. VM101/102 PID/startticks/config hashes unchanged. No permission for3.5–4GiB or changing existing guests/host tuning. Evidence `docs/evidence/talos-acceptance/ram-admission-3072.json`.
- After final restart, guest available1082–1083MiB (earlier warm platform~814MiB). CouchDB working set~91MiB; post-test guest~928MiB; subsequent idle989MiB. Re-measure; do not reuse optimistic old measurements.
- Historical host lifecycle snapshot available2171MiB; parent later2457MiB. After3072 boot host2438MiB, swap24KiB and IO9pages unchanged. Guest actual total2823MiB; Talos available1403–1420 but kubelet available642–706MiB because working-set accounting includes large active file cache (RSS~889MiB, workingSet~2135MiB). **These metrics are not interchangeable.** Flux896MiB gate refused; new app receipts use the conservative minimum. No cache-drop/pressure tricks or threshold reduction; ordinary workload evolution may warrant a fresh observation.
- Guard uses actual PSI-total deltas: full>=1% or some>=5% sustained30s, hard available1536MiB, swap growth64MiB and sustained swap-I/O protection. Earlier decaying avg10 false stops were corrected, not hidden.
- K8s1.36.6 API exited139/empty logs/no OOM; CPU change alone did not fix it.1.36.5 plus kubelet restart worked; both binaries ran `--version`; root cause not conclusively upstream. Official factory installer required; obsolete ghcr.io installer404.
- Talos1.14 hostname uses `HostnameConfig auto: off`; control-plane taint removal requires `$patch: delete`, not null. Stale empty former proof node alone was removed before storage/apps existed.

## Evidence and acceptance checkpoints
### Platform — bounded acceptance
- a0e27380: actual NodePort HTTP200 and trusted TLS200, nonce matches persisted file; wrong hosts404, wrong CA and outside SNI fail; PVC replacement UID/readback; correlated Cilium BPF policy-drop verdicts against known-running fixtures.
- Storage helper verifies dedicated XFS mount/device, rejecting OS-disk fallback. Platform target guard pins endpoint/TLS/context/node UID/name/IP. Follow-up4e2fd1a2 confirmed/fixed short/combined `-s` and Helm environment/proxy/TLS/preferences overrides;11 tests including mock mutator no-execution. Parent reviewed actual parser and successfully used guarded read-only API/node checks after RAM change. Existing datapath proof did not use override flags and remains applicable. App infrastructure labels avoid hard-deny API trap; per-frontend policies replace blanket grants.
- 82e20ee0: actual guard SIGKILL→proof QEMU stopped; SIGSTOP→15s watchdog→proof QEMU stopped; supervised recovery, fresh cgroup counter growth;5of6 approved cold attempts. Source101/102 PIDs/starttimes/config hashes unchanged. Supervisor deployed hashes match source.
- Parent independent node/guard checks and exact pre-fault nonce readback after all stops: `docs/evidence/talos-acceptance/platform-after-faults.md`.
- NOT proven: host reboot, every startup failure, comprehensive host DNS/IPv6 bypass testing, disk loss or Talos control-plane disaster recovery. Timeout-only historical host isolation evidence remains weak and is not promoted to verdict proof.

### Applications
- CouchDB778d1360: trusted Gateway401 auth denial, document create/read, pod replacement persistence, distinct clean PVC/PV logical restore and canonical SHA256 match, restored data survives another replacement. Source claim reattached; all pods deleted. `docs/evidence/talos-data/couchdb-live-*.json`.
- Parent reviewed result and test source: this does **not** yet prove revision-update/conflict/delete-document/CORS/replication workflows. Do not call it complete production migration or universal CRUD proof.
- Miniflux and Pocket-ID **worker live PASS404a716d**, including distinct clean-PVC restore. Miniflux proves authenticated feed/read state/content hash; initial schedulerfactor0 caused5 restarts, fixed1, and one DB-pool401 after DB restart recovered within1s (not a global authentication retry). Pocket-ID proves actual Chrome WebAuthn registration/fresh-cookie login, OIDC PKCE/JWKS signature/claims/userinfo/unknown-client rejection, same user/passkey after pod replacement and clean-PVC import. Browser uses exact independently CA-verified leaf-SPKI pin; no physical authenticator/attestation claim. Parent reviewed evidence and found audience-substring validation bug; owner correcting to exact string or array membership, plus negative test.
- Wallabag **bounded HTTP/recovery PASS3b070339**: OAuth login, live fixture URL extraction, read/update/archive/star, exact-content export, MariaDB replacement, distinct fresh-PVC restore/existing-user login/state/hash, delete→404. Only exact fixture FQDN receives SHA-pinned Graby SSRF adapter exception; no Internet/subnet opening.192MiB app/64MiB fixture latest cgroup peaks nearly filled limits, no latest OOM/max events; earlier replaced peaks unknown. NOT production capacity/20–25% headroom; Redis async integration pending. All pods deleted. Parent independently matched all four data archive hashes/private0600 modes and source/restore live PVC UIDs: `data-archive-identity-check.json`.
- Nextcloud1728MiB and Immich1600MiB group limits likely exceed capacity; do not bypass192MiB reserve. Authorized explicit component stages may establish narrower evidence with full integration marked BLOCKED. Collabora privilege-escalation exception is documented, not global privileged containers.
- Public pinned Immich CPU ONNX artifacts downloaded/hashed on workstation, not yet preloaded/inferred; no app Internet access granted.
- Media16 services/13 frontends: digest pins, exact guards/TLS, separate shared `/data` integration profile, local-unclaimed Plex adapter (NOT cloud auth), private stopped-volume recovery. Pinchflat live profileCRUD/restart/distinct-volume persistence passed but provider download unproved. Initial stale Talos measurement fallback disclosed; actual conservative kubelet706 was fresh. Helper briefly overlapped restored app: actual706 covered full576 budget, but checked448 was unsound; owner fixing deletion wait with negative regression. Remaining imports, helpers, exact frontends and real transfers mandatory. Protocol worker builds no-forwarding synthetic provider fixtures, not external account parity.
- Operations **acca13fc bounded PASS**: actual monitor/loopback synthetic and threshold alerts, offnode tar→distinct cleanPVC after source pod deletion/checksum match; private etcd snapshot12,443,680bytes captured (NO restore). **Flux BLOCKED beforeapply:** kubelet642.2<896; no controllers/CRDs/fixtures installed, no gate weakened. Drift/rollback/RBAC untested.15 offline tests; clean resource release. Immutable public fixture SHA `5d9a9926106f76346950af20e8afc0ef346ac548` remains available.

### Static/CI
- Strict schema gate downloads SHA256-locked exact Cilium/Gateway CRDs; **no missing-schema skips**. Apps defaults0, CronJobs suspended; namespaces/default-deny/probes/resources/security/digests/no host/NFS/no committed Secrets checked.
- Latest provisional parent full gate passed123 tests and412 rendered resources (including separate media integration), zero invalid/error/skipped, at4e2fd1a2 plus then-dirty app/parent changes. Subsequent560a5e11/data,015a809c/media and ongoing changes require fresh relevant validation/CI; this is not a source-stable final gate.
- Latest watched Talos PR CI **43026321616 SUCCESS** on `22b938b4675c81ad41aa6966351905ee0999c405`: static gate, fresh strict Talos generation, workflow lint. https://github.com/mich-murphy/home-infra/actions/runs/43026321616
- Newer worker commits/dirty work invalidate applicable CI. Finish with full gate, fresh push/watch, final no-touch source comparison.

## Next actions / unresolved acceptance
1. Continue active media first batch; inspect progress/cutoff and require helper-deletion guard fix. Grant further groups only after explicit release with fresh conservative metrics.
2. Integrate protocol fixture interface with media owner; prepare real download/import/helper stages. Data owner continues offline WOPI/Immich integration. Heavy data and Flux currently capacity-blocked by conservative metric; re-observe after ordinary work, never manipulate cache/lower gates to force a pass. Pocket-ID strict audience fix is unit-tested; future short lease should add replay/wrong-PKCE negatives and verify persisted passkey across latest VM cold start.
3. Resolve/test bounded heavy-component profiles honestly; document any capacity or external-account boundary as BLOCKED, not PASS.
4. Independently review results/identities/checksums and source no-touch comparison; update user-facing readiness matrix and docs; push/watch fresh CI.

**Overall NOT migration-ready.** Mandatory remaining gates include per-service real workflows, meaningful media/helper integration, app-specific clean-PVC restores, off-node recovery and etcd recovery, representative resource peaks/soak, final source comparison, network negative coverage, passkey/OIDC, Collabora editing, and actual ML inference. Full concurrency, native production networking, historical-data migration, GPU parity and HA remain separate blocked/unproven claims.
