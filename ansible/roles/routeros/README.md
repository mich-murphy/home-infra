# routeros role

Configures the Mikrotik RB5009 (RouterOS v7) over the API using
`community.routeros.api_modify`. All data lives in `group_vars/routeros.yaml`.

Every task is **non-destructive** (`handle_absent_entries: ignore`): it reconciles
only the entries declared here and never removes the router's existing WAN/base rules.
Managed entries carry a `managed: routeros role` comment.

## Prerequisites

1. Restricted API user on the RB5009:
   ```
   /user group add name=ansible policy=api,read,write,policy,test,sensitive
   /user add name=ansible group=ansible password=<secret>
   ```
   Put `routeros_api_user` / `routeros_api_password` in the vault (`just edit`).
2. Confirm the OPEN ITEMS in `group_vars/routeros.yaml` (interface names, bridge
   name, admin/IPMI IPs, KDS DNS) against the live router.
3. **Console/serial access ready** before the two gated steps below.

## Lockout-safe rollout

`just routeros` runs the safe steps (VLAN/DHCP/DMZ scaffolding, firewall *allows*,
NAT) but **skips** the two dangerous flips, which are double-gated (a var
*and* a `never` tag):

```sh
# 1. Safe scaffold — VLANs, DHCP, address-lists, allow rules, NAT
just routeros          # == ansible-playbook ... --limit routeros

# 2. Verify the bridge VLAN table, then enable filtering (have console ready):
cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit routeros --tags vlan-filtering -e routeros_enable_vlan_filtering=true

# 3. Verify all allows are present/ordered (`/ip firewall filter print`), THEN:
cd ansible && ansible-playbook run.yaml --vault-password-file .vaultpass \
  --limit routeros --tags default-drop -e routeros_enable_default_drop=true
```

## ⚠️ Caveat — validate against the live router

These tasks were authored from the plan and the `community.routeros` schema, not
against your live RB5009. Before trusting them: dry-run, and after each apply inspect
the result (`/interface bridge vlan print`, `/ip firewall filter print`,
`/ip dhcp-server print`). RouterOS firewall **rule ordering** in particular is not
fully controlled by `api_modify` when pre-existing rules are present — verify the
managed allows sit above the default-drop.
