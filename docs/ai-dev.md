# AI development VM

`ai-dev` is the single AI development VM. It retains Proxmox VMID 110 and its
150 GB disk, with 4 CPU cores, 4 GB RAM, and RAM-sized zram. Its only NIC is on
the physical `vmbr1` DMZ.

The supported remote path is:

```text
Moshi -> Tailscale private network -> OpenSSH -> Mosh when available -> Herdr
```

Tailscale SSH stays disabled. Moshi connects to the guest's normal OpenSSH
server through Tailscale, then uses Mosh's per-connection UDP server when the
network permits it. Herdr is the only persistent multiplexer and retains its
shared `Ctrl-A` prefix. `Ctrl+Shift+L` is encoded as F12 by a supporting
terminal, forwarded by Herdr, and bound by Fish to clear the focused pane.

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
and CPU update. Stop if VMID 110 or its disk would be destroyed or replaced.
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

The first activation directly replaces the old Ansible-managed Fish, Starship,
and global Git files and removes the retired Fisher plugins. It preserves Fish
variables, histories, credentials, OAuth sessions, OpenCode configuration, and
other application state. No migration backup is created. After Home Manager is
active, Ansible removes duplicate Arch CLI packages and the old
`.opencode/bin/opencode` binary. The second live AI host run must report no
changes when the upstream agent versions have not changed.

## Interactive setup

Home Manager owns OpenCode and the shared Fish, Starship, FZF, general Git
behavior, Hunk, Herdr, Yazi, and portable CLI configuration. Ansible writes
ai-dev's vaulted personal and BusinessCraft identity fragments with mode `0600`
and selects the BusinessCraft fragment below `~/businesscraft/`; the Mac retains
its separate Home Manager-owned identities. Ansible reruns the official stable
installers for Claude Code, Codex, Pi, Herdr, and Moshi on every deployment,
comparing versions before and after so unchanged installers remain idempotent.
Ansible does not copy SSH keys, OAuth sessions, or API keys. Authenticate each
tool interactively:

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

Ansible installs Herdr integrations first and Moshi integrations second so
their entries coexist. Check them after authentication:

```sh
herdr integration status
moshi-hook status
claude --version
codex --version
pi --version
opencode --version
```

Moshi's OpenCode hook is project-local. Ansible installs it in the home
workspace; run `moshi-hook install` once from each existing OpenCode project
root that should emit events. This repository does not inventory untracked
projects on the VM.

Moshi's full agent integration sends limited notification summaries, approval
details, metadata, pairing, and WebSocket control traffic through Moshi's
service. Terminal traffic, source files, transcripts, and diffs remain direct.

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

Replace `group:ai-dev-users` with the tailnet's approved selectors. Do not add a
grant with `tag:ai-dev` as a source; grants are additive, so a broader existing
grant can defeat this containment.

## Verification

On the guest, verify identity, network placement, containment, and services:

```sh
hostnamectl --static
tailscale status
sudo tailscale debug prefs
ip -brief address show ens18
ip route
sudo nft list ruleset
systemctl --user status moshi-hook
ss -ltn 'sport = :24543'
command -v nvim stylua gopls marksman
fish -c 'type -p opencode hunk yazi btop bat direnv'
nvim --headless \
  '+lua print(vim.g.clipboard.name, vim.o.clipboard)' \
  +qa
```

The guest must have one `ens18` address in `10.77.99.0/24`, no route to internal
VLANs, no physical-interface IPv6 address, and no listener for port 24543 except
`127.0.0.1`. Test that HTTPS and gateway DNS work, while new connections to
MGMT, SRV, DFLT, KDS, GST, other DMZ hosts, and tailnet peers fail.

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
