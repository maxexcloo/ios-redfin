# Redfin Handoff

## Current State — 2026-11-07

One checkout remains: `ios-redfin/`, next to the separate Jelly Star and Redmi ports.
The former `ios-redfin.bak/` has been consolidated into this checkout. `research/`
and `work/rootimg/` are real directories, with no dependency on the old location.
Distinct older artefacts remain at their original relative paths. Three conflicting
local files and the older repository metadata are preserved under gitignored
`archive/`. The factory ZIP is in `downloads/`. No device partitions were changed.

The fork contains upstream `redfin-int` plus macOS root tooling, documentation,
CI repairs and kernel patches 1047–1049. It is the correct port. Upstream's
[chilled_alligator](https://www.reddit.com/user/chilled_alligator/)
[posted working Pixel 5 footage](https://www.reddit.com/r/hackios/comments/1xj15zq/pixel_5_progress_metal_translation_performance/).
Their working phone includes manual state not fully captured by the root recipe;
these posts do not establish a reproducible installation from git alone.

**The local CPU-rendered UI now boots.** The user confirmed unlock, Settings and
touch work. It is laggy and has graphical glitches. The previously observed
SpringBoard stall was a synchronous `AVFlashlight` XPC wait into mediaserverd.
A plain ADT alone did not fix it: MobileGestalt retained camera/flash answers.
Backing up its plist and making `CacheVersion` stale allowed a fresh minimal
boot to reach the UI. Follow-up stacks no longer had that flashlight wait.

The three MediaToolbox `StartRecorderServer` flags remain false, so they are
not required for the minimal no-camera profile. Full camera/flash support needs
those capture servers enabled and Redwood's prewarm hook active; see the
upstream bring-up log. Do not enable hardware advertisement without its services.

`tools/sweet-root-tweaks.py` now invalidates MobileGestalt's hardware cache during
root preparation. Previous GPU-off diagnoses were incorrect; see the historical
[display correction](docs/redfin/STATUS-2026-11-06-display.md).

## Boot Profiles

`work/boot/minimal.img` is built locally from the preserved rk5a kernel
(`xnu/out-rk5a/kernel.development.sweet`, no experimental 1049 APFS spoof).
Its exact arguments are in `work/boot/minimal.cmdline`; the ADT is
`work/boot/minimal.adt`. CPU rendering, touch and USB are enabled; camera, flash
and direct scanout are disabled. It does not require SweetMetal2.

The working CPU image is the recovery baseline for subsequent experiments.
`work/boot/accelerated.img` uses the same minimal ADT and kernel with `GPU=2`,
`FLIP=1` and `GPUFREQ=4`; its live UI/performance test is in progress. It keeps
camera, flash and direct scanout disabled.

Build without connecting a phone:

```sh
NOBOOT=1 bash tools/redfin-boot.sh minimal xnu/out-rk5a/kernel.development.sweet
```

Omit `NOBOOT=1` to build and temporarily boot. The helper refuses multiple fastboot
devices or any product other than `redfin`, and targets the checked device.
Camera support is explicitly opt-in with `PRESET=camera`; it needs the capture
plug-in and firmware tables installed on the phone. GPU/Metal remain opt-in
with `GPU=1`/`GPU=2`.

After changing camera/flash advertisement, back up and invalidate the phone's
MobileGestalt cache too; otherwise cached capabilities may still make SpringBoard
wait on absent services. The live cache was rebuilt successfully. Original
MobileGestalt and launchd plists are saved in `logs/minimal-*.plist` locally and
`/var/local/redfin-debug-original-*-20261107.plist` on the phone. The temporary
stack/log instrumentation has been removed by restoring the original launchd
plist and verifying its bytes. The original psxdump job remains.

## Root Image & Verification

The preserved `work/rootimg/iosroot.img` is the original 32 GiB image. A read-only
HFS catalog inspection confirmed Setup completion flags and keybag presence,
and 528 launchd jobs with CommCenter removed. It also confirmed that this image
has **no** `/var/local`, SweetMetal2 or RedwoodAudio; VirtualAudio is disabled.
Later manual changes documented on the phone were never incorporated into this
image. Do not reinstall it expecting the phone's latest state.

The root builder is a CPU-only bring-up recipe, not a complete rk5a installer.
Working audio additionally requires restoring VirtualAudio when RedwoodAudio
is installed (see `docs/redfin/port-plan.md`, Haptics, audio DSP).
[The rk5a manifest](docs/redfin/STATUS-2026-10-30-rk5a.md) records the full
GPU/Metal configuration; [KNOWN-GOOD.md](docs/redfin/KNOWN-GOOD.md) lists
additional hand-maintained phone state.

Local checks: shim/image build, payload/ADT/AVB inspection, shell syntax,
mocked fastboot device selection and cached/cold patch-log checks. The original
root image's HFS catalog was inspected read-only; that does not establish its
filesystem health. Full kernel CI was not run locally.

Live checks: device product verified before each RAM-only boot; USB command/file
servers responsive; user confirmed CPU UI, unlock, Settings and touch. Captured
90 Hz panel scan and real touch events. No firmware or partitions were flashed.
Host change authorised by the user: temporary `192.168.7.1/24` alias on the Pixel's
USB interface `en15`, to remove after testing. No other port was modified.

GPU quality, stability, battery, charging, sleep and peripheral operation still
need verification. The saved root image predates the manual phone installations.
