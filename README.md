# iOS Redfin

Experimental iOS 16.7.16 (`20H392`, iPhone X userland) on Google Pixel 5 (`redfin`, SM7250 / Snapdragon 765G, Adreno 620). Built on [ios-redfin](https://github.com/DenialOfGravity/ios-redfin), ios-flame and ios-sweet.

## Status

**Unlock, Settings and touch work on this phone.** Metal with direct scanout is visibly smoother than CPU rendering, but measured scrolling remains about 29 fps; this is not yet a smooth or stable phone OS.

| Area | Local Evidence & Remaining Work |
| --- | --- |
| Boot | Minimal ADT plus invalidated MobileGestalt capability cache fixes the SpringBoard boot stall; CPU fallback retained |
| Rendering | Kernel 1051 passed CI; preserving recorded row pitch fixes striped plane, AirDrop and camera glyphs. Dead-fill mode 1 preserves text; A/B/B/A testing reintroduced missing characters in mode 2, so source defaults to 1 |
| Pacing | Governor with touch boost remains about 29.45 fps; vsync phase 5000 alone measured 29.07 fps. SweetFPS rewrites SpringBoard’s 30 fps request to 90, but delivered scrolling remains 28.92 fps with diagnostic logging off; CA timer/heartbeat overrides did not remove the limit |
| Other hardware | Wi-Fi, Bluetooth, audio, cameras and sensors are upstream results, unverified on this installation |
| Limitations | Charging under iOS, reliable suspend, cellular, GPS, NFC, fingerprint, SEP and Apple services remain unavailable or unfinished; the security model is permissive |

## Build & Check

Host tools use Python 3 and Bash. The native shim build needs LLVM (`clang`, `ld.lld`, `llvm-objcopy`, `llvm-nm`, `llvm-readelf`), LZ4 and AOSP `mkbootimg`/`avbtool`. Homebrew LLVM/LLD are recognised; AOSP tools live in `downloads/mkbootimg/` and `downloads/avb/`, or are selected with `MKBOOTIMG`/`AVBTOOL`.

```sh
mise run check
mise run build -- "$PWD/work/boot/working.payload" "$PWD/out/redfin.img"
```

Checks cover host syntax, existing synthetic tests, patch structure, local documentation links, Actions lint and whitespace. The build calls the existing native LLVM `shim/build.sh`; consolidating it behind the siblings' common Python entrypoint is deferred. It packs a boot-v3 image with an LZ4 Image and unsigned AVB footer padded to 96 MiB. Neither task accesses a phone.

`xnu/patches/` applies to XNU `8796.141.3` through blacktop/darwin-xnu-build. Phone tools and Metal also need Xcode's iOS SDK. The `xnu.yaml`, `metal2.yaml` and `userland.yaml` Actions workflows accept manual dispatches on `main`, for example `gh workflow run xnu.yaml --ref main`. Successful runs upload Actions artefacts; match their run revision to the intended source. A fresh clone must build or download its kernel.

## Device Workflow

The unlocked Google bootloader temporarily loads the shim with `fastboot boot`; XNU mounts an HFS+ root on `userdata`. Bootloader and firmware partitions remain intact. `sudo bash tools/build-root-mac.sh 32g` overwrites `work/rootimg/iosroot.img`, copies both cryptexes with numeric ownership, links the shared cache, applies the root tweaks and prunes the known FairPlay/voicemail crash loops. Later manual plug-ins and userland additions are not automatically included in that saved CPU root.

Installing the root is a separately approved data-erasing step: temporarily boot `recovery/twrp.img`, then use `tools/redfin-install-root.sh write`. It verifies every GiB; `tools/redfin-install-root.sh verify` only checks an existing installation. Keep the last 17 MiB of `userdata` outside the filesystem for logs.

Build the kernel-1046 CPU fallback without accessing a phone:

```sh
redfin_fallback=xnu/out-rk5a/kernel.development.sweet
NOBOOT=1 bash tools/redfin-boot.sh minimal "$redfin_fallback"
```

Temporarily boot the prepared phone with the tested accelerated configuration:

```sh
redfin_kernel=xnu/out-1051/kernel.development.sweet
redfin_args=(flamecpufreq=2 sweetgov=4060 sweetsurfkeep=1 sweetvsyncphase=0)
PRESET=ui bash tools/redfin-boot.sh working "$redfin_kernel" "${redfin_args[@]}"
```

The helper refuses multiple fastboot devices or another product. The default profile uses CPU rendering; `PRESET=ui` enables Metal, double buffering and direct scanout. Both omit camera/flash advertisement. Exact arguments and outputs stay in `work/boot/NAME.{adt,cmdline,payload,img}`. Preserve working images while comparing changes.

**Invalidate MobileGestalt's CacheVersion when changing ADT capabilities.** Stale camera/flash answers blocked SpringBoard in `AVFlashlight` initialisation after those nodes were removed. The root tweaks invalidate the cache; an installed phone also needs that change, with a backup, before rebooting. The camera preset requires firmware/tables, RedwoodAudio and MediaToolbox's D22/D221/Default `StartRecorderServer=true` with its prewarm hook active; the CPU root disables that server.

USB Ethernet uses host `192.168.7.1/24`, phone `192.168.7.2`, UDP 5140 logs, UDP 5141 commands and TCP 2223 files. Configure the interface belonging to this Pixel after enumeration; macOS interface names can change. For example, `python3 tools/flame-cmd.py 'p disp' --all` queries display state; `p scanout`, `p swapdone` and `p fc` query frame delivery and panel timing.

Count `SCANOUT latched` frames in direct mode; `FB shown=0` alone does not mean rendering stopped. Use identical gestures/phase markers, screenshots, thermal state and `/var/local/mtl2.log` timelines. `tools-claude/fps-parse.py` parses counters; `fb-shot.py` interprets framebuffer geometry. Keep thermal protection enabled. Existing tests rejected encode-thread mode 3, FP16/contraction/plain-colour experiments, triple buffering, GMEM/autotune and several timing knobs. Replace loaded dylibs by staging a new file and renaming it; in-place writes can retain stale code-signature state.

**Recovery:**

Keep the matching Android 14 `UP1A.231105.001.B2` archive, `downloads/redfin-up1a.231105.001.b2-factory-4e5a2679.zip`, and verified per-device persist/modemst/fsg backups. Verify the archive's full SHA-256 against [Google's redfin factory-image entry](https://developers.google.com/android/images#redfin). Stock recovery has not been exercised in this session.

Enter the bootloader with **Power + Volume Down** and verify `product: redfin` using `fastboot -s SERIAL getvar product`. A separately approved factory restore follows the matching archive's `flash-all` instructions, writes stock firmware and erases userdata; retain needed iOS files first and keep the cable connected. Verify Android reaches **Welcome to Pixel**, then check its build, charging and normal boot path.

Google's [full OTA packages](https://developers.google.com/android/ota#redfin) normally reinstall stock firmware without unlocking or wiping, but do not themselves restore the Android data filesystem after this port replaced it with HFS+. Reinitialising userdata is data-erasing. Never substitute another device's calibration dumps, and never relock until a complete unmodified stock system boots successfully and development has ended. If fastboot is unavailable, identify the actual boot state before firmware writes.

## Inputs Kept Locally

Keep Apple material, translated shaders, vendor firmware, calibration dumps, phone trees/logs and credentials out of Git. The local inputs are:

- iPhone X root, SystemOS and AppOS DMGs in `research/ipsw-x/dmg/`, and extracted `research/ipsw-x/d22ap.adt`; `tools/remotezip.py` fetches IPSW members.
- Adreno firmware in `fw-redfin/`: `a650_gmu.bin`, `a650_sqe.fw`, `a620_zap.mdt`, `a620_zap.b02`; `tools/redfin-gpufw.sh` extracts it from the matching factory archive.
- Built `SweetMetal2.bundle`, installed by `tools/flame-metal2-install.sh` once SSH is available; `/var/local/m2v-cache/<process>` must be writable by mobile. Tested `/var/local/mtl2-clients`: `* -chronod`.
- `/var/local/mtl2-env`, one `KEY=VALUE` per line: `TU_DEBUG=sysmem`, `SWEET_UBWC=1`, `SWEET_M2V_COLOR_WRITES=fetch`, `SWEET_M2V_SCRATCH=1`, `SWEET_TIMELINE=1`, `SWEET_U0011=1`, `SWEET_U0012=1`, `SWEET_U0013=1`, `SWEET_U0014=1`, `SWEET_NILENC=1`, `SWEET_PREWARM=2`, `SWEET_LUMA_BOOST=0`. `SWEET_DEADFILL=1` is the verified text-preserving mode and current source default.
- `work/rtc-offset` for PMIC clock calibration; `work/`, `logs/`, `out/` and `archive/` hold generated or preserved local artefacts. Experiment history and patch explanations remain in Git.

## Credits & Licences

This repository is a fork of ios-sweet and keeps its [MIT License](LICENSE). The flame additions are under
the same licence (Copyright (c) 2026 the ios-flame contributors), with these exceptions:

- `xnu/patches/` modify Apple's XNU, which is under the **Apple Public Source License 2.0**. The patched
  files stay under the APSL 2.0.
- Files that came from other projects keep their own licence, listed below.

Nothing from Apple's iOS, Google's images or Qualcomm's firmware is in this repository; see the README for
what you need to fetch yourself.

### Sources & Attribution

- **ios-redfin** (DenialOfGravity, <https://github.com/DenialOfGravity/ios-redfin>) and **ios-flame**
  (NWylynko, <https://github.com/NWylynko/ios-flame>): Pixel-specific shim, kernel patches and userland adaptations.
  Imported patches retain their original authorship and licence notices.

- **HackiOS** (OOSEX GANG, <https://github.com/oosexgang/hackios-xnu-userland>, MIT): `phone/audio/`
  (RedwoodAudio.driver, the CoreAudio HAL plug-in) adapts its `userland/src/audio_plugin.c`; licence
  in `phone/audio/LICENSE.HackiOS`. Patch 0914 implements its `/dev/redwood-audio` and `/dev/redwood-haptic`
  interfaces for this phone. Patch 0915 (`bsd/dev/sweet_adsp.c`, `bsd/sys/redwood_audio.h`) is HackiOS's kernel
  `redwood_adsp.c` and `sys/redwood_audio.h` (<https://github.com/oosexgang/hackios-xnu-kernel>, APSL 2.0) with the
  Pixel 5's numbers; the commit message lists what changed.
  Patches 0952-0955 (`bsd/dev/sweet_sound.c`, `sweet_mic.c`, `sweet_guard.c`) carry over HackiOS's kernel
  `redwood_sound.c`/`redwood_mic.c` APR message layouts and its `redwood_guard.c` speaker guard (unchanged but for
  names), APSL 2.0. The CS35L41, ALC5513 (rt5514) and LPASS register sequences in `sweet_cs35l41.c`/`sweet_mic.c`
  were written from the redbull kernel's `sound/soc/codecs/cs35l41*.c`, `rt5514.c`, `rl6231.c` and
  `techpack/audio` (GPL-2.0; LineageOS android_kernel_google_redbull) and the phone's device tree.

- **ios-sweet** (dipa-studio, <https://github.com/dipa-studio/ios-sweet>, MIT): the XNU port to the Redmi
  Note 10 Pro this is forked from. Patches 0001-0081, the shim and most of `tools/` started there.
- **XNU** (Apple, APSL 2.0): xnu-8796.141.3.
- **ios-topaz** (MakrSas, <https://github.com/MakrSas/ios-topaz>): the Redmi Note 12 4G fork of ios-sweet.
  - `phone/wifi/radio.c` is a userland port of its TopazModem radio (its patches 0123-0130).
  - Our patch 0123 contains its 0900 (en0 + Apple80211 for wifid) and 0128 (IOKit quiesce).
  - ios-topaz's CREDITS.md puts the HackiOS-derived kernel parts under the APSL 2.0.
  - Patch 0990 (`bsd/kern/redfin_sandbox_container.c`, Sandbox container path from CFFIXED_USER_HOME) is its 0936 /
    HackiOS's `minisandbox_container_path` in `kern_minimac.c` (APSL 2.0), with bounds checks, a kill switch and a log.
- **HackiOS** (OOSEX GANG, <https://github.com/oosexgang/hackios-xnu-kernel>, APSL 2.0): the origin of the
  Apple80211/wifid code above (`redwood_net`, `redwood_apple80211`, `redwood_sta`, `RedwoodWLAN`,
  `MiniIONetworkStack`), the keystore wrap/unwrap and the 10-bit surface formats in 0123/0124.
- **UniXNU** (<https://github.com/UniXNU/UniXNU>, BSD-2-Clause-Patent at the top level):
  - `phone/metal2/NativeBridgeMetalFrontend.mm`: NativeMetal, MIT, patched for iOS 16.
  - `phone/metal2/bridge/` (NativeMetalBridge/NativeMetalObjects): NativeMetal, MIT; see `phone/metal2/bridge/LICENSE`.
  - `phone/turnip/NativeAdrenoABI.h`: NativeAdreno, MIT.
  - The Mesa patches that `tools/build-turnip-ios.sh` applies; fetched, not copied.
- **metal2vulkan** (<https://github.com/steelbrain/metal2vulkan>, GPL-2.0-or-later OR LGPL-3.0-or-later):
  fetched at UniXNU's pin by `tools/build-m2v-bridge.sh`. `phone/metal2/bridge/patches/` are patches to it and
  fall under its licence. A built SweetMetal2.bundle links it statically.
- **Mesa / Turnip** (<https://gitlab.freedesktop.org/mesa/mesa>, MIT): the Vulkan driver for the Adreno 640,
  fetched by `tools/build-turnip-ios.sh`. `phone/turnip/patches/` are patches to it.
- **Linux**: `phone/wifi/` follows the drivers named in each file's header: ath10k (ISC) and the Qualcomm SMEM,
  SMP2P, GLINK, QRTR and remoteproc drivers (GPL-2.0). It also follows Bjorn Andersson's rmtfs, pd-mapper and
  tqftpserv for those protocols. The FTS touch driver (patch 0085) was written from Google's `fts_touch`
  module (GPL-2.0) and the phone's device tree.
- **HexagonRPC** (the Sensor Shell / HexagonRPC contributors, <https://github.com/linux-msm/hexagonrpc>,
  GPL-3.0-or-later; libhexagonrpc parts LGPL-3.0-or-later): `phone/fastrpc/` (`fastrpcd`, the ADSP sensors PD's
  file service) is built from hexagonrpcd's listener, localctl, apps_mem, iobuffer and libhexagonrpc marshalling
  code and interface definitions (each file keeps its header and says what fastrpcd changed). `fastrpcd` is a
  separate program under the **GPL-3.0-or-later** (`phone/fastrpc/LICENSE.hexagonrpc`); the files written for it
  (`transport.c`, `apps_std.c`, `fastrpcd.c`, `log.c`, the tests) are under the same licence. Argument layouts and
  method numbers were checked against Qualcomm's fastrpc (`apps_std_skel.c`, BSD-3-Clause) and Android's
  `adsprpc.c` (GPL-2.0) -- read, not copied.
- **blacktop/darwin-xnu-build** (<https://github.com/blacktop/darwin-xnu-build>, MIT): the XNU build.
- Fetched and built by the user, not in git:
  - Google's factory image, AOSP `mkbootimg` and `avbtool` (Apache 2.0)
  - TWRP
  - dropbear (MIT), toybox (0BSD) and dash (BSD)
- **LZ4** (Yann Collet, <https://github.com/lz4/lz4>, BSD-2-Clause): `phone/tools/lz4/lz4.c`, `lz4.h` from v1.10.0,
  unchanged (licence in `phone/tools/lz4/LICENSE`); sweetmon's LZ4 frame writer sits on its block compressor.
