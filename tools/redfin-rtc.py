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

os.chdir(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
live = sys.argv[1] if len(sys.argv) > 1 else "logs/live.txt"
before = Path(live).read_bytes().count(b"SWEET RTC: ")
t0 = time.time()
subprocess.run(
    [sys.executable, "tools/redfin-cmd.py", "--wait", "0.1", "rtc"],
    capture_output=True,
    check=False,
)
t1 = time.time()
for _ in range(100):
    found = re.findall(rb"SWEET RTC: (\d+)", Path(live).read_bytes())
    if len(found) > before:
        rtc = int(found[-1])
        off = round((t0 + t1) / 2 - rtc)
        Path("work/rtc-offset").write_text(f"{off}\n")
        print(
            f"RTC {rtc} s, Mac {time.ctime(t0)}: sweetrtcoff={off} -> work/rtc-offset"
        )
        sys.exit(0)
    time.sleep(0.1)
sys.exit(f'no "SWEET RTC:" reply in {live} (kernel 0099+ with sweetusb=2?)')
