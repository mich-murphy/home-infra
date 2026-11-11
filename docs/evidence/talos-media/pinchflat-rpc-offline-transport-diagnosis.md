# Offline diagnosis: missing RPC JSON and deliberate shutdown ordering

No new live grant, proof-runtime call, activation, recovery or archive operation.
No retained private media file/STOP marker was modified. The released window
77f1f267 remains blocked, not retrospectively passed. Its384 MiB peak,
2028 memory.events.max, observed OOM counters0 and sampled restartCounts0 are
unchanged facts with the original sampling limitations. They are not the cause
assigned to this transport failure or a capacity pass.

## Exact source review before changing transport

Pinned Pinchflat076f2fe78b32f5f0a4997639c89601774d34016b
[`docker/selfhosted.Dockerfile`](https://github.com/kieraneglin/pinchflat/blob/076f2fe78b32f5f0a4997639c89601774d34016b/docker/selfhosted.Dockerfile)
sets OTP27.2.4 and Elixir1.18.4. ERTS15.2.2 alone is not a unique OTP patch
identifier; review therefore followed the pinned Dockerfile rather than guessing
from ERTS metadata. Reviewed public upstream paths:

- [OTP27.2.4 erl_call documentation](https://github.com/erlang/otp/blob/OTP-27.2.4/lib/erl_interface/doc/references/erl_call_cmd.md):
  `-e` evaluates stdin; `-fetch_stdout` supplies a forwarding group leader for
  **both** `-a` and `-e`; `-no_result_term` suppresses the returned term, not IO.
  `-a` is the documented lightweight MFA interface with list/atom/number arguments.
- [erl_call.c](https://github.com/erlang/otp/blob/OTP-27.2.4/lib/erl_interface/src/prog/erl_call.c):
  read_stdin retains the exact bytes, with no appended newline. The `-e` branch
  calls erl_eval:eval_str/1; rpc_print_node_stdout forwards rex_stdout and retains
  the rex return. A nonnegative RPC transport result exits0 even if the returned
  term is an evaluation/application error. print_result_term gates its display.
- [erl_eval.erl](https://github.com/erlang/otp/blob/OTP-27.2.4/lib/stdlib/src/erl_eval.erl), eval_str/1:
  calls incremental erl_scan:tokens([], Str, 0), without feeding explicit eof.
  `{more,_}` becomes `{error,"Incomplete form (missing .<cr>)??"}`. Other parse/
  evaluation errors likewise become returned terms, not necessarily stderr.
- [erl_scan.erl](https://github.com/erlang/otp/blob/OTP-27.2.4/lib/stdlib/src/erl_scan.erl), scan_dot:
  whitespace after the dot finishes a form; an empty incremental tail needs more
  input. Merely ending the supplied byte list with a dot is insufficient here.
- [Elixir1.18.4 Code](https://github.com/elixir-lang/elixir/blob/v1.18.4/lib/elixir/lib/code.ex),
  eval_string/validated_eval_string: converts input using to_charlist, evaluates
  forms and returns `{value,binding}`. Exceptions are not converted into a success.

The old harness generated a final `.` with **no trailing whitespace**, piped it
with `printf '%s'`, then suppressed the result term. This is a concrete prepared
input/visibility defect: it can hide an incomplete-form error while returning0.
It is not evidence that `-e` inherently cannot forward IO or that Code evaluation
succeeded. The exact live error term was suppressed, and successful-call stderr
was discarded by the old kubectl wrapper. We cannot recover that missing stderr
or assert that no independent runtime error also occurred.

Offline inspection of the retained UID/container-ID bindings and both current
server streams/snapshots found **zero PROOF_JSON markers**, zero Incomplete-form
strings and zero eval_string/erl_eval/badarg/undef/syntax-error matches. No raw
server logs or secret bytes were printed. Server-log absence is consistent with
an error returned to the RPC client, but is not by itself causal proof.

## Bounded workstation reproduction — NOT Pinchflat

Downloaded public workstation OTP via Nix and the public Elixir1.18.4 OTP27 zip.
Tool reports **ERTS15.2.7.14** (not the exact native15.2.2). No Pinchflat code or
application was executed on the workstation. The optional committed test fixture
uses a unique test cookie, fresh unique loopback epmd/distribution ports, explicit
127.0.0.1 bind, one owned epmd and one owned BEAM with1 scheduler/async thread.
It disables auto-epmd startup, never uses global epmd/pkill or cookie files, and
terminates/waits only its exact Popen objects in finally/class cleanup. Failed
assertion runs also cleaned those owned processes.

Four real fixture methods pass:

1. `-e` final dot/no whitespace, fetched stdout, suppressed result: **exit0,
   empty stdout**. Same bytes with result printing: visible Incomplete-form term.
2. Appending newline: actual forwarded PROOF_JSON and `{ok,ok}` return.
3. Documented numeric-list MFA: actual stdout forwarded. erlang:error returns a
   visible badrpc term despite transport exit0.
4. Actual workstation Elixir1.18.4 `Elixir.Code eval_string [[codepoints]]`:
   JSON marker plus exact `{proof_rpc_ok, []}` sentinel. A raised RuntimeError
   produces visible badrpc/exception term and no JSON. ei_print_term represents
   exception-message binaries numerically, not as decoded JSON/plain text.

The first fixture MFA attempt using a quoted format-string argument failed with
an argument-parse diagnostic; numeric character-list arguments passed. Prepared
code uses numeric lists, not fragile string quoting. This remains a workstation
compatibility result, not native loader/RPC/Pinchflat acceptance.

## Prepared code changes; unexecuted against proof runtime

- Replace `-e` stdin evaluation with documented `-a` MFA, no new BEAM or binary.
  Invoke `Elixir.Code eval_string` with numeric character-list code, wrapped in
  an anonymous function so bindings stay empty. Success requires BOTH one real
  structured PROOF_JSON line and exact `{proof_rpc_ok, []}` return, plus all
  existing binary identity/one-BEAM/resource/restart/cgroup gates.
- Remove `-no_result_term`; keep genuine badrpc/error terms visible in private
  stdout rather than hiding them. No fallback or expression retry.
- Native remote commands now request exclusive0600 capture of **stdout and
  stderr on success and failure**, including partial timeout output. Capture
  metadata includes returncode and checkpoint Pod UID/container-ID binding.
  Errors remain errors; captured stderr is not echoed or treated as empty.

## Intentional shutdown ordering and remaining admission block

The historical cleanup race and STOP marker remain immutable. Outer watcher now
handles SIGINT/SIGTERM as a shutdown request instead of asynchronously interrupting
scale/wait. On the normal path it exits its monitoring context, stops/joins the
sampler, then scales0/deletes. Known OOM/control/counter failures still take the
emergency scale0 path immediately; join failure does not postpone emergency stop.

The prepared `finish_window(state, exact_owned_watcher_Popen)` helper signals that
owned supervisor and waits for its cleanup, rather than concurrently scaling0.
Future runner ordering must be:

1. On an ordinary result/failure, retain current/previous logs/full status while
   sampling continues. On known OOM/137/restart/counter failure, emergency stop
   takes priority instead.
2. Finish the embedded exercise monitor; call finish_window on the **exact owned
   outer watcher**. Do NOT independently scale while its normal shutdown runs.
3. Watcher joins sampler before intentional scale0; caller waits for exit, then
   independently verifies Pod absence. Timeout/failure triggers emergency stop
   and parent review, never another activation.

The old private runner is immutable historical evidence and does NOT adopt this
ordering automatically. Standalone provider CLI's self-cleanup must not be mixed
with an independently managed outer watcher: a future owned runner should import
exercise/monitoring and use finish_window, as above. No future runner was started.

Existing require_not_stopped remains fail-closed for every historical STOP marker;
there is **no clear/delete/ignore/override flag**, and changing state directory or
reusing an old grant is forbidden. A future activation needs NEW parent review,
explicit acknowledgement and exact run/STOP-history binding before any admission
path is extended. This checkpoint does not add such an acknowledgement bypass.

Validation: all24 scoped media test files pass, **161 methods**, with the4 real
workstation fixture methods enabled. Without explicit workstation tool prefixes,
that optional fixture is skipped (not silently claimed as a runtime pass).
Tests also cover success/failure stderr retention, explicit return sentinel,
sampling joined before normal scale0, exact-owned-watcher wait and emergency
fallback. No full-root CI or live acceptance claim.

Source SHA256s (public bytes retained separately from old proof state):

| Source | SHA256 |
| --- | --- |
| OTP27.2.4 erl_call.c | `9502407b25b7a5fc9d2164eedc74f840a819185e57828dffc0f3811ec61d3dec` |
| OTP27.2.4 erl_call docs | `683b65c81326670a9242cd1ce733d82338f4b2e081db8f73e7a4ec3e4ce728e7` |
| OTP27.2.4 erl_eval.erl | `32296c3651b51303f4ffb7e892dc17f6faed41c30a51a5cc8597d94046ee6789` |
| OTP27.2.4 erl_scan.erl | `6e1175072354516a34224ff3e74b57e2270798bf7b77aafc5dd3b749ac03a679` |
| Elixir1.18.4 code.ex | `1854c2ecd52c45db5aecb379f64f0857ebb9240a0fe57c450621080dda547add` |
| Public Elixir1.18.4 OTP27 zip | `5be18f35e329f7c5914a80dd9f323d7bbb144616df1ed16f6f0862a1900b4bb5` |
