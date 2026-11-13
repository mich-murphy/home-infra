# Stock yt-dlp workstation preflight — BLOCKED, not acceptance

## Scope and outcome

Offline workstation-only execution of the exact retained public-image Python ZIP
reduced two unknowns: stock version is **2025.05.22** and the real fixture RSS is
recognized as a one-item generic playlist. **Independent HTML extraction remains
blocked by the additional subprocess containment guard.** It did not produce an
id/title/upload_date/duration JSON contract. Do not interpret this as a proven
extractor/fixture incompatibility or a successful RSS→HTML→MP4 traversal.
No MP4 route was requested; no download was attempted. No native provider,
capacity, recovery, application, Source/profile/Oban/DB, VM/container, or production
acceptance is established. Parent retains acceptance and root-document ownership.

## Provenance and immutable inputs

- Supplied public image index: `4e975edf58f0861a5cbfe8fc6aac4851ff5a02dfc3f05ffeea4982e3084a5a4a`.
- Supplied amd64 manifest: `bda3091e59af351e5e928930c680a6ebe2cde728949e36c11000b9827ee2ed51`.
- Retained inspection: `/private/tmp/c2313729-8685-48a7-b3c0-698fa499b0ae/filesystem-evidence.json`.
- Selected `/usr/local/bin/yt-dlp`: 3,093,972 bytes, SHA256
  `11aae6b9d391bce3633d62929f0526e1efd431e9892db09b0c4573b31ba76038`.
  ZIP structure confirmed without printing executable contents; executed by Python,
  not an image ELF. No fetch, Docker or GitHub authentication was needed.
- Existing prepared synthetic `Proof Browser Fixture (2000).mp4`: 120,214 bytes,
  SHA256 `9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`.
  Located under the documented private proof-media state path by name, size and
  hash; no credentials or application config opened. Existing preparation records
  establish the twelve-second synthetic provenance; this run did not probe codecs.
- Fixture source SHA256: `d15822a17551649ba9ee958f45be9ea36e6455a3ec706f77bbd0e8da3094f083`.
- Provider source SHA256: `45db83071a9b943cf4372b3a6be7649a7a0e6c788e2e8fd998d1c3f7a7162935`.

Tool, MP4 and both source hashes were checked before/after each attempt and
unchanged. No existing media/evidence file was written. No provider helper was
imported or invoked; its stock/exercise code and fixture tests were read only.

## Isolation and commands

Platform: `macOS-27.0.1-arm64-arm-64bit-Mach-O`, Python `3.13.13`. This arm64 macOS Python
execution is not the image's Linux/amd64 application environment.

Private UUID workdirs were created mode 0700; scripts, stdout/stderr and results
were created mode 0600 with O_EXCL. Each CLI received fresh initially empty
HOME/XDG config/cache/data/state/TMPDIR directories, a minimal environment with
PATH `/usr/bin:/bin`, and Python `-I -B`. No inherited environment, cookie, netrc,
plugin, cache, user configuration or proxy settings were used. Netrc is opt-in
and was never enabled; the stock version does not accept `--no-netrc`.

Common CLI flags:

```text
--ignore-config --no-cache-dir --socket-timeout 3
--no-plugin-dirs --no-cookies --proxy ""
```

Bounded 25-second calls then added:

```text
--version
--skip-download --flat-playlist --dump-single-json <owned-origin>/feed.xml
--skip-download --no-playlist --dump-single-json <owned-origin>/video/proof-001
```

The HTML flags preserve the provider's prepared extractor flags; the extra flags
only isolate local settings. RSS flat-playlist is an independent workstation
observation, not a substitute for native collection-validation flags.

The unmodified genuine Fixture constructor selected an ephemeral 127.0.0.1 port;
fixed 7913 and other listeners were untouched. DNS was rejected except numeric
127.0.0.1 resolution for the owned port. Socket audit denied any other connection;
negative connect/DNS self-checks ran before the CLI. Extra child-process execution
was denied except exact read-only workstation `file -b <resolved-python>` and
`uname -p` platform probes. This is Python-level containment, not an OS sandbox.
No image ELF, Pinchflat, BEAM, host-service or production runtime was executed.

## Final observed result

- Version exit 0: `2025.05.22`.
- RSS exit 0: generic playlist, title `Offline synthetic proof collection`,
  playlist_count 1, identity equal to the owned feed URL. The sole transparent
  entry targets the owned HTML URL (with yt-dlp's internal force-videoid fragment),
  title `Synthetic proof 001`, timestamp 1767225600; RSS duration is null.
- HTML exit 1: sanitized diagnostic `external lookup/process denied`, following
  generic-extractor fallback. No JSON metadata object. This is a **guard-blocked**
  result; which further subprocess the tool wanted is not established here.
- Settled genuine server snapshot: feed 1 request, HTML 1, MP4 0; rejected 0;
  1,078 response-body bytes; media body/unique bytes 0. Fixture snapshot retained
  exact original media SHA and size. No native download-phase coverage exists.
- Actual id/title/upload_date/duration contract: **not observed**. Expected
  upload_date `20260101` and duration 12 remain unverified by independent extraction.

Earlier isolated attempts are preserved privately: unsupported `--no-netrc`
(exit 2), followed by guards stopping Python platform-identification subprocesses.
These were containment/harness negatives, not candidate acceptance results. The
final attempt permitted only the two exact public platform probes above and still
blocked a later subprocess. No artifact or fixture was changed to force a pass.

## Process lifecycle and private evidence

Final private workdir: `/private/tmp/pinchflat-stock-preflight-cb0945dc-eeef-49c4-bafc-9c0498370d77`. Raw streams and full metadata remain private;
`results.json` SHA256 `bc6aa4ebad495b704755ba3267266b19eac4f0ab968476e1fef378cd97b000d7`.
The server ran as an owned thread, was shut down, joined, and socket closed in
finally/context cleanup. Each CLI was waited/reaped; no global kill or daemon
change was used. Final PIDs/start timestamps (Unix ns):

- version: PID 27033, start 1794443530849715000, exit 0, reaped.
- rss: PID 27034, start 1794443531349710000, exit 0, reaped.
- html: PID 27038, start 1794443532346337000, exit 1, reaped.

Next step requires separately reviewed bounded subprocess policy or a deliberate
blocked disposition; it is not permission to weaken network containment, alter
fixture/source bytes, or run the application. This file alone is the checkpoint.
