# One RSS384 activation: native RPC output blocked; released

New grant/window `77f1f267-3749-4f10-acb2-3f2c3d2781ea`, 2026-11-11 UTC,
reviewed admission code fbbd981c. **One activation, one exercise, no retry.**
This is not a provider, decoder, capacity, persistence or recovery pass.
Parent retains requirements acceptance, readiness/brief/platform gates.

## Preparation and bounded execution

Read the exact new grant; retained its initial bytes and unchanged issued history.
Verified exact private kubeconfig/context/API/node UID, retained controller UID,
both retained PVC UIDs and bootstrap Secret. Independent exclusivity checks
found no foreign proof Pods. Hashed214 old files, including prior156 files and
new history, without altering their bytes.

Fresh stopped memory: **1335 MiB kubelet /1147 MiB Talos**. Collector refreshed
only those independent fields and `measured_at`. Mandatory dual-min admission,
unchanged384 main +128 fixture +192 reserve = **704 MiB**, passed. CPU canonical
`1` was accepted as exactly1000m, not rewritten or raised. Stopped `prepare`
returned `PREPARED_STOPPED_ONLY`, record
`pinchflat-rss-prepare-result-449d26ba6f0e468ba58c5b2988b493cc.json`.
Full-spec atomic preparation preserved retained claims/bootstrap; explicit stopped
readback verified UID, claims, bootstrap and full budget. Only approved optional
profile/code/input provisioning was performed; no base reapply.

Bounded900s outer workstation watcher was running before activation (recorded
23:13:48Z). One `batch activate` reached readiness. Private current main/fixture
log streams began23:13:57Z and remained alive with exact Pod UID/container-ID
bindings before native controls. Pod UID:
`2f5f4f66-a51f-400e-8ccb-617149bc7375`.

Inside the exercise, checkpoint monitoring covered the first native Oban pause
RPC. Its shell checks established PID1 `beam.smp`, actual exported release node
`pinchflat`/distribution `sname`, a syntactically valid actual cookie (not copied
into public evidence), ELF magic and executable/nonsymlink path. The returned
transport marker records expected bundled erl_call path
`/app/erts-15.2.2/bin/erl_call`, exact SHA
`73c690ffdc8151a4e01f825ca7c4eb5912245aa17808890438004ce90b658669`,
and one BEAM both before and after. The native shell returned successfully.

**But the193-byte output contained only the transport marker, no PROOF_JSON.**
The runner rejected it with `native lightweight RPC did not yield one structured
result`. Private RPC record:
`pinchflat-rpc-private-2f6d4a536b87483d8f6f9d5fb7ae23f6.log`, SHA
`eefdc337a556bcd242f1e9744a4d92ba615b405eb7bdeeab64fa12c01cb723c9`.
This does NOT establish that Oban queues paused or that remote evaluation
succeeded. RPC stdout/protocol/version acceptance remains blocked. No fallback
BEAM RPC, repeated control expression or second exercise was attempted.

The exercise stopped before native state SELECTs, stock downloader path/hash/
version execution, independent HTML extraction, destination creation, profile/
Source creation, indexing, download, fixture download-phase counters or output
hashing. No stock downloader runtime identity or provider acceptance is claimed.
No credentials/binaries were replaced; no output/source bytes were preseeded.

## Resource and cleanup observations — limitations retained

35 private counter/status sample records were retained; one is a cleanup-time
STOP. Observed restartCount values were0 for main and fixture, with empty
lastState in the precleanup snapshot. Sampled current-lifetime OOM, oom_kill and
oom_group_kill counters were0 for both containers. This does **not** prove zero
restarts/OOMs between observations or across lost container lifetimes.

Maximum observed native cgroup peaks:

- Main **402653184 bytes (384 MiB, exactly its limit)**; memory.events `max`
  reached **2028**, so the run encountered substantial limit pressure despite
  sampled OOM counters remaining0. Not a comfortable capacity margin/pass.
- Fixture **29372416 bytes (about28.0 MiB)**; observed max/OOM counters0.

On RPC failure, full status and current+previous log requests completed BEFORE
intentional scale0 (last request23:14:57.578447Z). Current logs succeeded for both
containers. Previous-log requests returned1 (no prior container available); their
private diagnostics and lastState bindings are retained. No known OOM or137
preceded deliberate cleanup, so emergency stop did not defer these captures.

At23:15:02.780143Z an outer-monitor cgroup exec/read raced deliberate scale0 and
failed. Its sample retains Running status/restartCount0 but no readable counter
payload; this is an explicit forensic gap, NOT a zero counter sample. STOP marker
`pinchflat-oom-stop-b5932d5eaeaa4590ad1cb52ab97ed1e8.json` and failed check
`pinchflat-oom-check-0f18df18c91f46048c82eec94f6e03f2.json` remain immutable.
The watcher attempted emergency stop after that failure. Its shutdown log also
records a monitor-join timeout and an interruption during its redundant deletion
wait; the runner subsequently exited the watcher and independently verified Pod
absence. No STOP marker was removed and no control/exercise retry followed.

The original private `window-result.json` predates forensic analysis and lists
no gaps. It was NOT overwritten: an append-only `forensic-addendum.json` records
this cleanup race. Terminal status/counters after deletion and kernel correlation
were not collected. No unmonitored running application was left behind.

## Release and immutability

Independent post-cleanup verification found **all proof app/helper Pods absent,
all proof Deployment/StatefulSet replicas0, all proof CronJobs suspended**.
The stopped approved384 profile remains installed; no replacement/restart or
fresh-PVC recovery occurred. All214 old files hashed identically, including old
archives/results, credentials, fixture, prior history and issued receipt copies.

Active grant was copied exclusively mode0600 to
`leases/revoked-media-pinchflat-rss384-77f1f267-3749-4f10-acb2-3f2c3d2781ea.json`,
then the active path was removed well before expiry. Issued history unchanged.
Post-release observation only: **1226 MiB kubelet /1104 MiB Talos**, measured_at
`1794438954.1375842`; no lease/expiry/identity update after release.
No VM start/RAM/host change, other-group activation, Internet/cloud access,
archive capture/restore or credential/binary replacement was performed.

Private directory: `media/rss384-window-77f1f267-3749-4f10-acb2-3f2c3d2781ea/`.

| Record | SHA256 |
| --- | --- |
| old-files-before.json AND old-files-after.json | `27c1316b3483fe628a959a4675dd48a936993a0f0f620ca96800f5ccb1b391bb` |
| release-proof.json | `013e3a87d12e00249957cb9485c3af6e7924ad0c1e6fd528a077ceb8baa70568` |
| post-release-memory.json | `21bb85742b605b8a8d87fe7491987a2d78eecb3e4c4b1308344b91c4038e013d` |
| window-result.json (original) | `84a7a36f424a292189f932594a625201e46f4860b07cc10633a16317e454d090` |
| resource-summary.json | `12695775c30689baef09d22c973b766d493cb25d8e75a272a7dc3a7618de5487` |
| forensic-addendum.json | `c3e389d68a48eb6d6488a6b2843f8828bf8314a44d4f90e37e2c588e99f4b9d2` |

No implementation change or new test claim in this evidence-only checkpoint.
Prior154 scoped offline methods are not native acceptance. Any further live work
requires separate parent review/new grant and explicit review of the retained
STOP marker; none is implied by this released experiment.
