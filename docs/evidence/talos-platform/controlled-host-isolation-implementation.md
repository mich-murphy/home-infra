# Implementation-only checkpoint; NO live isolation execution

Authorized read-only commands were executed via root@proxmox and the existing
localhost Kubernetes API. No listeners, test packets, instrumentation, cgroup
joins, new units, module loads, logger changes or production service calls ran.
A first SSH metadata connection to literal10.77.1.100 timed out; root@proxmox
worked. No private configs or credentials were printed.

Actual backend: iptables/ip6tables1.8.11 legacy. TRACE not loaded; IPv4 logger
nfnetlink_log, IPv6 NONE. Existing REJECT chain serialization matched the reviewed
source. Guard active; host_lifecycle approved_config and same_process succeeded.
At inspection MemAvailable2134MiB, swap28KiB, swapIO10. These are stale admission
metadata, not a grant. Existing listeners occupied neither UDP53 nor TCP18081;
no bind was attempted.

Cilium cilium-8thlg hostNetwork=true; bash5.3.9, perl/IO::Socket::INET and timeout
available; curl/wget/busybox absent. Only command/help/module presence was checked.
No client socket was created. Installed help confirmed systemd-run unit/property
options and iptables insertion/deletion options.

New collector is limited to one owned-child loopback trial and emits a capture,
not an acceptance verdict. Targetless exact-flow counter adjacency is a proposed
alternative to unavailable TRACE logging; parent must approve it before live
use. Original existing REJECT remains continuously in place. The node-origin
private-TCP gap remains open. See docs/talos-proof-host-isolation.md for exact
proposed commands, independent cleanup, limits and explicit nonclaims.

Offline tests cover exact rule/no target, adjacency, policy normalization,
cleanup idempotence/error, pidfd-owned worker kill, exited worker/no signal,
pidfd acquisition failure before GO, parent-death ordering and resource aborts.
A Linux-only no-network fork/PDEATHSIG integration test is included but skipped
on this macOS environment. Therefore real kernel supervisor-crash cleanup and
systemd StopPost operation still require separately authorized execution.
