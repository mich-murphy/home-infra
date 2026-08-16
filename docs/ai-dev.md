# AI development VM

`ai-dev` is the single AI development VM. It retains Proxmox VMID 110 and its
150 GB disk, with 4 CPU cores, fixed 5 GiB RAM, and an 8 GiB disk-backed
swapfile with a bounded zswap cache. Its only NIC is on the physical `vmbr1`
DMZ.

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

Home Manager is the steady-state owner of the shared shell and CLI environment.
Ansible builds the desired activation package, compares it with the current
Home Manager generation, and activates only when they differ. It does not
remove legacy files or packages during normal runs. A second live run must
report no changes when the Nix configuration and upstream agent versions have
not changed.

## Interactive setup

Home Manager owns OpenCode and the shared Fish, Starship, FZF, general Git
behavior, Hunk, Herdr, Yazi, and portable CLI configuration. Ansible writes
ai-dev's vaulted personal and BusinessCraft identity fragments with mode `0600`
and selects the BusinessCraft fragment below `~/businesscraft/`; the Mac retains
its separate Home Manager-owned identities. Ansible reruns the official stable
installers for Claude Code, Codex, Pi, Herdr, and Moshi on every deployment,
comparing versions before and after so unchanged installers remain idempotent.
It also installs the user-scoped `npm:@plannotator/pi-extension` Pi package.
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

## Plannotator remote reviews

Plannotator uses the fixed AI-Dev port `19432` with sharing disabled. Herdr
keeps Pi and its pending review alive, while the browser submits approval or
annotation feedback directly to Plannotator's HTTP decision interface.

For a laptop review:

1. Run `herdr --remote ai-dev`. The SSH connection creates a laptop-loopback
   forward from `127.0.0.1:19432` to the same loopback port on AI-Dev.
2. Start the Plannotator review from Pi. Pi displays a URL based at
   `http://localhost:19432`.
3. Ctrl-click the URL in Ghostty to open it in the Mac's default browser.
4. Approve the plan or submit annotations. Pi receives the decision and
   resumes automatically.

Opening the browser is deliberately one-click, not automatic. The forwarded
listener exists only while the laptop's Herdr SSH connection is active.
Detaching after a review starts leaves Pi waiting in Herdr; reattach and reopen
the displayed URL to complete it.

For a phone review, connect to the same Herdr session through Moshi and start
the review from Pi. When Moshi's Browser Preview indicator appears, tap it,
select the listener on port `19432`, and use the in-app browser to approve or
annotate the plan. Moshi creates its own per-session SSH forward; Plannotator
is not published on the tailnet or physical DMZ.

The fixed port supports one active review at a time. A second concurrent
Plannotator review can fail to bind or interfere with the first; finish or
cancel the first review before starting another.

### Plannotator troubleshooting

- If `herdr --remote ai-dev` reports that `19432` is already in use,
  `ExitOnForwardFailure` has stopped the attach rather than leaving reviews
  silently broken. Run `lsof -nP -iTCP:19432 -sTCP:LISTEN` on the laptop, stop
  the local process that owns the port, and reconnect.
- If Moshi does not show Browser Preview, first confirm that a review is still
  waiting and that `ss -ltn 'sport = :19432'` shows the Plannotator listener on
  AI-Dev. Then check `moshi-hook status` and
  `systemctl --user status moshi-hook`; its gateway must remain on
  `127.0.0.1:24543`.
- If Pi does not use port `19432` or tries to open a browser on AI-Dev, its
  process has a stale environment. In an idle Herdr pane run `exec fish`,
  confirm the variables below, and start a new Pi process. Do not restart the
  Herdr server merely to refresh the environment: stopping it exits every pane
  process.

```sh
fish -lc 'printf "%s\n" "$PLANNOTATOR_REMOTE" "$PLANNOTATOR_PORT" "$PLANNOTATOR_SHARE"'
# Expected: 1, 19432, disabled
```

While a review is active, `curl http://127.0.0.1:19432` must work on AI-Dev and
on the attached laptop. Direct requests to `http://ai-dev:19432` must fail from
the laptop and every other tailnet peer, and requests to the AI-Dev DMZ address
on `19432` must fail from the physical DMZ. Confirm that
`sudo nft list chain inet filter input` has no accept rule for `19432`. Closing
the laptop Herdr connection must remove the laptop's `127.0.0.1:19432`
listener.

On the laptop, inspect the effective client policy before the end-to-end test:

```sh
ssh -G ai-dev | grep -E \
  '^(user|localforward|exitonforwardfailure|identityagent|hashknownhosts) '
```

It must report user `michael`, forward-failure handling enabled, the
loopback-to-loopback `19432` forward, and the existing wildcard 1Password agent
and hashed-known-host settings.

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
sudo sshd -T | grep -E '^(allowtcpforwarding local|gatewayports no)$'
systemctl --user status moshi-hook
ss -ltn 'sport = :24543'
command -v nvim stylua gopls marksman
fish -lc 'echo $TMPDIR'
fish -lc 'env | grep ^PLANNOTATOR_ | sort'
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
