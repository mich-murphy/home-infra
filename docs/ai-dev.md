# AI development VM

`ai-dev` is the single AI development VM. It retains Proxmox VMID 110 and its
150 GB disk, with 4 CPU cores, fixed 5 GiB RAM, and an 8 GiB disk-backed
swapfile with a bounded zswap cache. Its only NIC is on the physical `vmbr1`
DMZ.

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

Moshi connects to the guest's normal OpenSSH server through Tailscale, then
uses Mosh's per-connection UDP server when the network permits it. Herdr is the
only persistent multiplexer and retains its shared `Ctrl-A` prefix.
`Ctrl+Shift+L` is encoded as F12 by a supporting terminal, forwarded by Herdr,
and bound by Fish to clear the focused pane.

## Deployment

The existing guest initially advertises the old `ai-dev-bgd` MagicDNS name. For
the first Ansible run only, temporarily set the inventory line to:

```ini
ai-dev ansible_host=ai-dev-bgd ansible_user=michael
```

Run the AI host play, verify that Linux and Tailscale both advertise `ai-dev`,
then restore the committed inventory line without `ansible_host`. Do not leave
the migration alias in steady state.

Before planning or applying Terraform, rotate any Tailscale authentication key
that was rendered into an old local cloud-init file. Remove the old
`terraform/files/ai-dev-bc.cfg` and `terraform/files/ai-dev-bgd.cfg` files after
rotation. They are ignored generated artifacts and must not be treated as a
credential store.

Run:

```sh
cd terraform
terraform fmt -check -recursive
terraform validate
terraform plan
```

The plan must report the address move from
`module.ai_dev["ai-dev-bgd"]` to `module.ai_dev`, followed by an in-place rename
and CPU/memory update. Stop if VMID 110 or its disk would be destroyed or
replaced.
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
just routeros
```

The ai-dev role clones the public `nix-config` repository to
`/home/michael/dev/nix-config`, fast-forwards it to `origin/main`, builds
`homeConfigurations."michael@ai-dev"`, and activates it as `michael`. A
non-fast-forward checkout or conflicting local change stops deployment.
Check mode builds the activation package but never activates it.

Home Manager is the steady-state owner of the shared shell, CLI environment,
and Moshi user unit. Ansible owns and deploys the ai-dev maintenance command,
builds the desired Home Manager activation package, compares it with the
current generation, and activates only when they differ. It then runs
`ai-dev-maintenance ensure-present`, which repairs missing tools without
updating installed tools. A second live run must report no changes when neither
repository's configuration has changed.

## Interactive setup

Home Manager owns OpenCode and the shared Fish, Starship, FZF, general Git
behavior, Hunk, Herdr, Yazi, and portable CLI configuration. Ansible deploys
`ai-dev-maintenance`, writes ai-dev's vaulted personal and BusinessCraft
identity fragments with mode `0600`, and selects the BusinessCraft fragment
below `~/businesscraft/`; the Mac retains its separate Home Manager-owned
identities.

Run ongoing coding-agent updates deliberately on ai-dev:

```sh
ai-dev-maintenance update
ai-dev-maintenance status
```

The update command runs the official stable installers for Claude Code, Codex,
Pi, Herdr, and Moshi independently, updates the declared Pi packages,
reconciles Herdr before Moshi integrations, and reports all failures together.
Its implementation and ai-dev package inventory live in the Ansible role that
deploys it. Hermes is deliberately absent: it belongs to the separate `hermes`
account described below, not to the management user's toolchain.
The status command is read-only. Ansible does not copy SSH keys, OAuth sessions,
or API keys. Authenticate each tool interactively:

```sh
gh auth login --hostname github.com --web --git-protocol ssh
claude
codex login --device-auth
pi
opencode auth login
```

Authenticate the GitHub CLI as both required GitHub accounts. Before running
GitHub CLI operations for a repository under `~/businesscraft/`, select the
BusinessCraft account explicitly:

```sh
gh auth switch --hostname github.com --user michaelmbc
gh auth status --hostname github.com
```

Use `/login` inside Pi if it does not prompt automatically. Select a headless or
device-code provider flow when OpenCode offers one.

Install Moshi on the approved phone, enable Tailscale, and run:

```sh
moshi-hook host setup
moshi-hook pair --token <token-from-Moshi-Hooks-settings>
systemctl --user restart moshi-hook
moshi-hook install
```

Scan the Easy Pair QR, save the MagicDNS host as `ai-dev`, and leave connection
mode on `Auto`. The gateway must remain on `127.0.0.1:24543`; OpenSSH permits
local TCP forwarding but disables gateway and Unix-socket forwarding.

`ai-dev-maintenance` installs Herdr integrations before Moshi integrations so
their entries coexist. Check the complete toolchain and loopback-only Moshi
runtime after authentication:

```sh
ai-dev-maintenance status
```

Moshi's OpenCode hook is project-local. The maintenance command installs it in
the home workspace; run `moshi-hook install` once from each existing OpenCode
project root that should emit events. This repository does not inventory
untracked projects on the VM.

Moshi's full agent integration sends limited notification summaries, approval
details, metadata, pairing, and WebSocket control traffic through Moshi's
service. Terminal traffic, source files, transcripts, and diffs remain direct.

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
long and the install is the largest on the VM. ai-dev installs the Docker
client for `DOCKER_HOST` queries but masks `docker.service` and
`docker.socket`; it must never run a daemon of its own.

### Access tiers

The agent observes broadly, acts narrowly, and proposes everything else.

| Tier | Reach | Mechanism |
| --- | --- | --- |
| Observe | Proxmox cluster and guest state | `PVEAuditor` API token |
| Observe | Containers, logs, stats, events | Read-only socket proxy |
| Propose | Any change to this repository | GitHub token, pull request only |
| Act | Nothing on a running host | Deliberately absent |

No credential the agent holds can change a running host. Remediation happens
by pull request, which `main`'s branch protection forces through review, and
which Portainer then deploys. A merge is the supervision that a watched SSH
session used to provide.

### Provisioning the credentials

Mint the Proxmox audit identity on the hypervisor. `PVEAuditor` is read-only by
construction, and privilege separation keeps the token's grant explicit:

```sh
ssh root@proxmox
pveum user add hermes-audit@pve --comment 'Read-only audit for ai-dev Hermes'
pveum acl modify / --users hermes-audit@pve --roles PVEAuditor
pveum user token add hermes-audit@pve ai-dev --privsep 1
pveum acl modify / --tokens 'hermes-audit@pve!ai-dev' --roles PVEAuditor
```

The token value prints once. Create the GitHub token in the GitHub UI, because
fine-grained tokens cannot be minted through the API: scope it to
`mich-murphy/home-infra` alone, grant Contents and Pull requests read/write,
and grant nothing else. Then store both in the vault:

```sh
cd ansible
ansible-vault edit group_vars/secrets.yaml --vault-password-file .vaultpass
```

```yaml
hermes_proxmox_token_id: "hermes-audit@pve!ai-dev"
hermes_proxmox_token_secret: "<token value>"
hermes_github_token: "<fine-grained token>"
```

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

Each account runs its own Herdr and Moshi. Pair Moshi separately for `hermes`
if the agent should reach the phone; the management user's pairing does not
carry across, and that separation is intentional. Pairing provisions its own
key, so connecting the phone to the agent account means running the pairing
flow again as `hermes`, not copying a key between accounts:

```sh
ssh hermes@ai-dev
moshi-hook host setup
moshi-hook pair --token <token-from-Moshi-Hooks-settings>
systemctl --user restart moshi-hook
```

Authorizing the operator key grants a human entry into the agent account. It
grants the agent nothing: no key on the agent's side reaches the management
user, whose home stays mode `0750`.

### Operating it

```sh
hermes setup
hermes --version
hermes update
```

Ansible installs the agent but does not update it; `hermes update` follows
`origin/main` of the upstream repository. That is an unpinned, self-updating
code path, which is acceptable on a disposable DMZ guest and is a reason the
agent lives here rather than on docker-host.

### Known exposure

The Docker socket proxy filters which requests are allowed, not what the
answers contain. `GET /containers/{id}/json` returns a container's environment
block, so the agent can read the Cloudflare DNS token, the Pocket ID
encryption key, and application API keys on docker-host. Removing that
exposure means moving those values out of Compose `environment:` entries, not
tightening the proxy. Treat the agent's credentials as revocable and rotate
them if ai-dev is ever suspect: delete the Proxmox token with
`pveum user token remove hermes-audit@pve ai-dev`, and revoke the GitHub token
in the GitHub UI.

## Agent scratch space

`/tmp` is a RAM-backed tmpfs carrying a per-user hard limit of 80% of its size
(1153 MiB at 4 GB RAM). Agent scratch exhausts that limit while `df` still shows
free space, and writes then fail with `EDQUOT`, which Node reports as the
unmapped `Unknown system error -122, write`.

Home Manager therefore sets `TMPDIR=/var/tmp/michael` for shells, and Ansible
sets the same value in `~/.config/environment.d/10-ai-dev-scratch.conf` for the
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
An Ansible-managed site plugin outside that checkout, at
`~/.local/share/nvim/site/plugin/osc52.lua`, uses Neovim's built-in OSC 52 copy
function and makes normal yanks use the system clipboard. Its paste callback
returns the last local yank immediately because remote terminals commonly block
OSC 52 clipboard reads, which would otherwise pause Neovim for up to ten
seconds. The plugin also reapplies `unnamedplus` after LazyVim's deferred
`VeryLazy` clipboard reset for SSH sessions. Use the terminal's paste action to
insert device clipboard content. This exception remains until the Neovim/Mason
package skip configuration is repaired separately.

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
its own.

```json
{
  "hosts": {
    "docker-host": "100.96.174.126",
    "proxmox": "100.106.15.105"
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

## Verification

On the guest, verify identity, network placement, containment, and services:

```sh
hostnamectl --static
tailscale status
sudo tailscale debug prefs
ip -brief address show ens18
ip route
sudo nft list ruleset
sudo sshd -T | grep -E '^(allowtcpforwarding local|gatewayports no)$'
systemctl --user status moshi-hook
ss -ltn 'sport = :24543'
command -v nvim stylua gopls marksman
fish -lc 'echo $TMPDIR'
systemctl --user show-environment | grep '^TMPDIR='
fish -c 'type -p opencode hunk yazi btop bat direnv'
nvim --headless \
  '+lua print(vim.g.clipboard.name, vim.o.clipboard)' \
  +qa
```

The guest must have one `ens18` address in `10.77.99.0/24`, no route to internal
VLANs, no physical-interface IPv6 address, and no listener for port 24543 except
`127.0.0.1`. Test that HTTPS and gateway DNS work, while new connections to
MGMT, SRV, DFLT, KDS, GST, other DMZ hosts, and tailnet peers fail.

Both `$TMPDIR` checks must report `/var/tmp/michael`, and that directory must be
mode `0700` and owned by `michael`.

Neovim and its temporary editor tools must resolve from `/usr/bin`; shared CLI
tools and OpenCode must resolve from the Home Manager profile. Confirm Fish
colours, the F12 clear binding, Starship, FZF, Git, Hunk, Herdr, Yazi, btop,
bat, and direnv match the Mac behavior. The shared instruction and skill links
must exist under `.claude`, `.codex`, `.pi`, and `.agents`. Existing OpenCode
authentication/plugins and all existing `~/.config/nvim` modifications must
remain intact. The Neovim clipboard check must report `OSC 52 (copy only)` and
include `unnamedplus`.

Herdr does not watch its live configuration. After changing
`~/dev/nix-config/config/herdr/config.toml`, run
`herdr server reload-config` in each active session that should receive the
new settings.

### Proxmox DMZ NIC reliability

The X13SAE-F's Intel I219-LM uses the `e1000e` driver for Proxmox `eno1`.
Transmit queue hangs on that interface leave the physical carrier up while
disconnecting `vmbr1` guests from the DMZ gateway. The guest then retains its
DHCP address and default route, but ARP for `10.77.99.1` remains incomplete and
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

The BusinessCraft test must report `michaelmbc` and the vaulted BusinessCraft
email. The personal test must report `Michael Murphy` and the vaulted personal
email.

## References

- [Moshi over Tailscale](https://getmoshi.app/docs/tailscale)
- [Moshi connections](https://getmoshi.app/docs/connections)
- [Moshi agent hooks](https://getmoshi.app/docs/hooks)
- [Moshi with Herdr](https://getmoshi.app/docs/herdr)
- [Herdr integrations](https://herdr.dev/docs/integrations/)
- [Tailscale grants syntax](https://tailscale.com/docs/reference/syntax/grants)
