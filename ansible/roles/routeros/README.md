# routeros role

Configures the Mikrotik RB5009 (RouterOS v7) over the API using
`community.routeros.api_modify`. All data lives in `group_vars/routeros.yaml`.

The role reconciles managed entries and leaves unrelated WAN/base rules alone.
Managed entries carry a `managed: routeros role` comment. The DMZ de-bridge is
the only managed removal, because physical isolation requires `routeros_dmz_port`
to be absent from the production bridge.

## Prerequisites

1. Restricted API user on the RB5009:
   ```
   /user group add name=ansible policy=api,read,write,policy,test,sensitive
   /user add name=ansible group=ansible password=<secret>
   ```
   Put `routeros_api_user` / `routeros_api_password` in the vault (`just edit`).
2. Confirm the OPEN ITEMS in `group_vars/routeros.yaml` (interface names, bridge
   name, admin/IPMI IPs, KDS DNS) against the live router.
3. Keep a console/serial fallback available before changing port maps or VLAN
   membership.

## Steady State

`just routeros` applies the full desired state:

```sh
just routeros
```

The normal run now maintains:

- VLAN filtering on the bridge.
- DMZ physical isolation by removing the DMZ port from the production bridge.
- An ordered managed forward-chain policy, with KDS DNS bypass blocks before WAN
  egress and the default drop last.
- RouterOS management services restricted to the static/reserved
  `routeros_admin_sources`.

After changes to the firewall matrix or port map, inspect `/interface bridge vlan print`,
`/interface bridge port print`, and `/ip dhcp-server print`. The role validates
managed firewall order during apply.
