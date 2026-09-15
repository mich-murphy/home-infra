# AI development VM

`ai-dev` is the single AI development VM. Its only NIC is on the physical
`vmbr1` DMZ, and it carries an 8 GiB disk-backed swapfile with a bounded zswap
cache. `terraform/main.tf` holds its current spec.

The supported remote path is:

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

## Deployment

Generated cloud-init files under `terraform/files/` are ignored build
artifacts, not a credential store: rotate any Tailscale authentication key that
was rendered into one.

Before an approved Terraform run, create two distinct, short-lived, tagged,
single-use fields in the existing 1Password `proxmox_creds` item under the
`Terraform SCP` section: `tailscale docker-host authkey` and `tailscale ai-dev
authkey`. Do not reuse the old shared `tailscale authkey` field. The fields must
be present before `terraform plan` can render either guest's vendor data; this
repository does not create or revoke keys.

If bootstrap fails, inspect cloud-init status and the guest's Tailscale state
without retrying blindly. A key that was consumed, exposed in logs/artifacts,
expired, or is no longer needed must be revoked in the Tailscale admin console
and replaced with a newly scoped key in the matching 1Password field. Record
which guest was affected, remove stale generated files, and rerun only after the
new field is available. On expiry or revocation, expect that guest to require
an explicit rejoin; never copy the other guest's key as a recovery shortcut.

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

Then stage the guest and router changes:

```sh
cd ansible
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit ai-dev --check --diff
ansible-playbook run.yaml --vault-password-file .vaultpass --limit ai-dev
ansible-playbook run.yaml --vault-password-file .vaultpass --limit ai-dev
cd ..
(cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass --limit routeros --tags services,oob,vlans,dmz,dhcp,firewall,bridge,vlan-filtering,default-drop,verify -e routeros_enable_vlan_filtering=true -e routeros_enable_default_drop=true)
```

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

The ai-dev role builds and activates Home Manager from the public `nix-config`
repository. A non-fast-forward checkout or conflicting local change stops
deployment; check mode builds the activation package but never activates it.

Home Manager is the steady-state owner of the shared shell, CLI environment,
and Moshi user unit. Ansible owns and deploys the ai-dev maintenance command,
builds the desired Home Manager activation package, compares it with the
current generation, and activates only when they differ. It then runs
`ai-dev-maintenance ensure-present`, which repairs missing tools without
updating installed tools. A second live run must report no changes when neither
repository's configuration has changed.

## Interactive setup

Home Manager owns the portable CLI configuration. Ansible deploys
`ai-dev-maintenance` and writes the vaulted git identity fragments, selecting
the BusinessCraft one below `~/businesscraft/`.

Run ongoing coding-agent updates deliberately on ai-dev:

```sh
ai-dev-maintenance update
ai-dev-maintenance status
```

The update command runs the official stable installers for Claude Code, Codex,
Pi, Herdr, and Moshi independently, reconciles Herdr before Moshi
integrations, and reports all failures together. Its implementation lives in
the Ansible role that deploys it. Hermes is deliberately absent: it belongs to
the separate `hermes` account described below, not to the management user's
toolchain.
The status command is read-only. Ansible does not copy SSH keys, OAuth sessions,
or API keys. Authenticate each tool interactively:

```sh
gh auth login --hostname github.com --web --git-protocol ssh
claude
codex login --device-auth
pi
```

Authenticate the GitHub CLI as both required GitHub accounts. Before running
GitHub CLI operations for a repository under `~/businesscraft/`, select the
BusinessCraft account explicitly:

```sh
gh auth switch --hostname github.com --user <businesscraft-account>
gh auth status --hostname github.com
```

Use `/login` inside Pi if it does not prompt automatically.

Pair Moshi from the phone with `moshi-hook host setup` and `moshi-hook pair`.
The gateway must remain on `127.0.0.1:24543`: OpenSSH permits local TCP
forwarding but disables gateway and Unix-socket forwarding.

## Hermes infrastructure agent

Hermes manages infrastructure, and it reads input nobody controls: web pages
through its bundled browser, and container logs, which are strings written by
whatever produced them. It therefore runs as its own `hermes` account, not as
the management user. `/home/michael` is mode `0750`, so the agent cannot read
the management user's GitHub tokens, SSH keys, or Claude and Codex sessions.
That separation is the point: scoping the agent's own credentials achieves
nothing while broader credentials sit beside it in the same home directory.

Ansible owns the account, installs the agent with `--skip-setup`, and deploys
its credentials. The installer clones `NousResearch/hermes-agent` into
`~/.hermes/hermes-agent`, builds a uv virtualenv, links `~/.local/bin/hermes`,
and pulls a Hermes-managed Node and a Playwright browser, so the first run is
long and the install is the largest on the VM.

ai-dev carries no Docker client. The observer speaks plain HTTP, so the
agent queries it directly, and `DOCKER_HOST` records the endpoint. Installing
the client would drag in `containerd` and `runc`, about 100 MiB of container
runtime on a guest with no reason to carry it. Nothing here prevents
installing one later; the agent simply does not need it.
The endpoint is intentionally a reduced status projection rather than a
Docker API: it supports only ping, version, container listing, and strict-name
or ID inspection, and bounded tail-only container logs (no follow). It returns
safe IDs, names, image references, state, status, exit codes, health status,
and demultiplexed container log text. It does not support stats, events,
archive operations, or full `docker inspect`; commands depending on those
routes must use an approved, separately protected diagnostic path.

### Access tiers

The agent observes broadly, acts narrowly, and proposes everything else.

| Tier | Reach | Mechanism |
| --- | --- | --- |
| Observe | Proxmox cluster and guest state | `PVEAuditor` API token |
| Observe | Sanitized container status | Read-only Docker observer |
| Propose | Any change to this repository | GitHub token, pull request only |
| Act | Nothing on a running host | Deliberately absent |

No credential the agent holds can change a running host. Remediation happens
by pull request, which `main`'s branch protection forces through review, and
which Portainer then deploys. A merge is the supervision that a watched SSH
session used to provide.

### Provisioning the credentials

Two credentials are minted by hand and kept in the Ansible vault: a Proxmox
API token holding `PVEAuditor` with privilege separation, which is read-only by
construction, and a fine-grained GitHub token scoped to this repository alone
with Contents and Pull requests read/write and nothing else. Fine-grained
tokens cannot be minted through the API, so that one is created in the GitHub
UI. `ansible/roles/ai-dev/defaults/main.yaml` names the vault keys the role
reads.

The play installs the agent without these and reports their absence, so the
host can be provisioned before the tokens exist. With them present it writes
`~hermes/.config/hermes/env` at mode `0600`, sourced from the account's
`.profile`.

### Reaching the agent

The account is a normal login. Ansible authorizes the same operator key that
reaches the management user and enables linger, so the account can hold its
own persistent Herdr and Moshi services. Either path works:

```sh
ssh hermes@ai-dev          # dedicated session, own Herdr and Moshi
sudo -u hermes -i          # from an existing management-user pane
```

Prefer the dedicated SSH session when the agent should keep long-running work
alive independently of the management user's Herdr, which is the usual case
for infrastructure monitoring. Use `sudo -u hermes -i` for a quick look from a
pane that is already open.

Each account runs its own Herdr and Moshi, both installed by the role.
Reaching the phone from the agent account means running the same pairing flow
again as `hermes`, not copying a key across; that separation is intentional.

Authorizing the operator keys grants a human entry into the agent account. It
grants the agent nothing: no key on the agent's side reaches the management
user, whose home stays mode `0750`.

Two keys are authorized, and the second one matters. SSH offers the keys held
in the 1Password agent before any key sitting on disk, and `MaxAuthTries` is
6. Authorizing only the on-disk operator key means the agent's six keys are
offered and refused first, and the connection is dropped as
`Too many authentication failures` before the right key is ever tried.
Authorizing a key the agent holds avoids relying on client-side
`IdentitiesOnly`.

### First run

Ansible installs the agent, Herdr and Moshi, and deploys the scoped
credentials. Three steps stay manual because each is interactive or
secret-bearing.

Give the agent a model. Its `.env` ships as a blank template, so it has no
provider key until the wizard runs:

```sh
ssh hermes@ai-dev
hermes setup
hermes doctor
```

Pair the phone to this account. The management user's pairing does not carry
across:

```sh
moshi-hook host setup
moshi-hook pair --token <token-from-Moshi-Hooks-settings>
systemctl --user enable --now moshi-hook.service
```

Ansible stops short of starting that service. An unpaired account has no
credential for it, so starting it early either fails the play or leaves a unit
crash-looping where a later real failure would hide. Linger is already on, so
enabling it once after pairing survives logout.

In Moshi, add a second host: MagicDNS name `ai-dev`, username `hermes`,
connection mode `Auto`.

Start work inside Herdr so a dropped connection does not kill the session:

```sh
herdr new infra
hermes chat
```

### Operating it

```sh
hermes --version
hermes update
moshi-hook status
```

Ansible installs the agent but does not update it; `hermes update` follows
`origin/main` of the upstream repository. That is an unpinned, self-updating
code path, which is acceptable on a disposable DMZ guest and is a reason the
agent lives here rather than on docker-host.

### Known exposure

The observer is deliberately narrower than the Docker API. Its fixed backend
is not exposed and is the only service with a read-only Docker socket mount;
the observer projects fields instead of relaying Docker responses. It resolves
the backend once before serving requests, so a backend address change requires
an observer reconciliation/restart; a stale or unavailable backend fails closed
with a generic response. This does not make status values trustworthy: names,
image references, status text, and
health status are written by workloads and should be treated as untrusted
input. Treat the agent's credentials as revocable: delete the Proxmox token
and revoke the GitHub token if ai-dev is ever suspect.

### Optional media-broker connection

The production deployment is documented in
[`docs/hermes-media.md`](hermes-media.md). The Hermes media-broker MCP
connection is opt-in and disabled in the role defaults. The live ai-dev host
group explicitly enables it. When enabled, Ansible adds only the managed `mcp_servers.media_broker`
entry and `MEDIA_BROKER_TOKEN` reference in `~/.hermes/.env`; it preserves the
Photon, Moshi, and other MCP settings. The operator-supplied token must be a
single-line 32-256 character URL-safe value (`A-Z`, `a-z`, `0-9`, `_`, or `-`).
It is never generated, logged, or copied into YAML. An unowned same-name entry fails
closed unless an operator explicitly enables the takeover setting. Disabling
removes only the managed entry and token, without requiring the token variable.

The live endpoint is `http://docker-host:8765/mcp`, reached over Tailscale.
The sanitized Docker observer, broker, and source-pinned access controls have
been deployed and tested. Backend keys stay on docker-host in restricted
files. The broker uses a 5 MiB response bound for the observed 2.27 MB Lidarr
inventory. Ansible does not restart the Hermes gateway. After subsequent
approved configuration changes, restart the Hermes user service explicitly
and verify its four read-only tools.

## Agent scratch space

`/tmp` is a RAM-backed tmpfs carrying a per-user hard limit of 80% of its
size. Agent scratch exhausts that limit while `df` still shows
free space, and writes then fail with `EDQUOT`, which Node reports as the
unmapped `Unknown system error -122, write`.

Home Manager therefore sets `TMPDIR` to a disk-backed path under the
management user's `/var/tmp` for shells, and Ansible sets the same value in `~/.config/environment.d/10-ai-dev-scratch.conf` for the
lingering systemd user manager. Ansible also provisions the directory plus
`/etc/tmpfiles.d/ai-dev-scratch.conf`, which ages the scratch root at 10d and
reaps leftover Claude, Bun, and Pi scratch at 2d. Do not raise the quota
instead; that keeps gigabytes of scratch in RAM.

Existing Herdr panes retain the environment with which their shells started.
After first deploying this setting, replace the shell in each idle pane with
`exec fish`. To refresh every pane at once, stop and restart Herdr at a
controlled time; stopping the server exits its pane processes. New shells then
inherit the disk-backed `TMPDIR`:

```sh
exec fish
# Or, when every pane can be stopped:
herdr server stop
herdr
```

`quota` and `repquota` are not installed, so read the live limit through
`quotactl_fd`:

```sh
python3 - <<'EOF'
import ctypes, os, struct
libc = ctypes.CDLL("libc.so.6", use_errno=True)
fd = os.open("/tmp", os.O_RDONLY | os.O_DIRECTORY)
buf = ctypes.create_string_buffer(72)
libc.syscall(443, fd, 0x80000700, os.getuid(), buf)  # quotactl_fd Q_GETQUOTA/USRQUOTA
hard, _, used = struct.unpack("<3Q", buf.raw[:24])
print(f"/tmp user quota: {hard * 1024 // 2**20} MiB limit, {used // 2**20} MiB used")
EOF
```

Attribute usage with `du -shx /tmp/* | sort -h | tail` and delete stale session
scratch directories.

## Neovim exception

Neovim remains deliberately outside Home Manager on ai-dev. Pacman owns
`/usr/bin/nvim` and the temporary editor LSP/formatter packages. Ansible clones
the public Neovim configuration into `~/.config/nvim` only when it is missing,
with updates disabled; it never pulls, resets, or edits an existing checkout.
An Ansible-managed site plugin outside that checkout,
`~/.local/share/nvim/site/plugin/osc52.lua`, routes yanks through OSC 52; its
own comments explain why paste is served from the local yank cache. Use the
terminal's paste action to insert device clipboard content.

## Tailnet policy

The tailnet policy is managed outside this repository. Give only approved user
and iOS device selectors permission to initiate OpenSSH and Mosh traffic:

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

Replace `group:ai-dev-users` with the tailnet's approved selectors. Grants are
additive, so a broader existing grant can defeat this containment.

The Hermes agent requires the single exception below: ai-dev as a source,
reaching one read-only port on docker-host and the Proxmox API. Keep it this
narrow. Any wider grant with `tag:ai-dev` as a source erases the separation the
guest exists to provide.

Both destinations are tagged devices (`tag:proxmox` and `tag:server`), but the
grants below scope by host rather than by tag: `tag:server` covers more than
docker-host, and this guest should reach exactly one machine on that port. Name
them in the `hosts` block, since a bare hostname in `dst` does not resolve on
its own. Read each address with `tailscale ip -4 <host>`; they are deliberately
not recorded here, because this repository is public.

```json
{
  "hosts": {
    "docker-host": "<tailscale ip -4 docker-host>",
    "proxmox": "<tailscale ip -4 proxmox>"
  },
  "grants": [
    {
      "src": ["tag:ai-dev"],
      "dst": ["docker-host"],
      "ip": ["tcp:2375"]
    },
    {
      "src": ["tag:ai-dev"],
      "dst": ["proxmox"],
      "ip": ["tcp:8006"]
    }
  ]
}
```

The Docker port is pinned a second time in docker-host's `DOCKER-USER` chain,
so a mistake in this policy alone does not expose the Docker API.

The tailnet policy is necessary but not sufficient. ai-dev's own nftables
output chain drops the whole `100.64.0.0/10` range, so the guest cannot
initiate a tailnet session even where a grant permits it. The two endpoints
above are the only exceptions, alongside MagicDNS and the telemetry collector,
and the ai-dev role asserts that the blanket drop survives beside them. Adding
a grant without the matching egress rule produces a connection that times out
with no obvious cause.

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

## Verification

On the guest, verify identity, network placement, containment, and services:

The ai-dev role already asserts hostname, Tailscale preferences, the nftables
ruleset and the `sshd` forwarding options on every run, so the checks below are
only the ones nothing enforces automatically:

```sh
tailscale status
ip -brief address show
ip route
systemctl --user status moshi-hook
ss -ltn 'sport = :24543'
command -v nvim stylua gopls marksman
fish -c 'type -p hunk yazi btop bat direnv'
nvim --headless \
  '+lua print(vim.g.clipboard.name, vim.o.clipboard)' \
  +qa
```

The guest must have one address on the DMZ interface named by
`ai_dev_physical_interface`, no route to internal VLANs, no physical-interface
IPv6 address, and no listener for port 24543 except `127.0.0.1`. Test that HTTPS and gateway DNS work, while new connections to
MGMT, SRV, DFLT, KDS, GST, other DMZ hosts, and tailnet peers fail.

Neovim and its temporary editor tools must resolve from `/usr/bin`; shared CLI
tools must resolve from the Home Manager profile. Confirm Fish, Starship, FZF,
Git, Hunk, Herdr, Yazi, btop, bat, and direnv match the Mac behavior. The
shared instruction and skill links must exist under `.claude`, `.codex`,
`.pi`, and `.agents`. All existing `~/.config/nvim` modifications must remain
intact. The Neovim clipboard check must report `OSC 52 (copy only)` and
include `unnamedplus`.

Herdr does not watch its live configuration. After changing
`~/dev/nix-config/config/herdr/config.toml`, run
`herdr server reload-config` in each active session that should receive the
new settings.

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
ssh michael@ai-dev 'herdr status server'
```

The first command may show historical events from the current boot, but its
latest timestamp must not advance after TSO is disabled and the link is reset.

From an unapproved tailnet device, TCP 22 and UDP 60000-61000 must be denied.
From the approved phone, verify key-based OpenSSH, Mosh and SSH fallback,
Wi-Fi/cellular roaming, persistent Herdr panes, agent inbox and approval events,
deep links, and direct OSC52 clipboard copying.

Finally, verify the shared Git identities:

```sh
mkdir -p ~/businesscraft/identity-test ~/personal-identity-test
git -C ~/businesscraft/identity-test init
git -C ~/personal-identity-test init
git -C ~/businesscraft/identity-test config user.name
git -C ~/businesscraft/identity-test config user.email
git -C ~/personal-identity-test config user.name
git -C ~/personal-identity-test config user.email
```

The BusinessCraft test must report the BusinessCraft account and its vaulted
email. The personal test must report the personal identity and the vaulted
email.

## References

- [Moshi over Tailscale](https://getmoshi.app/docs/tailscale)
- [Moshi connections](https://getmoshi.app/docs/connections)
- [Moshi agent hooks](https://getmoshi.app/docs/hooks)
- [Moshi with Herdr](https://getmoshi.app/docs/herdr)
- [Herdr integrations](https://herdr.dev/docs/integrations/)
- [Tailscale grants syntax](https://tailscale.com/docs/reference/syntax/grants)
