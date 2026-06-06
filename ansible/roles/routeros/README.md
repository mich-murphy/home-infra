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
3. **Out-of-band access staged before any VLAN-filtering work.** The role pulls
   `routeros_oob_port` (`ether7`) out of the bridge and gives it `10.66.0.1/30`.
   Plug a laptop into it with a static `10.66.0.2/30` and confirm you can reach
   `10.66.0.1` over SSH/WinBox. This is the only fallback that survives
   vlan-filtering — under filtering, untagged-VLAN1 console access **and**
   Winbox-by-MAC both stop working (learned the hard way on 2026-06-03).

## Normal run (safe scaffold)

`just routeros` is **safe** — it never enables the two lockout-risk flips:

```sh
just routeros
```

It maintains: the out-of-band port, VLAN interfaces + per-VLAN DHCP, DMZ physical
isolation, the firewall address-lists / **allow** rules / NAT, and management
services restricted to `routeros_router_admin_sources` (MGMT + OOB subnets).
`routeros_enable_vlan_filtering` / `routeros_enable_default_drop` default to
`false`, and the vlan-filtering flip is additionally `never`-tagged.

The run ends with read-only verification. To run only the checks:

```sh
just routeros-verify
```

## Lockout-risk flips (explicit, one at a time)

⚠️ A 2026-06-03 apply that enabled vlan-filtering with MGMT bound to the raw bridge
caused a full management lockout that needed a physical reset. Do these only with the
OOB port verified (prereq 3):

```sh
just routeros-strict
```

The strict recipe applies the normal scaffold plus the two explicit hardening flips:
`vlan-filtering` and `default-drop`. It is intentionally separate from
`just routeros` so the lockout-risk path is auditable in shell history and review.

After any flip, run the read-only verifier:

```sh
just routeros-verify-strict
```

Also inspect `/interface bridge vlan print`, `/interface bridge port print`,
`/ip dhcp-server print`, and `/ip firewall filter print` if a check fails.

## MGMT / VLAN 1 DHCP (why it stays on the raw bridge)

MGMT keeps its gateway IP and DHCP server on the **raw `bridge` interface**, reachable
on VLAN 1 via the bridge PVID (=1) untagged path. The bridge is **not** a tagged member
of VLAN 1 in `bridge.yaml` (untagged ports only).

Adding the bridge to VLAN 1's *tagged* list — the earlier design — is what broke
dynamic MGMT DHCP under vlan-filtering: the bridge then expected VLAN 1 tagged while the
raw-bridge IP/DHCP operate untagged, so untagged clients' DISCOVERs went unanswered.
That was the recurring AP / GL.iNet / docker-host "random" DHCP loss. Static-lease hosts
kept working (which masked it). A later attempt to fix it by moving MGMT onto a dedicated
`vlan1-mgmt` interface **caused the 2026-06-03 lockout** (creating that interface hijacks
VLAN 1 CPU delivery from the raw-bridge IP); that approach was abandoned for this one.

⚠️ This binding is unverified under live vlan-filtering. Before trusting it: enable
filtering from the OOB port and confirm a VLAN 1 client still pulls a DHCP lease.

## Proxmox host topology

The RouterOS port map assumes the Proxmox host is cabled and bridged like this:

- `eno2` -> `vmbr0` -> RB5009 `ether3`: production/MGMT uplink. The host address
  is `10.77.1.100/24` with gateway `10.77.1.1`; VMs/LXCs without an explicit VLAN tag
  land on native MGMT.
- `eno1` -> `vmbr1` -> RB5009 `ether2`: untagged DMZ uplink. The Proxmox host should
  not have an IP on this bridge; ai-dev guests on `vmbr1` get DHCP from `10.77.99.1`.

Keep `vmbr1` as an untagged bridge unless there is a deliberate need to trunk VLANs into
the DMZ. Allowing all VLAN IDs on the DMZ bridge makes the host side broader than the
RouterOS model, which treats `ether2` as a single untagged L3 DMZ interface.

## Service VLAN cutover checks

`docker-host` is a service workload and should not live on native MGMT. Terraform tags
its NIC with VLAN 20, and this role reserves `10.77.20.246` on `srv-dhcp`. After the
VM reconnects or reboots, verify the guest has a `10.77.20.0/24` lease, then update any
external DNS records that still point service names at the old `10.77.1.246` address.

The ai-dev guests should land on the physical DMZ (`10.77.99.0/24`) through `vmbr1`.
If they receive `10.77.1.0/24` leases, the RB5009 DMZ port is still bridged into MGMT
or the cabling/port map is wrong; do not enable `default-drop` until that is corrected.
