#!/usr/bin/env bash
set -euo pipefail

target="${1:?target triple is required}"
out="${2:?output directory is required}"
version="3.12.12+20260114"
base="https://github.com/astral-sh/python-build-standalone/releases/download/20260114"
case "$target" in
  darwin-amd64) triple="x86_64-apple-darwin" ;;
  darwin-arm64) triple="aarch64-apple-darwin" ;;
  windows-amd64) triple="x86_64-pc-windows-msvc" ;;
  linux-amd64) triple="x86_64-unknown-linux-gnu" ;;
  linux-arm64) triple="aarch64-unknown-linux-gnu" ;;
  *) echo "unsupported target: $target" >&2; exit 2 ;;
esac
archive="cpython-${version}-${triple}-install_only.tar.gz"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
curl --fail --location --retry 2 --connect-timeout 10 -o "$tmp/$archive" "$base/$archive"
curl --fail --location --retry 2 --connect-timeout 10 -o "$tmp/SHA256SUMS" "$base/SHA256SUMS"
expected="$(grep "  $archive$" "$tmp/SHA256SUMS" | awk '{print $1}')"
if command -v sha256sum >/dev/null 2>&1; then actual="$(sha256sum "$tmp/$archive" | awk '{print $1}')"; else actual="$(shasum -a 256 "$tmp/$archive" | awk '{print $1}')"; fi
[[ -n "$expected" && "$actual" == "$expected" ]] || { echo "CPython archive checksum mismatch" >&2; exit 1; }
mkdir -p "$out/python"
tar -xzf "$tmp/$archive" -C "$out/python" --strip-components=1
python_bin="$out/python/bin/python3"
if [[ "$target" == windows-* ]]; then python_bin="$out/python/python.exe"; fi
"$python_bin" -m pip install --disable-pip-version-check --no-compile --no-cache-dir -r requirements-cli.txt
