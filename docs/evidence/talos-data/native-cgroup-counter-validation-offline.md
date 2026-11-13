# Native cgroup counter validation — OFFLINE correction

No live grant, runtime query, image/native execution or new functional acceptance.
Binding authority remains released; parent owns independent binding acceptance,
root docs/gates/integrity review and any future native grant.

## Narrow validation correction

`Supervisor.validate_forensics()` no longer defaults missing `oom` or `oom_kill`
to zero. Both `memory.events` and `memory.stat` now require genuine counter
records: lowercase kernel-style key and canonical nonnegative decimal integer.
Empty/malformed lines, duplicate keys, signed/negative/fractional values and
missing mandatory keys reject. Events require `oom` and `oom_kill`, both zero;
stat requires `anon` and `file` observations (zero is valid). Other well-formed
kernel counters remain accepted; no exhaustive kernel-version key list or full
memory-capacity inference is imposed.

`memory.current` and `memory.peak` must each be positive decimal integer bytes,
independently at or below **192MiB**. There is deliberately **no peak >= current
assertion**, because the kernel files are read sequentially. No limits, budgets,
PHP ini, admission, receipts, application logic, cleanup or retry policy changed.

## Payload source inspection

The unchanged PHP `cgroups()` function performs actual
`file_get_contents('/sys/fs/cgroup/' . $file)` reads of all four kernel files.
A false read becomes explicit `['gap' => 'unavailable']`, not a fabricated number
or empty default; the supervisor's string-type gate rejects that marker. Empty
successful reads fail the new mandatory counter/scalar checks. The payload's
exception path reports `BLOCKED_OR_FAILED` and exits1. No capture failure can be
accepted merely because the application phase returned successfully.

The PHP payload was **not modified or executed**. Source-inspection regression
coverage pins these direct-read and explicit-gap expressions, and validates all
four missing/non-string source-error cases through the real supervisor parser.
This is offline evidence, not attestation of a running image/kernel or PHP.

## Offline tests and hashes

Focused tests passed: supervisor35, initializer35, compiler8, data42 = **120**.
Every cluster/Talos/VM/image/native runtime call is forbidden or mocked. The
existing bounded serialization tests use local Python processes only.
`git diff --check` passed.

New positives include an untouched four-file native kernel example copied from
the already retained read-only binding-helper log, plus exact192MiB boundaries,
zero anon/file observations, future well-formed counters and current > peak.
The captured example is **not Nextcloud native-process runtime evidence**.
Negatives cover absent/empty OOM records, duplicate/malformed/negative counters
(including optional keys), missing anon/file, source-error gap markers and
missing fields, and malformed/zero/negative/over-limit current/peak observations.

- Updated supervisor SHA256:
  `7e1e200171c4afee2d333cd1156fddefd2e83d50b621e876a397a026cc29f6b0`.
- Unchanged native PHP SHA256:
  `f0bbc365f398aa09a390aa753c5bc78a0f306108dcee9595002e0ebcb6c15a21`.

Parent review must use the updated supervisor source hash rather than treating
the earlier postbinding handoff's historical source hash as current. No old
handoff, receipt, journal, UID or evidence file was changed.

## Resource interpretation remains bounded

The supplied Nextcloud35 documentation context states128MB minimum and512MB
recommended per process, with PHP memory_limit512MB recommended. The unchanged
**192MiB** CLI envelope is a bounded trial constraint, **not a capacity claim**
or a claim that the recommendation is met. Neither limits nor ini were altered.
No native install/cron, functional Nextcloud PASS, capacity/durability or
production-readiness claim follows from parser tests or the earlier binding.
