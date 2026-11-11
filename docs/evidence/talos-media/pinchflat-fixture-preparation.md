# Pinchflat offline fixture preparation — candidate, not acceptance

## Status and scope

Implemented only a stdlib, loopback HTTP candidate origin and its offline socket
protocol tests. **No real Pinchflat Source/index/download pipeline has passed.**
No cluster/host-service calls, deployment, activation, image export, manifest,
policy, browser, recovery, or existing evidence changes are part of this work.
Preserve all earlier archives; future runs need distinct evidence directories.

Target supplied by prior research:

- Pinchflat `v2025.6.6`, commit
  `076f2fe78b32f5f0a4997639c89601774d34016b`.
- `ghcr.io/kieraneglin/pinchflat:v2025.6.6@sha256:4e975edf58f0861a5cbfe8fc6aac4851ff5a02dfc3f05ffeea4982e3084a5a4a`.
- Bundled **yt-dlp version is UNKNOWN**. The Dockerfile downloads latest and the
  updater attempts boot/daily updates. An image tag does not establish the actual
  extractor version; no workstation binary may silently replace the stock one.

Prior public-source findings (provided to this implementation, not fetched again
in this offline task):

- [`sources/source.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/sources/source.ex)
  intentionally retains “tenuous support for non-youtube sources”: arbitrary HTTP
  URLs are allowed; individual YouTube video URLs are rejected. The source must
  classify as a playlist/channel with collection identity and title.
- [`sources/sources.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/sources/sources.ex)
  and [`yt_dlp/media_collection.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/yt_dlp/media_collection.ex):
  stock yt-dlp first-item metadata includes `channel`, `channel_id`, `playlist_id`,
  `playlist_title`, and `filename`.
- [`slow_indexing/slow_indexing_helpers.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/slow_indexing/slow_indexing_helpers.ex):
  slow indexing uses the original URL; missing `live_status` is allowed for
  generic media.
- [`media/media_item.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/media/media_item.ex)
  requires `upload_date`.
- [`downloading/media_downloader.ex`](https://github.com/kieraneglin/pinchflat/blob/v2025.6.6/lib/pinchflat/downloading/media_downloader.ex):
  custom `/config/extras/yt-dlp-configs` options apply to DOWNLOAD, not source
  validation/indexing. They cannot provide all-phase networking containment.

## Origin contract

Run `scripts/talos-proof-media-pinchflat-fixture.py` with an explicitly attested,
**newly generated**, exactly two-second H264/AAC MP4, at most 2 MiB. No MP4 is
committed. The script checks size, regular-file/single-link status and `ftyp`,
not codecs, duration or synthetic provenance; those need independent generation
and ffprobe records. It takes one bounded immutable snapshot and never writes
its input or an application destination. The input must never be a writable
shared application download, a pre-seeded output, or a copy of downloaded media.
Use an isolated input directory, later mounted read-only if authorized.

Exactly these resource targets exist (GET and HEAD):

| Target | Meaning |
| --- | --- |
| `/feed.xml` | One-item RSS playlist, title and collection link; entry links to HTML, no direct MP4 enclosure |
| `/video/proof-001` | Independent HTML video page; canonical URL, JSON-LD VideoObject identifier/name/uploadDate/duration/contentUrl, HTML video/source |
| `/media/proof-001.mp4` | Immutable caller-supplied MP4 snapshot |

The candidate entry identity is `proof-001`, title `Synthetic proof 001`, upload
UTC date `2026-01-01`, duration two seconds. RSS-only publication metadata is
insufficient: the HTML must independently yield stable id/title/upload_date/
duration when the **actual bundled extractor** re-extracts it. JSON-LD presence
alone is not evidence that that extractor will use every field. Collection
identity/classification and native compatibility remain unproven. No thumbnail
is exposed; add nothing unless native evidence establishes a genuine need and
it is separately reviewed.

Properties:

- Binds only `127.0.0.1`; port defaults to ephemeral. No upstream HTTP/DNS client,
  subprocess, URL forwarding, arbitrary path mapping, redirect, directory
  serving, or application/database access. Host headers cannot alter URLs.
  `https://schema.org` is a JSON-LD vocabulary identifier, not a fetched resource.
- Exact request-target match: query strings, absolute proxy targets, traversal,
  encoded variants and other paths return 404. Other methods are unsupported.
  Request bodies on supported paths are rejected; every connection closes.
- Single bounded byte range (including suffix/open-ended) yields 206; invalid,
  duplicate, multipart and unsatisfiable ranges yield 416. HEAD sends no body.
- Synchronous server, listen backlog 4, socket inactivity timeout two seconds;
  stdlib request-line/header limits apply. No per-request history/log retention.
  CLI lifetime defaults to 300 seconds, maximum 900; a current request can extend
  the deadline. This is a controlled local origin, **not a hostile-network
  hardened server** (e.g. slow clients can consume the run window).
- At most 512 parsed requests and 32 MiB reserved response-body bytes. CLI exits
  after request cap/deadline/interrupt. State is fixed three-route counters plus
  a coverage bytearray no larger than 2 MiB; media is no larger than 2 MiB.
  No unbounded URL keys, request logs or range histories.
- Startup prints feed URL JSON; shutdown prints bounded JSON evidence (request
  count, route counters, rejected count, body budgets, media size/SHA-256,
  media bytes and unique byte coverage). There is deliberately no status URL.
  Body budget counts reserved writes conservatively on failure; media coverage
  counts successfully written/flushed slices, **not client acknowledgement or
  app job completion**. Range retries increase total bytes, not unique coverage.

## Offline check performed

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tests/talos-proof-media-pinchflat-fixture_test.py -v
```

Result: **13 tests passed**. Actual HTTP sockets bind/connect to ephemeral
loopback ports. A connect guard rejects every non-fixture socket destination.
Tests cover RSS/HTML metadata, Host-header independence, HEAD, complete download
hash, range reconstruction/unique coverage, invalid/duplicate ranges, path
rejection, request-body rejection, budgets, and bounded immutable file loading.
Test media is intentionally a small `ftyp`-prefixed byte payload, **not a playable
MP4**: this proves protocol behavior only. Neither ffmpeg nor yt-dlp was available
on PATH for this implementation; no codec check or reference extractor smoke
test was performed. Nothing here claims a real application pipeline pass.

## Proposed generation and integration contract (NOT executed/authorized)

When separately authorized, generate a new input in an empty private directory
using already provisioned tools. For example (commands are preparation guidance,
not an activation grant):

```sh
input_dir=$(mktemp -d)
ffmpeg -n -f lavfi -i color=c=blue:s=160x90:r=10 \
  -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 \
  -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 32k \
  -movflags +faststart "$input_dir/proof-001.mp4"
ffprobe -v error -show_streams -show_format -of json "$input_dir/proof-001.mp4"
chmod 0444 "$input_dir/proof-001.mp4"
python3 scripts/talos-proof-media-pinchflat-fixture.py \
  --synthetic-input --mp4 "$input_dir/proof-001.mp4" --seconds 300
```

Retain generator version/command, ffprobe codecs/duration, size and input hash.
The future fixture must share a loopback network namespace with the real app
(e.g. an explicitly reviewed sidecar); current code does not bind a Service IP
or other interface. Generic loopback HTTP needs no YouTube TLS proxy. Do not
expose this stdlib origin publicly or broaden its listener casually.

Mandatory future acceptance, in order:

1. Obtain explicit authorization for the actual group, isolation, limits and
   recovery scope. **Proposed** app 256 MiB + fixture 128 MiB + reserve 192 MiB =
   576 MiB is not a grant or measured fit. Multiple yt-dlp queues can exceed the
   app cap even with per-queue concurrency 1; measure and constrain aggregate
   concurrency before a live run. These scripts do not set resource limits.
2. Inspect existing global/application Cilium policies as well as namespace
   policy. Prove effective all-phase egress containment: fixture loopback only,
   no public DNS/HTTP or updater escape. Download-only yt-dlp config is not
   sufficient. Do not activate networking or modify policy based on this doc.
3. Record the actual app image digest and bundled yt-dlp executable path,
   `--version` and SHA-256 **before and after** native extraction/download.
   Record attempted updater actions; block external updates rather than
   assuming the image tag pins yt-dlp. No downloader replacement or forged
   completion rows. If a later optional workstation reference smoke is used,
   label its version/hash **reference-version only**, ignore external configs
   and proxy environment, and enforce OS-level fixture-only connections; flags
   alone are not containment. It does not satisfy bundled-version acceptance.
4. Use stock native source validation on the RSS URL. Retain sanitized real
   collection classification/id/title and requested first-item fields. Prove
   independent extraction of the HTML URL yields stable id/title/upload_date/
   duration, then run real slow indexing using the original URL. Fail closed
   if native validation rejects the collection or required metadata is absent;
   do not patch the downloader or pre-seed app records to force a pass.
5. Begin with an **empty, unique** destination on the app download PVC, distinct
   from the read-only input. Record actual native Source, indexed media item,
   download job and completed state, with their relationships and paths. Show
   the stock app initiated the download; retain fixture route counters,
   complete unique media-byte coverage and input/output hash correspondence.
   If the app remuxes/postprocesses, additionally prove encoded stream/content
   identity and explain differing file hashes rather than asserting equality.
6. Record resource peaks and absence of OOM/restarts; successful direct HTTP or
   extractor commands alone are not application acceptance. Retain native
   output/provenance through app replacement, then demonstrate **two separate
   fresh-PVC recovery** runs with native state/output checks and new evidence
   archives. Do not substitute the old PVC or overwrite earlier archives.

Any failure remains a documented blocker. This preparation grants none of those
live operations and supplies no fake completed state or pre-seeded output.
