# Architecture review: historical snapshot

The original static review is superseded by repository retirement cleanup.
ai-dev (VM 110), its Arch template provisioning path, CLIProxyAPI/controller,
agent observer/backend, and media broker are no longer declared or supported.
The coordinator confirmed live destruction of VM 110 and unused Arch template
9002 on 2026-10-07, with no remaining configs or zvols; the latest 2026-10-07
VM backup was retained. The AI vendor snippet was deleted and the backup-job
exclusion now contains only Ubuntu templates 9001 and 9003. Portainer-owned
media-broker stack 40 was deleted through its owner API without changing other
stacks. No cold retired VM remains. Observer containers/networks/source,
dedicated broker secret copies, unused vault/release secrets and the two retired
Terraform state records were subsequently removed and verified. No broad
Terraform apply was performed; shared application API credentials were not
revoked.

Current declarations retain TrueNAS and Docker at 10 GiB each and UniFi normally
stopped. Physical DMZ isolation remains reserved infrastructure. Jellyfin uses
the active encoding path `/cache/transcodes` on local disk. The old, unused
`/transcode` tmpfs mount remains in the running container until a Portainer-managed
recreation; its removal is declared in Compose. Actual transcoding/playback was
not tested. See [Proxmox host](proxmox-host.md),
[Docker deployment](docker-deployment.md), and [TrueNAS storage](truenas-storage.md)
for maintained policies.

Beszel's Docker connectivity was restored, both systems report up, missing
CPU/memory/disk/status rules were configured, and its SMTP test was accepted
(inbox receipt subsequently confirmed by the user). Durable agent/firewall
ownership remains pending.
TrueNAS access through 1Password approval revealed recorded special-vdev and
PHY 3 link errors plus an undismissed CRITICAL VolumeStatus alert; the counters
were stable over the short sample, not certified resolved. Subsequently,
photos/Nextcloud `sync=standard` and application-context fsync checks were
verified, native TrueNAS SMTP/alert delivery was configured and its test job
succeeded, and both SSD extended SMART tests passed. The guarded full scrub
67305 was canceled after fresh PHY 3 counters increased by one each; a genuine
review-required email was SMTP-accepted. It did not complete integrity acceptance.
Physical-path closure and a post-repair full scrub remain pending. See the
storage record and [roadmap handover](homelab-roadmap-handover.md) for evidence
and the remaining sequenced work. Workload scheduling, management reachability,
automated monitoring restoration, and off-host backup improvements remain
separate follow-up tasks.
