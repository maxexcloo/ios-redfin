# HANDOFF: iOS 16 on Pixel 5 (redfin) — 2026-11-06

Read this first, then `docs/redfin/STATUS-2026-10-30-rk5a.md` (upstream's known-good
state) and `NOTES.md`. This file records only what *this* session did and where it stopped.

## TL;DR

**iOS 16 boots on the Pixel 5 and runs, but never draws a frame.** The kernel log shows
launchd, backboardd, SpringBoard, USB Ethernet (192.168.7.2), battery (97 %), all 8 cores
scaling and HID key events — and **zero** `SWEET FB` / `SWEET SURF` / `AppleCLCD` / `IOMFB`
/ `SWEET SCANOUT` lines. The display path never initialised.

Cause: this session booted with **`sweetgpu=0`**. Upstream's rk5a cmdline has `sweetgpu=1`.
Patch `0095-flame-gpu-present.patch` shows the present path is built around the Adreno 2D
engine (panel switches to 4352-byte rows; the GPU scales each frame onto it). With the GPU
off there is no present path at all, so SpringBoard has no display and hangs on its logo.

**Next action:** build the GPU/Metal chain (below) and boot with the full rk5a args.

## Where everything is

Repo: `/Users/max.schaefer/Downloads/ios-redfin/repo` — branch `main`, HEAD `a8746bb`,
pushed to `maxexcloo/ios-redfin` (fork of `DenialOfGravity/ios-redfin`).

Note: the working tree is `redfin-int`'s content re-committed on `main`. Upstream keeps
its redfin work on `redfin-int` / `known-good-rk5a`; the fork's `main` is now the useful one.

| Artefact | Path | sha256 (short) |
|---|---|---|
| iOS root image (32 GiB HFSX) | `work/rootimg/iosroot.img` | `8226ab55…` |
| Per-GiB hashes for verify | `work/rootimg/iosroot.gib.sha256` | 32 lines |
| Kernel (rk5a = `ws-z-gpu4` patch set) | `xnu/out-rk5a/kernel.development.sweet` | `daca9c39…` |
| ADT (highmem+camera+flash+backlight) | `work/boot/redfin-hi.adt` | |
| Boot image, console visible | `out/r-k3.img` | `a8f43515…` |
| Boot image, console muted | `out/r-k2.img` | |
| Probe (writes nothing) | `out/redfin-probe-safe.img` | `a7fe6265…` |
| Show-log pager (reads log ring) | `out/redfin-showlog.img` | |
| TWRP for redfin | `recovery/twrp.img` (3.7.0_11-0) | `9adc9aae…` |
| iPhone X IPSW DMGs (7.0 GB) | `research/ipsw-x/dmg/` | CRC-verified |
| iPhone X device tree | `research/ipsw-x/d22ap.adt` | |

New tools added this session (all on `main`, pushed):

- `tools/build-root-mac.sh` — builds the iOS root on macOS in one sudo. Fixes three bugs
  that made the WSL-derived one-off fail silently: size not passed through (16 GiB volume
  filled → `ditto` died), bash 3.2 aborting on empty array expansion under `set -u`
  (killed the cleanup trap and the partial image), and no logging.
- `tools/retweak-root.sh` — re-applies tweaks to an existing image, no 20-min re-copy.
- `tools/prune-root.py` — removes the daemons upstream disables in
  `docs/redfin/disabled-services.md`: `fairplayd.H2` (relaunch loop; its dead MIG port
  deadlocks locationd's CLMescalSigner) and `voicemail.vmd` (CommCenter retry loop, ~1 core,
  219→912 MB in 20 min); parks `AirFair.syncBundle`. `*.before-prune` backups, `--revert`.
  Already applied to `iosroot.img`.
- `tools/redfin-install-root.sh` — writes the image to `userdata` over adb from TWRP and
  verifies every GiB. Guarded on device name, resolved `userdata` path and partition size.
- `tools/root-hashes.sh` — regenerates the per-GiB hash list.
- `tools/redfin-verify-batches.sh` — batch verify with TWRP restart (TWRP's adbd is flaky).

## State of the phone

- Bootloader **unlocked**, slot a, `redfin`, userdata = `/dev/block/sda19` (117 GB).
- **iOS root is written and verified**: all 32 GiB match `iosroot.gib.sha256`.
- Android userdata is gone (first 32 GiB). Android system/vendor/boot untouched.
- The image is 32 GiB; the rest of the partition is untouched on purpose (the kernel keeps
  its log ring in the last ~17 MiB).
- `fstypeovr` launchd job (`org.iosonpixel.fstypeovr`, makes statfs report apfs for /) is
  **NOT** installed — it exists only on upstream's hand-tuned phone and in no branch of git.
  Not yet proven necessary, since the system gets as far as running SpringBoard.

## Two things that bit this session (do not repeat)

1. **`sweetgpu=0` breaks the display.** The present path needs the GPU. Use `sweetgpu=1`.
2. **`sweetfb_noconsole=1` mutes the kernel console**, so a hang looks like a dim logo with
   no information. Leave it off while debugging. `out/r-k3.img` has it off.

Also: `fastboot boot` of a boot image whose cmdline lives in the payload is fine — ABL's
"boot.img missing cmdline or OS version" warning is harmless.

## How to see the kernel log without TWRP

TWRP's adbd on this phone crashes (`Could not set SELinux context for subprocess`,
SIGABRT), so `adb shell`/`adb exec-out` are unreliable and long `dd` reads kill it.

Better: the shim's show-log build reads the persistent console ring (last 4 MiB of
userdata, kernel patch 0047) and pages it on screen every 4 s:

```sh
fastboot boot out/redfin-showlog.img      # read-only; shows the PREVIOUS boot's log
```

Film it. Or, if adb works, `tools/sweet-log-pull.sh out.txt`.

## Correction (2026-11-06, later): the GPU is NOT the blocker

`docs/redfin/STATUS-2026-11-06-display.md` supersedes the section below. Measured on a
live boot with `sweetgpu=0`: `p disp` says display on with scanout direct, `p fc` says
the panel scans at 89.9 Hz, and `p scanout 0` produced a real 1125x2436 frame
(`SWEET FB: swap 3 layer 0 surface 3`). The display path does not need the GPU.

The "zero display lines" this section is built on was a logging bug: `sweet_log_copy()`
advanced its cursor before `sock_send()`, so every boot backlog chunk was discarded while
the host address did not yet exist (patch 1048 fixes it). A malformed patch 1047 was also
silently dropped by CI, which is now a build failure.

The real symptom is `p swapdone` = `swap done 0, ticks 0`: CoreAnimation painted once and
was never asked again, with every backboardd and SpringBoard thread in `TH_WAIT`. That is
above the kernel. Also note `sweetscanout=2` is newer than upstream's last known-good
GPU-off display (`docs/redfin/port-plan.md`, "Touch works": `sweetgpu=0`, no
`sweetscanout`), and the same doc records `r3` hanging when display args changed.

The Metal chain below is still worth having for fit-scale quality, but do not start there.

## Next: the GPU/Metal chain (this is what unblocks the display)

1. **Fix the metal2 CI on the fork.** `.github/workflows/metal2.yml` is `runs-on: macos-14`,
   which GitHub has retired ("configuration 'macos-14-arm64-us-default' is not supported").
   `macos-15` works — that is how the kernel was built. One-line change, push, run.
   Output: `SweetMetal2.bundle` + `libvulkan_freedreno.dylib`.
   (The published `builds-metal2` branch is stale: `e55662c`, not rk5a's `7a8ca88`.)
2. **Extract Adreno firmware from the Pixel 5 factory image** (`redfin`, Android 14
   `UP1A.231105.001.B2`): `a650_gmu.bin`, `a650_sqe.fw`, `a620_zap.mdt`/`.bNN` from
   `vendor.img` → `/firmware`. Pass to `tools/mkpayload.py --gpufw DIR`.
3. **Rebuild the boot image with rk5a's full cmdline** (`sweetgpu=1 sweetmtl=2` etc., see
   `docs/redfin/STATUS-2026-10-30-rk5a.md`) and boot.
4. If it still shows nothing, try `sweetmtl=0` (kernel GPU present, CA renders on the CPU) —
   isolates "GPU present broken" from "Metal bundle broken".

Also worth trying early, and cheaper: **`sweetgpu=1 sweetmtl=0` alone**, no Metal bundle.
That should give a CPU-rendered SpringBoard on a GPU-presented panel, which is the minimum
for a lock screen.

## Other open items

- Fork housekeeping done: default branch `main`, issues enabled, topics set
  (`ios xnu redfin pixel-5 sm7250 qualcomm ios16 darwin`), README rewritten for Pixel 5
  (it said "# ios-flame / Google Pixel 4"). `maxexcloo/ios-redfin-build` was deleted by the
  user; the fork's own Actions work, so no separate build repo is needed.
- CI note: `.github/workflows/xnu.yml` and `metal2.yml` both pin `macos-14`. The kernel
  builds fine on `macos-15` because patch `0082` adds `IORPC.kernelContent` for Xcode 16
  `iig`. Consider upstreaming that fix.
- Upstream never published the rk5a kernel (`known-good` docs reference it but only
  `builds-xnu` from Oct 26 / `ws-u-display` exists). The kernel here was built from
  `redfin-int`, whose 272 patches are byte-identical to `ws-z-gpu4` except
  `0020-stage-bearssl.sh` (GitHub mirror fallbacks).
- Later, not now: grow `/` from 32 GiB to fill userdata (upstream uses 109 GiB), install the
  `fstypeovr` job, build the userland bundle (`builds-userland`) for Wi-Fi/BT/sound/camera,
  and pull per-device firmware.
- Boot args used in `out/r-k3.img` are rk5a's **minus** `sweetgpu`/`sweetmtl` (both 0) and
  minus `sweetrtcoff`/`sweetfb_noconsole`. Saved next to it as `work/boot/r-k3.cmdline`.

## Handy commands

```sh
cd ~/Downloads/ios-redfin/repo

fastboot devices
fastboot boot out/r-k3.img                    # console visible
fastboot boot out/redfin-showlog.img          # read the previous boot's log on screen

# rebuild a boot image from the current kernel + ADT
python3 -I tools/mkpayload.py xnu/out-rk5a/kernel.development.sweet \
    work/boot/redfin-hi.adt work/boot/r-k4.payload --cmdline "$(cat work/boot/r-k3.cmdline)"
MKBOOTIMG="python3 $PWD/downloads/mkbootimg/mkbootimg.py" \
AVBTOOL="python3 $PWD/downloads/avb/avbtool.py" \
    bash shim/build.sh "$PWD/work/boot/r-k4.payload" "$PWD/out/r-k4.img"

# root image: rebuild tweaks only, or verify what is on the phone
sudo bash tools/retweak-root.sh work/rootimg/iosroot.img
bash tools/redfin-install-root.sh verify
```
