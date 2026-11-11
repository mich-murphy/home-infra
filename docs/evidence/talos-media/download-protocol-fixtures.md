# Closed synthetic download protocol fixtures

## Status and scope

Implemented and tested **offline over actual loopback TCP sockets**, using Python stdlib only. This is not a recorded qBittorrent/SABnzbd run. Real-client completion, image Python availability under the supplied nonroot command, cluster network policy behavior, and real synthetic MP4 transfer remain integration gates owned by the media runner owner. No live cluster/host/source access or external downloads were used for this work.

The fixture is intentionally not a provider emulator, general proxy, file server, open tracker, or Internet peer. It holds exactly one bounded payload in memory and serves only its generated torrent and one yEnc article. Plaintext NNTP with the **public synthetic-only** credentials `fixture` / `fixture-public` is deliberate. There is no TLS, real Usenet account, provider-account proof, upstream forwarding, or source/copyrighted data claim.

Owned implementation paths:

- `kubernetes/apps/media/fixtures/download-protocols/server.py`: importable fixture and server CLI.
- `scripts/talos-proof-media-protocols.py`: repository CLI wrapper.
- `tests/talos-proof-media-protocols-test.py`: offline socket tests.
- Adjacent Kustomization/resources: optional, namespace supplied by caller, not linked into media root, **replicas: 0**.

## Invocation contract

From repository root (commands here are local/offline examples):

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-protocols-test.py -v

# Deterministic built-in non-media bytes; generates metadata, not a downloaded file.
python3 scripts/talos-proof-media-protocols.py generate \
  --output-dir /absolute/new-artifact-directory

# To serve an existing, caller-generated synthetic MP4:
python3 scripts/talos-proof-media-protocols.py serve \
  --payload /absolute/regular/synthetic.mp4 --name synthetic-proof.mp4 \
  --bind 127.0.0.1 --advertise-ip 127.0.0.1 \
  --announce http://127.0.0.1:8080/announce
```

`generate` and `serve` must receive the **same payload, name and announce URL** when used together. `generate` writes only `artifact.torrent`, `artifact.nzb`, and `manifest.json`, exclusively creating files (never overwriting). Alternatively fetch both artifacts from the running instance to eliminate mismatches. No payload is written by the fixture. The default deterministic payload exercises all octets, multiple torrent pieces, yEnc escaping and NNTP dot-stuffing, but is **not a playable MP4**. For application/media validation the owner must supply its real generated synthetic MP4 (the previously generated 14790-byte MPEG4/AAC 160x90 file is suitable).

Inputs are nonempty regular files <=2MiB. Symlinks in any path component, `..` components, directories, FIFOs, oversized files and unsafe download basenames are rejected. On macOS use the canonical `/private/...` path rather than `/var/...` symlinks. Kubernetes projected ConfigMap keys are symlinks too: do not pass one directly as `--payload`. Use an owner-created, isolated regular file via a guarded init step / suitable `subPath` mount, not an application download volume. No host, NFS or socket mount belongs on this fixture.

Default listeners: loopback HTTP `8080`, BEP3 peer `6881`, NNTP `8119`. Each has a configurable port. `--advertise-ip` must be a reachable literal IPv4; the compact tracker returns this address and the peer listener port. For a pod, use its downward-API Pod IP, not service DNS. The announce URL can use service DNS. IPv6-only clusters are not supported by this fixture.

### HTTP

- `GET /artifact.torrent`: one single-file private torrent, 16KiB SHA1 pieces.
- `GET /artifact.nzb`: one file, one yEnc article; message ID derived from SHA256.
- `GET /stats`: JSON `name`, `size`, `sha256`, `infohash`, `message_id`, and `counters`.
- `GET /announce?info_hash=<percent-encoded-20-bytes>&...`: BEP3 compact IPv4 peer list for exactly the fixture infohash. Unknown hashes receive a bencoded failure and no peer.
- All other paths rejected; no filesystem routing, proxying, arbitrary payload endpoint or API mutation.

BEP3 peer validates the protocol and infohash before responding, sends a real bitfield and unchoke, requires interest, and validates requested piece index/offset/length before sending a `piece` message. No extensions, DHT, PEX, webseed, peer discovery or upstream connection is implemented. `private=1` and the single controlled tracker prevent an artifact from advertising public peer discovery. The owner should additionally disable DHT/PEX/LSD globally in its temporary qBittorrent configuration and enforce destination-specific egress policy; the torrent flag alone is not a network boundary.

### NNTP

Configure SAB's only enabled temporary server to the fixture service, port `8119`, SSL **off**, public username/password above, at most 2 connections, and no backups/external servers. Submit `/artifact.nzb`. The server supports `CAPABILITIES`, `MODE READER`, `AUTHINFO USER/PASS`, exact `GROUP alt.binaries.synthetic`, `BODY`, `ARTICLE`, `HEAD`, `STAT`, and `QUIT`. Retrieval requires authentication and the exact bracketed message ID; unknown articles return `430`, unsupported commands `500`. There is no posting, arbitrary spool access, article-number retrieval, STARTTLS or real account authentication. CRC32 and yEnc size cover the original bytes; NNTP multiline dot-stuffing is applied separately. This small subset is intended for SAB's message-ID retrieval; compatibility with the repository's running SAB version must still be demonstrated, not inferred from these tests.

### Evidence counters

`tracker_announces`, `peer_handshakes`, `piece_requests`, `piece_bytes`, `nntp_auth`, `nntp_body_requests`, `nntp_payload_bytes`, `rejected`. Snapshot before and after submission. Counters are cumulative per process, reset only by restart, and thread-safe; there is intentionally no reset endpoint. Piece/body bytes count server sends (retries may exceed file size), **not app completion**. A clean EOF/timeout may also increment `rejected`; use positive transfer counters and output hash, not `rejected == 0`, as success criteria. Startup/shutdown stdout contains metadata/counters only. Do not record binary artifact/body/MP4 contents in evidence.

Per listener: maximum 16 concurrent clients, socket idle timeout 5s, request loops bounded (peer 4096 messages, NNTP 256 commands), session deadline checked between messages at 60s. Strict frame/line/block bounds prevent unbounded request allocations. No subprocess, execution, shell, upstream socket or filesystem request command exists. Use only inside the isolated proof network, never expose a LoadBalancer/NodePort/HTTPRoute.

## Optional Kustomize interface and exact owner additions

`kubernetes/apps/media/fixtures/download-protocols/kustomization.yaml` can be included by an owner overlay that supplies a namespace. It deliberately does **not** create a Namespace, amend shared media root/policies, start the fixture, or grant cross-namespace traffic. Its Deployment pins the existing Tautulli image digest, overrides the entrypoint with Python, runs UID/GID 1000, drops ALL capabilities, disables privilege escalation and SA token mounting, uses read-only rootfs, code-only ConfigMap mount, and limits memory to 128MiB. The immutable image was read from local media manifests, not downloaded or executed. Python availability at `python3` is a pending runtime check. No liveness probe invokes commands.

The media owner must make these deliberate integration changes in **its** paths:

1. Add a dedicated overlay/profile reference and namespace (for example `proof-download-protocols`); keep the common/default profile stopped. Own any guarded lease/scale-up/scale-down, quota allowances and cleanup. Never add an unconditional root inclusion/startup.
2. Patch arguments for the regular synthetic MP4 input and safe basename. The existing downward API supplies the Pod IP. In-cluster announce defaults to same-namespace `http://download-protocols:8080/announce`; external generators must use `http://download-protocols.<fixture-namespace>.svc:8080/announce`. Prefer fetching artifacts from the fixture itself.
3. Replace/patch the fixture's same-namespace ingress peers with **combined** namespace+pod selectors: `kubernetes.io/metadata.name: proof-qbittorrent` AND `app.kubernetes.io/name: qbittorrent` on TCP 8080/6881; `proof-sabnzbd` AND `app.kubernetes.io/name: sabnzbd` on TCP 8119. For runner HTTP artifact/stat access, combine the actual runner namespace with `talos-proof.media/download-protocol-client: 'true'` on TCP 8080 only. Do not broaden to namespace-only selectors.
4. Add reciprocal client **egress** rules in the existing qBittorrent/SAB and runner policy owners: destination fixture namespace AND `app.kubernetes.io/name: download-protocols`, same narrow ports. Preserve only required DNS access for clients. Fixture egress is empty: it never initiates network calls, and Pod IP comes from the environment. Policies are additive: audit that no other policy already permits broad fixture ingress/egress.
5. Configure app APIs under the runner's existing credential redaction and rollback procedures. This fixture does not own app credentials, real APIs, PVC inspection, admission policies or leases. For SAB disable scripts/unpack/repair expectations for this no-PAR single-file fixture if needed, and require actual completed history/output rather than a queue entry.

## Required real-client acceptance (NOT performed here)

For **each** qBittorrent and SAB run, the owner must record:

1. Lease and unique run identity; independently prove destination and temporary/incomplete locations are empty before submission. A fresh isolated subdirectory/PVC is preferable. If using a shared PVC, the expected output file must demonstrably not exist. Never mount that destination into the fixture, prepopulate it, copy fixture bytes there, or accept a preexisting file.
2. Source synthetic MP4 size and SHA256; fixture `/stats` has matching values. Record zero/baseline transfer counters and artifact infohash/message ID. Do not print payload/base64 or secret app credentials.
3. API submission and the app's real completed state: qBittorrent progress=1/completed bytes matching length, or SAB completed history with success/no missing article failures. Empty-queue CRUD and an accepted upload are not completion evidence.
4. Positive fixture counter deltas: qBit `peer_handshakes > 0`, `piece_requests > 0`, `piece_bytes >= size`; SAB `nntp_body_requests > 0`, `nntp_payload_bytes >= size` (HEAD/STAT/auth alone do not qualify).
5. SHA256 of the actual output in the app destination exactly equals the fixture manifest, with actual output size equal too. Then, separately, any desired ffprobe/playability validation on this synthetic MP4. Counters without the app output hash, or a hash without protocol transfer, are insufficient.
6. Restore app settings, remove jobs and synthetic outputs under the lease, scale fixture to zero, revoke temporary policies/profile and release resources. Keep only text evidence/metadata/counters.

## Offline results

`PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-protocols-test.py -v`: **6 tests passed**. Tests use real local HTTP/TCP sockets and independently decode returned torrent pieces and yEnc content. Coverage includes compact peer discovery; exact handshake and infohash; bitfield/unchoke/interest; per-piece SHA1 and full SHA256; NZB message ID; NNTP pre-auth denial, wrong and public credentials, capability list, reader mode, BODY/ARTICLE/HEAD/STAT/QUIT; real dot-stuffing, CRC32 and exact bytes; unknown infohash/article/path rejection; invalid peer frame/request rejection; single-byte and maximum 2MiB yEnc round trips; symlinks, traversal, invalid name and size rejection. No Internet or subprocess is used by tests. The optional Kustomize resources are supplied for owner integration; no cluster apply/image pull or real-client compatibility validation was performed.
