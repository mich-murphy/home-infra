#!/usr/bin/env bash
set -euo pipefail

ANSIBLE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly ANSIBLE_DIR
readonly MAINTENANCE="${ANSIBLE_DIR}/roles/ai-dev/files/hermes-maintenance"
BASH_BIN=$(command -v bash)
readonly BASH_BIN
TEST_ROOT=$(mktemp -d)
export STUB_LOG="${TEST_ROOT}/sudo-calls.log"
readonly TEST_ROOT
trap 'rm -rf "$TEST_ROOT"' EXIT

# A Hermes home with stub tools on disk, so path checks behave as on ai-dev.
hermes_home="${TEST_ROOT}/hermes-home"
hermes_bin="${hermes_home}/.local/bin"
mkdir -p "$hermes_bin"
cat >"${hermes_bin}/stub-tool" <<'SCRIPT'
#!/usr/bin/env bash
case "${1:-}" in
  --version)
    echo "$(basename "$0") 1.0.0"
    ;;
  update)
    if [[ ${STUB_UPDATE_FAIL:-0} == 1 ]]; then
      echo 'git pull failed: network unreachable'
      exit 1
    fi
    # Real hermes update exits 1 when its own gateway restart fails after a
    # successful update; the wrapper must tolerate exactly that.
    echo 'Update complete! (v1.0.0 -> v1.0.1)'
    exit 1
    ;;
  install)
    exit 0
    ;;
  *)
    exit 0
    ;;
esac
SCRIPT
chmod +x "${hermes_bin}/stub-tool"
for command in hermes herdr moshi-hook; do
  ln -s stub-tool "${hermes_bin}/${command}"
done

fake_bin="${TEST_ROOT}/fake-bin"
mkdir -p "$fake_bin"
# Records every call; executes "as hermes" commands for real, emulates systemctl.
cat >"${fake_bin}/sudo" <<'SCRIPT'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_LOG"
if [[ ${1:-} == "-u" ]]; then
  shift 2
  shift
  while [[ ${1:-} == *=* ]]; do shift; done
  exec "$@"
fi
while (($#)); do
  case "$1" in
    list-unit-files)
      if [[ ${STUB_NO_UNITS:-0} == 1 ]]; then
        exit 0
      fi
      printf 'hermes-gateway.service enabled\nmoshi-hook.service  enabled\n'
      exit 0
      ;;
    is-active)
      echo active
      exit 0
      ;;
    restart)
      exit 0
      ;;
  esac
  shift
done
exit 0
SCRIPT
# The update path pipes curl output into sh; a no-op installer keeps it inert.
cat >"${fake_bin}/curl" <<'SCRIPT'
#!/usr/bin/env bash
echo true
SCRIPT
chmod +x "${fake_bin}/sudo" "${fake_bin}/curl"

run_maintenance() {
  : >"$STUB_LOG"
  HERMES_MAINTENANCE_HOME="$hermes_home" PATH="${fake_bin}:/usr/bin:/bin" \
    "$BASH_BIN" "$MAINTENANCE" "$@"
}

# No arguments must fail with usage.
if run_maintenance >/dev/null 2>&1; then
  echo "maintenance unexpectedly passed without a mode" >&2
  exit 1
fi

# Unknown modes must fail with usage.
if run_maintenance bogus >/dev/null 2>&1; then
  echo "maintenance unexpectedly accepted a bogus mode" >&2
  exit 1
fi

# Status reports stub versions and enabled unit state.
run_maintenance status >"${TEST_ROOT}/status.log"
for wanted in 'Hermes:.*hermes 1.0.0' 'Herdr:.*herdr 1.0.0' 'Moshi:.*moshi-hook 1.0.0' \
  'hermes-gateway.service' 'moshi-hook.service' 'active'; do
  grep -q -- "$wanted" "${TEST_ROOT}/status.log"
done

# Restart drives each enabled unit through systemctl --machine=hermes@.
run_maintenance restart >"${TEST_ROOT}/restart.log"
grep -q 'restart hermes-gateway.service' "$STUB_LOG"
grep -q 'restart moshi-hook.service' "$STUB_LOG"

# With no enabled units, restart reports it and stays a no-op.
STUB_NO_UNITS=1 run_maintenance restart >"${TEST_ROOT}/restart-empty.log"
grep -q 'nothing to restart' "${TEST_ROOT}/restart-empty.log"
if grep -q 'restart ' "$STUB_LOG"; then
  echo "restart unexpectedly invoked systemctl with no enabled units" >&2
  exit 1
fi

# Update refreshes the toolchain, reconciles the Moshi integration, and
# finishes by restarting the enabled units. The stub updater exits 1 with the
# success marker, matching upstream's self-restart failure mode.
run_maintenance update >"${TEST_ROOT}/update.log"
grep -q 'hermes update' "$STUB_LOG"
grep -q 'moshi-hook install --target hermes' "$STUB_LOG"
grep -q 'restart hermes-gateway.service' "$STUB_LOG"

# A real update failure (nonzero without the success marker) fails the run.
if STUB_UPDATE_FAIL=1 run_maintenance update >"${TEST_ROOT}/update-fail.log" 2>&1; then
  echo "update unexpectedly passed after a genuine updater failure" >&2
  exit 1
fi
grep -q 'FAILED: Hermes update' "${TEST_ROOT}/update-fail.log"

echo "hermes-maintenance tests passed"
