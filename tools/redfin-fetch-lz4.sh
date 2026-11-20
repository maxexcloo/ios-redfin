#!/bin/bash
# Fetch LZ4's block compressor at the v1.10.0 pin into work/lz4/ for sweetmon.
# Source: github.com/lz4/lz4 at LZ4_COMMIT (the v1.10.0 tag), lib/ only.
# The files stay out of git; phone/tools/lz4/LICENSE covers the licence either way.
set -euo pipefail
cd "$(dirname "$0")/.."
LZ4_COMMIT=ebb370ca83af193212df4dcbadcc5d87bc0de2f0
out=work/lz4
mkdir -p "$out"
for file in lz4.c lz4.h; do
	curl -fsSL "https://raw.githubusercontent.com/lz4/lz4/$LZ4_COMMIT/lib/$file" -o "$out/$file"
done
sha256sum -c <<'EOF'
9396f7de527bc8435de9c7569fb7998e56545a84b4f3c2d808c0235c01774539  work/lz4/lz4.c
26b82efc53d1570f3b54eef02e9c4764c1ad374ff03cac04e2ced5ea4d4c552f  work/lz4/lz4.h
EOF
