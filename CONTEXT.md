# Home Infrastructure

Canonical language for the infrastructure and operational policies managed by
this repository.

## Language

**RouterOS firewall policy**:
The ordered traffic rules and NAT intent enforced on the router, including
strict and recovery postures.
_Avoid_: Router rules, firewall config

**Docker host provisioning**:
The Ansible-owned preparation of the Docker host, including Docker runtime
installation, storage mounts, published-port policy, daemon policy, and
bootstrap deployment.
_Avoid_: Media role, application stack deployment
