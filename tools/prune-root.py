#!/usr/bin/env python3
"""Apply the redfin daemon switches that tools/sweet-root-tweaks.py does not.

  sudo prune-root.py MOUNTED_ROOT

Idempotent. Writes backups beside each file it changes (never overwrites them),
so a revert is `--revert`.

What it does, and why (all from the port's own docs):

  fairplayd.H2   removed. It exits right after a container lookup and launchd
                 relaunches it every 10 s; MIG requests to
                 com.apple.fairplayd.versioned queue forever after that, and
                 locationd's CLMescalSigner (FairPlay SAPInit) deadlocks its
                 main thread - which hangs every app making a synchronous
                 CoreLocation call. (docs/redfin/disabled-services.md,
                 tools-claude/quickwins-launchd.py --no-fairplayd)
                 TRADE-OFF: no FairPlay, so DRM'd content (App Store purchases,
                 Apple Music/TV downloads) cannot work. It did not work with the
                 dead daemon either, but this is a deliberate choice.

  vmd            removed (com.apple.voicemail.vmd). With no CommCenter it
                 retries com.apple.commcenter.coretelephony.xpc in a tight loop:
                 ~1 full core, 219 MB -> 912 MB in 20 min, ~100k os_log lines.
                 (disabled-services.md, 2026-10-29 / r63a)

  AirFair        AirFair.syncBundle moved to /var/local/disabled/SyncBundles/
                 (iPhone Storage fix). Skipped silently if not present.

Not done here (deliberately):
  - ReportCrash/spindump: the redfin docs do not list them as removed, and
    ReportCrash is what writes the crash reports we will want while debugging.
  - growing / to fill userdata: a separate, later step.
"""

import os, plistlib, shutil, sys

SUFFIX = ".before-prune"
LAUNCHD_REL = os.path.join("System", "Library", "xpc", "launchd.plist")

# label -> why (see module docstring)
REMOVE_LABELS = {
    "com.apple.fairplayd.H2": "fairplayd: relaunch loop + locationd deadlock",
    "com.apple.voicemail.vmd": "vmd: CommCenter XPC retry loop, ~1 core",
}
AIRFAIR = os.path.join(
    "System",
    "Library",
    "PrivateFrameworks",
    "AirFair.framework",
    "SyncBundles",
    "AirFair.syncBundle",
)


def backup(path):
    """Copy beside the original once; a marker records "did not exist"."""
    bak = path + SUFFIX
    if os.path.exists(bak):
        return
    if os.path.exists(path):
        shutil.copy2(path, bak)
        print(f"  backup {bak}")
    else:
        open(path + SUFFIX + ".absent", "w").close()


def revert(root):
    n = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            if not f.endswith(SUFFIX):
                continue
            p = os.path.join(dirpath, f)
            orig = p[: -len(SUFFIX)]
            shutil.copy2(p, orig)
            os.remove(p)
            print(f"  restored {orig}")
            n += 1
    print(f"reverted {n} file(s)")
    return 0


def main(argv):
    if len(argv) == 3 and argv[1] == "--revert" and os.path.isdir(argv[2]):
        return revert(argv[2])
    if len(argv) != 2 or not os.path.isdir(argv[1]) or argv[1].startswith("--"):
        sys.exit(__doc__)
    root = argv[1]
    path = os.path.join(root, LAUNCHD_REL)
    if not os.path.isfile(path):
        sys.exit(f"{path}: not found - is this an iOS root?")

    with open(path, "rb") as f:
        plist = plistlib.load(f)

    backup(path)
    removed = 0
    for sect, jobs in list(plist.items()):
        if not isinstance(jobs, dict):
            continue
        for key in list(jobs):
            job = jobs[key]
            label = job.get("Label") if isinstance(job, dict) else None
            # on-demand jobs are keyed by path (com.apple.voicemail.vmd.plist)
            base = os.path.basename(key)
            hit = label in REMOVE_LABELS or any(
                base == lab + ".plist" or base == lab for lab in REMOVE_LABELS
            )
            if hit:
                why = REMOVE_LABELS.get(label) or REMOVE_LABELS.get(
                    base[: -len(".plist")] if base.endswith(".plist") else base
                )
                print(f"  removed {sect}/{key}  ({why})")
                del jobs[key]
                removed += 1
    if removed:
        with open(path, "wb") as f:  # in place: keeps owner and mode
            plistlib.dump(plist, f, fmt=plistlib.FMT_BINARY)
        print(f"launchd.plist: {removed} job(s) removed")
    else:
        print("launchd.plist: nothing to remove (already pruned?)")

    src = os.path.join(root, AIRFAIR)
    if os.path.isdir(src):
        dst = os.path.join(root, "private/var/local/disabled/SyncBundles")
        os.makedirs(dst, exist_ok=True)
        target = os.path.join(dst, os.path.basename(AIRFAIR))
        if os.path.exists(target):
            print("  AirFair.syncBundle: already parked")
        else:
            shutil.move(src, target)
            print(f"  AirFair.syncBundle -> {target}")
    else:
        print("  AirFair.syncBundle: not present, skipped")

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
