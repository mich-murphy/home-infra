# Headless integration acceptance review

Independent offline reader `475e6728-5f5f-4a4` reviewed media commit `224430b9`. **HOLD activation; both operational entrypoints remain BLOCKED.** No edits, tests, runtime, private state or credentials were accessed by reviewer.

- **High—framing:** `headless.py:78–87` requires exact Content-Length120214, while `kubernetes/apps/media/plex/plex-unclaimed-proxy.py:93–99` deliberately strips Content-Length. Direct-opener doubles do not cover the actual adapter/Gateway path. Review validated length preservation or a separately bounded framing contract; do not simply drop the guard.
- **High—queued progress:** `headless-integration.py:309–328` can treat two pre-response reports delivered in one later parser batch as watermark plus post-response progress (`headless.py:330–367`). Consumption order is not frame-production order. Existing queued-report test delivers old reports before the reply and misses this case. Require a conservative pipe/parser boundary with adversarial backlog/partial-block tests.
- **High—session correlation:** activity/history validate item/client and fresh history ID, not an observed native session. Merely sending the receipt session does not establish attribution. Review supported PMS/Tautulli2.18.2 session mapping, or explicitly review a weaker fresh-client isolation oracle; never invent fields.
- **High—aggregate budget:** per-Pod effective limits do not bound replicas, rollout surge, simultaneous old/new or terminating Pods. Two individually valid Plex512 Pods can exceed896. Require cardinality/update-strategy and complete simultaneous-Pod accounting; old448+256 and proposed512+192 are not interchangeable profiles.
- **Medium—total deadline:** parent guards can invoke360s kubectl operations; stream open has socket, not total-header, timeout; final acceptance lacks a post-history expiry check. Cover guards/open/decode/stop/history/teardown with an end-to-end deadline.

Unknown HTTP outcome stays unresolved: killing/reaping local workers does not cancel a server-accepted request or prove stop ordering. Never claim remote cleanup complete or retry playing automatically after uncertainty. Add real owned-descendant cleanup tests, not just leader-reap doubles.

Native settings, monitoring thresholds, pagination totals/completeness, history durability delay and session mapping remain source/runtime gates. Returned-page length<=100 is not pagination completeness. Darwin exact-PID RSS sampling is a watchdog, not a hard ceiling. No new TLS-ignore, credential stdout, fake application response or Origin/Referer-stripping path was found; non-browser decoding still does not repair the browser401 failure.

Reported53 related unit tests and6 workstation decoder checks are component preparation only. Parent full484-method gate subsequently passed; it does not close these findings. No media grant or readiness promotion follows.
