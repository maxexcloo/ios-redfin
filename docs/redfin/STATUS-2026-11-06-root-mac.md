# redfin: iOS root built on macOS, written, and booted (2026-11-06)

Bring-up steps 3 (write the root) and 4 (boot XNU) re-run from macOS instead of WSL, against the
image from `tools/build-root-mac.sh`. Nothing was flashed; the kernel was `fastboot boot`ed.

## What was done

**Root image.** `work/rootimg/iosroot.img`, 32 GiB, built by `tools/build-root-mac.sh 32g`
(11 GiB used) and re-tweaked/pruned by `tools/prune-root.py`: `com.apple.fairplayd.H2` and
`com.apple.voicemail.vmd` removed from `System/Library/xpc/launchd.plist` (backup
`launchd.plist.before-prune` kept). sha256 `8226ab55b24ec6fed33e9e11d84e3a69e939b5861529782a6c1aac4d85618898`.

**Step 3 - written to userdata.** `userdata` is `/dev/block/sda19`, confirmed live in TWRP
(117155278848 bytes; the image is the first 32 GiB, the kernel log lives at the tail and is not
touched). All 32 GiB verified by per-GiB SHA-256 against `work/rootimg/iosroot.gib.sha256`
(`tools/root-hashes.sh`, 32 chunks).

- **One defect found and fixed:** the earlier write had dropped the last 1 KiB. GiB 31 mismatched
  because the HFS+ *alternate* volume header (at byte 34359737344, the last 1024 bytes of the
  volume) was all zeros on the phone. Only that block was rewritten; all 32 GiB then matched.
  A full-image re-write is not needed, but the installer's verify step is what caught it.

**Step 4 - booted.** `fastboot boot out/r-k1.img` (header v3, AVB hash footer, LZ4 kernel
`out/kernel`, ramdisk `out/ramdisk` = `work/boot/r-k1.payload`).
Cmdline from `work/boot/r-k1.cmdline`: `rd=ufsroot0 ufsrw=1 rootrw=1 sweetfb_hz=90
sweetusb=2 sectouch=1 sweetgpu=0 sweetfbflip=1 sweetnull=backboardd,SpringBoard ...`.

Result: the kernel comes up and the phone exposes **CDC-ECM USB Ethernet** ("Sweet iOS (USB
Ethernet)", MAC `02:00:5e:77:ee:01`); the host sees it as `en15` with link `active`. It stayed up
for 28+ minutes without a reset.

ABL prints `boot.img missing cmdline or OS version` on every `fastboot boot` here; it is harmless
(the header carries os_version 14.0.0 and a cmdline).

## Kernel console log (recovered)

The kernel keeps a 4 MiB ring and copies it to the last 4 MiB + 4 KiB of `userdata`
(patch 0069). Header at 0x1b46bfa000 of the partition: `SWEETLOG`, 4 MiB ring, 323339 bytes
written. Decoded to `logs/sweetlog-rk5a-boot.txt` (**gitignored**).

That ring still held the *previous* boot (the rk5a camera-preset cmdline), which documents a
complete iOS bring-up:

- `hfs: mounted iOSRoot on device b(1, 0)`, `exec launchd`, libignition handshake
- `exec SpringBoard`, `exec backboardd`, `exec wifid`, `exec bluetoothd`
- 8 CPUs on (`cpu=0..7 ... came alive`), thermal + cpufreq + GPU pool lines running
- `SWEET ARP tx ... spa 192.168.7.2 tpa 192.168.7.1` - the phone waiting for the host address

Because the ring is overwritten per boot, the `r-k1` run's own console was not captured: it needs
either a reset out of iOS (then read the tail from TWRP/Android) or the live UDP stream, which
needs the host at 192.168.7.1/24.

## Open

- **Host side of the link.** `en15` gets only a link-local address; macOS needs
  `sudo ifconfig en15 192.168.7.1 netmask 255.255.255.0` (or `tools/sweet-usbnet.sh`, which is
  Linux-only as written) before the live log on UDP 5140, the command server on 5141 and the
  SSH/FlameBridge path work. Not yet done - the local host tools assume `ip`/`nmcli`.
- No photo of the screen for this run; the evidence is USB enumeration + link-active + the
  recovered console of the previous, identically-built boot.
- `r-k1` boots with `sweetgpu=0` (CPU rendering) and `sweetnull=backboardd,SpringBoard`.
- Two phones were on USB at once during this session; `adb` without `-s` hit the other one
  (`TrebleDroid with GApps`, serial `JELLYS0000009037`). Always pass `-s 0A281FDD4000KH`.
