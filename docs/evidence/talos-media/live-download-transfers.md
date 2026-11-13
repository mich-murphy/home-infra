# Actual qBittorrent + SAB synthetic transfer and recovery

2026-11-11 approximately16:12–16:28UTC, parent-granted serial exclusive transfer receipts (`protocol_fixture=download-protocols`). Exact API64120/nodeUID4845bfd5-3bdb-453d-8503-83b43edb7a1e, private existing credentials/state unchanged. ConfiguredVM3072MiB. No other app groups, source/Docker/otherVM/host changes. **Lease RELEASED** after final all-application-pod list `[]`. Parent acceptance review remains separate from these bounded results.

## Actual results

| Client | Actual TCP/completion | Persistence/recovery |
|---|---|---|
| qBittorrent5.3.0 | BEP3 tracker1, handshake1, piece_requests2, piece_bytes32044; progress1/completed32044/amount_left0/state stalledUP; disk size/hash exact | FixtureOFF restart read-before-write PASS; stopped2PVC snapshot→different fresh2PVC restore→activate→existing torrent and output hash PASS; nondefault durable preference also retained |
| SABnzbd5.1.3 | NNTP auth1/body_requests1/payload_bytes32044; actual history Completed/no fail_message; disk size/hash exact | FixtureOFF restart read-before-write PASS; stopped2PVC snapshot→different fresh2PVC restore→activate→existing completed history and output hash PASS |

Both downloaded genuine mathematically generated WAV,32044bytes, SHA256 `3efcae84508fce7c87b5366774aa9cc25b54281a4b5f9301761c270c90b12562`. Fixture had NO client PVC. Unique destination absence/empty-directory check preceded submission; payload was mounted only by fixture. Client output was never copied/preseeded. No external peer/indexer/account/provider, no production-media migration or capacity claim. WAV transfer is not MP4 playback/import/transcode proof.

Sanitized companion JSON includes real zero-baseline/final counter snapshots, source content identity, successful attempt deltas, podUID/imageID/current+last failure status, cgroup current/peak/anon/file/events, archive hashes and distinct source/destination PVC UIDs. No credentials, original SAB misc config, raw logs or binary archives copied to Git. Earlier failed observations/archives remain private and previous committed evidence is unchanged.

## Exact live command families

Same private state `~/.local/state/home-infra/talos-proof/media`, config CA/kubeconfig, explicit talosconfig; new parent `leases/media-{qbittorrent,sabnzbd}-transfer.json`. Every activation refreshed `talos-proof-media-memory.py SERVICE --talosctl .../bin/talosctl`, taking fresh actual kubelet/Talos floor-MiB minimum through correct endpoint50120/node172.31.250.10. Main/fixture256+128+reserve192 gate unchanged. Observed minima included1181,1162,1150,1156,1136,1127 for qbit and1143,1075,1077,1065,1079,1120,1105 for SAB, all>=576 for transfer activation. No stale fallback/cache-pressure/limit change.

- `batch activate qbittorrent STATE` repaired HTTPRoute without resetting existing PVC refs; `functional qbittorrent` API/prefs exercise.
- `transfer start-fixture SERVICE --state STATE`; `transfer exercise SERVICE --state STATE --ca CA` (initial failures below); bounded same-client resume/recheck after observed compatibility fixes, without replacing output with source bytes.
- `transfer stop-fixture SERVICE`: captures both client/fixture resources, scales fixture0, waits actual pod deletion, removes temporary protocol ingress/egress policies.
- `batch restart SERVICE STATE`; `transfer verify SERVICE ...` with fixtureOFF.
- `recovery snapshot SERVICE --state STATE`; fresh memory; `recovery restore SERVICE --state STATE`; fresh memory; `batch activate SERVICE STATE`; `transfer verify SERVICE ...`.
- qBit additionally `functional ... --phase verify` reads prior preference and exact retained torrent identity before settings writes.
- SAB `transfer cleanup-settings` removed temporary fixture NNTP server and restored original download/complete directories AFTER final recovered-history/hash verification; outputs/history retained.
- `batch stop SERVICE STATE`, wait pods deleted; qbit namespace empty before SAB activation; final filtered all proof application/helper namespaces `[]`.

## All failures/repairs retained, not hidden by latest clean pod

1. Prior401 remains in first-live-batch evidence. Host-without-external-port route repair produced authenticated login **HTTP204 empty body** and preferences200; old fixture code expected legacy200 `Ok.` and falsely rejected. Updated exact-version-compatible204/empty acceptance; subsequent authenticated preferences and denied anonymous preferences are mandatory. Torrent submission likewise could be204/empty, so initial accepted upload was falsely labeled rejected. Both failed attempts are retained.
2. Initial qBit destination was exclusively empty but created by exec as root0755. Actual app UID1000 could not persist output: observed state error, then progress1/stalledUP with **no disk file**. Neither was accepted. Repaired ONLY fresh destination owner1000/group1000/mode0750, restarted fixture into a fresh process, forced real torrent recheck/redownload, then required physical output hash. Successful recheck used its own captured ZERO counters and positive deltas; no reconstructed/assumed baseline was used for PASS. Earlier first-process bytes/counters do not substitute for final disk evidence. Runner now initializes fresh directories with explicit ownership and rejects error/missingFiles/unknown even if progress1.
3. SAB initial trusted Gateway requests403 because proof hostname absent from strict allowlist. Configured ONLY sabnzbd.proof.invalid and pipeline-sabnzbd.proof.invalid using authenticated localhost API inside selected SAB pod. No host validation bypass, password rotation or world allowance. Seed updated for future fresh-only initializations; existing key unchanged.
4. SAB basic settings test wrongly expected set_config `{status:true}`;5.1 returns config resource. Fixed to require actual readback and restore instead. Empty servers returns config{} rather than servers[]; normalized absence only, not ignored errors.
5. First SAB NNTP attempt timed out with queue still Downloading, zero successful auth/body and thousands of refusals. Public exact5.1.3 newswrapper.py sends lowercase `authinfo user/pass`; fixture incorrectly case-sensitive for AUTHINFO subcommand. Corrected case-insensitive protocol subcommand (credential remains exact); actual socket regression uses lowercase. Paused SAB queue, stopped/deleted old fixture, refreshed admission, started fresh zero-counter fixture, then resumed SAME queued NZB. No fabricated successful history or reset of failure evidence.
6. SAB then genuinely Completed and transferred32044bytes, but strict filename assumption failed: actual client normalized name to `synthetic-proof.1.1.wav`. Accepted ONLY this exact observed normalized synthetic basename in addition to original. Actual file size/hash are still mandatory; arbitrary paths/names remain rejected. Existing output was NOT renamed/copied to make test pass.
7. Manual qBit intended-Origin (external18443) and hostile-Origin probes returned401. Scoped constant X-Forwarded-Host route header was added; corrected API setting name is web_ui_reverse_proxy_enabled (first guessed support_enabled name was absent/ineffective). Intended-Origin-only probe still401 after enabling correct setting. **This does NOT establish a broken native browser:** exact5.3 Sec-Fetch-Site:same-origin browser branch differs. Actual private CDP/native browser login and hostile-origin comparison remain OPEN; no time/cap-safe browser activation was attempted. No Origin rewrite/stripping, CSRF disable, host validation disable, broad proxy trust, or global trust/proxy change. CLI no-Origin authentication success is labeled only that scope.

No OOM/restart failure was observed in captured container lifetimes; earlier semantic/API/protocol failures above remain failures regardless of restartCount0. Cgroup peaks/events are in JSON rather than inferred from latest status. Default manifests remain replicas0/helpers suspended. All retained client Deployment claims now reference recovered freshPVCs: use activate, not start, for resumed work. Original PVCs/archives preserved.

## Remaining acceptance gaps

Actual native-browser qbit auth/CSRF; real MP4 transfer followed by arr import/hardlink/shared recovery; further media/helper groups under separately granted budgets. These successful local BEP3/NNTP+WAV restores do not imply real provider-account integration, external-download fidelity, all-service simultaneous capacity or full media acceptance.
