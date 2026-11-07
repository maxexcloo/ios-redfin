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
`work/boot/accelerated.img` enabled Metal and double buffering, but kept direct
scanout off. It booted, yet the user reported no improvement; one 5 s window
showed 106 swaps, 61 shown and 45 dropped, with presentation fence waits around
76 ms. These windows include variable activity and are not a controlled FPS test.

`work/boot/accelerated-direct.img` changed only `sweetscanout=2`. The user
reported noticeably smoother interaction; live probes confirmed two scanout
slots and direct presentation, and kernel logs confirmed Turnip/Metal with
writable shader caches. This is the current live configuration. The user later reported a temporary
stall that recovered without a reboot. The kernel remained responsive. Logs
contain a display swap-wait timeout and resumed frames, but do not establish
that timeout as the cause. This is experimental, not a stable baseline.

`PRESET=ui` reproduces that configuration in the boot helper. The corresponding
`work/boot/working.img` has the same effective arguments, ADT hardware properties and firmware as
the tested image. Graphical defects and some stutter remain; no sustained frame
rate or stability claim has been established. Camera and flash remain disabled.

Build without connecting a phone:

```sh
NOBOOT=1 bash tools/redfin-boot.sh minimal xnu/out-rk5a/kernel.development.sweet
```

Experimental accelerated UI profile (requires the installed SweetMetal2 bundle and firmware):

```sh
PRESET=ui bash tools/redfin-boot.sh working xnu/out-rk5a/kernel.development.sweet
```

Omit `NOBOOT=1` from the diagnostic command to build and temporarily boot.
The helper refuses multiple fastboot devices or any product other than `redfin`, and targets the checked device.
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
filesystem health. Kernel CI passed for commit `dcb5388` (run `42332704046`);
no local full kernel build was needed for these host-tool and root-tweak changes.

Live checks: device product verified before each RAM-only boot; USB command/file
servers responsive; user confirmed CPU UI, unlock, Settings and touch. Captured
90 Hz panel scan and real touch events. No firmware or partitions were flashed.
Host change authorised by the user: temporary `192.168.7.1/24` alias on the Pixel's
USB interface `en15`, removed and verified after testing. No other port was modified.

GPU acceleration and direct scanout are live; graphical correctness, sustained
frame pacing, stability, charging, full suspend/wake and peripheral operation
still need work or verification. The saved root image predates the manual phone
installations. No camera/audio/charging services were enabled during this task.

## Quality Assessment

- Proven locally: UI boot, unlock, Settings, touch, USB debugging, Metal and direct
  scanout. The user confirmed direct scanout feels smoother; graphical glitches
  remain. Smooth UI is a plausible incremental target, not yet achieved fully.
- Upstream reports camera, sound, Wi-Fi, Bluetooth and sensors, with defects and
  hand-maintained firmware/state. These are not verified on this installation.
- Charging while iOS runs and full suspend/wake are unresolved daily-use risks.
  CPU idle power collapse alone does not establish low overnight drain.
- Cellular branches contain QMI/IPA experiments, not a complete calls/SMS/data
  implementation. Video acceleration remains subsystem bring-up work.
- AppleKeyStore is an always-unlocked stub, with no real SEP. App Store and Apple
  ID services are unsupported; there is no demonstrated path to native iPhone
  security or full Apple service compatibility.

Prioritise display correctness and measured frame pacing, then charging and sleep,
before enabling peripherals individually. A polished experimental device is a
credible goal; a flawless everyday iPhone replacement is not currently supported
by the evidence. See the upstream README and rk5a manifest for author claims.
