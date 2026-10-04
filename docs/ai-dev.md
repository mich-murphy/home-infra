# ai-dev

`ai-dev` is the isolated DMZ guest. Its only NIC is on the physical
`vmbr1` DMZ, and it carries an 8 GiB disk-backed swapfile with a bounded zswap
cache. `terraform/main.tf` holds its current spec.

Its workload is CLIProxyAPI (CPA), which pools Claude Max and ChatGPT Pro
(Codex) subscription accounts behind one endpoint, together with the stock CPA
management dashboard and a routing controller that keeps CPA's credential
order in "burn the soonest weekly reset first" order. Clients reach it only
over Tailscale, and upstream traffic leaves from the residential IP. The
canonical specification is `docs/requirements.md` in the private
`mich-murphy/cliproxy-controller` repository; this document covers the host.
It replaced the Hermes infrastructure agent;
[Retiring Hermes](#retiring-hermes) covers the clean-up on the live host.

The management user's remote path is:

```text
Moshi -> Tailscale private network -> OpenSSH -> Mosh when available -> Herdr
```

Tailscale SSH stays disabled, and this is load-bearing rather than incidental.
Tailscale SSH is not OpenSSH: it takes over port 22, so Mosh cannot bootstrap
through it, and it does not implement `-L`/`-R` port forwarding, which Moshi's
Browser Preview depends on. Moshi's own documentation recommends leaving it off
so port 22 returns to the OS `sshd`. Enabling it would break the path above and
fail the identity assertions in the ai-dev role.

Disabling it costs nothing in key handling. Moshi's Easy Pair appends its own
public key to the target account's `authorized_keys` during pairing, so no
private key is ever pasted into the phone. Ansible manages only its own
operator key line, leaving Moshi's entry intact.

Herdr is the only persistent multiplexer on the guest.

## What runs

The `ai-dev` role owns the host: identity, packages, the nftables policy and
memory protection. The `cliproxy` role owns the proxy and the controller.

- `cliproxy.service` runs CPA as the `cliproxy` system user on
  `0.0.0.0:8317`: the client API, the management API and the dashboard.
- `cliproxy-controller.service` runs the routing controller as a systemd
  `DynamicUser` on `0.0.0.0:8318`: the status API and status page.

nftables admits both ports on `tailscale0` only. The physical DMZ stays
default-denied, and the guest still cannot initiate a session to any tailnet
peer. CPA reaches the Anthropic and OpenAI endpoints over the DMZ's public IPv4
route.

Both services are hardened systemd units: a read-only system apart from their
own state, no capabilities, private `/tmp` and devices, and a system call
filter. The controller has no `MemoryDenyWriteExecute` because its Bun runtime
JIT-compiles.

On disk:

- `/opt/cliproxy/<version>/cli-proxy-api`: the pinned CPA release binary,
  linked from `/usr/local/bin/cli-proxy-api`.
- `/etc/cliproxy/config.yaml`: rendered by Ansible, `root:cliproxy` `0640`.
- `/var/lib/cliproxy/auths/`: OAuth credential files, one per account.
- `/var/lib/cliproxy/static/management.html`: the pinned stock dashboard,
  root-owned and read-only to CPA.
- `/opt/cliproxy-controller/<version>/cliproxy-controller`: the pinned
  controller release binary.
- `/etc/cliproxy-controller/env` and `management-key`: the controller's
  environment and key, root-only `0600`. systemd hands the service a private
  copy of the key (`LoadCredential`), at the path the environment names.
- `/var/lib/private/cliproxy-controller/state.json`: the controller's
  hysteresis and cache statistics (`StateDirectory`).

### Pinned releases

Every artefact is pinned by version and SHA-256 in
`ansible/roles/cliproxy/defaults/main.yaml`, and Renovate raises each bump as
a pull request that changes both together. None of them automerge: each
deploys only when the play runs, and each must stay in step with the
controller's parity and contract tests.

- **CPA** is the upstream linux amd64 release tarball, checked against the
  checksum upstream publishes in the release's `checksums.txt`.
- **The dashboard** is the stock CPAMC `management.html`, pinned by the digest
  GitHub records for the release asset. `disable-auto-update-panel: true` stops
  CPA replacing it, and because the file is present and root-owned, CPA never
  falls back to the unverified `https://cpamc.router-for.me/` page. Bump it only
  together with `upstream-dashboard.version` in the controller repository,
  whose parity test gates the change.
- **The controller** is a release asset of the private
  `mich-murphy/cliproxy-controller` repository. Private release downloads do
  not accept token authentication, so the play reads the release through the
  GitHub API with `cliproxy_controller_github_token`, a fine-grained token
  with read-only Contents access to that one repository. Without the token
  the play installs CPA alone and reports the controller as skipped, so the
  host can be provisioned first.

### Configuration ownership

Ansible owns `config.yaml`. CPA cannot write it, so dashboard Config Panel
saves fail, and CPA hashes the management key in memory at each start instead
of rewriting the file with the hash. Change settings in
`ansible/roles/cliproxy/templates/config.yaml.j2` and re-run the play. A
restart, and any routing change, clears CPA's session bindings, so each
session's next request binds afresh and rebuilds its prompt cache; apply
changes at a quiet time.

The credential files are runtime state: logins, the priorities the controller
patches and `websockets: true` on Codex credentials all live there. They are
not backed up by this repository; losing them means logging every account in
again.

### Client access

CPA's client API has no API keys (`access.api-keys: []`). Any device that can
open TCP 8317 on ai-dev can spend the pooled subscriptions. That is a
deliberate, accepted decision: Tailscale identity, the narrow tailnet grant
below and the nftables admit on `tailscale0` are the access control.

The management API, the dashboard and the controller's status API all require
the management key, `cliproxy_management_secret` in the Ansible vault. CPA
blocks a client address after repeated wrong keys, and the controller
throttles wrong keys so its endpoint is no faster than CPA's for guessing.

## Tailnet policy

The tailnet policy is managed outside this repository. Two grants reach
ai-dev. Grants are additive, so a broader existing grant can defeat either.

Give only approved user and iOS device selectors permission to initiate
OpenSSH and Mosh traffic:

```json
{
  "grants": [
    {
      "src": ["group:ai-dev-users"],
      "dst": ["tag:ai-dev"],
      "ip": ["tcp:22", "udp:60000-61000"]
    }
  ]
}
```

The proxy grant is the client access control for CPA and the controller, so
keep it to the devices that should spend the subscriptions:

```json
{
  "grants": [
    {
      "src": ["group:ai-proxy-users"],
      "dst": ["tag:ai-dev"],
      "ip": ["tcp:8317", "tcp:8318"]
    }
  ]
}
```

Replace both groups with the tailnet's approved selectors, and prefer naming
your own devices or user over `autogroup:member` or `*`.

No grant should have `tag:ai-dev` as a source. Hermes needed grants from ai-dev
to the docker-host observer (`tcp:2375`), the media broker (`tcp:8765`) and the
Proxmox API (`tcp:8006`); delete them from the policy. Nothing on the guest
initiates a tailnet session any more.

The tailnet policy is necessary but not sufficient. ai-dev's own nftables
output chain drops the whole `100.64.0.0/10` range, so the guest cannot
initiate a tailnet session even where a grant permits it. MagicDNS is the only
exception, and the ai-dev role asserts both that and the blanket drop on every
run.

### Persistent nftables migration

The ai-dev role owns only `/etc/nftables.d/ai-dev.nft`, which is included by the
administrator-owned `/etc/nftables.conf`. On a fresh host the role creates the
small root configuration; an existing root configuration is preserved and gets
one include line (or uses an existing `/etc/nftables.d/*.nft` include). The role
validates the fragment, the staged root configuration, and the live replacement
transaction before changing either persistent file. Reload and stop operate on
only the `inet ai_dev` table; the distro service still loads the complete root
configuration at boot.

A previously deployed role file containing `flush ruleset` or `table inet filter`
is ambiguous and fails closed. Migrate it manually before rerunning the role:
make a root-only backup, copy any unrelated tables/rules into the administrator's
persistent configuration, remove the legacy global flush and old role table,
then validate `/etc/nftables.conf` with `nft -c`. Only after that conversion,
and after confirming that any active `inet filter` table is legacy ai-dev state,
set `ai_dev_allow_legacy_nft_migration=true` once to remove that active table.
The role never parses, overwrites, or automatically backs up an ambiguous root
file, so unrelated persistent rules cannot be silently discarded or resurrected.

## Deployment

Generated cloud-init files under `terraform/files/` are ignored build
artifacts, not a credential store: rotate any Tailscale authentication key that
was rendered into one. `terraform/files/ai-dev.cfg` holds the key rendered for
the last ai-dev bootstrap; the rollout below checks and removes it.

Before an approved Terraform run, create a short-lived, tagged, single-use
`tailscale authkey` field in the existing 1Password `proxmox_creds` item under
the `Terraform SCP` section. Both guests read this shared field: the field must
be present before `terraform plan` can render either guest's vendor data, and
this repository does not create or revoke keys.

If bootstrap fails, inspect cloud-init status and the guest's Tailscale state
without retrying blindly. A key that was consumed, exposed in logs/artifacts,
expired, or is no longer needed must be revoked in the Tailscale admin console
and replaced with a newly scoped key in the 1Password field. Record
which guest was affected, remove stale generated files, and rerun only after the
new key is available. On expiry or revocation, expect that guest to require
an explicit rejoin.

Run:

```sh
cd terraform
terraform fmt -check -recursive
terraform validate
terraform plan
```

Stop if VMID 110 or its disk would be destroyed or replaced; `main.tf` keeps a
`moved` block, so an address move is the only structural change a plan should
ever report here.
If the plan instead proposes creating all BPG-provider VMs or asks for the
legacy Telmate provider, stop: the local state predates the earlier provider
migration and must be reconciled/imported before this rename can be planned.
A plan that only re-creates `local_sensitive_file.cloud_init_ai_dev` after the
file was deleted is expected.

Then stage the guest changes:

```sh
cd ansible
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit ai-dev --check --diff
ansible-playbook run.yaml --vault-password-file .vaultpass --limit ai-dev
```

On a fresh build, follow with the strict RouterOS command from the README so
the router's DMZ policy is in place.

Check mode installs nothing, so it cannot show the services starting; the
tasks that unpack binaries, start units and probe health report as skipped.
The configuration template runs with diff disabled, because the file carries
the management key.

The Proxmox IP configuration does not request guest IPv6, and the ai-dev role
persists the physical DMZ IPv6 disablement after networking is available. A
per-interface networkd drop-in disables DHCPv6, IPv6 link-local addresses, and
router advertisements so networkd cannot undo the sysctl policy at reboot.
The existing cloud-init IPv4 configuration and Tailscale interface are preserved.
This cloud-init template cannot guarantee first-boot isolation: its `runcmd` phase
runs after networking. Do not treat a fresh ai-dev guest as isolated until an
image/bootstrap mechanism that disables physical-interface IPv6 before network
startup has been verified. Any such mechanism must leave Tailscale IPv6
available. Legacy `inet filter` removal is disabled by default; only set
`ai_dev_allow_legacy_nft_migration=true` after an operator has confirmed that
table is role-owned. Verify generated vendor data in a temporary render before
an approved provisioning run.

## Rollout

The first CPA rollout replaces Hermes on the live guest. Each step below is
manual; run them in order.

1. **Rendered Tailscale key.** In the Tailscale admin console, check whether
   the key rendered into `terraform/files/ai-dev.cfg` is still valid and revoke
   it if so, then delete the file. Do not print it; the key is the only secret
   in the file. Remove any key left in the 1Password `tailscale authkey` field
   the same way.
2. **Tailnet policy.** Add the proxy grant above for your devices, and delete
   every grant with `tag:ai-dev` as a source.
3. **Check, then apply.** Run the check-mode and apply commands from
   [Deployment](#deployment). The apply installs CPA and the dashboard, closes
   Hermes's tailnet egress, and reports the controller as skipped until its
   token exists.
4. **Retire Hermes.** Run the decommission in
   [Retiring Hermes](#retiring-hermes), then revoke its two credentials.
5. **Log in the accounts.** Add two or three Claude and two or three Codex
   accounts as described in [Logging in accounts](#logging-in-accounts).
6. **Install the controller.** Create a fine-grained GitHub token with
   read-only Contents access to `mich-murphy/cliproxy-controller` only, add it
   to the vault as `cliproxy_controller_github_token`, and run the play with
   `--tags cliproxy`.
7. **Check the dry run.** Leave `cliproxy_controller_dry_run` on until the
   controller's logs and status page look right; see
   [Turning off dry run](#turning-off-dry-run).
8. **Turn off dry run**, then run the [verification](#verification) checks
   with real clients.
9. **Renovate.** Add the repository secret described in
   [Renovate](#renovate) before the next scheduled run.
10. **Switch clients.** Only once the proxy is verified live, activate the
    proxy-by-default client configuration from `nix-config` and the live
    `~/.codex/config.toml`; the `claude-direct` and `codex-direct` fallbacks
    bypass it.

## Logging in accounts

Open the dashboard at `http://ai-dev:8317/management.html` and sign in with the
management key, `cliproxy_management_secret` in the vault (from `ansible/`,
`ansible-vault view group_vars/secrets.yaml --vault-password-file .vaultpass`
shows it). Its **OAuth Login** page has **Start Anthropic Login** and
**Start Codex Login**. Open the authorization link, sign in to the account you
are adding, and wait for the browser to land on a `http://localhost:...`
callback page that fails to load: the callback listener runs on ai-dev, not on
your machine. Copy that full URL into **Callback URL**, choose
**Submit Callback URL**, and wait for the success message. Repeat once per
account, signing out of the provider between accounts so each login picks a
different one.

The same logins work over SSH, run as the service user so the credential file
lands in CPA's auth directory with the right owner:

```sh
sudo -u cliproxy /usr/local/bin/cli-proxy-api \
  -config /etc/cliproxy/config.yaml -claude-login -no-browser
sudo -u cliproxy /usr/local/bin/cli-proxy-api \
  -config /etc/cliproxy/config.yaml -codex-device-login
```

The Claude login prints an authorization URL; after signing in, paste the
`http://localhost:54545/callback?...` URL the browser ends on when the command
asks for it. The Codex device login prints a code to enter at the provider's
device page. CPA picks up each new credential file without a restart.

Every Codex credential needs `"websockets": true`; the controller sets it once
it runs, and the dashboard shows it per credential.

## Retiring Hermes

The ai-dev role no longer installs or manages Hermes, and the firewall change
already cuts its tailnet egress. The account, its files and its services stay
on the live host until an explicit decommission run removes them:

```sh
cd ansible
ansible-playbook run.yaml --vault-password-file .vaultpass --limit ai-dev \
  --tags hermes-decommission -e ai_dev_hermes_decommission=true
```

It stops and disables the `hermes*.service` and `moshi-hook.service` user
units, disables linger, ends any remaining `hermes` session and process,
removes the account with its home and group, removes the management user's
`hermes-maintenance` command and the `hermes` mosh timeout drop-in, and
restarts `sshd`. Every step is idempotent, so a rerun after a partial failure
finishes the job, and a run without the variable changes nothing. The
management user's SSH, Mosh and Herdr access is untouched; restarting `sshd`
does not drop existing sessions. Add `--check --diff` first to preview it.

Then revoke the agent's credentials, which this repository no longer holds:

- the Proxmox API token with `PVEAuditor` (Datacenter, Permissions, API
  Tokens), and the dedicated user behind it if nothing else uses it;
- the fine-grained GitHub token scoped to this repository (Settings,
  Developer settings, Fine-grained tokens).

Remove the `hermes` host from the Moshi app as well. The docker-host observer
and media broker keep running unchanged with no consumer; see
[`docs/hermes-media.md`](hermes-media.md).

## Operating it

```sh
systemctl status cliproxy cliproxy-controller
journalctl -u cliproxy -f
journalctl -u cliproxy-controller -f
curl -fsS http://127.0.0.1:8317/healthz
curl -fsS http://127.0.0.1:8318/healthz
```

The controller logs one JSON object per line; `routing order changed`,
`credential patched` and `usage poll failed` are the messages to watch. Its
status page is at `http://ai-dev:8318/` and asks for the management key, which
it keeps only in that browser tab.

To rotate the management key, replace `cliproxy_management_secret` in the vault
and run the play with `--tags cliproxy`; it rewrites CPA's configuration and the
controller's key file and restarts both. Reload the dashboard and status page
afterwards.

Upgrades arrive as Renovate pull requests that bump a version and its checksum
together. After merging one, run the play with `--tags cliproxy`.

### Turning off dry run

The controller starts with `CONTROLLER_DRY_RUN=true`: it reads credentials,
polls usage and drains the usage queue, but logs the priority changes it would
make instead of sending them. Before turning it off, check that:

- `journalctl -u cliproxy-controller` shows `dry run: would patch credential`
  lines whose order matches each account's weekly reset times;
- the status page lists every credential with a fresh usage read, and no
  `usageError`, `lastCredentialsError` or `lastQueueError`.

Then set `cliproxy_controller_dry_run: false` in
`ansible/group_vars/ai_dev.yaml`, commit it, and run the play with
`--tags cliproxy`. The status page shows the controller's dry-run state, and
`credential patched` lines replace the dry-run ones.

### Renovate

The self-hosted Renovate workflow also runs on `mich-murphy/cliproxy-controller`,
so `RENOVATE_TOKEN` needs the same access to that repository as it has to this
one. The controller pin is read through the GitHub releases API with a
separate repository secret, `CLIPROXY_CONTROLLER_RELEASES_TOKEN`: a
fine-grained token with read-only Contents access to
`mich-murphy/cliproxy-controller` alone. Add it before Renovate's next run.

## Verification

The ai-dev role asserts hostname, Tailscale preferences, the nftables ruleset
and the `sshd` forwarding options on every run, and the cliproxy role waits for
both services' health endpoints, so the checks below are only the ones nothing
enforces automatically.

On the guest, check identity, network placement and containment:

```sh
tailscale status
ip -brief address show
ip route
ss -ltn 'sport = :8317 or sport = :8318'
```

The guest must have one address on the DMZ interface named by
`ai_dev_physical_interface`, no route to internal VLANs, and no
physical-interface IPv6 address. Test that HTTPS and gateway DNS work, while
new connections to MGMT, SRV, DFLT, KDS, GST, other DMZ hosts, and tailnet
peers fail. From a tailnet device outside the proxy grant, TCP 8317 and 8318
must be refused; from an approved one, `curl http://ai-dev:8317/healthz`
answers.

With clients pointed at the proxy, check the end-to-end behaviour:

- `codex doctor` reports WebSocket support, with no "falling back to HTTP"
  warning.
- `journalctl -u cliproxy` shows `responses websocket: client connected` and
  `codex websockets: upstream connected ... reused=true` while Codex runs.
- `claude -p hi --output-format json` reports `ephemeral_1h_input_tokens`.
- The controller status page shows a high cache hit rate, with
  `cache_read_tokens` growing per credential across turns of one session.
- The status page shows every credential with a fresh usage read, CPA's order
  in sync, and WebSocket on every Codex credential.

### Proxmox DMZ NIC reliability

The Proxmox `eno1` NIC uses the `e1000e` driver.
Transmit queue hangs on that interface leave the physical carrier up while
disconnecting `vmbr1` guests from the DMZ gateway. The guest then retains its
DHCP address and default route, but ARP for the DMZ gateway remains incomplete and
Tailscale reports `ai-dev` offline.

Keep TCP segmentation offload disabled on the physical interface. Proxmox
`/etc/network/interfaces` must contain:

```text
iface eno1 inet manual
    post-up /usr/sbin/ethtool -K eno1 tso off
```

After changing the hook, apply it live with
`ethtool -K eno1 tso off`. If the transmit queue is already wedged, reset only
the isolated DMZ link with `ip link set dev eno1 down` followed by
`ip link set dev eno1 up`; Proxmox management remains on `eno2`/`vmbr0`.

Verify recovery from Proxmox and an approved tailnet device:

```sh
journalctl -k -g 'eno1: Detected Hardware Unit Hang'
qm guest exec 110 -- /usr/bin/ping -c 3 1.1.1.1
tailscale ping ai-dev
curl -fsS http://ai-dev:8317/healthz
```

The first command may show historical events from the current boot, but its
latest timestamp must not advance after TSO is disabled and the link is reset.

From an unapproved tailnet device, TCP 22 and UDP 60000-61000 must be denied.
From the approved phone, verify key-based OpenSSH, Mosh and SSH fallback,
Wi-Fi/cellular roaming, and persistent Herdr panes.

## References

- [CLIProxyAPI](https://github.com/router-for-me/CLIProxyAPI)
- [CLIProxyAPI management dashboard (CPAMC)](https://github.com/router-for-me/Cli-Proxy-API-Management-Center)
- [Moshi over Tailscale](https://getmoshi.app/docs/tailscale)
- [Moshi connections](https://getmoshi.app/docs/connections)
- [Moshi with Herdr](https://getmoshi.app/docs/herdr)
- [Tailscale grants syntax](https://tailscale.com/docs/reference/syntax/grants)
- [systemd credentials](https://systemd.io/CREDENTIALS/)
