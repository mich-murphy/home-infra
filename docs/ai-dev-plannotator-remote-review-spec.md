# AI-Dev Plannotator remote review specification

Status: approved for later implementation
Date: 2026-08-16
Scope: `home-infra` and the separately deployed `nix-config` repository

## Objective

Make Plannotator reviews started by Pi inside the persistent AI-Dev Herdr
session usable from both supported clients:

- a Mac laptop attached with `herdr --remote ai-dev`; and
- the approved phone connected through Moshi.

The implementation must make the review URL easy to open, carry browser
requests back to the Plannotator server, and return submitted approval or
feedback to the waiting Pi process. It must not publish Plannotator on the
physical DMZ or require a separately managed SSH tunnel.

## Decision

Use one fixed Plannotator port, `19432`, with two client adapters:

- The laptop adapter is an OpenSSH `LocalForward` declared in the Mac Home
  Manager SSH configuration. `herdr --remote` includes the user's SSH
  configuration and keeps that forward alive as part of its existing remote
  attach connection.
- The phone adapter is Moshi Browser Preview. `moshi-hook` discovers the
  Plannotator HTTP listener and Moshi creates its own per-session SSH forward.

Herdr is the process host and terminal interface, not the feedback transport.
The browser sends its decision to the Plannotator HTTP server; the Pi extension
resolves the pending review and resumes Pi in the Herdr pane.

```text
Laptop browser                     Moshi in-app browser
      |                                     |
Herdr-owned SSH LocalForward       Moshi-managed SSH forward
      |                                     |
      +---------- AI-Dev port 19432 --------+
                          |
              Plannotator Pi extension
                          |
                  Pi in a Herdr pane
```

Do not implement Tailscale Serve for this workflow. It remains a possible
future adapter if the Pi extension gains native `--tailscale` support or a
browser URL independent of the terminal session becomes a hard requirement.

## User interaction

### Laptop

1. The user runs `herdr --remote ai-dev`.
2. Herdr opens its normal SSH connection and OpenSSH establishes the declared
   laptop-loopback forward for port `19432`.
3. Pi invokes Plannotator on AI-Dev.
4. Plannotator starts its HTTP server and displays a URL based at
   `http://localhost:19432` in the Pi pane.
5. The user Ctrl-clicks the URL in Herdr. Ghostty opens it in the Mac's default
   browser. Browser opening is deliberately user initiated.
6. The user approves or submits annotations.
7. The HTTP response reaches the remote Pi extension through the SSH forward;
   Pi receives the decision and continues automatically.

### Phone

1. The user connects to the existing AI-Dev Herdr session through Moshi.
2. Pi invokes Plannotator on AI-Dev.
3. `moshi-hook` detects the HTTP listener on port `19432` and activates the
   Browser Preview indicator.
4. The user taps Preview, selects the Plannotator listener, and Moshi opens its
   in-app browser.
5. The user approves or submits annotations; Pi receives the decision and
   continues automatically.

True automatic browser launch on the laptop is not in scope. Neither Herdr nor
standard terminal protocols provide a trusted remote-to-local browser-launch
operation. A future implementation would require a separately designed local
helper and is not justified for this workflow.

## Current state

The repository already provides most of the implementation:

- Pi installs `npm:@plannotator/pi-extension` in
  `ansible/roles/ai-dev/tasks/tools.yaml`.
- `moshi-hook` runs as a persistent user service and its port `24543` gateway
  is verified as loopback-only.
- OpenSSH permits local TCP forwarding and sets `GatewayPorts no` in
  `ansible/roles/ai-dev/tasks/identity.yaml`.
- Herdr and the systemd user manager persist after SSH logout.
- AI-Dev nftables accepts only SSH and Mosh from `tailscale0`, accepts
  loopback, and drops other unsolicited tailnet and physical-DMZ input.
- The Mac Home Manager SSH configuration currently has no `ai-dev` host block
  or local forward.
- The AI-Dev Home Manager configuration currently has no persistent
  Plannotator environment settings.

## Required changes

### 1. AI-Dev Plannotator environment

Repository: `nix-config`
Expected owner: `hosts/ai-dev.nix`

Add these session variables to the AI-Dev Home Manager configuration:

```nix
PLANNOTATOR_REMOTE = "1";
PLANNOTATOR_PORT = "19432";
PLANNOTATOR_SHARE = "disabled";
```

`PLANNOTATOR_REMOTE=1` is intentional. It gives the Pi integration stable
remote behavior: fixed-port binding, no attempt to run `xdg-open` on AI-Dev,
and a visible `http://localhost:19432` URL for the laptop forward.

Remote mode binds Plannotator to `0.0.0.0`. This is acceptable only with the
existing nftables policy and tailnet grants continuing to deny direct access
to port `19432`. The implementation must verify that invariant; it must not add
port `19432` to nftables or the tailnet grants.

Existing Herdr panes retain the environment with which their shells and Pi
processes started. After deployment, start a new shell/Pi process for testing.
Do not restart the Herdr server merely to refresh the environment unless the
operator explicitly chooses to stop every pane.

### 2. Laptop SSH adapter

Repository: `nix-config`
Expected owner: `home/ssh.nix`

Add an `ai-dev` SSH host setting that generates semantics equivalent to:

```sshconfig
Host ai-dev
    User michael
    LocalForward 127.0.0.1:19432 127.0.0.1:19432
    ExitOnForwardFailure yes
```

Preserve the existing wildcard 1Password SSH agent and known-host settings.
Use the current Home Manager `programs.ssh.settings` interface rather than
writing an unmanaged SSH fragment. Confirm the exact option types against the
locked Home Manager version before editing.

`ExitOnForwardFailure yes` makes a local port collision fail the remote attach
immediately instead of leaving browser review silently broken. The failure
message should direct the user to find and stop the local listener occupying
`19432`, then reconnect.

### 3. Documentation and verification

Repository: `home-infra`

Update `docs/ai-dev.md` to document:

- the laptop `herdr --remote ai-dev` review flow;
- the Moshi Browser Preview review flow;
- the one-click rather than auto-open browser behavior;
- the single-active-review limitation of fixed port `19432`;
- troubleshooting for local port collision, missing Moshi Preview, and a
  stale Pi/Herdr environment; and
- verification that port `19432` is unreachable directly over the DMZ and
  tailnet.

Add automated or deployment-time assertions only where they are stable when
Plannotator is not running. Do not add a permanent listener merely to make a
test convenient.

## Invariants

- The laptop listener is `127.0.0.1:19432`, never a LAN-facing address.
- OpenSSH retains `GatewayPorts no` and `AllowTcpForwarding local`.
- AI-Dev port `19432` is not granted through the tailnet policy.
- AI-Dev port `19432` is not accepted from the physical DMZ interface.
- Moshi's gateway remains loopback-only on `127.0.0.1:24543`.
- Plannotator sharing remains disabled.
- The implementation does not add Tailscale Serve, Funnel, Traefik, a reverse
  proxy, or a custom browser-launch daemon.
- Submitted feedback travels through Plannotator's HTTP decision interface;
  no terminal keystroke injection or Herdr-specific feedback protocol is
  introduced.

## Known limitation

Port `19432` supports one active Plannotator listener. A second concurrent Pi
review may fail to bind or pre-empt a previous same-process review. Supporting
concurrent reviews would require a port range plus multiple laptop forwards,
or native dynamic forwarding support in the client. That expansion is outside
this specification.

## Acceptance criteria

### Configuration

- `nix build --no-link '.#homeConfigurations."michael@ai-dev".activationPackage'`
  succeeds in `nix-config`.
- The Mac Home Manager activation succeeds without replacing the existing
  wildcard SSH identity-agent settings.
- `ssh -G ai-dev` reports user `michael`, a loopback local forward from `19432`
  to remote `127.0.0.1:19432`, and forward-failure handling enabled.
- A fresh AI-Dev Fish shell reports all three expected `PLANNOTATOR_*` values.

### Laptop end-to-end

- `herdr --remote ai-dev` succeeds when local port `19432` is free.
- Starting a Pi Plannotator review creates an AI-Dev listener on port `19432`
  and displays a `http://localhost:19432` review URL.
- Ctrl-clicking the URL opens the review in the Mac's default browser.
- Approving a plan resumes Pi automatically.
- Rejecting or annotating a plan returns the exact feedback to Pi.
- Detaching after starting a review leaves Pi waiting in Herdr; reattaching and
  reopening the URL permits the review to complete.

### Phone end-to-end

- Moshi Browser Preview detects the Plannotator listener.
- Opening the detected listener loads the review without public exposure.
- Approval and annotated feedback both return to the same Pi process.

### Containment

- While a review is active, `curl http://127.0.0.1:19432` succeeds on AI-Dev.
- The approved laptop can reach the review only through local
  `127.0.0.1:19432` while the Herdr SSH connection is active.
- Direct connections to AI-Dev port `19432` fail from another tailnet peer,
  from the laptop using the AI-Dev MagicDNS address, and from the physical DMZ.
- `sudo nft list ruleset` still contains no input accept rule for port `19432`.
- Closing the laptop Herdr remote connection removes its local listener on
  port `19432`.

### Failure behavior

- Occupying laptop port `19432` causes `herdr --remote ai-dev` to fail loudly.
- Stopping the Plannotator review makes the forwarded URL unavailable without
  affecting Herdr, Pi outside the review, Moshi, or SSH.
- A failed or abandoned browser connection does not submit an implicit
  approval.

## Rollout

1. Change and build `nix-config` first.
2. Activate the Mac Home Manager configuration and inspect `ssh -G ai-dev`.
3. Deploy the AI-Dev Home Manager configuration through the existing
   `home-infra` Ansible workflow.
4. Start a fresh shell and Pi process in an existing or new Herdr pane.
5. Execute the laptop, phone, containment, and failure acceptance tests.
6. Update `docs/ai-dev.md` with the verified behavior and troubleshooting
   details.

## Rollback

Remove the three AI-Dev `PLANNOTATOR_*` session variables and the `ai-dev`
`LocalForward`/`ExitOnForwardFailure` SSH settings, rebuild both Home Manager
profiles, and start a fresh AI-Dev shell. No persistent proxy or external
network state needs cleanup.

## Handoff instructions

The implementation session should begin by reading:

- this specification;
- `docs/ai-dev.md`;
- `ansible/roles/ai-dev/tasks/identity.yaml`;
- `ansible/roles/ai-dev/tasks/tools.yaml`;
- `ansible/roles/ai-dev/templates/nftables.conf.j2`;
- `nix-config/AGENTS.md`;
- `nix-config/hosts/ai-dev.nix`; and
- `nix-config/home/ssh.nix`.

Implement only the approved SSH-forward/Moshi design. Preserve unrelated dirty
worktree changes in both repositories. Validate statically before any live
activation, and do not broaden the tailnet or host firewall policy to make a
test pass.
