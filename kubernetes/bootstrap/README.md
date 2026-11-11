# Explicit isolated proof bootstrap

Requires Python3, kubectl with Kustomize, Helm3, openssl. No Flux, metrics-server,
cert-manager, Mayastor, monitoring, LB pool, L2 announcements or production DNS.

1. Provision dedicated Talos node: CNI none, kube-proxy disabled, KubePrism7445,
   schedulable control plane. Confirm dedicated new64GiB user disk actually mounted
   at `/var/mnt/proof` via Talos mount/block-device evidence **before provisioning**.
   Talos must permit kubelet access to that user-volume path. No production NFS.
2. Export private `KUBECONFIG`, `PROOF_CONTEXT`, exact `PROOF_API_SERVER` (including
   SSH-forward URL), and `PROOF_DISK_MOUNT_CONFIRMED=yes`. Do not commit kubeconfig.
   Run `./kubernetes/bootstrap/install.sh`. Installer checks server and single-node
   supported kubelet version, verifies locked downloads, installs CRDs before Cilium,
   and applies Kustomize. Require explicit parent authorization before execution.
3. Run `./kubernetes/bootstrap/tls.sh` (fresh synthetic7-day self-signed wildcard cert).
4. With parent approval set `PROOF_TESTS_AUTHORIZED=yes`; run `verify.sh`, redirecting
   non-secret output into `docs/evidence/talos-network-storage/`. New fixtures only;
   replicas return0 on exit; PVC intentionally retained. No disk quota is enforced by
   this provisioner despite requested64Mi. Set no expansion expectations.
5. Gateway needs explicit **proof-only SSH/QEMU user-mode forward** to its generated
   NodePorts (discover `kubectl -n proof-gateway get svc`). Never modify production
   NAT/DNS. For forwarded HTTP port18080:
   `curl --fail --resolve fixture.proof.invalid:18080:127.0.0.1 http://fixture.proof.invalid:18080/`.
   For HTTPS18443, export public cert only into private temp file:
   `kubectl -n proof-gateway get secret proof-tls -o jsonpath='{.data.tls\.crt}' | base64 -d > "$TMP_CERT"`
   then `curl --fail --cacert "$TMP_CERT" --resolve fixture.proof.invalid:18443:127.0.0.1 https://fixture.proof.invalid:18443/`.
   Compare nonce/body with PVC. Do **not** use `-k` as TLS trust proof. An unrelated
   hostname must not route. Record Gateway Accepted/Programmed and route ResolvedRefs.
   `kubectl port-forward service/...` can bypass the Cilium NodePort datapath: use the
   VM's approved NodePort forward for acceptance, not a Service port-forward.

## App contract

Use namespace `proof-<service/trust-group>` with namespace label
`app.kubernetes.io/part-of: talos-proof`, restricted Pod Security, no host networking,
hostPath or privileged app pods; service account tokens disabled unless justified.
Start workloads replicas0 and run only bounded staged tests. StorageClass `proof-local`.
HTTPRoutes attach `proof-gateway/proof`, hostname `<service>.proof.invalid`. Baseline
permits ingress from validation and Cilium reserved `ingress` identity, **not** all
pods in the Gateway namespace (Envoy uses the reserved identity). Explicit dependency
Cilium/Kubernetes policies must grant source egress **and** destination ingress.
All other ingress/egress defaults denied; CoreDNS TCP/UDP53 is the only baseline
app egress. Clusterwide `egressDeny` for world, host, remote-node and API server wins
against additive allow policies. Never add broad cluster/world exceptions. CoreDNS
can resolve external names, but apps cannot connect to those returned destinations.

## Safety and evidence limits

Local-path controller is trusted infrastructure outside the app label boundary;
its API access is necessary to provision volumes, and its helper namespace alone
needs privileged Pod Security for hostPath. App pods must never be admitted there.
The underlying VM's process/cgroup-scoped network deny is independent defense in depth;
network policies alone do not sandbox privileged/host-network workloads or node processes.

Inspect Cilium policy enforcement and capture denied packet verdicts during negative
requests (`kubectl -n kube-system exec ds/cilium -c cilium-agent -- cilium-dbg monitor --type drop`)
using a bounded external timeout/process; correlate source/destination and policy drop.
A timeout to an unroutable address alone is **not** proof of policy enforcement.
The denied same-cluster live backend paired with successful validation is stronger
functional isolation evidence. Do not send test requests to real production endpoints.
No automatic destructive PV cleanup; `Retain` plus refusal teardown means synthetic
volumes require explicit human-approved cleanup. No restore/VM-reboot/HA result is implied.
