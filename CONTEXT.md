# Home Infrastructure

Canonical language for the infrastructure and operational policies managed by
this repository.

## Language

**RouterOS firewall policy**:
The ordered traffic rules and NAT intent enforced on the router, including
strict and recovery postures.
_Avoid_: Router rules, firewall config

**ai-dev provisioning**:
The initial and recovery-time preparation of the ai-dev machine performed from
outside the machine.
_Avoid_: Ongoing updates, maintenance

**Docker host provisioning**:
The Ansible-owned preparation of the Docker host, including Docker runtime
installation, storage mounts, published-port policy, daemon policy, and
bootstrap deployment.
_Avoid_: Media role, application stack deployment

**Subscription proxy**:
CLIProxyAPI (CPA) on ai-dev, owned by the Ansible cliproxy role: one tailnet
HTTPS endpoint, `https://ai-dev.<tailnet>.ts.net` through `tailscale
serve`, that pools Claude and Codex subscription accounts, with the stock
management dashboard and no client API keys. Tailscale identity and the
tailnet grant to tcp:443 are its client access control.
_Avoid_: AI gateway, API proxy, Hermes

**Routing controller**:
The cliproxy-controller service beside CPA. It sets CPA's credential
priorities so the account whose weekly quota resets soonest fills first,
enables Codex WebSockets, and reports routing order and cache hit rates on its
status page at `/controller/` on the same HTTPS name. It never redeems banked
resets.
_Avoid_: Scheduler, load balancer

**Hermes decommission**:
The opt-in, one-time ai-dev role run that removes the retired Hermes agent's
account, services and files from a live host.
_Avoid_: Hermes maintenance, uninstall
