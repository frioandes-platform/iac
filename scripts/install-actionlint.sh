#!/usr/bin/env bash
# Linux amd64 CI helper; immutable release archive verified against its checksum.
set -euo pipefail
: "${RUNNER_TEMP:?Run this helper inside GitHub Actions}"
: "${GITHUB_PATH:?Run this helper inside GitHub Actions}"
mkdir -p "$RUNNER_TEMP/actionlint-bin"
archive="$RUNNER_TEMP/actionlint-bin/actionlint.tar.gz"
curl --fail --silent --show-error --location --retry 3 \
  https://github.com/rhysd/actionlint/releases/download/v1.7.7/actionlint_1.7.7_linux_amd64.tar.gz \
  --output "$archive"
printf '%s  %s\n' 023070a287cd8cccd71515fedc843f1985bf96c436b7effaecce67290e7e0757 "$archive" | sha256sum --check
tar -xzf "$archive" -C "$RUNNER_TEMP/actionlint-bin" actionlint
chmod u+x "$RUNNER_TEMP/actionlint-bin/actionlint"
printf '%s\n' "$RUNNER_TEMP/actionlint-bin" >> "$GITHUB_PATH"
