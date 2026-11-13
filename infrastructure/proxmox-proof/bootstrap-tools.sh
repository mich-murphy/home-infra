#!/usr/bin/env bash
set -euo pipefail
umask 077
STATE=${STATE:-$HOME/.local/state/home-infra/talos-proof}
case "$(uname -s)-$(uname -m)" in Darwin-arm64) platform=darwin-arm64;; Linux-x86_64) platform=linux-amd64;; *) echo unsupported >&2; exit 1;; esac
mkdir -p "$STATE/bin" "$STATE/downloads"
chmod 700 "$STATE" "$STATE/bin" "$STATE/downloads"
base=https://github.com/siderolabs/talos/releases/download/v1.14.5
curl -fL "$base/talosctl-$platform" -o "$STATE/downloads/talosctl-$platform"
curl -fL "$base/sha256sum.txt" -o "$STATE/downloads/sha256sum.txt"
(cd "$STATE/downloads"; grep " talosctl-$platform$" sha256sum.txt | if command -v sha256sum >/dev/null; then sha256sum -c -; else shasum -a 256 -c -; fi)
install -m 700 "$STATE/downloads/talosctl-$platform" "$STATE/bin/talosctl"
"$STATE/bin/talosctl" version --client
