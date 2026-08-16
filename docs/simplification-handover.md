# Home Infrastructure Complexity Review

> **Status:** Approved implementation handover
> **Approved:** 16 August 2026
> **Approval base:** `main` at `4067893` plus the pre-existing working-tree changes listed below
> **Purpose:** Authoritative scope and execution order for a future session implementing the agreed simplification work

## Future-session execution contract

This handover is approved as the implementation direction. A future session should continue from the repository state it finds rather than repeating the architecture review.

Before editing:

1. Read repository instructions and inspect `git status`, the current branch, recent history, and all existing diffs.
2. Preserve the user-owned working-tree changes that existed when this handover was approved:
   - swap/zswap work under `ansible/roles/common` and related group variables;
   - NFS/media changes;
   - `docs/ai-dev.md` changes;
   - `terraform/main.tf` memory changes.
3. Reconcile this handover against commits made after approval. Do not reapply completed work.
4. Keep the implementation incremental and verifiable. Separate the Talos/Kubernetes branch preservation from deletion on `main`, and separate unrelated simplifications into reviewable commits.
5. Treat live-network, container-decommissioning, VM-state, branch-push, and other consequential actions as explicit operational steps. Resolve exact targets read-only before changing them.

Known gate: "Mad Villainy" is not yet a canonical network name in this repository. Confirm whether it means DFLT/VLAN 30 or a new VLAN before changing RouterOS `ether6`.

## Final assessment

The live platform is appropriate for a single-server homelab: Terraform provisions infrastructure, Ansible configures hosts and RouterOS, Docker Compose defines applications, and Nix supplies reproducible tooling. The largest avoidable cost is maintaining the inactive Talos/Kubernetes replacement platform on `main` alongside the live Docker platform.

The target operating model should be:

```text
Terraform       Proxmox VM and UniFi object provisioning
Ansible         Host, bootstrap-stack, and RouterOS configuration
Docker Compose  Application definitions
Portainer       GitOps deployment of application stacks
Nix + CI        Reproducible tools and focused validation
```

Ansible and Portainer deliberately share Docker deployment responsibilities at a clear seam: Ansible owns the bootstrap stack that must exist before Portainer can operate; Portainer owns application stacks after bootstrap. This is necessary complexity, but the ownership and decommissioning behavior need to be explicit.

## Agreed direction

1. Preserve all Talos and Kubernetes work on a dedicated remote branch, proposed as `feature/talos-kubernetes`.
2. Remove Talos/Kubernetes and every supporting integration from `main` after the branch is safely pushed.
3. Keep Ansible deployment of the bootstrap stack: Traefik, Docker socket proxy, Portainer, and Pocket ID.
4. Keep Portainer GitOps for application stacks, but codify its expected stack inventory and decommissioning procedure.
5. Make strict RouterOS operation the default; require an explicit recovery-mode override to weaken it.
6. Convert RouterOS `ether6` from its current wired-management fallback into an untagged access port for the "Mad Villainy" client VLAN, while preserving `ether7` as dedicated OOB management.
7. Treat the powered-off UniFi VM as intentional cold infrastructure while the server operates with 32 GB RAM.
8. Remove completed `ai-dev` Home Manager migration logic.
9. Replace the Docker hardening rollout document with a concise steady-state policy and exception record.
10. Require service-level regression verification when simplifying Docker backend networks.

## Validated findings

### 1. Move the inactive Talos/Kubernetes platform to a dedicated branch

Talos/Kubernetes is explicitly not live, yet it contributes approximately 12,000 lines of Kubernetes content, 9,000 lines of vendored Kubernetes schemas, Talos configuration, a 418-line migration runbook, dedicated CI workflows, Nix tools, Renovate rules, Terraform cutover resources, and RouterOS reservations.

The branch operation should be performed before deletion:

1. Create `feature/talos-kubernetes` from the current commit, including the complete prepared platform.
2. Push the branch and verify it exists remotely.
3. On `main`, remove `kubernetes/`, `talos/`, Kubernetes schemas, migration documentation, Kubernetes/Talos workflows, and related Nix and Renovate configuration.
4. Remove `enable_talos`, the Talos VM and ISO, Docker-host shutdown coupling, and GPU handover from [terraform/main.tf](/Users/mm/dev/home-infra/terraform/main.tf:131).
5. Remove Kubernetes-only address reservations and firewall rules from the RouterOS role.
6. Keep the future cutover work isolated on the feature branch until there is an approved migration date.

This is preferable to an archive directory because the inactive platform disappears from normal navigation, validation, dependency updates, and maintenance while remaining fully recoverable in Git.

### 2. Preserve the two-stage Docker deployment model, but close its lifecycle gap

The original recommendation to choose exactly one Docker deployment controller was too strong. Portainer cannot bootstrap itself, and its HTTPS route depends on Traefik. The current Ansible-owned `docker/init` stack is therefore a legitimate bootstrap module: [Ansible Docker role](/Users/mm/dev/home-infra/ansible/roles/docker/tasks/main.yaml:96).

The intended ownership should be documented as:

| Owner | Responsibility |
| --- | --- |
| Ansible | Docker host configuration and `/srv/init`: Traefik, socket proxy, Portainer, Pocket ID |
| Portainer GitOps | All application Compose stacks under `docker/` except `docker/init` |
| Git | Compose definitions and the expected active-stack inventory |

An initial live read-only check found 37 running containers with the expected hardening, but also found `mlflow`, `ai-observability-mlflow-backup-1`, and `ai-observability-mlflow-retention-1` still running after the MLflow stack was removed from the repository. The operator subsequently removed that stack through Portainer, and a follow-up live check confirmed that those containers are no longer running. The immediate cleanup is complete, but the incident demonstrates that deleting source does not decommission the corresponding Portainer stack.

Do not replace Portainer merely to eliminate this split. Instead:

- add a small declarative inventory of expected Portainer stack names and Compose paths;
- document that deleting a stack requires disabling/removing it in Portainer before deleting its source;
- add a read-only drift check comparing expected stacks or containers with the live Docker host;
- document how Portainer Git credentials, repository, branch, path, and update policy are configured, without storing secrets in Git.

### 3. Make strict RouterOS state the safe default

The RouterOS implementation is complex because it manages a security-critical device with real lockout risk. Its explicit firewall policy and extensive verification earn their complexity.

The operational interface is the problem: `routeros_enable_vlan_filtering` and `routeros_enable_default_drop` currently default to false in [group_vars/routeros.yaml](/Users/mm/dev/home-infra/ansible/group_vars/routeros.yaml:110), while the normal `just routeros` recipe overrides them.

Change the steady-state defaults to strict. Recovery/scaffold execution should explicitly set both values false and should retain the out-of-band-access warnings. A direct playbook run should converge to the production security posture rather than silently weaken it.

The physical port policy should also change:

- keep `ether7` as the existing dedicated OOB management port (`10.66.0.1/30`), so recovery access is preserved throughout the change;
- remove `ether6` from `routeros_vlan1_untagged_ports`, where it currently acts as a wired MGMT fallback;
- add `ether6` to the bridge as an untagged access port with the PVID and bridge-VLAN membership for the "Mad Villainy" client VLAN;
- allow clients connected to `ether6` the same internet and inter-VLAN policy intended for that VLAN, without granting MGMT-plane access;
- extend RouterOS verification to assert the `ether6` bridge PVID, tagged/untagged membership, DHCP lease path, internet access, and MGMT isolation.

"Mad Villainy" does not currently appear as a canonical network name in the repository. Before implementation, confirm whether it is the existing DFLT network (VLAN 30, `10.77.30.0/24`) or a new VLAN. Do not change the port until that mapping is explicit. `ether8` can remain unused unless a second wired management fallback is deliberately required; it should not replace the already-proven `ether7` OOB path without a separate recovery design.

### 4. Document the actual 32 GB memory constraint and intentional UniFi shutdown

The physical server was designed for 64 GB, but a faulty 32 GB module has been removed and the current installed capacity is 32 GB. The UniFi controller VM is intentionally configured with `on_boot = false` and `started = false`: [terraform/main.tf](/Users/mm/dev/home-infra/terraform/main.tf:217). It is retained as cold infrastructure for future AP or network-controller changes.

This is not Terraform drift. Update the README to distinguish designed capacity from current installed capacity and state that the controller must be started before running the UniFi Ansible role or `terraform/network`. Remove the stale Terraform comment referring to a generic 31 GiB host ceiling when the Talos resources leave `main`.

The AP model also needs one authoritative value: the README says U7 Pro while RouterOS variables say U6-Pro.

### 5. Remove completed Home Manager migration logic

The live `ai-dev` host contains the `ai-dev-bootstrapped` completion marker. A second read-only check found none of the retired Pacman/AUR packages or legacy OpenCode/Fisher files targeted by the migration tasks.

The one-time migration is complete. Remove from [home-manager.yaml](/Users/mm/dev/home-infra/ansible/roles/ai-dev/tasks/home-manager.yaml:130):

- marker detection and creation;
- Fisher and legacy configuration discovery/removal;
- retired OpenCode binary removal;
- removal of packages now owned by Home Manager.

Simplify steady-state activation to build the desired Home Manager generation, compare it with the current generation, and activate only when different. Update [docs/ai-dev.md](/Users/mm/dev/home-infra/docs/ai-dev.md:71) so it describes current ownership rather than migration behavior.

### 6. Docker hardening rollout is complete; the document is stale

A live check confirmed all 37 running containers use `no-new-privileges`. Expected application, database, and LinuxServer.io containers drop all capabilities and add back only their documented initialization/runtime requirements. The intentional exceptions remain Traefik, Portainer, Pocket ID, and `immich-ml`; Traefik reaches Docker through the restricted socket proxy, which itself drops all capabilities and is read-only.

The rollout described in [docs/docker-hardening.md](/Users/mm/dev/home-infra/docs/docker-hardening.md:1) has therefore reached steady state. Replace the rollout order, candidate tables, and repeated validation instructions with a shorter document containing:

- the default hardening policy;
- retained-capability classes and why they exist;
- explicit exceptions and their observed failure reasons;
- Docker socket ownership and proxy policy;
- a short verification checklist for future image changes;
- the latest live-validation date.

Fresh-volume initialization cannot be proven by inspecting the currently warm volumes. Keep that as a future image-change verification requirement rather than describing the whole rollout as incomplete.

### 7. Improve, document, and validate the Proxmox template scripts

Both scripts pass `bash -n`, but ShellCheck is not currently available in the project environment. The scripts are understandable, but they are unsupported operational interfaces and have maintainability risks:

- they assume execution as root directly on the Proxmox host without checking;
- they mutate global Proxmox storage paths;
- a failure after `qm create` can leave a partially created VM that makes the next run report “nothing to do”;
- the Ubuntu first-boot wait has no timeout;
- both consume moving `latest`/`current` images, so builds are not reproducible even though download integrity is checked;
- invocation and recovery behavior are undocumented.

Keep Bash if these remain host-local administration tools, but add a clear usage contract, prerequisite checks, bounded waits, actionable failure messages, and cleanup guidance. Add ShellCheck to Nix/CI. Do not create a shared Bash abstraction merely to remove two-script repetition; the scripts build materially different images and explicit steps are easier to audit.

### 8. Fix Docker network declarations

The Miniflux, ownCloud, and Wallabag backend networks explicitly use public ranges (`172.80.1.0/24`, `172.40.1.0/24`, and `172.60.1.0/24`) without assigning fixed container addresses: [Miniflux](/Users/mm/dev/home-infra/docker/miniflux/compose.yml:68), [ownCloud](/Users/mm/dev/home-infra/docker/owncloud/compose.yml:120), [Wallabag](/Users/mm/dev/home-infra/docker/wallabag/compose.yml:107).

Remove these IPAM blocks and let Docker allocate private subnets. This reduces configuration and avoids routing collisions.

Apply the change one stack at a time rather than redeploying all three together. For each of Miniflux, ownCloud, and Wallabag:

1. Render the Compose configuration before deployment.
2. Record the current network, container health, and restart counts.
3. Redeploy only that stack with the explicit IPAM block removed.
4. Confirm application-to-database/cache name resolution and connectivity.
5. Confirm the Traefik HTTPS route and container health.
6. Exercise an application-level read/write workflow: create and retrieve a feed item in Miniflux, upload/download a test file in ownCloud, and save/read an article in Wallabag.
7. Confirm logs contain no DNS, connection, migration, or permission errors and restart counts remain stable.

If any check fails, restore that stack's previous Compose definition and redeploy it before proceeding. The regression checks are part of the change, not optional follow-up work.

### 9. Simplify Terraform and shared network knowledge

- The `proxmox_vm` module has only one caller, `ai-dev`. Inline it or migrate enough real VMs to it that its interface earns its keep; do not preserve a hypothetical seam.
- Terraform and Ansible separately define VLAN IDs, subnets, and infrastructure addresses. Consolidate the shared network facts into a small machine-readable inventory, or add a consistency test if direct sharing makes either tool harder to operate.
- Keep the Proxmox and UniFi Terraform roots separate because they have different providers, credentials, state, lifecycle, and availability requirements.
- Keep `prevent_destroy` on valuable VMs.

### 10. Simplify Ansible, Nix, CI, Renovate, and repository documentation

- Remove unused zram support if no real host requires it after the current zswap changes settle.
- Pin Ansible collection versions rather than using unbounded lower constraints.
- Remove the generated mocked module under `ansible/.ansible/` and ignore generated lint state.
- Ensure CI syntax-checks `ansible/run.yaml`; the current lint exclusion misses the actual play composition.
- Correct the Docker role description: it configures Docker and deploys the bootstrap stack but does not install Docker.
- After the Talos/Kubernetes branch split, remove its tools from the Nix shell and its workflows and rules from CI/Renovate.
- Re-test whether the custom Black, yamllint, and ansible-lint Nix patches remain necessary after the environment shrinks.
- Stop ignoring `docs/*` by default. Track documentation normally and delete temporary documents deliberately.
- Correct existing README drift: nonexistent game-server wording, current RAM, UniFi cold-start procedure, AP model, and Docker deployment ownership.

Repeated Compose labels and explicit security declarations should generally remain repeated. DRY should remove duplicated knowledge and competing ownership, not turn readable YAML into a generator.

## Recommended implementation order

1. Create and push the dedicated Talos/Kubernetes branch.
2. Remove the inactive platform and all cross-cutting support from `main`.
3. Update README architecture, RAM, UniFi, and Docker ownership documentation.
4. Remove completed Home Manager migration logic and shorten its documentation.
5. Make RouterOS strict mode the default and recovery mode explicit.
6. Confirm the canonical VLAN mapping for "Mad Villainy", then convert `ether6` into its wired access port while preserving and verifying `ether7` OOB access.
7. Remove unnecessary Docker IPAM declarations one stack at a time with the specified application-level regression checks.
8. Add the Portainer expected-stack inventory, lifecycle documentation, and drift check. The previously orphaned MLflow stack has already been removed and verified absent.
9. Replace the Docker hardening rollout plan with a steady-state policy.
10. Harden and document the Proxmox template scripts and add ShellCheck.
11. Simplify Terraform, Ansible variability, Nix, CI, Renovate, and repository hygiene.

No infrastructure or repository state should be deleted merely because it appears unused. Each destructive step should first verify its exact target and preserve recovery through Git, Portainer backups, or existing VM/storage protections as appropriate.
