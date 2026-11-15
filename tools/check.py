"""Run phone component host tests and patch structure checks without a phone."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for component in ("fastrpc", "sensors", "wifi"):
    subprocess.run(["sh", f"phone/{component}/test.sh"], cwd=ROOT, check=True)
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
