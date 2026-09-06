#!/usr/bin/env bash
set -euo pipefail

ANSIBLE_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
readonly ANSIBLE_DIR
readonly MAINTENANCE="${ANSIBLE_DIR}/roles/ai-dev/files/ai-dev-maintenance"
BASH_BIN=$(command -v bash)
readonly BASH_BIN
TEST_ROOT=$(mktemp -d)
readonly TEST_ROOT
trap 'rm -rf "$TEST_ROOT"' EXIT

empty_home="${TEST_ROOT}/empty-home"
mkdir -p "$empty_home"
if HOME="$empty_home" PATH=/usr/bin:/bin "$BASH_BIN" "$MAINTENANCE" status >"${TEST_ROOT}/missing.log" 2>&1; then
  echo "status unexpectedly passed without installed tools" >&2
  exit 1
fi
for tool in Claude Codex Pi Herdr Moshi OpenCode; do
  grep -q "$tool" "${TEST_ROOT}/missing.log"
done

fake_home="${TEST_ROOT}/fake-home"
fake_bin="${fake_home}/.local/bin"
mkdir -p "$fake_bin"
cat >"${fake_bin}/fake-tool" <<'SCRIPT'
#!/usr/bin/env bash
case "$(basename "$0")" in
  herdr)
    [[ ${1:-} == integration ]] && { echo "integrations ready"; exit 0; }
    ;;
  moshi-hook)
    [[ ${1:-} == status ]] && { echo '{}'; exit 0; }
    ;;
  systemctl)
    exit 0
    ;;
  ss)
    echo "LISTEN 0 128 127.0.0.1:24543 0.0.0.0:*"
    exit 0
    ;;
esac
echo "$(basename "$0") 1.0.0"
SCRIPT
chmod +x "${fake_bin}/fake-tool"
for command in node claude codex pi herdr moshi-hook opencode systemctl ss; do
  ln -s fake-tool "${fake_bin}/${command}"
done
HOME="$fake_home" PATH="${fake_bin}:/usr/bin:/bin" "$BASH_BIN" "$MAINTENANCE" status >"${TEST_ROOT}/healthy.log"
