#!/usr/bin/env python3
"""Calibrate the phone's clock: sweetrtcoff = Mac time - PM8150 RTC (kernel 0099+).

  tools/redfin-rtc.py [LIVE_LOG]     (default: logs/live.txt)

Sends "rtc" to the command server, reads "SWEET RTC: N" from the live log (redfin-live.py
may hold the UDP port), writes the offset to work/rtc-offset; tools/redfin-boot.sh
passes it as boot-arg sweetrtcoff. The RTC is battery-backed: calibrate once, again only
if the battery was fully drained.
"""

import os
import re
import subprocess
import sys
import time
from pathlib import Path

from redfin_log import LIVE_LOG


def replies(path):
    try:
        return re.findall(rb"SWEET RTC: (\d+)", path.read_bytes())
    except FileNotFoundError:
        return []


os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
live = Path(sys.argv[1]) if len(sys.argv) > 1 else LIVE_LOG
before = len(replies(live))
t0 = time.time()
subprocess.run(
    [sys.executable, "tools/redfin-cmd.py", "--wait", "0.1", "rtc"],
    stdout=subprocess.DEVNULL,
    check=True,
)
t1 = time.time()
for _ in range(100):
    found = replies(live)
    if len(found) > before:
        rtc = int(found[-1])
        off = round((t0 + t1) / 2 - rtc)
        output = Path("work/rtc-offset")
        output.parent.mkdir(exist_ok=True)
        output.write_text(f"{off}\n")
        print(
            f"RTC {rtc} s, Mac {time.ctime(t0)}: sweetrtcoff={off} -> work/rtc-offset"
        )
        sys.exit(0)
    time.sleep(0.1)
sys.exit(f'no "SWEET RTC:" reply in {live} (kernel 0099+ with sweetusb=2?)')
