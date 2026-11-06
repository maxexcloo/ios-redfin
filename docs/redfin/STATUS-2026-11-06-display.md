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

### The timing that reframes it

That single frame was **not** caused by the `p scanout 0` before it.
Reconstructed from both boots:

| Boot | Args | First frame (`p swapdone` > 0) |
|---|---|---|
| `r-k6` | `sweetscanout=2`, console on | **t = 1503 s** (~25 min) |
| `r-k7` | `sweetscanout=0 sweetfb_noconsole=1` | still `0` at t = 582 s |

`SWEET FB: swap 3 ...` landed within a second of the command by coincidence: it
was the first frame iOS had produced after ~25 minutes of booting. So this is
not a dead present path and not a scanout regression — it is an extremely slow
first boot that eventually paints once.

`docs/redfin/port-plan.md` records the same shape: *"`r3` hangs after
SpringBoard/backboardd start (console stays up)"*. ios-sweet documents a **4-5
minute** first boot on an 84-patch tree; ours has 277.

### Two inference errors made here, worth not repeating

1. `SWEET FB: 5s` never appearing looked like a dead vsync timer. It is not:
   `AppleCLCD::statLine()` returns early when `swaps == 0 && shown == 0`, so a
   boot with no frames prints nothing by design.
2. The booted kernel was assumed not to be rk5a because some 5 s reporters were
   silent. The payload *is* rk5a (a prefix of
   `xnu/out-rk5a/kernel.development.sweet`); the reporters were silent for the
   same reason as (1).

Both are the same mistake: treating an absent log line as evidence. On this
port, assert from a positive probe (`p <cmd>` reply, a register read, a
`/dev/pmem` dump) rather than from silence.

So the open question is **why first boot is so slow / where it stalls**, not
"how does the panel get a picture". It is above the kernel; the GPU/Metal chain
will not move it.

### Same-SoC reference: YinCQL/UniXNU-picasso

`https://github.com/YinCQL/UniXNU-picasso` — Redmi K30 5G (picasso, **SM7250**),
default branch `feat/ios16-gpu`, same iPhone X / iOS 16.7.16 (`20H392`) target.
Its status is the closest independent data point for this SoC:

> *"original early userspace runs; service startup is still incomplete... a
> usable SpringBoard display and persistent Data are not established."*

`docs/backboard-watchdog-investigation.md` there reports:

> *"userspace watchdog timeout: no successful checkins from backboardd... 382
> seconds without a successful backboardd checkin. audiomxd and CommCenter also
> have no successful checkins; logd, thermalmonitord, runningboardd and configd
> have recent checkins."*

and `docs/memory-pressure-investigation.md` a VM-page shortage that kills system
services, then UFS read timeouts and SIGBUS exits.

Two consequences for redfin:

- Their healthy set (`logd`, `runningboardd`, `configd`) versus unhealthy
  (`backboardd`, `audiomxd`, `CommCenter`) is a pattern worth testing here. Ours
  differs: `wdt_test=no_user_checkin` disables the supervisor, so the same stall
  would be silent rather than a reboot — which is what we see.
- If their cause is memory pressure, a 32 GiB HFS+ root with the 4 MiB log ring
  at the tail on a RAM-only boot is a plausible contributor. Their Data volume
  runs **in RAM**; ours does not.

Their display path is UEFI/GOP, not our shim + SDE, so the display register work
does not transfer. The userspace diagnosis does.

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

1. Boot `out/r-k7.img` and **let it run past 25 minutes** before concluding
   anything. The only frame ever seen arrived at 25 min on `r-k6`.
2. If a UI appears, the non-blockers are confirmed and the remaining work is
   speed, not bring-up.
3. If not, read `backboard-watchdog-investigation.md` and
   `memory-pressure-investigation.md` in YinCQL/UniXNU-picasso, then check
   whether `logd`, `runningboardd` and `configd` are healthy here while
   `backboardd` is not (`p prof start NAME 100 2 24 100 --all` reveals on- vs
   off-CPU samples, but not stacks — the profiler records thread state only).
4. Do **not** start with the GPU/Metal chain. `SweetMetal2.bundle` builds
   (`builds-metal2`, source `72e9730` = rk5a's r70) and the firmware is in
   `fw-redfin/`, but no measurement above points at it.

## Other ports worth reading (reference, gathered 2026-11-06)

Grouped by relevance to redfin. Most of these target other phones; they are
recorded because the *methods* transfer even when the hardware does not.

**Exact SoC (SM7250 / Adreno 620)**

- <https://github.com/YinCQL/UniXNU-picasso> — Redmi K30 5G, branch
  `feat/ios16-gpu`, same iPhone X / iOS 16.7.16 userland. Userspace stalls at
  service start; documents backboardd watchdog checkins and VM-page shortage.
  **The single most relevant port.** Boots via UEFI/GOP, not our shim.

**Same board family / Adreno 618-620 class**

- <https://github.com/dipa-studio/ios-sweet> — the origin of this tree
  (Redmi Note 10 Pro, SM7150). Reaches the home screen **CPU-only, no GPU
  driver**, first boot 4-5 min. 84 patches versus our 277.
- <https://github.com/edi194/ios-fajita> — OnePlus 6T (SDM845), based on
  ios-sweet, active.
- <https://github.com/seshubonn/ios-karna> — POCO X3 (SM7150-AC, Adreno 618).
- <https://github.com/TigerShota/ios-sweet> — Redmi Note 9 Pro 5G (gauguin),
  reaches SpringBoard UI, touch working, CPU rendering.
- <https://github.com/DC28088/ios-sweet> — Redmi Note 10 Pro; has a
  `codex/native-adreno-metal` branch.
- <https://github.com/turgayasuk-sketch/ios-topaz> — Redmi Note 12, lock screen
  in ~3 min via **direct MDP scanout, no GPU compositor** — the same strategy as
  our patch 0975-0989, worth diffing against ours.

**Other SoCs, useful for method**

- <https://github.com/oosexgang/hackios-xnu-kernel> — HackiOS kernel (APSL 2.0),
  origin of our Apple80211/wifid and `redwood_*` audio patches.
- <https://github.com/oosexgang/hackios-xnu-userland> — MIT, `phone/audio/`.
- <https://github.com/UniXNU/UniXNU> — NativeMetal, NativeAdreno, the Mesa
  patch set; source of `phone/metal2/`.
- <https://github.com/steelbrain/metal2vulkan> — the Vulkan-on-Metal bridge.
- <https://github.com/Ken-u/MaliMetal> — Mali Metal stack that presents frames
  (PanVK + metal2vulkan on RK3588).
- <https://github.com/oosexgang/hakios-mt6768> — MediaTek HakiOS; boot chain in
  `boot_a` with iOS in an `xnusys` partition, touch firmware loaded before XNU.

**Caveats**

- Fork counts are misleading: ios-sweet shows 863 forks, nearly all renamed
  clones with zero changes. The substantive ones are DC28088, TigerShota,
  seshubonn, TigerShota, `limonetexd` (whose README says "99% vibe coded" —
  treat its present/ring claims as unverified) and ios-sapphire.
- `DenialOfGravity/ios-flame` is 404 now; flame history survives in this tree.
- Verify a repo's *actual* branch before trusting its description: several
  repos' default branch is not the one advertised in their README.
