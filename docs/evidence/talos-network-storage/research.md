# Upstream research and offline validation

Research used direct HTTPS fetches (this worker has no websearch tool). Primary
versioned sources, rather than historical branch assumptions:

- Cilium1.20.4 tested Kubernetes1.33–1.36:
  https://github.com/cilium/cilium/blob/v1.20.4/Documentation/network/kubernetes/compatibility.rst
- Cilium1.20.4 Gateway prerequisites, Gateway API1.6.1 and TPROXY requirements:
  https://github.com/cilium/cilium/blob/v1.20.4/Documentation/network/servicemesh/gateway-api/installation.rst
- Cilium native NodePort GatewayClassConfig example:
  https://github.com/cilium/cilium/blob/v1.20.4/examples/kubernetes/gateway/gateway-with-parameters.yaml
- Talos-specific KubePrism, capabilities and cgroup setup:
  https://docs.siderolabs.com/kubernetes-guides/cni/deploying-cilium
- Mayastor real node requirements (rendered upstream fetched successfully):
  https://openebs.io/docs/quickstart-guide/prerequisites
  > Two CPU cores;1GiB RAM; HugePage support; minimum2GiB of2MiB-sized pages,
  > free and available exclusively for each io-engine pod.
- Local-path0.0.37 implementation, limitations and manifest:
  https://github.com/rancher/local-path-provisioner/tree/v0.0.37
  https://raw.githubusercontent.com/rancher/local-path-provisioner/v0.0.37/deploy/local-path-storage.yaml
- Historical Cilium failure report is not a permanent1.19 prohibition:
  https://github.com/cilium/cilium/issues/46010
  Maintainers linked node-IP/wildcard LoadBalancer fixes; issue closed, later report
  confirms1.19.5 resolved it. Separate IPsec reports exist; this proof does not use
  IPsec or LB node-IP allocation. Selected1.20.4 for actual1.36 compatibility.

Latest-release API queries returned Cilium1.20.4, Gateway API1.7.0, local-path0.0.37
and Mayastor2.12.2. Latest Gateway API was deliberately NOT chosen because exact
Cilium-compatible1.6.1 was documented. Historical branch manifests were inspected
only via `git show`; no old bootstrap applied. Old OpenEBS umbrella4.4.0 and Cilium
1.18.10 were not copied as authoritative version choices.

## Reproducible offline evidence

Commands run successfully (no kubeconfig, no cluster mutation):

```
kubectl kustomize kubernetes/platform
kubectl kustomize kubernetes/platform/validation
bash -n kubernetes/bootstrap/install.sh kubernetes/bootstrap/tls.sh kubernetes/bootstrap/verify.sh
helm template cilium /tmp/talos-platform-research/cilium-1.20.4.tgz -n kube-system -f kubernetes/platform/cilium/values.yaml
```

Helm3.18.6 temporary binary verified against upstream SHA256; not committed.
Cilium render26 resources:2 DaemonSets,1 Deployment, digest-pinned images.
Platform Kustomize render16 resources; fixtures7 resources with all3 Deployments
replicas0. Python safe YAML parse succeeded on all rendered outputs. Public artifact
SHA256 values are in `kubernetes/bootstrap/artifacts.lock.json`.

Rendered Cilium images:
- `quay.io/cilium/cilium:v1.20.4@sha256:20fe92e4c86641233a450098c158d2d29085f3419931ab6bf681d2485dedf16e`
- `quay.io/cilium/operator-generic:v1.20.4@sha256:7a7a3489dc66ad67e420d285c8a8d2e169b0957ad15e120f593d27081bf38d82`
- `quay.io/cilium/cilium-envoy:v1.39.5-1792733054-8c73b2816bc8239e27f1fd53b271884688137459@sha256:547ab45f6092f681d9f54f3be9fa8fb1e705c9c5dc2df388efe3a52aa6965629`

## Pending live gates — not claimed passed

1. Talos dedicated disk identity/mount and VM cgroup production-private deny.
2. Cilium readiness and no node-network regression; actual platform memory usage.
3. Synthetic PVC write/read and fresh-pod read; WFFC binding to correct node/path.
4. DNS and validation positive access; cross-app denial; Cilium policy-drop verdicts
   for synthetic private/documentation-world addresses, never actual integrations.
5. Gateway Accepted/Programmed and route ResolvedRefs; HTTP body through approved
   VM NodePort forward; HTTPS body with explicit trusted synthetic cert; wrong host
   rejection. Certificate key stays outside git.
6. Node reboot recovery/backup restore, if later authorized, are distinct from pod
   restart and not implied by platform manifests.

Checkpoint update: parent reduced initial proposed guest RAM to2560MiB; VM creation
and `/var/mnt/proof` confirmation are still pending. All live gates above remain open.
TLS helper now also verifies exact context API server before modifying secrets.
