# Talos isolated proof delivery

## Checkout and scope
- Worktree `/Users/mm/dev/home-infra-talos-proof`, branch `feat/talos-live-proof`, base `8de8c051` (origin/main); registered with `gh stack`.
- Draft PR https://github.com/mich-murphy/home-infra/pull/2005 pushed with `gh stack submit --auto`. Initial Talos CI43020494235 SUCCESS on pushed `5d9a9926`; watched with `gh run watch --interval 60 --exit-status`. Newer dirty work invalidates that evidence where changed.
- Original `/Users/mm/dev/home-infra` has extensive pre-existing user edits: never modify/stage/reset. Historical `origin/feature/talos-kubernetes` is reference ONLY: its cutover stops Docker/moves GPU/changes networking, prohibited.
- Deliver resource-safe live Talos proof, declarative replicas of all current services, functional/isolation/recovery evidence and honest migration readiness matrix.
- Absolute exclusions: no changes/restarts/stops to Docker services or existing guests, no production storage writes, no production DNS/router changes, no GPU reassignment. Read-only discovery allowed; mutate dedicated proof resources only.
- Fresh proof data/credentials only. Secrets stay outside git mode0700/0600, never stdout. No production integrations/downloads/notifications.

## Capability and ownership
Parent owns brief, integration, root app Kustomization, CI/static gates, runbook, final acceptance. Model verified `openai/gpt-6.1-sol` for workers. Background progress/steering supported. Max3 active; receipts ≠ startup. Resume `max_turns=200` appears NOT to override original30turn limit (node interrupted twice); reconcile actual statuses and resume bounded checkpoints, no duplicate writers.

| Worker | Owned paths | Reconciled status |
|---|---|---|
| `d03adc99-6042-4c0` | `talos/`, `infrastructure/proxmox-proof/`, platform doc/evidence | STOPPED/ABORTED30turn cap after workingAPI and hostnamepatch. Parent explicitly TAKES OWNERSHIP of these paths/livehostintegration now; do not resume worker without reassignment. Checkpoint70d7214d plus dirty working1.36.5/bootstrap/evidence. |
| `b3689397-1069-4a2` | inventory doc/evidence | COMPLETE/STOPPED9520a571; parent read all;36 containers, no-touch discovery comparison clean. |
| `6befdde0-8478-4ba` | `kubernetes/platform/`, `kubernetes/bootstrap/`, architecture doc, network-storage evidence | ACTIVE live install on verifiedstabletalos-proof node; exclusive PLATFORM lease. Parent remaps QEMU NodePorts when known. |
| `3a63b030-2464-411` | `kubernetes/apps/media/`, `scripts/talos-proof-media*`, `tests/talos-proof-media*`, media doc/evidence | Offline82cefb65/7ad72bf8; resumed/queued200 for safety corrections + remaining proofs. NO live lease. 16 services,13 frontends. |
| `aded9180-673d-409` | `kubernetes/apps/data/`, `scripts/talos-proof-data*`, `tests/talos-proof-data*`, data doc/evidence | STOPPED/WAITING livelease after0c17e2b3/0b5c034f.26 offlinepasses; exactendpoint/nodeUID guard, frontendCNP, cleanPVCrestore and browservirtualauth implemented. ResumeCouchDB firstafterplatform. |
| `2f71adc3-4f23-46d` (replaces expired575577df) | `kubernetes/operations/`, operations scripts/tests/doc/evidence | Fresh worker explicitREASSIGNMENT after old575577df completed5d9a9926/sessionexpired. Offline exacttarget/UID/leasehardening and recoverytests; NO live lease. |

Reviewer `0bd982bd-f35e-44e` review COMPLETE: P1guardfailopen, P1platformtargetnotproofbound, P2mountfallback/isolationattribution/lifecycle/docs. Parentacceptedfindings. ExplicitREASSIGNMENT: sameworker now IMPLEMENTER owns `infrastructure/proxmox-proof/`, `tests/talos-proof-host_test.py`, `docs/talos-proof-host-lifecycle.md`, `docs/evidence/talos-platform/host-lifecycle*`. Localimplementation allowed; NO outage/liveguardreplacement untilparent grants checkpoint. Parent retains `talos/`, mainplatformdoc and otherplatformevidence; no infraedits whileworkeractive.

Shared worktree, explicit-path commits only. No editing active worker files. Live application batches require one coordinator-granted resource lease; workers can perform independent offline work. Parent decides acceptance.

## Decisions and measured constraints
- Proxmox31,834MiB; existing101 TrueNAS/102 Docker each10GiB;111 stopped. Initial available5,024MiB, then4.5GiB before proof.36 Docker containers use3,609.792MiB (3.525GiB) idle excluding cache/peaks: full concurrent replication cannot fit on2.5–3GiB node. Staged proofs ≠ full concurrent readiness.
- VM120: initial2560MiB fixed,2vCPU,32GiBOS+64GiBdata, noGPU, QEMU slirp172.31.250.10/24. No global ip_forward/bridge/router/DNS changes. Host loopback forwards50120→50000,64120→6443,18080→30080,18443→30443 via SSH. Scoped QEMU cgroup OUTPUT firewall blocks private/CGNAT/linklocal/IPv6; fail-closed starts must be verified. Slirp is NOT native production networking parity.
- Talos1.14.5, K8s1.36.5 (working A/B correction), Cilium1.20.4, GatewayAPI1.6.1 verified compatibility. Official factory installer required (old ghcr.io installer returned404). Dedicated `/dev/sdb1` XFS `/var/mnt/proof` verified live. Local-path0.0.37 proof-local Retain/WFFC. Mayastor requires2dedicatedCPU+1GiBordinary+2GiBhugepages beforeK8s, and one node cannot provide replicas: rejected with upstream evidence.
- Namespace `proof-<service/trust-group>`, part-of=talos-proof for apps, proof-validation probes, proof-gateway ingress, storage/controller infrastructure distinct label. Default deny; only DNS/exact dependencies; app egress hard-denies world/host/API. All app replicas0/CronJobs suspended until explicit resource lease. No production NFS.
- Synthetic `*.proof.invalid` Gateway TLS, no realDNS/ACME. CiliumGatewayClassConfig has nofixedNodePort. Parent mapped QEMU live+persisted ONLYVM120args HTTP18080→30659,HTTPS18443→30310 usingQMP, no reboot. Dynamicremapping neededifGatewayrecreated; no svcportforward equivalence. PublicCA `~/.local/state/home-infra/talos-proof/config/proof-gateway-ca.crt`.
- ParentappliedTalos KubeNodeConfigtaint `$patch: delete` no-reboot (null didnotremovegeneratedNoSchedule). NodeReady,Cilium+CoreDNS+localpathRunning0restarts verified. Guestavailable813MiB/2384total,hostavailable2476MiB,swap24KiB PSI0. Optional3072MiB proof-onlyRAMincreaseapproved ONLYduringfuturecoldstartlease iff freshadmission supports RAM+1536MiB+overhead; nohostARCchanges/otherguestchanges.

## Live access / working API (12:40 UTC)
- Private state `$HOME/.local/state/home-infra/talos-proof`; KUBECONFIG=`.../config/kubeconfig`, expected API `https://127.0.0.1:64120`; inspect context name from file, never dump credentials.
- Talos binary `.../bin/talosctl`; TALOSCONFIG=`.../config/talosconfig`; endpoint127.0.0.1:50120, node172.31.250.10. SSH control socket `.../ssh-control`.
- Parent independently verified API `/readyz`=ok, K8s1.36.5, node name+hostname `talos-proof`, UID `4845bfd5-3bdb-453d-8503-83b43edb7a1e`. Parent deleted ONLY stale empty formerproofnode `talos-ate-q71` UID1ecc0e0d-ee19-4d16-8c3f-4f002b5bce27 afterhostnamechange, noPVs/apps. Single newnode nowNotReady preCNI.
- APIsegfault experiment:1.36.6 exited139/emptylogs/noOOM. CPUhost→x86-64-v2-AES alone failed. APIimage1.36.5 plus explicitkubeletrestart worked; allcomponents aligned1.36.5. Bothversionbinaries --version passed, so rootcause NOT fullyproved. Retainworking1.36.5; sourceupdated. HostisolationpublicHTTPS200+privateattemptfail evidence saved, reviewercheckingcounterstrength.
- Resource guard twice stopped ONLY proof VM on overly sensitive decaying PSIavg10>.1%, despite2.7–3.2GiB host available, unchanged24KiB pre-existing zram/no swapIO. Parent correction: actual PSI total deltas and sustained meaningful rates (full>=1%/some>=5%30s), hard available>=1536MiB and swapgrowth<=64MiB retained. Current host guard sample available3.6GiB,deltaPSI0,swap24KiB; VMrunning. Boot/API must stabilize before apps. No RAM bump until full-resident measured margin.

## Corrections and verification
- Platform storage namespace mistakenly selected app egressDeny API → corrected c6e2ef7b to distinct infra label + narrow API/DNS policy. Global allport ingress grants removed; perapp/frontend policies responsible. Parent observed diff, live uptake NOT YET.
- All20 app frontend HTTPRoutes added to proof Gateway; media exact-port Cilium ingress identity policies committed; data adding same after removal global grant. Parent schema/safety gate passes current render.
- Data lifecycle binds onlycontext (not endpoint/nodeUID), and private symlinkcheck afterresolve ineffective → sent to data owner; observed edits, final recheck pending.
- Media batch anynonempty envlease + arbitraryKUBECONFIG inadequate → sent resumed owner, require exactendpoint/node identity, privatefile safety and crossgroup exclusivity; uptake pending.
- Parent strict schema gate uses SHA256-locked official Cilium/GatewayCRDs, NO ignore-missing schemas. Latest intermediate render182media+112data+17platform all valid; shellcheck passed after targeted remote-shell SC2016 annotation. Added app/ops offline suites to gate, rerun pending. CI initial source passed; modified tests require fresh checks.
- Ops offline5tests include real loopback HTTPsink, recoverymanifest render and twoFluxcontrollers/23objects/noClusterRoleBindings. No actual cluster observability/recovery/reconcile yet. Public pushed fixture SHA5d9a9926 available for later Flux proof.

## Acceptance / next action
**NOT ACCEPTED**. No apps deployed yet; no migration-ready claim. Resume platform owner only after APIready/noderegistered. Platform exclusive live tests first: CNI, policy drops, storage and real NodePort trustedTLS. Then serial data groups, media groups, operations/recovery. Each worker must provide sanitized exact commands/identities/functional results, not just readiness. Parent independently verifies live source-state and reruns invalidated gates.

Remaining mandatory gates include per-service functionality, meaningful integrations/helpers, restart+cleanPVC restore, off-node backup and etcd recovery, resource peaks/soak, no-touch final source comparison, no production-network reachability, secure origins/passkey/OIDC and Collabora/ML workflows. Synthetic tests do not prove production data migration or GPU parity. Full concurrency/native production network/HA remain explicitly separate blocked/unproven gates.
