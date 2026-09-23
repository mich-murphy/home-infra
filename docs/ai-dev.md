# ai-dev

`ai-dev` is the isolated DMZ guest. Its only NIC is on the physical
`vmbr1` DMZ, and it carries an 8 GiB disk-backed swapfile with a bounded zswap
cache. `terraform/main.tf` holds its current spec. Its sole workload is the
Hermes infrastructure agent, running under the dedicated `hermes` account
described below.

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

## Hermes infrastructure agent

Hermes manages infrastructure, and it reads input nobody controls: web pages
through its bundled browser, and container logs, which are strings written by
whatever produced them. It therefore runs as its own `hermes` account, not as
the management user. `/home/michael` is mode `0750`, so the agent cannot read
the management user's GitHub tokens or SSH keys.
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

Pair the phone to this account:

```sh
moshi-hook host setup
moshi-hook pair --token <token-from-Moshi-Hooks-settings>
```

Once the pairing secret exists, the role takes over the daemon: the next play
installs the `moshi-hook.service` user unit and enables it through
`systemctl --machine=hermes@ --user`. Linger is already on, so the service
survives logout and reboot. `moshi-hook service install` cannot finish its
own enablement over sudo (no user session bus), which is why the role drives
systemd directly. The daemon keeps the default `127.0.0.1:24543` gateway
listen address: sshd permits local TCP forwarding but disables gateway and
Unix-socket forwarding, so it must stay on loopback.

In Moshi, add a host: MagicDNS name `ai-dev`, username `hermes`, connection
mode `Auto`.

Start work inside Herdr so a dropped connection does not kill the session:

```sh
herdr new infra
hermes chat
```

### Operating it

Day-to-day management needs no login to the agent account. The role owns
env-file reconciliation, opt-in package updates, and user-service restarts:

```sh
cd ansible
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit ai-dev --tags hermes,hermes-media
# Additionally refresh the hermes account's Hermes, Herdr, and Moshi:
ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit ai-dev --tags hermes -e ai_dev_hermes_update=true
```

Updates stay opt in per run: `hermes update` follows `origin/main` of the
upstream repository. That is an unpinned, self-updating code path, which is
acceptable on a disposable DMZ guest and is a reason the agent lives here
rather than on docker-host. Without `ai_dev_hermes_update=true` the play
installs missing pieces but never advances the toolchain.

Two upstream quirks to expect in update output. The updater's own
gateway-restart phase usually fails after a successful update (it restarts
in-process against a mixed old/new checkout), so `hermes update` exits 1
despite printing `Update complete!`; the role treats exactly that
code-plus-marker combination as success because the handler below restarts
the gateway through systemd instead, then verifies the service is active.
The updater also reports stashing local changes on every run: its own npm
steps rewrite tracked lockfiles inside the checkout, which the stash dance
then restores. Both messages are expected, not symptoms.

Whenever the role changes the scoped credential env, the media-broker entries,
or a toolchain version, a handler restarts the account's enabled
`hermes*.service` and `moshi-hook.service` user units through
`systemctl --machine=hermes@ --user`. Linger keeps that user manager running
without a session; this path needs systemd 256 or newer, which Arch carries.
Fresh hosts before first-run setup and pairing have no such units yet: the
handler reports that and changes nothing, rather than starting services that
have no credentials.

For ad-hoc checks between playbook runs, the role installs
`hermes-maintenance` for the management user. It drives the same operations
through sudo, so neither a session on the agent account nor a sudo entry for
it is ever needed:

```sh
hermes-maintenance status
hermes-maintenance update
hermes-maintenance restart
```

The account itself stays password-locked with no sudo entry; the agent reads
untrusted input, so the capability to change the host must not exist on its
account at all. Direct interactive access for first-run setup and debugging
remains `ssh hermes@ai-dev` or `sudo -u hermes -i`.

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
Photon, Moshi, and other MCP settings. The managed include list covers the
broker's twelve read tools (nine media reads and three qBittorrent torrent reads)
and its seven gated write tools; the broker itself
enforces the environment gates and the delete confirmation flow. The operator-supplied token must be a
single-line 32-256 character URL-safe value (`A-Z`, `a-z`, `0-9`, `_`, or `-`).
It is never generated, logged, or copied into YAML. An unowned same-name entry fails
closed unless an operator explicitly enables the takeover setting. Disabling
removes only the managed entry and token, without requiring the token variable.

The live endpoint is `http://docker-host:8765/mcp`, reached over Tailscale.
The sanitized Docker observer, broker, and source-pinned access controls have
been deployed and tested. Backend keys stay on docker-host in restricted
files. The broker uses a 5 MiB response bound for the observed 2.27 MB Lidarr
inventory. When reconciliation changes the managed entry or token, the role's
handler restarts the account's enabled gateway and moshi-hook user units
discovered at run time. After subsequent approved configuration changes,
verify the broker's twelve read and seven gated write tools.

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
reaching one media-broker port on docker-host and the Proxmox API. Keep it this
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
systemctl --machine=hermes@ --user status moshi-hook
ss -ltn 'sport = :24543'
```

The guest must have one address on the DMZ interface named by
`ai_dev_physical_interface`, no route to internal VLANs, no physical-interface
IPv6 address, and no listener for port 24543 except `127.0.0.1`. Test that HTTPS and gateway DNS work, while new connections to
MGMT, SRV, DFLT, KDS, GST, other DMZ hosts, and tailnet peers fail.

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
ssh hermes@ai-dev 'herdr status server'
```

The first command may show historical events from the current boot, but its
latest timestamp must not advance after TSO is disabled and the link is reset.

From an unapproved tailnet device, TCP 22 and UDP 60000-61000 must be denied.
From the approved phone, verify key-based OpenSSH, Mosh and SSH fallback,
Wi-Fi/cellular roaming, persistent Herdr panes, agent inbox and approval events,
and deep links.

## References

- [Moshi over Tailscale](https://getmoshi.app/docs/tailscale)
- [Moshi connections](https://getmoshi.app/docs/connections)
- [Moshi agent hooks](https://getmoshi.app/docs/hooks)
- [Moshi with Herdr](https://getmoshi.app/docs/herdr)
- [Herdr integrations](https://herdr.dev/docs/integrations/)
- [Tailscale grants syntax](https://tailscale.com/docs/reference/syntax/grants)
