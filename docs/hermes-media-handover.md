# Hermes media integration handover

Prepared 2026-09-17. Supersedes the 2026-09-14 edition, whose repository and
deployment references are now historical. This is a handover, not authorization
for additional live changes.

## Goal and remaining work

Hermes on ai-dev should read household playback history and eventually manage
Sonarr, Radarr, and Lidarr through human-approved conversations in **Moshi iOS
and Photon iMessage**. Do not substitute Seerr or an external approval page.

The read-only Plex/Tautulli and Arr phase is deployed. Remaining, in the
recommended order:

1. Add Jellyfin playback history, including reporting setup (still deferred —
   see below; an upgrade path opened on 2026-09-08).
2. Design and implement independently verified conversational approvals.
3. Introduce a small set of approved Arr mutations. Deletion comes last.

## Start the next session here

1. Fetch current main in both repositories and inspect the working trees
   before changing anything. The broker application and its deployment
   definition now live in different repositories (below).
2. Read this file, `docs/hermes-media.md`, `docs/ai-dev.md`, and
   `docker/media-broker/compose.yml` in home-infra, plus `README.md` and
   `SECURITY.md` in the mich-murphy/media-broker repository.
3. Confirm the desired next phase with the owner and obtain authorization for
   its live changes, including plugin installation or service restarts.
4. Recheck live versions, channel capabilities, and plugin state. Dated
   observations below are evidence, not a promise that infrastructure is
   unchanged.
5. Use one Luna implementation writer and a fresh independent reviewer.
   Discover currently available agents/models before dispatch. The parent owns
   acceptance, publication, merges, and live operations. Do not silently
   switch execution protocols when a governed subagent lane fails.

## Repository split completed 2026-09-17

The broker application moved out of this repository into the **public**
[`mich-murphy/media-broker`](https://github.com/mich-murphy/media-broker)
repository (local checkout: `/Users/mm/dev/media-broker`):

- Application source, source tests, Dockerfile, and the isolated container
  probe moved there. Head of main is `0fd6a43`.
- [PR #1](https://github.com/mich-murphy/media-broker/pull/1): production
  hardening and CI quality gates (Ruff format/lint with McCabe 8, strict
  mypy, pytest, pip-audit, image build).
- [PR #2](https://github.com/mich-murphy/media-broker/pull/2): public
  visibility preparation, including `SECURITY.md` with GitHub private
  vulnerability reporting. The source repository is public, and the GHCR
  package was made public on 2026-09-17 during the migration, so Portainer
  and Renovate pull anonymously and no registry credentials are required.
- [PR #3](https://github.com/mich-murphy/media-broker/pull/3): per-endpoint
  projectors collapsed into declarative field tables. New history adapters
  should follow that pattern.
- CI publishes `ghcr.io/mich-murphy/media-broker:main` (rolling) and
  `:sha-<commit>` (immutable, for rollback/audit) on every merge to main.
- Locked validation still uses **uv 0.12.5** (pinned in CI and the
  Dockerfile, tracked by a Renovate custom manager). The accepted lock
  resolved MCP 1.28.1, pytest 9.0.3, pytest-asyncio 1.3.0.

home-infra keeps only the stack definition and host policy, merged in
[PR #1769](https://github.com/mich-murphy/home-infra/pull/1769) (2026-09-17,
commits `cf04488` through `f6c7837`):

- `docker/media-broker/compose.yml` is an ordinary image-only Compose file;
  the stack is an ordinary Portainer Git stack on the shared polling source,
  inventoried in `docker/portainer-stacks.yaml`. Container renamed from
  `media-broker-candidate` to `media-broker`.
- The host image build, `/srv/hermes-media-candidate` checkout, deploy
  preflight/launcher scripts, and the manual-update exception are gone. A
  short-lived host auto-update timer (`59dc542`) was replaced by the Renovate
  digest-pin model (`09fd80f`).
- `tests/media-broker-stack.sh` keeps infra-side assertions (Compose
  contract including the never-build rule, published-port policy, inventory
  coverage) and runs in CI. The previously orphaned
  `ansible/tests/hermes-media*.sh` scripts now run in the quality gate.
- Ansible provisioning defaults remain inert
  (`docker_media_broker_enabled: false`); Portainer owns deployment.

## Deployment pipeline (current)

Merging to media-broker `main` deploys without manual host steps:

1. **Publish**: dedicated-repo CI pushes `:main` plus an immutable
   `:sha-<commit>` tag to GHCR.
2. **Pin**: the Compose reference here is `:main@sha256:<digest>`. Renovate
   updates the digest when `:main` moves and automerges under the existing
   digest-automerge rule. Run Renovate's workflow dispatch to pin a fresh
   release immediately instead of waiting for its cron.
3. **Redeploy**: the digest bump is a commit on home-infra `main`, which is
   what Portainer's Git polling watches.

The digest pin is the deploy trigger: Portainer compares Git commits and
never consults the registry. Rollback is `git revert` of the digest bump, or
an emergency editor update pinning a known `:sha-<commit>` tag.

**Never add a `build:` block to this Compose file.** The two Portainer 2.45
incidents (per-source polling scheduler; rebuild from a retained stale Git
context when a build block exists, even with `PullImage: false`) are
preserved in `docs/hermes-media.md`. The earlier "do not connect this stack
to the shared source" rule is obsolete — the broker is explicitly allowed on
it now — but must be understood as contingent on the image coming from GHCR.

## Migration state — performed and verified 2026-09-17

The owner performed the one-time migration runbook in `docs/hermes-media.md`:
old manual stack deleted (brief downtime; the `media-broker-candidate` name
retired with it), the GHCR package made public (no Portainer registry
credentials needed), and the stack recreated from Git with the same nonsecret
values. Post-migration verification (counts/status only, per live discipline):

- **Stack**: new Portainer stack ID **40** (old 39 died with the manual
  stack), tracking `main`; container `media-broker` healthy; running image
  digest `91fee67d…` matched the anonymously resolved registry `:main`
  digest exactly.
- **Access controls**: unauthenticated request → 401; untrusted Origin with
  a valid token → 403; authenticated MCP initialize → 200 (server
  `media-broker 1.28.1`, protocol `2025-06-18`); `tools/list` returned
  exactly the four read-only tools; `arr_root_folders` reads succeeded for
  Sonarr, Radarr, and Lidarr (3 root folders each); the broker port was
  unreachable from a non-ai-dev client (DOCKER-USER policy intact).
- **Pipeline proof**: Renovate was dispatched with its schedule override
  and opened/automerged the initial digest-pin PR
  [#1771](https://github.com/mich-murphy/home-infra/pull/1771); Portainer's
  Git polling redeployed the stack on the pin commit within one polling
  cycle. The end-to-end loop (media-broker merge → publish → digest pin →
  automerge → Portainer redeploy) is proven.
- **Cleanup**: `/srv/hermes-media-candidate` removed from docker-host;
  `/etc/media-broker/secrets` untouched; rollback evidence under
  `/var/lib/hermes-rollout` retained; no stray media-broker systemd units or
  timers exist.

Not re-run: a conversational read through Hermes itself (its configuration
was untouched, so no restart or re-approval was needed); an owner spot-check
in Moshi/Photon is a cheap final confirmation.

## Security boundaries and sensitive data

Unchanged by the split, and still binding:

- Backend API keys and the broker bearer stay in the five host-managed files
  under `/etc/media-broker/secrets` (`broker-token`, `sonarr-api-key`,
  `radarr-api-key`, `lidarr-api-key`, `tautulli-api-key`): directories
  `root:65532` mode `0750`, files `root:65532` mode `0640`. File-backed
  Compose secret declarations do not set host permissions. Never put key
  values in Portainer variables, Compose environment, Git, or command
  arguments. The source repository is now public — treat anything committed
  there as published.
- No write tools, generic upstream passthrough, approval endpoints, Seerr,
  or Jellyfin integration exist in the broker.
- Never print credentials, messages, or individual household playback
  records. Report counts/status only during live verification. (One early
  ActivityLog query on 2026-09-14 printed event text before this discipline
  was applied; no credentials were involved. Aggregate projections only.)
- Endpoint `http://docker-host:8765/mcp`, exact Host `docker-host:8765`,
  exact Origin `http://docker-host:8765`. The host port binds only the
  docker-host Tailscale IPv4; the source-pinned `DOCKER-USER` exception
  admits ai-dev before the broker-port drop. No Traefik/shared 443 or LAN
  exception. Keep host firewall and Tailscale grant checks; the
  `docker-host` role asserts the rules on every run.
- The broker runs as `65532:65532` with a read-only filesystem, five
  read-only secret mounts, no Docker socket, and no media mounts. The 5 MiB
  response bound accommodates the ~2.27 MiB Lidarr inventory.
- The Docker observer on port 2375 remains a separate sanitized-read
  component with its internal-only backend; preserve that topology and its
  source checksum validation.

## Live locations and access notes

Repository (this file): `/Users/mm/dev/home-infra`. Broker source:
`/Users/mm/dev/media-broker`.

| Component | Location |
| --- | --- |
| docker-host | `100.96.174.126`; SSH `mm@docker-host`, passwordless sudo |
| ai-dev | `100.84.159.38`; SSH alias `ai-dev`, management user `michael` |
| Canonical Compose | `docker/media-broker/compose.yml` (home-infra) |
| Broker secret directory | `/etc/media-broker/secrets` |
| Observer bootstrap | `/srv/init`; root-owned source and checksum in its restricted `.env` |
| Hermes config | `/home/hermes/.hermes/config.yaml` |
| Hermes environment | `/home/hermes/.hermes/.env` |
| Hermes ownership marker | `/home/hermes/.config/hermes/media-broker.managed` |
| Hermes integration helper | `/home/hermes/.local/bin/manage-hermes-media.py` |
| Hermes Python with YAML | `/home/hermes/.hermes/hermes-agent/venv/bin/python` |

Removed with the split: `/srv/hermes-media-candidate`, its `.env`, and its
`source-manifest.json`. Do not resurrect them.

The ignored local `.envrc` contains `PORTAINER_API` (mode 0600). Parse its
literal assignment without shell evaluation; pass the credential through
protected stdin to remote Python, never command arguments or output. The
local Portainer API is `https://127.0.0.1:9443` on docker-host via SSH. Never
dump full stack/container metadata containing env.

Hermes runs a **user** gateway unit (UID 30033):

```sh
sudo -n -u hermes env XDG_RUNTIME_DIR=/run/user/30033 \
  systemctl --user status hermes-gateway.service
```

Use explicit Bash/Python for ai-dev remote commands; its login shell is fish.
Check status without printing message-bearing journals.

Historical rollback/evidence directories on docker-host
(`/var/lib/hermes-rollout/security-1cd2601` and `observer-31da1267c641`, plus
image tag `home-infra/media-broker:rollback-5dc476a`) predate the split and
are retained evidence only. Current rollback is `git revert` of a digest bump
or pinning an immutable GHCR `:sha-<commit>` tag.

## Jellyfin history work — deferred, resume conditions updated

Owner-deferred on 2026-09-14 after a read-only audit: no plugin installed, no
restart, no credential or broker changes. Re-verified 2026-09-17:

- Jellyfin server still pinned to `10.11.11`
  (`sha256:aefb67e6...b35db`) in `docker/jellyfin/compose.yml`; Playback
  Reporting plugin absent.
- No structured playback history exists: only unstructured ActivityLog text
  events (~3,590 start/stop rows since 2025-05-02) and per-item UserData play
  states. Collection starts at enablement; no backfill is possible. An empty
  query does not prove no playback occurred.
- Stable plugin catalog (checked 2026-09-17) still offers only v17.0.0.0
  (`targetAbi 10.11.0.0`, broken on 10.11.9+ by the `IUserManager.Users`
  removal; open issues #128 and #135) and v19.0.0.0 (`targetAbi 12.0.0.0`).
  Plugin GUID `5c534381-91a3-43cb-907a-35aa02eb9d2c`.
- Root cause of the missing v18 stable release: the v18 tag (`e899995`)
  contains the runtime fix but its own `build.yaml` still declares
  `version: 17`, so the catalog can never list it from that tag. Issue #133
  ("v18 is not fully released") remains open. Sideloading the GitHub-release
  zip is a flavor of the rejected untrusted-DLL workaround — do not do it
  without explicit owner reversal.
- **New since the deferral: Jellyfin 12.0 stable released 2026-09-08 and
  12.1 on 2026-09-15.** Plugin v19 targets 12.0.0.0, so the second resume
  condition (server on a Jellyfin 12 release with plugin v19 available) is
  now satisfiable. Upgrading the household's production media server is a
  major-version live change requiring explicit owner authorization, a backup,
  a compatibility audit of every other installed plugin, and a rollback
  plan. The alternative is waiting on the upstream stable catalog.

Broker and Jellyfin already share the `proxy` Docker network
(`http://jellyfin:8096`); no reachability work needed.

Once unblocked, in order:

1. Re-obtain owner authorization for the chosen path (server upgrade plus
   plugin installation, including any Jellyfin restart).
2. Establish what the plugin v19 API actually exposes (`/user_usage_stats/*`
   endpoints), the narrowest usable authentication, and create a Jellyfin
   credential in a new host-managed secret under
   `/etc/media-broker/secrets` — not Hermes or Portainer environment values.
3. Implement the adapter in the **media-broker repository** following the
   existing patterns: declarative projection table (PR #3 style), read-only
   GETs with exact endpoint allow-listing, bounded requests/results/date
   ranges, no redirects or environment proxies, sanitized errors, and
   source-prefixed identifiers (`jellyfin_*`) so Jellyfin records are
   distinct from Tautulli records. Note that `config.py` currently requires
   every upstream at startup: the host secret and stack variables must exist
   before the new image deploys, or the stack goes unhealthy.
4. Test movies, episodes, music, user attribution, time zones, pagination,
   sessions versus completed plays, missing records, authorization failures,
   and empty results.
5. Review (one writer, fresh independent reviewer), merge with
   authorization, let CI publish the image, verify the Renovate digest bump
   deploys through Portainer, and verify live using counts only — expecting
   an initial stack-variable update for `JELLYFIN_URL`/`JELLYFIN_API_KEY_FILE`
   in Portainer alongside the new secret file.

## Conversation-approved Arr mutations

This requires a new authorization boundary, not just enabling native prompts.
Earlier research found Hermes/Moshi/Photon native confirmation mechanisms are
not independently enforced against a compromised or instruction-following
Hermes process with the same UID and access to its files.

Required design:

- Hermes proposes an immutable, exact plan identifying service, target IDs,
  intended values, relevant previous state, and expected side effects.
- A separately owned service keeps authoritative plan state and validates
  human approval. Hermes must not be able to create approval evidence, edit
  the verifier's state, access its credentials, or invoke an ungated write
  path.
- Approval arrives inside Moshi or Photon from a verified authorized human,
  bound to the correct conversation and plan. A text string such as "yes",
  supplied or quoted by the agent, is not evidence of approval.
- Bind approvals to plan identity/content, expiration, and one-time
  consumption. Recheck target state immediately before execution. Changed
  plans or relevant state require fresh approval. Handle retries without
  duplicate side effects.
- Give the executor only explicitly supported typed actions. Keep backend
  keys outside Hermes; avoid generic URL, method, or arbitrary-payload
  forwarding.
- Maintain a restricted audit trail without leaking credentials or household
  message/playback contents into ordinary logs.

First investigate the actual trusted ingress available in each channel:
sender identity, message provenance, replay protection, separation from
agent-controlled credentials. Do not assume either channel supplies signed
callbacks or an adequate independent approval API. If neither can provide a
trustworthy path, present that blocker and design choices to the owner rather
than pretending the normal confirmation dialog solves it.

Suggested initial scope, to agree with the owner: add an explicitly
identified movie/series/artist; change monitoring state or an explicitly
named quality profile for one target. Treat immediate
searching/downloading, root-folder changes, moves, rescans, and bulk
operations as separate side effects requiring explicit scope. Exclude
deletion and destructive filesystem operations initially.

Tests must cover forged/quoted approvals, agent-originated echoes, wrong
sender or conversation, expired/replayed approvals, plan tampering, stale
library state, concurrency, partial failure, retry/idempotency, and direct
bypass of the verifier. Start with dry-run plans and a tightly bounded live
action only after independent review and owner authorization.

## Code and validation pointers

media-broker repository (`/Users/mm/dev/media-broker`):

- Application: `src/media_broker/{server,config,adapters}.py`
- Source tests: `tests/test_broker.py`; isolated container probe:
  `tests/container.sh` (desktop-linux context only)
- CI: `.github/workflows/ci.yaml` (quality gate + GHCR publish);
  `renovate.json` tracks the pinned uv version

home-infra repository:

- Stack definition: `docker/media-broker/compose.yml`;
  inventory: `docker/portainer-stacks.yaml`
- Infra assertions: `tests/media-broker-stack.sh` (runs in CI,
  `--source-only` mode)
- Hermes integration: `ansible/roles/ai-dev/tasks/hermes-media.yaml` and
  `ansible/roles/ai-dev/files/manage-hermes-media.py`; focused checks:
  `ansible/tests/hermes-media*.sh` (now in the quality gate)
- Observer: `docker/init/agent-observer/observer.py`,
  `docker/init/compose.yml`, `tests/agent-observer_test.py`
- Deployment runbook and incident history: `docs/hermes-media.md`

Earlier research/review artifacts remain local, not repository files:

`/Users/mm/.pi/agent/sessions/--Users-mm-dev-home-infra--/subagent-artifacts/outputs/`

- `1bd3648b-0dba-4be0-97a1-29f7fe79f3fc/approvals-live.md`
- `4056cd7f-0efa-4ebf-9814-7599a2ee2bd2/media-wiring-plan.md`
- `726853de-f4e7-46d8-abc9-f1585991afe0/approval-isolation.md`
- `ac26eac6-8259-4e41-a5c4-9dd69fefeb72/security-review.md`
- `0772e700-ddd7-455b-9ac5-3b4e9cc10a3b/promotion-review.md`

Treat deployment recommendations in older artifacts as superseded by
`docs/hermes-media.md` and this handover.

## Earlier release references (pre-split)

- [PR #1753](https://github.com/mich-murphy/home-infra/pull/1753): read-only
  broker, sanitized Docker observer, host policy, Hermes integration.
- [PR #1754](https://github.com/mich-murphy/home-infra/pull/1754): Portainer
  ownership, CI coverage, dependency security patches.
- [PR #1755](https://github.com/mich-murphy/home-infra/pull/1755): image-only
  Portainer update procedure (historical; superseded by the registry
  pipeline).
