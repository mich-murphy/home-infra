# Transferred media ownership — next separate stage gates (OFFLINE ONLY)

Historical preflight checklist. The subsequent separately granted window is now
released; see [actual native workflow chronology](native-workflows-20261111.md).
All three receipts are revoked again. Jellyfin anonymous-media exposure, Plex
browser401 and Pinchflat OOM block the prepared workflows below. Do not rerun
fresh Jellyfin setup over retained partial state or activate without a NEW grant.

The successor owns existing media manifests/scripts/tests/runbook/evidence, but
NOT the five arr/recovery paths reserved to ACTIVE9775baeb. Parent owns root
integration, readiness/brief and acceptance. Data owns the current exclusive live
window. All old media receipts remain revoked. This checklist is preparation,
not authorization, a new receipt, or evidence of app compatibility.

Reviewed runbook and live-browser/player, Plex/qBit/Jellyfin source-followup and
Pinchflat-provider evidence, plus current player/provider scripts and focused
regressions. No cluster, host, production, credential or archive operations ran.
36 focused offline methods passed: Jellyfin7, Plex discovery3, playback3,
browser7, provider6, safety10. Node player syntax and `git diff --check` passed.
Provider tests render Kustomize locally; they do not contact the cluster.

## Shared prerequisites for EACH separately granted stage

- [ ] Data explicitly released; parent issues exact current identity/context,
  group, expiry and stage scope. No old receipt reuse or self-authorization.
- [ ] Parent supplies existing private STATE, CA, KUBECONFIG, TALOSCONFIG,
  TALOS_PROOF_MEDIA_LEASE, installed Playwright MODULE and ROOT/bin/talosctl.
  No bootstrap, credential rotation, old fixture overwrite or archive mutation.
- [ ] Collect fresh successful independent kubelet and Talos available-memory
  readings with the existing memory collector. Admit their MINIMUM only;
  no stale fallback, cache tricks, changed VM size or reduced resource ceiling.
- [ ] Prior apps/helpers actually deleted. Preserve all failed pod UIDs,
  current/previous termination/restart status, images, cgroups and private logs
  before deletion. Never replace failure chronology with a clean latest pod.
- [ ] Verified HTTPS Gateway path; browser HTTP AND WebSocket guards before
  navigation; independent CA/hostname validation and exact leaf SPKI only.
- [ ] Stop/revoke/release after stage; ask parent before expanding scope.

## 1. Jellyfin FIRST — no Plex prerequisite

Exact prepared setup/exercise/resume and restart/two-PVC recovery commands:
[standalone Jellyfin sequence](plex-qbit-jellyfin-source-followup.md#prepared-serial-standalone-jellyfin-sequence--not-executed).
Use standalone `group=jellyfin`,704MiB activation (512+192reserve),768MiB
when the64MiB seeder is charged. Start only if initialization is needed; stop
before seeding; subsequent activation preserves existing claim references.
Do NOT run the older WAV/music functional workflow before the fresh video setup.

The live-only entry sequence, after that grant:

```sh
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh start jellyfin "$STATE"
bash scripts/talos-proof-media-batch.sh stop jellyfin "$STATE"
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-fixture.py --state-dir "$STATE" --browser-video --seed jellyfin
python3 scripts/talos-proof-media-memory.py jellyfin --talosctl "$ROOT/bin/talosctl"
bash scripts/talos-proof-media-batch.sh activate jellyfin "$STATE"
python3 scripts/talos-proof-media-jellyfin.py setup --state "$STATE" --ca "$CA" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
```

- [ ] Real native12.4 compatibility, fresh scan and exact stream/range.
- [ ] Read actual `media_path` from private jellyfin-browser-prepared.json;
  pass it verbatim to `browser.py jellyfin --jellyfin-lifecycle` with state,
  CA, MODULE and the exact retained12sec fixture. No guessed GUID.
- [ ] Actual advancing frames concurrently with native start/progress/stop;
  saved noncompleted resume and a second decoded run consuming that resume.
- [ ] Authenticated outsider listing/metadata/PlaybackInfo/actual-byte denial,
  including owner-ID spoof attempt;401 is not an authenticated ACL PASS.
- [ ] Latest PASSED browser functional basename only for read-before-write
  restart and distinct-fresh-PVC recovery verification. No candidate-file PASS.
- [ ] Explicit UUID snapshot `--manifest`; every claim gets a different UID;
  activate, NOT start, after restoration; preserve original PVCs and archives.

## 2. Plex — narrow discovery BEFORE any library-write grant

Use separately granted `group=media-plex-tautulli`,896MiB full group+reserve
(Plex384+adapter64+Tautulli256+reserve192). Existing retained seeded fixture is
not permission to reseed; if seeding is separately required, charge64 extra.

`dependencies.py start` deliberately does not reapply existing Deployments.
The stopped adapter-only gap was subsequently implemented and explicitly approved:
`plex-discover.py --prepare-adapter --group media-plex-tautulli --state STATE --ca CA`.
It tests the entire old spec atomically and compares the entire result, allowing
only the code ConfigMap reference change. Live native agent discovery then
advertised `xn`; creation/API scan passed. Browser playback still failed401 with
actual Origin/Referer, so there is no decoded-playback/Tautulli acceptance.
Do not bypass this by header stripping, unguarded kubectl or ordinary base reapply.

Historical commands (new grant required for any future execution):

```sh
python3 scripts/talos-proof-media-memory.py media-plex-tautulli --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-dependencies.py start --group media-plex-tautulli \
  --service plex --state "$STATE"
python3 scripts/talos-proof-media-plex-discover.py --group media-plex-tautulli \
  --state "$STATE" --ca "$CA"
# STOP HERE for native response/contract review. DISCOVERY_ONLY is NOT PASS.
```

- [ ] Discovery responses all successful; inspect retained native XML privately.
  Current helper records per-request errors but does not make its process exit
  status a functional gate. Review actual agent/scanner/language contract.
- [ ] Native personal agent must advertise `xn`; otherwise STOP, no en/en-US/xn
  guessing, provider substitution or endpoint/type/location trial-and-error.
- [ ] Parent explicitly approves exact library creation before running:

```sh
python3 tests/talos-proof-media-functional.py plex --group media-plex-tautulli \
  --base https://plex.proof.invalid:18443 --ca "$CA" --state-dir "$STATE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4"
python3 scripts/talos-proof-media-memory.py media-plex-tautulli --talosctl "$ROOT/bin/talosctl"
python3 scripts/talos-proof-media-dependencies.py start --group media-plex-tautulli \
  --service tautulli --state "$STATE"
python3 scripts/talos-proof-media-browser.py plex --group media-plex-tautulli --tautulli \
  --state "$STATE" --ca "$CA" --module "$MODULE" \
  --fixture "$STATE/Proof Browser Fixture (2000).mp4" \
  --media-path '/library/parts/ACTUAL_PART_ID/ACTUAL_TIMESTAMP/file.mp4'
```

- [ ] Replace the media-path placeholder ONLY from actual scanned Media/Part key.
- [ ] Tautulli actual configuration/readback: zero tiny-clip ignore threshold,
  same native Plex machine, no prior item history. No sequential simulation.
- [ ] Genuine concurrent decoded frames/native timeline/same-client activity,
  explicit stop and unique durable positive-duration history. Preserve timing
  failures; no invented playback or lowered gate. Capture both apps, then stop:
  `dependencies.py stop --group media-plex-tautulli --state "$STATE"`.

## 3. Pinchflat native RSS provider — independent later grant if ready

Exact prepare/activate/exercise/replacement/two-PVC recovery sequence:
[provider procedure](pinchflat-provider-integration.md#prepared-future-sequence--not-a-grant).
Requires standalone `group=pinchflat`, exact `provider_fixture=pinchflat-rss`,
576MiB full budget (256+128+192). No requirement that Plex pass first.

- [ ] Stock bundled extractor HTML metadata and native RSS Source classification.
- [ ] Actual native slow-index/download jobs linked to same Source/item; isolated
  stage queues, per-queue1 is NOT a global concurrency proof.
- [ ] Full download-phase unique120214-byte coverage, unchanged fixture UUID,
  real native output hash and unchanged stock yt-dlp path/hash/version.
- [ ] Updater job attempts/states and denied external network behavior observed;
  no stock replacement, external allowance or SQL/record patching on mismatch.
- [ ] Replacement and two independently fresh restored app PVCs pass native
  read-before-write verification using explicit PASSED result and UUID manifest.

Custom muted Chrome decoder evidence never implies native web UX, audible output,
GPU, production clients or full-media migration acceptance. Native qBit Secure
cookie remains a separate OPEN gap; no settings or routing change is authorized.
