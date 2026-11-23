#!/bin/bash
# Fetch LZ4's block compressor at the v1.10.0 pin into work/lz4/ for sweetmon.
# Source: github.com/lz4/lz4 at LZ4_COMMIT (the v1.10.0 tag), lib/ only.
# The files stay out of git; phone/tools/lz4/LICENSE covers the licence either way.
set -euo pipefail
cd "$(dirname "$0")/.."
LZ4_COMMIT=ebb370ca83af193212df4dcbadcc5d87bc0de2f0
out=work/lz4
checksum=(sha256sum)
if command -v shasum >/dev/null; then
	checksum=(shasum -a 256)
fi
verify() (
	cd "$1" || exit
	"${checksum[@]}" -c <<'EOF'
9396f7de527bc8435de9c7569fb7998e56545a84b4f3c2d808c0235c01774539  lz4.c
26b82efc53d1570f3b54eef02e9c4764c1ad374ff03cac04e2ced5ea4d4c552f  lz4.h
EOF
)
if verify "$out" >/dev/null 2>&1; then
	exit 0
fi
mkdir -p "$out"
staging=$(mktemp -d "$out/fetch.XXXXXXXX")
trap 'rm -rf "$staging"' EXIT
for file in lz4.c lz4.h; do
	curl -fsSL "https://raw.githubusercontent.com/lz4/lz4/$LZ4_COMMIT/lib/$file" -o "$staging/$file"
done
verify "$staging"
mv "$staging/lz4.c" "$staging/lz4.h" "$out/"
