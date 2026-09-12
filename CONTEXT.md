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

**ai-dev maintenance**:
Ongoing user-tool and Home Manager updates initiated and verified on ai-dev
after provisioning. The Ansible ai-dev role owns and deploys the maintenance
command even when a human invokes it directly on the host.
_Avoid_: Provisioning, bootstrap

**Docker host provisioning**:
The Ansible-owned preparation of the Docker host, including Docker runtime
installation, storage mounts, published-port policy, daemon policy, and
bootstrap deployment.
_Avoid_: Media role, application stack deployment

**Hermes infrastructure agent**:
The Hermes install owned by the isolated `hermes` account on ai-dev, its
scoped Proxmox, Docker, and GitHub credentials, and the tiers of reach they
grant. Observes broadly, proposes changes by pull request, and changes nothing
on a running host.
_Avoid_: ai-dev maintenance, the management user's coding agents
