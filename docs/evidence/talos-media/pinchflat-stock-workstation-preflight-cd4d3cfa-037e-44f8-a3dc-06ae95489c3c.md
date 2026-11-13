# Stock workstation preflight — single denied-subprocess diagnostic

## Finding: `ffmpeg -bsfs` denied, not executed

Exactly one additional offline HTML extraction attempt was made. The unchanged
subprocess policy denied a request for executable **`ffmpeg`**, argument shape
**`["ffmpeg", "-bsfs"]`**: one fixed option requesting bitstream-filter discovery,
with no media filename, URL, output path, credentials or shell command argument.
Neither `/usr/bin/ffmpeg` nor `/bin/ffmpeg` exists. Existence was checked read-only
under the fixed child PATH `/usr/bin:/bin`; no wider PATH search or execution was
performed. No binary was available there to hash. The request was logged before
rejection, not converted into a simulated file-not-found result.

This identifies the immediate blocker left unresolved in checkpoint `df17cae9`.
It does **not** authorize ffmpeg execution, prove that removing this blocker would
suffice, or establish extractor/native-provider/capacity/recovery acceptance.

## Exact scope and containment

- New private UUID workdir: `/private/tmp/pinchflat-stock-diagnostic-b3fc37a5-dc6c-474d-a63e-6ec5f35c6874` (0700).
- New wrapper only: retains all previous DNS/connect restrictions and exact
  read-only platform-probe exceptions (`file -b <resolved-python>`, `uname -p`).
  **No new subprocess permission was added.** The only guard addition records a
  denied Popen executable/argv/environment-keynames before the original rejection.
- Denied record created 0600 with O_EXCL; environment **values are not logged**.
  Raw stdout/stderr and results also remain private 0600/O_EXCL. All immediate
  workdir file/directory modes were checked (0600/0700 respectively).
- Fresh initially empty HOME/XDG/TMPDIR directories, minimal environment, Python
  `-I -B`; ignore config/cookies/plugins/cache and explicit empty proxy. No netrc
  opt-in, credential/config read, external DNS/network, public fetch, application,
  VM/container/BEAM, proof/host/production runtime, or MP4 download.
- Genuine unmodified fixture constructor selected an owned ephemeral loopback
  port; no fixed-port listener or existing process was touched. Connect/DNS
  negative self-checks ran before the CLI under the same guard.

CLI flags (one HTML attempt only; no version/RSS retry):

```text
--ignore-config --no-cache-dir --socket-timeout 3
--no-plugin-dirs --no-cookies --proxy ""
--skip-download --no-playlist --dump-single-json <owned-origin>/video/proof-001
```

Environment key names recorded at denial (no values):
`HOME, LANG, PATH, PYTHONDONTWRITEBYTECODE, PYTHONNOUSERSITE, TMPDIR, XDG_CACHE_HOME, XDG_CONFIG_HOME, XDG_DATA_HOME, XDG_STATE_HOME, __CF_USER_TEXT_ENCODING`.
These are observed key names, not credentials; platform/runtime may add keys to
the minimal supplied environment.

## Result and cleanup

HTML exit **1**, no extracted JSON metadata contract. Genuine server
settled snapshot: HTML 1 request, feed 0, MP4 0, rejected 0; 653 response-body
bytes; media body/unique bytes 0. This is diagnosis only, not metadata acceptance.

Owned orchestrator PID 29884, start 1794444322651263000 Unix ns; HTML PID
29887, start 1794444322660636000 Unix ns, bounded 25 seconds, waited/reaped.
The fixture server thread was shut down and joined and its socket closed.
The orchestrator then exited. No global kill, daemon change or listener takeover.
The denied ffmpeg request created no ffmpeg child process.

## Immutable inputs and checkpoint preservation

Before/after SHA256 comparisons were identical for public tool, retained MP4,
fixture/provider source, old wrapper/run script, and the prior public report:

- `selected-0f46da092696e385ca83ea5e689e57f9af661fa8e17765be7916c3421990ab75.data`: `11aae6b9d391bce3633d62929f0526e1efd431e9892db09b0c4573b31ba76038`.
- `Proof Browser Fixture (2000).mp4`: `9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`.
- `talos-proof-media-pinchflat-fixture.py`: `d15822a17551649ba9ee958f45be9ea36e6455a3ec706f77bbd0e8da3094f083`.
- `talos-proof-media-pinchflat-provider.py`: `45db83071a9b943cf4372b3a6be7649a7a0e6c788e2e8fd998d1c3f7a7162935`.
- `guarded.py`: `1b9a63b78ebc66b9823e9badd0547de66b09bc7c5ac5ff10671a6201cd2d13d7`.
- `run.py`: `78e29ab22aebd8f949e4ee4d259c9148dc3bd5fd9156c00c4dee7f77d078699f`.
- `pinchflat-stock-workstation-preflight-841f8c84-a0ec-403f-ba00-cdfa4c57556c.md`: `862feeb949f6889d197b61551e3ca3fe586a719463007e369fab049a5764183f`.

The tool remains the exact selected public-image Python ZIP SHA256
`11aae6b9d391bce3633d62929f0526e1efd431e9892db09b0c4573b31ba76038`;
fixture remains 120214 bytes SHA256
`9f754faabc2f1d7a460a8b3ff0ef3f9124c9cab7407af3e66a649c720ae348cb`.
No old wrapper/artifact/fixture/tool/report was modified.

Private result SHA256: `6559636e9b150e087eedec5cfda44c8816f9d8b5f55ebba44500f349889f8f0a`.
Private denied-record SHA256: `7c866db69745be6c0b317434bb966f6f9d9dd4bc9df1026ed2887dd7997e370d`.
This new evidence path is the sole repository change for this diagnostic;
parent retains root-doc and acceptance ownership. No further attempt was made.
