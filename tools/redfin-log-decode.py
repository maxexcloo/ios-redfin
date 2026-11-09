#!/usr/bin/env python3
"""Decode the XNU persistent console ring pulled by redfin-log-pull.sh xnu.

  tools/redfin-log-decode.py RING.bin OUT.txt

Header (sweet_ufs.c, struct sweet_log_header): magic "SWEETLOG", u32
version, u32 ring size, u64 total bytes written; the ring follows the
4 KiB header block.
"""

import struct
import sys
from pathlib import Path

raw = Path(sys.argv[1]).read_bytes()
assert raw[:8] == b"SWEETLOG", "no SWEETLOG header"
ver, size, total = struct.unpack_from("<IIQ", raw, 8)
ring = raw[4096 : 4096 + size]
if total <= size:
    data = ring[:total]
else:
    pos = total % size
    data = ring[pos:] + ring[:pos]
Path(sys.argv[2]).write_bytes(data.replace(b"\0", b""))
print(f"version {ver} ring {size} written {total} -> {len(data)} bytes")
