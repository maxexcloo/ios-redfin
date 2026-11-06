# redfin, 2026-11-06 evening: the display stall measured, and the state we were missing

Second session of the day (the first is `STATUS-2026-11-06-display.md` / `HANDOFF-REDFIN.md`).
This one stops guessing about the display and asks the running kernel, then closes every
difference from the known-good phone that exists in the tree. **Still no UI: CoreAnimation
presents 5 frames at boot and then nothing.** What follows is what that is now known *not* to be.

## Branch to work from

`redfin-int` (= `known-good-rk5a`'s content plus the ws-n merges), or a fork of it. `main` still
carries the inherited flame base: 123 patches ending at 0124, **zero** redfin patches. Do not boot
`main`. This session worked on `work` = `redfin-int` + 13 commits (docs, root tools, xnu 1047/1048),
which is what fork `maxexcloo/ios-redfin` builds in CI.

Newest upstream workstreams (`ws-n-*`, 2026-11-04..06) are cellular/IPA/video only — no display,
compositor or boot change — so they are not "better" for this problem.

## Three things that were simply missing (all now installed on the phone)

1. **`SweetMetal2.bundle` was never installed.** CI artifact of r70 (`metal2` run 42164469371),
   installed to `/System/Library/Extensions/SweetMetal2.bundle` (sha256 `954b013b…` verified by
   reading it back over the file server).
2. **`/var/local` did not exist** — not the directory, not anything in it. The bundle then refused
   the device: `ShaderCache(ShaderCacheError { path: "/var/local/m2v-cache/backboardd",
   kind: PermissionDenied })`. Created `/var/local`, `/var/local/m2v-cache/<process>` (0777),
   `/var/local/mtl2-env` (r70 env), `/var/local/mtl2-clients` (`* -chronod`).
3. **The clock was at April 1970** — `sweetrtcoff` was missing from the cmdline. Calibrated with
   the `rtc` poke: `sweetrtcoff=1786049190`. iOS now logs `2026-11-06 …`.

Result: the Metal stack comes up on this phone for the first time —
`MTL2[26 SpringBoard]: device Turnip Adreno (TM) 620 in 3186 ms`, kernel GPU present flips
(`SWEET GPU: present: flip 1/2`, panel stride 4352), `SWEET FB: 5s: swaps 5 shown 4`.

## The stall, measured (not inferred)

With GPU present, Metal device up, clock right, direct scanout on:

```
p swapdone   swap done 0
p prof start backboardd 100 3 24 100
             0 user + 0 kernel + 5915 off-CPU samples   (22 threads, all waiting)
p prof start SpringBoard 100 3 24 100
             0 user + 0 kernel + 4673 off-CPU samples   (17 threads, all waiting)
```

SpringBoard is fully initialised (UIKit eventfetch, SBWiFiManager, CoreMotion, metal2vulkan
threads all present) and idle in `mach_msg_trap`. Nothing is spinning; nothing is stuck; the
system is waiting for a boot completion that never arrives. launchd completes every boot task and
starts 631 processes, so the kernel side of boot is fine.

Crash loops, counted over 25 minutes: `nanotimekitcompaniond` **148×**, `bluetoothd` **139×**
(every ~10 s). `spindump` runs a few times.

`logs/watch-*.tsv` has the per-minute rows; one row looks like
`21:21:57  1464.3  0  0  off  on`.

## The last documented difference: root volume type

`KNOWN-GOOD.md` lists `org.iosonpixel.fstypeovr` (statfs reports "apfs" for /) under "phone-side
state it relies on", and it exists in no branch of git. Done in the kernel instead:

- **xnu 1049** `xnu/patches/1049-redfin-root-reports-apfs.patch`: `sweet_root_as_apfs()` in
  `bsd/vfs/vfs_syscalls.c` makes `statfs`/`fstatfs`/`statfs64`/`getfsstat` report
  `f_fstypename = "apfs"` for the mount with `MNT_ROOTFS` whose type is hfs.
- Effect, measured: **`apfs_iosd` now runs** (it never did before) and immediately issues APFS
  ioctls at HFS+ (`SWEET HFS: unknown ioctl 0x41684a3e ('J' 62, 360 bytes) … -> ENOTTY`).
- It does **not** unblock boot: `watch-r4-apfs` = `NO FRAMES`, `swapdone 0`, same crash loops.

## What is now ruled out (with the measurement that rules it out)

| Hypothesis | Ruled out by |
| --- | --- |
| The GPU is needed for anything on screen | frames with `sweetgpu=0` (earlier session) and with `sweetgpu=1` (this one) |
| Metal / the bundle is the blocker | device up, `Turnip Adreno (TM) 620`, still no frames |
| It is just a very slow first boot (25 min) | `watch-r3-metal-time`: 5 frames at 58.9 s, **none** in the following 24 min |
| The clock (1970) breaks boot | fixed to 2026-11-06, unchanged |
| The root volume type gates boot | 1049 runs `apfs_iosd`, unchanged |
| Backboardd/SpringBoard are stuck or spinning | 0 on-CPU samples in 3 s for both, all threads waiting |
| A kernel or launchd boot task fails | every boot task completes, 631 processes start |

## What is left

The remaining difference is *data on his phone*, not code: his `/var/local` tree, his hand-built
root image, and whatever `fstypeovr` did beyond statfs. Two ways to close it, in order of value:

1. Ask the author for `tar czf - /var/local`, `launchctl print system` and the root-build command.
2. Diff our running services against iOS's expected set. Installed for that:
   `org.iosonpixel.psxdump` (a `RunAtLoad` job: `/var/local/bin/dash -c 'sleep 150; psx …'` writes
   `/var/local/psx.log` at t≈150 s and t≈300 s). `/tmp/expected-labels.txt` holds the 532 job
   labels from `launchd.plist`; `logs/expected-labels.txt` is the same list in the repo.
   The job is inert until the next boot.

## Tooling added

- `tools-claude/redfin-watch.py SECONDS LABEL` — unattended watcher: pokes `p swapdone`,
  `p scanout`, `p disp` once a minute, keeps the raw log, writes `logs/watch-LABEL.tsv` and a
  verdict in `logs/watch-LABEL.txt`. This is how "5 frames then nothing" was established twice.
- `tools-claude/push-userland.sh`-equivalent done by hand this session: 29 binaries from
  `builds-userland` → `/var/local/bin`, `RedwoodAudio.driver` → HAL, and three launchd jobs
  (`wland`, `sensd`, `fastrpcd`) merged into `/System/Library/xpc/launchd.plist` (528 → 531),
  held off with `/var/local/{wland,sensd,fastrpcd}.off` because their firmware is not on the phone.
  `launchd.plist.bak` is the untouched original.

## Boot args used (`work/boot/r4.cmdline`)

rk5a's line minus `sweetrtcoff=1792779327` (replaced by our calibration) and with rk5a's
`sweetgpu=1 sweetmtl=2 sweetgpufreq=4 sweetscanout=2 sweetfbflip=1`.

## Open, at the time of writing

The phone dropped off USB (no fastboot, no adb, no USB device) after a `poke reboot` + failed
`fastboot boot`: physical power+vol-down. This is the known unattended failure mode; the watcher
above covers everything else.
