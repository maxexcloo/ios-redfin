"""Run host tests, pd-mapper QMI tests and patch structure checks without a phone."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
subprocess.run(
    [sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"],
    cwd=ROOT,
    check=True,
)
subprocess.run(["sh", "phone/wifi/test.sh"], cwd=ROOT, check=True)
patches = subprocess.check_output(["git", "ls-files", "*.patch"], cwd=ROOT, text=True)
for patch in patches.split():
    result = subprocess.run(
        ["git", "apply", "--numstat", patch],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        sys.exit(f"{patch}: malformed patch\n{result.stderr}")
