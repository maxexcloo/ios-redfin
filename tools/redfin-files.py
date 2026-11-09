#!/usr/bin/env python3
"""Files on the running phone (bsd/dev/sweet_files.c, TCP 2223 via FlameBridge 127.0.0.1:2223).

tools/redfin-files.py put LOCAL REMOTE [MODE]     (mode octal, default from LOCAL)
tools/redfin-files.py get REMOTE LOCAL
tools/redfin-files.py read REMOTE OFFSET LEN LOCAL   (range; works on devices: /dev/pmem at a PA)
tools/redfin-files.py mkdir REMOTE [MODE]
tools/redfin-files.py link TARGET REMOTE          (symlink)
tools/redfin-files.py rm REMOTE
tools/redfin-files.py chmod REMOTE MODE
"""

import os
import socket
import stat
import sys
from pathlib import Path

HOST, PORT = (
    __import__("os").environ.get("PHONE_FILES_HOST", "192.168.7.2"),
    2223,
)  # or FlameBridge 127.0.0.1


def conn():
    s = socket.create_connection((HOST, PORT), timeout=30)
    return s


def reply(s):
    line = b""
    while not line.endswith(b"\n"):
        c = s.recv(1)
        if not c:
            raise SystemExit("connection closed without a reply")
        line += c
    line = line.decode().strip()
    if not line.startswith("OK"):
        raise SystemExit(f"phone: {line}")
    return line


def read_range(s, path, off, n):
    """READ (kernel 0094+): n bytes of path at off; one request per connection."""
    s.sendall(f"READ {path} {off} {n}\n".encode())
    n = int(reply(s).split()[1])
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(min(1 << 20, n - len(buf)))
        if not chunk:
            raise SystemExit(f"short read: {len(buf)} of {n} bytes")
        buf += chunk
    return bytes(buf)


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    cmd, args = argv[0], argv[1:]
    s = conn()
    if cmd == "put":
        local, remote = args[0], args[1]
        mode = (
            int(args[2], 8) if len(args) > 2 else stat.S_IMODE(os.stat(local).st_mode)
        )
        data = Path(local).read_bytes()
        s.sendall(f"PUT {remote} {mode:o} {len(data)}\n".encode() + data)
        print(remote, reply(s))
    elif cmd == "get":
        s.sendall(f"GET {args[0]}\n".encode())
        n = int(reply(s).split()[1])
        buf = bytearray()
        while len(buf) < n:
            chunk = s.recv(min(65536, n - len(buf)))
            if not chunk:
                raise SystemExit("short read")
            buf += chunk
        Path(args[1]).write_bytes(buf)
        print(args[0], n, "bytes ->", args[1])
    elif cmd == "read":
        data = read_range(s, args[0], int(args[1], 0), int(args[2], 0))
        Path(args[3]).write_bytes(data)
        print(args[0], len(data), "bytes ->", args[3])
    elif cmd in ("mkdir", "link", "rm", "chmod"):
        verb = {"mkdir": "MKDIR", "link": "LINK", "rm": "RM", "chmod": "CHMOD"}[cmd]
        if cmd == "mkdir" and len(args) == 1:
            args = args + ["755"]
        s.sendall(f"{verb} {' '.join(args)}\n".encode())
        print(cmd, " ".join(args), reply(s))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
