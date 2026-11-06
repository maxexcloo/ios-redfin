# ios-redfin

**Apple's iOS 16 running on a Google Pixel 5.**

A port of [ios-sweet](https://github.com/dipa-studio/ios-sweet) to the Pixel 5 (`redfin`, Qualcomm SM7250 /
Snapdragon 765G, Adreno 620), via [ios-flame](https://github.com/NWylynko/ios-flame) and its sunfish branch.
Apple's open-source XNU kernel (xnu-8796, the iOS 16 generation), with ios-sweet's, flame's, sunfish's and the
redfin patches on top, runs the **unmodified iOS 16.7.16 (20H392) userland of the iPhone X**. The phone is
booted with `fastboot boot` from Google's own bootloader. Nothing is flashed to the boot chain; the iOS root
lives in the `userdata` partition.

![Lock screen, home screen, Settings, General, Control Center, Today view, Spotlight, Clock, Calendar, Notes, Photos and Safari, all rendered through Metal on the Adreno 620](docs/img/metal2-tour.jpg)

> Experimental bring-up, not a usable phone OS. It **erases Android's user data**, Apple's security model is
> mostly switched off (permissive AMFI and sandbox, stub keystore), and many parts are missing. Do not put
> anything personal on it.

## What works (2026-10-30, kernel 1046 / image rk5a)

| Area | State |
| --- | --- |
| Boot | Google ABL (unlocked) -> `fastboot boot` of the shim -> XNU. Every reset lands back in fastboot (the shim sets the PON reason) |
| CPU | All 8 cores (1x Cortex-A76 prime 2.4 GHz, 1x Cortex-A76 gold 2.2 GHz, 6x Cortex-A55 1.8 GHz), PSCI, DVFS with touch/frame boost |
| Storage | UFS; the iOS root is an HFS+ image in `userdata`, read/write (~109 GiB once grown) |
| Display | The 1080x2340 Samsung command-mode panel ABL leaves running, 90 Hz. iOS sees an iPhone X (1125x2436); the Adreno 620 scales each frame to fit, double-buffered, with Apple's continuous corners. Brightness slider works |
| GPU / Metal | Metal on Mesa's Turnip Vulkan driver through metal2vulkan (`sweetmtl=2`): backboardd, SpringBoard and apps render on the GPU with a shader cache and pipeline prewarm. Home-screen swipes reach ~60 fps |
| Touch, buttons | Samsung sec_ts over SPI, interrupt-driven; power and volume keys |
| Haptics | The DRV2624 motor plays iOS's UI haptics (RedwoodAudio.driver actuator device) |
| Sound, mic | Both CS35L41 speaker amps through the audio DSP; records from the ALC5513 (rt5514) mics |
| Camera | Camera.app live preview and photos on the back (IMX363) and front (IMX355); ultra-wide (IMX481) streams |
| USB | Ethernet to the Mac: SSH (dropbear), a kernel file server, the live kernel log, internet sharing |
| Wi-Fi | The radio driven from userland (`wland`): **Settings -> Wi-Fi works**, wifid joins at boot and rejoins after a dropped link |
| Bluetooth | WCN3998 over UART through `btd`'s bridge: **Settings -> Bluetooth** scans and finds nearby devices |
| Battery | Real percentage from the fuel gauge (seeded from the gauge, then coulomb-counted) |
| Sensors | The DSP's sensor process stays up (`fastrpcd`); accelerometer, gyro, light, compass and pressure reach iOS as HID services through `sensd` |
| Apps | The stock apps from the IPSW (Settings, Safari, Camera, Photos, Notes, Weather, Voice Memos, Calculator, Clock, ...) and app extensions (e.g. text-to-speech voices) |
| Time | PMIC RTC |

**Not working yet:** charging while iOS runs (charge the phone in the bootloader), Wi-Fi signal bars (the signal
patch is held back: it resets the phone on join), auto-rotation, auto-brightness and the proximity sensor, the
Control Center flashlight button, Bluetooth pairing and audio profiles (untested), cellular, GPS, NFC, the
fingerprint sensor, SEP, hardware video decode/encode, App Store and Apple ID services.

## How it boots

```
ABL (Google's bootloader, unlocked)
  -> fastboot boot redfin-rNN.img       LZ4 kernel + AVB hash footer, or ABL refuses it
       shim (shim/): acts as iBoot. Logs to UFS, sets the PON reason, builds the boot args
       and jumps to XNU with an Apple device tree (tools/mkadt.py)
  -> XNU (xnu/patches): every driver built in: UFS, display, GPU, touch, keys, USB, RTC, RPMh,
       audio DSP (APR, FastRPC, QRTR), speaker amps, mics, haptics, cameras, flash, thermal,
       CPU frequency, battery, sensor HID services, Bluetooth UART bridge, en0 for wifid
  -> launchd and the iPhone X userland from userdata
       + phone/: SweetMetal2.bundle (Metal), RedwoodAudio.driver (sound, haptics, camera),
         wland (Wi-Fi), btd + bluetool (Bluetooth), fastrpcd + sensd (DSP files, sensors), debug tools
```

## Repository

| Path | What |
| --- | --- |
| `xnu/patches/` | 0001-0081 from ios-sweet, 0082-0124 from ios-flame, 0125-0160 from the sunfish series, **0900-1046 for redfin** (272 patches; [one line per patch](NOTES.md#redfin-patches)) |
| `shim/` | The bare-metal shim ABL boots (`shim/build.sh`) |
| `tools/` | Host tools: ADT and payload, boot-and-collect-logs loop, SSH/file/command access to the running phone, GPU and Metal debugging, ios-sweet's root-image scripts |
| `phone/` | Code that runs in iOS: `wifi/` (wland), `metal2/` + `turnip/` (Metal on Turnip), `metal/` (the older template driver), `gpu/`, `tools/` (psx, pstack, openapp, lsreg, netsvc, oslog, ...) |
| [NOTES.md](NOTES.md) | Hardware facts, Google ABL boot image rules, test loop, one line per redfin patch |
| [HANDOFF.md](HANDOFF.md) | The engineering log, newest first: every step, what broke and why |
| [METAL-NEXT.md](METAL-NEXT.md) | The plan for Metal at user quality (metal2vulkan + Turnip) and why |
| [RECOVERY.md](RECOVERY.md), [DEVICE.md](DEVICE.md) | Back to stock Android; the test phone and host setup |
| [docs/redfin/](docs/redfin/) | Port plan, hardware map, known-good state (rk5a), quality-of-life and scanout plans, disabled-services list |
| `docs/ios-sweet/` | ios-sweet's README and notes (the history of patches 0001-0081) |

## Not in git: what you need to get yourself

Scripts expect these at the paths shown (all gitignored). None of them can be shared: they are Apple's or
Google's/Qualcomm's files, or data from your own phone.

- **The phone**: a Pixel 5 (`redfin`) with the bootloader unlocked, on the final Android 14 build
  `UP1A.231105.001.B2`. Keep Google's factory image ([RECOVERY.md](RECOVERY.md)). Back up the per-device
  partitions first (persist, modemst1/2, fsg, fsc, ...). They hold your IMEI and calibration data, so keep
  them private.
- **Boot image tools**: AOSP `mkbootimg` in `downloads/mkbootimg/` and `avbtool.py` in `downloads/avb/`.
  Boot header v3: ABL takes the DTB from `vendor_boot`, so no stock DTB is needed.
- **TWRP** 3.7.0_11-0 for redfin (`recovery/twrp.img`, sha256 `9adc9aae...`). It writes the root image and
  reads the logs back. Boot it with `fastboot boot`, never flash it.
- **The iOS root**: the iPhone X iOS 16.7.16 (20H392) IPSW. `tools/remotezip.py` fetches single files from
  Apple's CDN (the three DMGs are ~7.5 GB, not the whole 6.2 GB+ restore). Build the HFS+ volume with
  `tools/build-root-mac.sh` on macOS (needs one sudo: owners inside the volume must be root/_logd/mobile),
  then write it from TWRP with `tools/redfin-install-root.sh`, not `fastboot flash userdata`.
- **Firmware** from the factory image's `vendor.img` (`/firmware`):
  - GPU: `a650_gmu.bin`, `a650_sqe.fw` and `a620_zap.mdt`/`.bNN` (put into the device tree by
    `mkpayload.py --gpufw`).
  - Audio DSP: `adsp.*` in `/private/var/local/fw` on the phone; the sensor files for `fastrpcd`.
  - Wi-Fi and modem firmware plus your own modemst/fsg images.
  - Bluetooth: `crbtfw32.tlv`, `crnv32.bin` in `/private/var/local/fw`.
  - Cameras: register tables made from the vendor camera module files with `tools/redfin-camtab.py`.
- **Toolchains**: Xcode with the iOS SDK (`work/userland/bin/ios-cc`), Homebrew `llvm`, `lld` and `lz4` for the
  shim, [blacktop/darwin-xnu-build](https://github.com/blacktop/darwin-xnu-build) for the first kernel build,
  Mesa and metal2vulkan checkouts for `tools/build-turnip-ios.sh` and `tools/build-m2v-bridge.sh` (pins in the
  script headers), and dropbear, toybox and dash built for iOS (HANDOFF.md, "SSH into iOS works").

## Run it

The kernel needs Xcode 15's `iig` in the original recipe, but patch 0082 adds `IORPC.kernelContent` for
Xcode 16+ `iig`, so the CI runs on `macos-15` (macos-14 has been retired by GitHub).

```sh
gh workflow run xnu.yml --ref main                      # kernel -> branch builds-xnu, artifact xnu-kernel
python3 tools/mkadt.py work/boot/redfin-hi.adt --highmem --camera --flash --backlight
python3 tools/mkpayload.py xnu/out/kernel.development.sweet work/boot/redfin-hi.adt \
    work/boot/payload.bin --cmdline "$(cat work/boot/redfin.cmdline)"
shim/build.sh "$PWD/work/boot/payload.bin" "$PWD/out/redfin.img"
sudo bash tools/build-root-mac.sh 32g                   # iOS root image (one sudo)
bash tools/redfin-install-root.sh write                 # from TWRP, erases Android userdata
fastboot boot out/redfin.img
```

`tools/redfin-boot.sh NAME KERNEL [ARGS...]` is the one-shot version: packs kernel + ADT + boot args and
`fastboot boot`s it. `tools/redfin-install-root.sh` verifies every GiB after writing;
`tools/retweak-root.sh` re-applies the root tweaks without rebuilding. NOTES.md, HANDOFF.md and
`docs/redfin/` cover each step and the boot args.

## Credits

Built on ios-sweet by dipa-studio, with Wi-Fi from ios-topaz and HackiOS, and Metal from UniXNU, metal2vulkan
and Mesa. Licences and details in [CREDITS.md](CREDITS.md).
