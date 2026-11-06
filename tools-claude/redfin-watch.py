#!/usr/bin/env python3
"""redfin-watch.py: watch a booted Pixel 5 unattended and write a verdict for later.

  tools-claude/redfin-watch.py SECONDS LABEL

Listens to the live kernel log (UDP 5140 from 192.168.7.2), asks the phone for its
display state once a minute over the command server (UDP 5141), and appends a row per
minute to logs/watch-LABEL.tsv. Raw log: logs/watch-LABEL.log. Summary at the end:
logs/watch-LABEL.txt (frames presented? scanout? which daemons are crash-looping?).

Nothing is written to the phone. Safe to leave running; a phone that reboots or drops
off USB just stops answering and the rows go empty.

Why these probes (they are positive answers, not absent log lines):
  p swapdone   frames the display path completed (0 = CoreAnimation is not presenting)
  p scanout    direct scanout on/off and how many slot surfaces it holds
  p disp       display power state
The 5 s FB/SCANOUT lines only appear when there are frames, so their absence is a
symptom too; the pokes give an answer either way.
"""

import collections
import os
import re
import socket
import sys
import time

PORT_RX, PORT_TX = 5140, 5141
PHONE = "192.168.7.2"
POKES = (b"p swapdone", b"p scanout", b"p disp")

secs = int(sys.argv[1]) if len(sys.argv) > 1 else 1500
label = sys.argv[2] if len(sys.argv) > 2 else time.strftime("%H%M%S")
root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
logdir = os.path.join(root, "logs")
os.makedirs(logdir, exist_ok=True)
raw_path = os.path.join(logdir, "watch-%s.log" % label)
tsv_path = os.path.join(logdir, "watch-%s.tsv" % label)
sum_path = os.path.join(logdir, "watch-%s.txt" % label)

rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
rx.bind(("0.0.0.0", PORT_RX))
rx.setblocking(False)
tx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
tx.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

raw = open(raw_path, "ab")
tsv = open(tsv_path, "w")
tsv.write("mac_time\tuptime_s\tswapdone_now\tswaps_in_5s\tscanout\tdisp\n")
tsv.flush()

state = {"uptime": None, "swapdone": None, "swaps5": 0, "scanout": "", "disp": ""}
execs = collections.Counter()
frames_seen = 0
first_frame_s = None
boot_ts = None


def handle(line):
    global frames_seen, first_frame_s
    m = re.match(r"\[\s*([0-9.]+)\] (.*)", line)
    if not m:
        return
    up, text = float(m.group(1)), m.group(2)
    state["uptime"] = up
    if "exec " in text:
        execs[text.split("exec ", 1)[1].strip()] += 1
    if text.startswith("SWEET FB: swapdone"):
        d = re.search(r"swapdone now (\d+)", text)
        if d:
            state["swapdone"] = int(d.group(1))
    elif text.startswith("SWEET SCANOUT:") and "(p scanout (state))" in text:
        state["scanout"] = "on" if text.startswith("SWEET SCANOUT: on") else "off"
    elif text.startswith("SWEET FB: display"):
        state["disp"] = "on" if "display on" in text else "off"
    elif text.startswith("SWEET FB: 5s: swaps"):
        n = re.search(r"swaps (\d+)", text)
        if n:
            k = int(n.group(1))
            state["swaps5"] = k
            frames_seen += k
            if k > 0 and first_frame_s is None:
                first_frame_s = up


start = time.time()
next_poke = start
buf = b""
rows = 0
while time.time() - start < secs:
    if time.time() >= next_poke:
        for p in POKES:
            try:
                tx.sendto(p, (PHONE, PORT_TX))
            except OSError:
                pass
        next_poke = time.time() + 60
    try:
        data, _ = rx.recvfrom(65536)
        raw.write(data)
        raw.flush()
        buf += data
        *lines, buf = buf.split(b"\n")
        for ln in lines:
            handle(ln.decode(errors="replace"))
    except BlockingIOError:
        time.sleep(0.05)
        # a quiet minute still lands a row
        if time.time() >= next_poke - 59.5 and rows * 60 < time.time() - start:
            pass
    if time.time() - start >= (rows + 1) * 60:
        rows += 1
        tsv.write(
            "%s\t%s\t%s\t%d\t%s\t%s\n"
            % (
                time.strftime("%H:%M:%S"),
                state["uptime"],
                state["swapdone"],
                state["swaps5"],
                state["scanout"],
                state["disp"],
            )
        )
        tsv.flush()

raw.close()
tsv.close()
top = ", ".join("%s x%d" % (k, v) for k, v in execs.most_common(6))
lines = [
    "watch %s: %d s, %d one-minute rows" % (label, secs, rows),
    "last uptime: %s s" % state["uptime"],
    "last swapdone: %s (frames completed by the display path; 0 = CA is not presenting)"
    % state["swapdone"],
    "frames counted in 5 s windows: %d; first at %s s" % (frames_seen, first_frame_s),
    "direct scanout: %s; display power: %s"
    % (state["scanout"] or "?", state["disp"] or "?"),
    "exec counts: %s" % (top or "none"),
    "",
    "verdict: "
    + ("FRAMES" if frames_seen else "NO FRAMES")
    + ("; scanout on" if state["scanout"] == "on" else ""),
]
open(sum_path, "w").write("\n".join(lines) + "\n")
print("\n".join(lines))
