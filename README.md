# iOS Redfin

Experimental iOS 16.7.16 (`20H392`, iPhone X userland) on the Google Pixel 5 (`redfin`, SM7250 / Snapdragon 765G, Adreno 620), built on [ios-redfin](https://github.com/DenialOfGravity/ios-redfin), ios-flame and ios-sweet.

## Status

**Unlock, Settings, touch and brightness control work on this phone, but it is not yet a consistently smooth or stable phone OS.**

| Area           | Evidence & Remaining Work                                                                                                                                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Boot           | A minimal ADT plus an invalidated MobileGestalt capability cache reaches SpringBoard; the CPU-rendering fallback is retained                                                                                                                           |
| Rendering      | Kernel 1055 with Metal and direct scanout is visibly smoother than CPU rendering and keeps text, AirDrop and camera glyphs intact. Dead-fill mode 1 is the text-preserving source default; mode 2 and fetcher-only ordering lose characters            |
| Pacing         | Scene-verified Settings runs deliver about 52–66 fps with frame gaps up to 43 ms; other repeated-swipe workloads measured about 29 fps. SweetFPS requests 90 fps without a demonstrated delivery gain                                                  |
| Brightness     | Control Centre slider changes reach completed panel commands; kernel 1055 enforces the cap on both request paths. Luminance mapping and battery-current estimates are provisional, not measured calibration                                            |
| Haptics        | Direct requests, UIKit selection feedback and system vibration reach completed DRV2624 transactions within the 1.5-second continuous-on limit; tactile quality is unassessed                                                                           |
| Sensors        | Accelerometer and gyroscope data reach public CoreMotion clients in bounded trials, including stop/restart and a 16-second idle period. Services stay disabled; gyro calibration, other sensors and long-term stability are unverified                 |
| Other hardware | Wi-Fi is disabled and Bluetooth shows Unavailable. Audio and cameras are unverified here; upstream results are not local proof                                                                                                                         |
| Cellular       | Imported from upstream (wland 19073fc, SweetFPS 27efaa0), opt-in via `/var/local/cell.on`. Upstream reports SIM PIN unlock, LTE data with Wi-Fi off and SMS send; unverified here, and its stable `cell.on` word set is not recorded in the repository |
| Limitations    | Charging under iOS, reliable suspend, GPS, NFC, fingerprint, SEP and Apple services are unavailable or unfinished; the security model is permissive                                                                                                    |

## Build & Check

Mise provides Python. The shim build needs LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`), LZ4 and AOSP `mkbootimg`/`avbtool`; Homebrew LLVM/LLD are recognised, and the AOSP tools come from `PATH`, `downloads/mkbootimg/` and `downloads/avb/`, or `MKBOOTIMG`/`AVBTOOL`.

```sh
mise run check
mise run build -- "$PWD/work/boot/working.payload" "$PWD/out/redfin.img"
```

`xnu/patches/` applies to XNU `8796.141.3` through blacktop/darwin-xnu-build. Phone tools and Metal need Xcode's iOS SDK through `tools/ios-cc`. The XNU, Metal2, Userland and Shim workflows run on `main` pushes and manual dispatches (`gh workflow run xnu.yaml --ref main`) and upload Actions artefacts; match an artefact's run revision to the intended source. A fresh clone must build or download its kernel.

## Device Workflow

The unlocked Google bootloader temporarily loads the shim with `fastboot boot`; XNU mounts an HFS+ root on `userdata`, and bootloader and firmware partitions stay intact. `sudo bash tools/build-root-mac.sh 32g` overwrites `work/rootimg/iosroot.img` with the CPU root; later plug-ins and userland additions are installed separately.

Installing the root is a separately approved data-erasing step: temporarily boot `recovery/twrp.img`, then run `bash tools/redfin-install-root.sh write`, which verifies every GiB; `bash tools/redfin-install-root.sh verify` only checks an existing installation. Keep the last 17 MiB of `userdata` outside the filesystem for logs.

Build the kernel-1046 CPU fallback without accessing a phone:

```sh
redfin_fallback=xnu/out-rk5a/kernel.development.sweet
NOBOOT=1 bash tools/redfin-boot.sh minimal "$redfin_fallback"
```

Temporarily boot the prepared phone with the accelerated configuration:

```sh
redfin_kernel=xnu/out-1055/kernel.development.sweet
redfin_args=(flamecpufreq=2 sweetgov=4060 sweetsurfkeep=1 sweetvsyncphase=0)
PRESET=ui bash tools/redfin-boot.sh working "$redfin_kernel" "${redfin_args[@]}"
```

The default profile renders on the CPU; `PRESET=ui` adds Metal, direct scanout, brightness and haptics (needs the installed `SweetHaptics.dylib`). Arguments and outputs stay in `work/boot/NAME.{adt,cmdline,payload,img}`; preserve working images while comparing changes.

**Invalidate MobileGestalt's CacheVersion when changing ADT capabilities.** Stale camera/flash answers block SpringBoard in `AVFlashlight` initialisation. The root tweaks invalidate the cache; an installed phone needs the same change, with a backup, before rebooting. The camera preset requires firmware/tables, RedwoodAudio and MediaToolbox's D22/D221/Default `StartRecorderServer=true` with its prewarm hook; the CPU root disables that server.

USB Ethernet uses host `192.168.7.1/24`, phone `192.168.7.2`, UDP 5140 logs, UDP 5141 commands and TCP 2223 files; configure the interface belonging to this Pixel after enumeration. For example, `python tools/redfin-cmd.py 'p disp' --all` queries display state, and `p scanout`, `p swapdone` and `p fc` query frame delivery and panel timing. `tools/redfin-live.py` records the live log and `tools/redfin-files.py` moves files.

Count `SCANOUT latched` frames in direct mode; `FB shown=0` alone does not mean rendering stopped. `tools/fps-parse.py` parses the counters and `tools/fb-shot.py` interprets framebuffer geometry. Replace loaded dylibs by staging a new file and renaming it; in-place writes can retain stale code-signature state.

**Recovery:** keep the matching Android 14 `UP1A.231105.001.B2` archive, `downloads/redfin-up1a.231105.001.b2-factory-4e5a2679.zip`, and verified per-device persist/modemst/fsg backups, and verify the archive's SHA-256 against [Google's redfin factory-image entry](https://developers.google.com/android/images#redfin). Stock recovery has not been exercised on this phone. Enter the bootloader with **Power + Volume Down** and confirm `product: redfin` with `fastboot -s SERIAL getvar product`. A separately approved factory restore follows the archive's `flash-all` instructions, writes stock firmware and erases userdata; retain needed iOS files first, keep the cable connected, then verify Android reaches **Welcome to Pixel** and check its build, charging and normal boot. Google's [full OTA packages](https://developers.google.com/android/ota#redfin) reinstall stock firmware without unlocking or wiping but do not restore the Android data filesystem replaced by HFS+; reinitialising userdata erases data. Never substitute another device's calibration dumps, never relock until an unmodified stock system boots and development has ended, and identify the actual boot state before firmware writes if fastboot is unavailable.

## Inputs Kept Locally

Apple material, translated shaders, vendor firmware, calibration dumps, phone trees/logs and credentials stay out of Git:

- iPhone X root, SystemOS and AppOS DMGs in `research/ipsw-x/dmg/` and the extracted `research/ipsw-x/d22ap.adt`; `tools/remotezip.py` fetches IPSW members.
- Adreno firmware in `fw-redfin/` (`a650_gmu.bin`, `a650_sqe.fw`, `a620_zap.mdt`, `a620_zap.b02`), extracted from the factory archive by `tools/redfin-gpufw.sh`; `tools/redfin-pull-firmware.sh` pulls the wider set over adb.
- Live device-tree facts in `shim/soc.args`, refreshed by `tools/redfin-pull-soc.sh`; Android observations in `recon/` from `tools/redfin-recon.sh`.
- A built `SweetMetal2.bundle`, installed by `tools/redfin-install-metal2.sh` once SSH is available; `/var/local/m2v-cache/<process>` must be writable by mobile, and the tested `/var/local/mtl2-clients` is `* -chronod`.
- A built `SweetHaptics.dylib` from the Userland artefact or `phone/haptics/build.sh`, installed at `/var/local/lib/SweetHaptics.dylib` by staging and rename.
- `/var/local/mtl2-env`, one `KEY=VALUE` per line: `TU_DEBUG=sysmem`, `SWEET_UBWC=1`, `SWEET_M2V_COLOR_WRITES=fetch`, `SWEET_M2V_SCRATCH=1`, `SWEET_TIMELINE=1`, `SWEET_U0011=1`, `SWEET_U0012=1`, `SWEET_U0013=1`, `SWEET_U0014=1`, `SWEET_NILENC=1`, `SWEET_PREWARM=2`, `SWEET_LUMA_BOOST=0`.
- `work/rtc-offset` for PMIC clock calibration (`tools/redfin-rtc.py`); `work/`, `logs/`, `out/` and `archive/` hold generated or preserved artefacts.

## Credits & Licences

This repository is a fork of ios-sweet and keeps its [MIT License](LICENSE); the flame additions use the same licence (Copyright (c) 2026 the ios-flame contributors). `xnu/patches/` modify Apple's XNU and stay under the **Apple Public Source License 2.0**. Files from other projects keep their own licences, listed below. Nothing from Apple's iOS, Google's images or Qualcomm's firmware is in this repository.

- **ios-redfin** ([DenialOfGravity](https://github.com/DenialOfGravity/ios-redfin)) and **ios-flame** ([NWylynko](https://github.com/NWylynko/ios-flame)): Pixel-specific shim, kernel patches and userland adaptations. Imported patches retain their original authorship and licence notices.
- **ios-sweet** ([dipa-studio](https://github.com/dipa-studio/ios-sweet), MIT): the Redmi Note 10 Pro XNU port this forks. Patches 0001-0081, the shim and most of `tools/` started there.
- **XNU** (Apple, APSL 2.0): xnu-8796.141.3. **blacktop/darwin-xnu-build** ([GitHub](https://github.com/blacktop/darwin-xnu-build), MIT) builds it.
- **HackiOS** (OOSEX GANG, [userland](https://github.com/oosexgang/hackios-xnu-userland), MIT; [kernel](https://github.com/oosexgang/hackios-xnu-kernel), APSL 2.0):
  - `phone/audio/` (RedwoodAudio.driver, the CoreAudio HAL plug-in) adapts its `userland/src/audio_plugin.c`; licence in `phone/audio/LICENSE.HackiOS`. Patch 0914 implements its `/dev/redwood-audio` and `/dev/redwood-haptic` interfaces for this phone.
  - Patch 0915 (`bsd/dev/sweet_adsp.c`, `bsd/sys/redwood_audio.h`) is its kernel `redwood_adsp.c` and `sys/redwood_audio.h` with the Pixel 5's numbers; the commit message lists the changes.
  - Patches 0952-0955 (`bsd/dev/sweet_sound.c`, `sweet_mic.c`, `sweet_guard.c`) carry over its `redwood_sound.c`/`redwood_mic.c` APR message layouts and its `redwood_guard.c` speaker guard (unchanged but for names), APSL 2.0.
  - It originates the Apple80211/wifid code (`redwood_net`, `redwood_apple80211`, `redwood_sta`, `RedwoodWLAN`, `MiniIONetworkStack`), the keystore wrap/unwrap and the 10-bit surface formats in patches 0123/0124.
- **Redbull kernel** (LineageOS android_kernel_google_redbull, GPL-2.0): the CS35L41, ALC5513 (rt5514) and LPASS register sequences in `sweet_cs35l41.c`/`sweet_mic.c` were written from its `sound/soc/codecs/cs35l41*.c`, `rt5514.c`, `rl6231.c` and `techpack/audio` and the phone's device tree.
- **ios-topaz** ([MakrSas](https://github.com/MakrSas/ios-topaz)): the Redmi Note 12 4G fork of ios-sweet, whose CREDITS.md puts the HackiOS-derived kernel parts under APSL 2.0.
  - `phone/wifi/radio.c` is a userland port of its TopazModem radio (its patches 0123-0130).
  - Patch 0123 contains its 0900 (en0 + Apple80211 for wifid) and 0128 (IOKit quiesce).
  - Patch 0990 (`bsd/kern/redfin_sandbox_container.c`, Sandbox container path from CFFIXED_USER_HOME) is its 0936 / HackiOS's `minisandbox_container_path` in `kern_minimac.c` (APSL 2.0), with bounds checks, a kill switch and a log.
- **UniXNU** ([GitHub](https://github.com/UniXNU/UniXNU), BSD-2-Clause-Patent at the top level):
  - `phone/metal2/NativeBridgeMetalFrontend.mm`: NativeMetal, MIT, patched for iOS 16.
  - `phone/metal2/bridge/` (NativeMetalBridge/NativeMetalObjects): NativeMetal, MIT; see `phone/metal2/bridge/LICENSE`.
  - `phone/turnip/NativeAdrenoABI.h`: NativeAdreno, MIT.
  - The Mesa patches that `tools/build-turnip-ios.sh` applies are fetched, not copied.
- **metal2vulkan** ([GitHub](https://github.com/steelbrain/metal2vulkan), GPL-2.0-or-later OR LGPL-3.0-or-later): fetched at UniXNU's pin by `tools/build-m2v-bridge.sh`. `phone/metal2/bridge/patches/` patch it and fall under its licence; a built SweetMetal2.bundle links it statically.
- **Mesa / Turnip** ([freedesktop](https://gitlab.freedesktop.org/mesa/mesa), MIT): the Adreno 620 Vulkan driver, fetched by `tools/build-turnip-ios.sh`. `phone/turnip/patches/` patch it.
- **Linux**: `phone/wifi/` follows the drivers named in each file's header: ath10k (ISC) and the Qualcomm SMEM, SMP2P, GLINK, QRTR and remoteproc drivers (GPL-2.0), plus Bjorn Andersson's rmtfs, pd-mapper and tqftpserv for those protocols. The FTS touch driver (patch 0085) was written from Google's `fts_touch` module (GPL-2.0) and the phone's device tree.
- **HexagonRPC** (the Sensor Shell / HexagonRPC contributors, [linux-msm](https://github.com/linux-msm/hexagonrpc), GPL-3.0-or-later; libhexagonrpc parts LGPL-3.0-or-later): `phone/fastrpc/` (`fastrpcd`, the ADSP sensors PD's file service) is built from hexagonrpcd's listener, localctl, apps_mem, iobuffer and libhexagonrpc marshalling code and interface definitions; each file keeps its header and says what changed. `fastrpcd` is a separate program under the **GPL-3.0-or-later** (`phone/fastrpc/LICENSE.hexagonrpc`), as are the files written for it (`transport.c`, `apps_std.c`, `fastrpcd.c`, `log.c` and the tests). Argument layouts and method numbers were checked against Qualcomm's fastrpc (`apps_std_skel.c`, BSD-3-Clause) and Android's `adsprpc.c` (GPL-2.0), read but not copied.
- **LZ4** (Yann Collet, [GitHub](https://github.com/lz4/lz4), BSD-2-Clause): `phone/tools/lz4/lz4.c` and `lz4.h` from v1.10.0, unchanged (licence in `phone/tools/lz4/LICENSE`); sweetmon's LZ4 frame writer uses its block compressor.
- Fetched and built locally, not in Git: Google's factory image, AOSP `mkbootimg` and `avbtool` (Apache 2.0), TWRP, dropbear (MIT), toybox (0BSD) and dash (BSD).
