#!/bin/bash
# Write work/rootimg/iosroot.gib.sha256: the SHA-256 of each 1 GiB chunk of the
# root image, so tools/redfin-install-root.sh can verify the phone's copy after
# writing without reading 32 GiB back.
#
#   bash tools/root-hashes.sh [IMG]
set -euo pipefail
cd "$(dirname "$0")/.."
IMG=${1:-work/rootimg/iosroot.img}
OUT=${IMG%.img}.gib.sha256

[[ -f $IMG ]] || { echo "no image at $IMG" >&2; exit 1; }

python3 - "$IMG" "$OUT" <<'PY'
import hashlib, sys
src, dst = sys.argv[1], sys.argv[2]
total = 1 << 30
with open(src, 'rb') as f, open(dst, 'w') as o:
    i = 0
    while True:
        h, n = hashlib.sha256(), 0
        while n < total:
            c = f.read(1 << 22)
            if not c:
                break
            h.update(c); n += len(c)
        if not n:
            break
        o.write(f'{i} {h.hexdigest()}\n')
        i += 1
print(f'{dst}: {i} GiB')
PY
ls -l "$OUT"
