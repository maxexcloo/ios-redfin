# HANDOFF: redfin display — the GPU is not the blocker (2026-11-06)

Supersedes the "Next: the GPU/Metal chain" section of `HANDOFF-REDFIN.md` and the
older `docs/redfin/STATUS-2026-11-06-root-mac.md`. Read those for the root image,
boot chain and tooling; this file only corrects the display diagnosis.

## Correction first

`HANDOFF-REDFIN.md` said:

> Cause: this session booted with `sweetgpu=0`. Upstream's rk5a cmdline has `sweetgpu=1`.
> ... With the GPU off there is no present path at all.

That is wrong, and the evidence was a logging bug. Measured on a live boot
(`out/r-k6.img`, `sweetgpu=0`), by asking the running kernel:

```
p disp      SWEET FB: display on (p disp; scanout direct)
p fc        intf frame_count 37506 -> 37596 = 89.9 Hz; panel set to 90 Hz
p scanout 1 SWEET SCANOUT: on, 2 slot surfaces
p scanout 0 SWEET FB: swap 3 layer 0 surface 3 1125x2436 fmt 0x42475241 bpr 4608
```

Display on, panel scanning at 89.9 Hz, MDP scanout active, and a real 1125x2436
iPhone X frame presented — all with `sweetgpu=0`. The GPU is for *quality*
(fit-scale instead of centre-crop), not for getting anything on screen.

### Why "zero display lines" was never true

Two independent bugs made a working display path look dead:

1. **Every boot log was discarded.** `sweet_log_copy()` advances its stream
   cursor, and `ud_log_thread()` passed the live cursor straight in. A failed
   `sock_send()` therefore consumed the chunk permanently. Until the host adds
   192.168.7.1 by hand — which is after enumeration — every send fails, so the
   entire boot backlog (mount, launchd, `SWEET FB`, `SWEET SURF`) was thrown
   away. Captures always began around "exec xpcproxy". Fixed: patch **1048**.
2. **CI silently dropped a patch.** Patch 1047 was malformed ("corrupt patch at
   :40") and `build.sh`'s `patches()` only warns, so the run went green and
   published a kernel without it. Fixed: 1047 regenerated, and a new
   **Verify every patch applied** step fails the build naming any
   `xnu/patches/*.patch` not reported applied.

Never trust "the log has no X" on this port without first proving the log
reaches you. `p <command>` over UDP 5141 is the reliable channel: it prints its
answer into the ring, and a reply arriving proves the path works.

## Where the display actually stops

```
p swapdone   swap done 0, ticks 0
```

Zero swaps while idle. Combined with:

```
p prof start backboardd  ->  0 user + 0 kernel + 2604 off-CPU samples
p prof start SpringBoard ->  0 user + 0 kernel + 1664 off-CPU samples
```

all threads of both processes sit in `TH_WAIT`, including
`com.apple.coreanimation.render-server` and `com.apple.coreanimation.display.primary`.
Nothing is stuck and nothing is spinning: CoreAnimation painted once (the
`swap 3` above) and was never asked for another frame.

So the open question is **why CoreAnimation stops after its first frame**, not
"how does the panel get a picture". It is above the kernel; spending time on
the GPU/Metal chain will not move it.

Things already ruled out:

- `/var/db/.AppleSetupDone` is absent, but the Setup skip *is* applied —
  `/var/mobile/Library/Preferences/com.apple.purplebuddy.plist` has
  `SetupDone=True SetupFinishedAllSteps=True SetupVersion=11` (that is the file
  `tools/sweet-root-tweaks.py` writes). So it is not a stuck Setup Assistant.
- `progressd`, `setupd`, `mobileactivationd`, `datamigrator` are not running.
- No `SWEET Sandbox: <proc> privilege N denied` lines, so the
  `work_interval_create(CA_CLIENT)` denial patch 0064 guards against is not
  firing.

## What "very dim content" on screen is

Not a dim UI. `sweetfb_noconsole` was **absent** from the r-k6 cmdline, so the
kernel keeps drawing console text over the GUI. Patch 0067's
`sweetfb_noconsole=1` mutes it safely (it does not do the
`PE_initialize_console` switch that panics).

Measured with the panel buffer readable at `/dev/pmem 0xa0000000`:

| Address | Content |
|---|---|
| `0xa0000000` (ABL splash / panel buffer) | 2 distinct byte values, luma 240 — a flat near-white field |
| `0xa1400000`, `0xc4000000` (scanout slots 0/1) | byte-identical to each other, 251 distinct values, 25 % non-zero |

The slots holding identical content is worth a look: the MDP is meant to read
CA's surface there, and a copy of ABL's buffer would explain why the presented
frame is indistinguishable from the console overlay.

## Boot args: the regression to check

Upstream's last *known-good GPU-off display* is documented in
`docs/redfin/port-plan.md` ("Touch works, 2026-10-24"): `sweetgpu=0` and **no
`sweetscanout`**. It reached the GUI, and that same doc records `r3` **hanging**
after SpringBoard/backboardd start when the display args changed.

We booted `sweetscanout=2` (patch 1046's auto-on-at-first-slot-swap default),
which is *newer* than that known-good config. Direct scanout makes `present()`
return early, so the CPU copy never runs — if the MDP's scaler/address setup is
wrong for this surface, the result is exactly what is on screen: an old buffer
plus console text, with `swap done 0`.

Untested as of this writing: `sweetscanout=0 sweetfb_noconsole=1`, which is
`out/r-k7.img`. That is the closest match to the documented working config.

## Images

| Image | Kernel | Args | Purpose |
|---|---|---|---|
| `out/r-k6.img` | 1048 | `sweetscanout=2`, console **on** | the boot all measurements above came from |
| `out/r-k7.img` | 1048 | `sweetscanout=0 sweetfb_noconsole=1` | console muted, CPU present path — not yet booted |

Both are RAM-only `fastboot boot` images. Cmdline in `work/boot/r-k6.cmdline`
and `work/boot/r-k7.cmdline`.

## Firmware

`fw-redfin/` (gitignored) now holds the Adreno 620 firmware extracted from the
Pixel 5 `UP1A.231105.001.B2` factory image by `tools/redfin-gpufw.sh`:

```
a650_gmu.bin 41548   a650_sqe.fw 31632   a620_zap.mdt 6860   a620_zap.b02 1676
```

Verified: the GMU's `PREALLOC_REQ` blocks are `0x4000+0x8000`,
`0x144000+0x13000`, `0x157000+0x9000` — exactly what patch 0904 documents — and
`a620_zap.mdt` has one PT_LOAD of 0x68c at paddr 0x5000, matching
`a620_zap.b02`. `tools/redfin-boot.sh` now defaults `GPUFW=fw-redfin` and
refuses to build a `GPU=1` image when a file is missing (it previously pointed
at a dead WSL path, so every GPU boot silently shipped without firmware).

## Live-debugging setup

```sh
sudo ifconfig en15 inet 192.168.7.1/24     # after every boot: en15 re-enumerates

python3 tools/flame-cmd.py 'p disp' --wait 5 --all        # display state
python3 tools/flame-cmd.py 'p swapdone' --wait 5          # frames presented
python3 tools/flame-cmd.py 'p scanout 0|1' --wait 5       # direct scanout on/off
python3 tools/flame-cmd.py 'p fc' --wait 5                # panel Hz + tear registers
python3 tools/flame-cmd.py 'p prof start NAME 100 2 24 100'   # sample a process
python3 tools/flame-files.py read /dev/pmem 0xa0000000 4096 /tmp/x.bin

python3 tools/flame-cmd.py reboot                          # PSCI reset to fastboot
```

`--all` matters: without it only `POKE:`/`SWEET CMD:` result lines are shown and
the answer (which is a `SWEET FB:` line) is filtered out. A silent reply is a
symptom too — print on the first send after a failed one (this is what hid
patch 147's answer).

## Next

1. Boot `out/r-k7.img`. Does a real UI appear with the console muted and
   scanout pinned off? That separates "kernel can present" from "CA stopped".
2. If yes, the regression is 1046's auto scanout (`sweetscanout=2`) and the
   fix is in that auto-on path, not the GPU.
3. If no, CoreAnimation stopped after one frame. Look at what asks it for the
   next frame: the vsync notification path (IOMFB notify type 5), and whether
   backboardd's display thread ever wakes. `p prof start backboardd 100 2 24 100`
   with `--all` shows whether it gets off-CPU samples only.
4. Do **not** start with the GPU/Metal chain. `SweetMetal2.bundle` builds
   (`builds-metal2`, source `72e9730` = rk5a's r70) and the firmware is ready,
   but no measurement above points at it.
