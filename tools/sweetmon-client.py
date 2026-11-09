#!/usr/bin/env python3
"""sweetmon-client.py: minimal test client for phone/tools/sweetmon (protocol: bce31d1^:docs/redfin/sweetmon.md).
usage: sweetmon-client.py [-H HOST] [-p PORT] [-k TOKEN|-K KEYFILE] [-t SECS] [-o DIR] [CMD ...]
  Connects, authenticates, sends each CMD (one argv word per command line, e.g. 'rate 500 1' 'klog 0x101d0ef08'),
  prints a one-line summary of every frame for SECS seconds (default 5; 0 = until the first E frame after a trace).
  T chunks are joined per trace id and written to DIR/trace-<id>.lz4 and, decompressed (python lz4 if present, else
  tools/lz4py.py), DIR/trace-<id>.swtr (kdebug) or .bin (pmem)."""

import argparse
import json
import os
import socket
import struct
import sys
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("-H", "--host", default="192.168.7.2")
ap.add_argument("-p", "--port", type=int, default=5150)
ap.add_argument("-k", "--token", default=None)
ap.add_argument("-K", "--keyfile", default=None)
ap.add_argument("-t", "--secs", type=float, default=5)
ap.add_argument("-o", "--out", default=".")
ap.add_argument(
    "-q", "--quiet", action="store_true", help="no per-frame lines for S/K/P"
)
ap.add_argument("cmds", nargs="*")
a = ap.parse_args()
tok = a.token or (Path(a.keyfile).read_text().strip() if a.keyfile else None)


def lz4_decompress(d):
    try:
        import lz4.frame

        return lz4.frame.decompress(d)
    except ImportError:
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import lz4py

        return lz4py.decompress(d)


s = socket.create_connection((a.host, a.port), timeout=10)
s.settimeout(0.5)


def send(cmd):
    b = cmd.encode()
    s.sendall(struct.pack("<IB", len(b) + 1, ord("C")) + b)


buf = b""
if tok:
    send("auth " + tok)
for c in a.cmds:
    send(c)
traces, counts, nbytes = {}, {}, 0
t0 = time.time()
end = t0 + a.secs if a.secs > 0 else None
done = False
while not done and (end is None or time.time() < end):
    try:
        d = s.recv(1 << 20)
    except TimeoutError:
        continue
    if not d:
        print("closed by phone")
        break
    buf += d
    nbytes += len(d)
    while len(buf) >= 5:
        n = struct.unpack_from("<I", buf)[0]
        if len(buf) < 4 + n:
            break
        ty, p = chr(buf[4]), buf[5 : 4 + n]
        buf = buf[4 + n :]
        counts[ty] = counts.get(ty, 0) + 1
        ts = f"{time.time() - t0:7.3f}"
        if ty in "HRSFE":
            j = json.loads(p)
            if ty == "S":
                if not a.quiet:
                    busy = [
                        round(100 * (c[0] + c[1] + c[3]) / max(1, sum(c)))
                        for c in j.get("cpu", [])
                    ]
                    top = " ".join(f"{r[1]}:{r[2]:.0f}" for r in j.get("procs", [])[:4])
                    print(
                        ts,
                        "S busy%={} temp_max={} self={} nproc={} top: {}".format(
                            busy,
                            j.get("temp", {}).get("max"),
                            j.get("self"),
                            j.get("nproc"),
                            top,
                        ),
                    )
            else:
                print(ts, ty, json.dumps(j))
            if ty == "E":
                z = traces.pop(j["id"], b"")
                base = os.path.join(a.out, "trace-{:d}".format(int(j["id"])))
                Path(base + ".lz4").write_bytes(z)
                if z and "error" not in j:
                    raw = lz4_decompress(z)
                    ext = ".swtr" if j["kind"] == "kdebug" else ".bin"
                    Path(base + ext).write_bytes(raw)
                    print(
                        ts,
                        "wrote {!s}{!s}: {:d} bytes (E says {:d}){!s}".format(
                            base,
                            ext,
                            len(raw),
                            int(j["bytes"]),
                            "" if len(raw) == j["bytes"] else " MISMATCH",
                        ),
                    )
                if a.secs == 0:
                    done = True
        elif ty == "K":
            pos = struct.unpack_from("<Q", p)[0]
            if not a.quiet:
                tail = (
                    p[8:]
                    .rstrip(b"\n")
                    .rsplit(b"\n", 1)[-1][:100]
                    .decode("utf-8", "replace")
                )
                print(ts, f"K pos={int(pos):d} n={len(p) - 8:d} | {tail!s}")
        elif ty == "T":
            tid, seq = struct.unpack_from("<II", p)
            traces[tid] = traces.get(tid, b"") + p[8:]
            print(ts, f"T id={int(tid):d} seq={int(seq):d} n={len(p) - 8:d}")
        elif ty == "P":
            if not a.quiet and counts["P"] % 16 == 1:
                print(ts, "P x{:d}".format(int(counts["P"])))
        else:
            print(ts, ty, len(p), "bytes")
el = time.time() - t0
print(
    f"frames {counts!s}, {int(nbytes):d} bytes in {el:.1f} s ({nbytes / el / 1e6:.2f} MB/s)"
)
