#!/bin/bash
# Pack kernel + ADT + boot-args into a shim boot image and fastboot-boot it
# on the Pixel 5 (redfin). RAM only: nothing is flashed.
#
#   tools/redfin-boot.sh NAME KERNEL [EXTRA BOOT-ARGS...]
#
# Waits for the phone to show up in fastboot (e.g. after flamereboot).
# Image: work/boot/NAME.img; args: work/boot/NAME.cmdline.
#
# Environment (C5: the present/clock experiments are one variable each):
#   PRESET=ui      tested UI: Metal, double buffering, 625 MHz GPU, direct scanout, haptics, brightness, no camera/flash
#   PRESET=camera  the r18g+ line (GPU=2, Metal v2, sec_ts touch, haptics, backlight, torch, cameras, sweetnull)
#   GPU=0|1|2      CPU rendering / kernel GPU present / plus Metal on Turnip (PRESET=camera sets 2)
#   FLIP=1         double-buffered present (0905 sweetfbflip=1)          e.g. r19b: PRESET=camera FLIP=1
#   GPUFREQ=1..4   sweetgpufreq: 275 / 400 / 500 (default 3) / 625 MHz    e.g. r19c: PRESET=camera GPUFREQ=4
#   NOBOOT=1       build work/boot/NAME.img only (no fastboot)
#   GPUFW=DIR      Adreno firmware for GPU>=1 (default fw-redfin/, tools/redfin-gpufw.sh)
# Default: CPU rendering, touch, no camera/flash advertisement, direct scanout off.
# The camera preset requires camera tables and a working capture plug-in on the phone.
# Read the result from the klog: "present: 300 frames in N ms = F/s (single buffer|flip, gpufreq G); ... put off,
# flips, late" (0942) and "5s: ... GPU busy" lines.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ "$#" -lt 2 ]; then
	echo "usage: $0 NAME KERNEL [BOOT-ARGS...]" >&2
	exit 1
fi
name=$1 kernel=$2; shift 2
P=$PWD/work/boot
mkdir -p "$P"
base="debug=0xc serial=3 cpus=8 keepsyms=1 rd=ufsroot0 ufsrw=1 rootrw=1"
base="$base unentitled_ios_sim_launch=1 ignition_level=1 wdt_test=no_user_checkin launchd_unsecure_cache=1"
base="$base wdt=-1 sweetfb_noconsole=1 sweetfb_hz=90 ufslogsecs=2"
base="$base flametouch=0 sweetusb=2 sweetgpu=0 sweetgpufreq=3 sweetmtl=0"
base="$base sweetbattery=1 sectouch=1 sweetfbx=0x107 sectouchx=0xd sweetscanout=0"
base="$base sweetcam=0 sweetcamdev=0 sweettorch=0"
# redfin: touch is Samsung sec_ts on SPI SE0 (sectouch=1), so sweettouch/flametouch stay 0.
# GPU (A620, xnu 0904/0905): sweetgpu=0 sweetmtl=0 = CPU rendering. GPU=1 below = kernel GPU + the GPU
# present (CA still renders on the CPU); GPU=2 = plus Metal on Turnip (sweetmtl=2, needs the metal2 install);
# FLIP=1 adds the double-buffered present (sweetfbflip=1). sweetgpufreq: 1 275, 2 400, 3 500, 4 625 MHz.
if [ "${PRESET:-}" = camera ]; then
	GPU=${GPU:-2}
	base=$(printf '%s\n' $base | grep -v -e '^sweetcam=' -e '^sweetcamdev=' -e '^sweettorch=' | tr '\n' ' ')
	base="$base sweethaptic=2 sweetbl=1 sweetnull=backboardd"
	base="$base sweettorch=2 sweetcam=2 sweetcamdev=1"
	adt_args=(--highmem --camera --flash --backlight)
elif [ "${PRESET:-}" = ui ]; then
	GPU=${GPU:-2}
	FLIP=${FLIP:-1}
	GPUFREQ=${GPUFREQ:-4}
	base=$(printf '%s\n' $base | grep -v -e '^sweetscanout=' | tr '\n' ' ')
	base="$base sweetscanout=2 sweethaptic=1 sweetui=1 sweetbl=2"
	adt_args=(--highmem --backlight)
elif [ -n "${PRESET:-}" ]; then
	echo "unknown PRESET=$PRESET (ui, camera)" >&2
	exit 1
else
	adt_args=(--highmem)
fi
python3 -I tools/mkadt.py "$P/$name.adt" "${adt_args[@]}"
GPU=${GPU:-0}
if [ "$GPU" -ge 1 ]; then
	base=$(printf '%s\n' $base | grep -v -e '^sweetgpu=' -e '^sweetfb_thread=' -e '^sweetddr=' | tr '\n' ' ')
	base="$base sweetgpu=1 sweetfb_thread=1 sweetddr=1"
	[ "${FLIP:-0}" = 1 ] && base="$base sweetfbflip=1"
	# The GPU is useless without its firmware: check before building, not on the phone.
	GPUFW=${GPUFW:-fw-redfin}
	missing=
	for f in a650_gmu.bin a650_sqe.fw a620_zap.mdt a620_zap.b02; do
		[ -s "$GPUFW/$f" ] || missing="$missing $f"
	done
	[ -z "$missing" ] || {
		echo "GPU=$GPU needs Adreno firmware in $GPUFW/:$missing" >&2
		echo "  tools/redfin-gpufw.sh FACTORY.zip   (see the header there)" >&2
		exit 1
	}
fi
if [ "$GPU" -ge 2 ]; then
	base=$(printf '%s\n' $base | grep -v -e '^sweetmtl=' | tr '\n' ' ')
	base="$base sweetmtl=2"
fi
if [ -n "${GPUFREQ:-}" ]; then
	base=$(printf '%s\n' $base | grep -v -e '^sweetgpufreq=' | tr '\n' ' ')
	base="$base sweetgpufreq=$GPUFREQ"
fi
# Real time: PM8150 RTC + offset (tools/flame-rtc.py LOG calibrates it once).
[ -f work/rtc-offset ] && base="$base sweetrtcoff=$(cat work/rtc-offset)"
# Extra args replace defaults with the same key (XNU would take the first).
for a in "$@"; do
	k=${a%%=*}
	base=$(printf '%s\n' $base | grep -v -x -e "$k" -e "$k=.*" | tr '\n' ' ')
done
cmdline="$base $*"
echo "$cmdline" > "$P/$name.cmdline"
if [ "$GPU" -ge 1 ]; then
	python3 -I tools/mkpayload.py "$kernel" "$P/$name.adt" "$P/$name.payload" --cmdline "$cmdline" --gpufw "$GPUFW" >/dev/null
else
	python3 -I tools/mkpayload.py "$kernel" "$P/$name.adt" "$P/$name.payload" --cmdline "$cmdline" >/dev/null
fi
shim/build.sh "$P/$name.payload" "$P/$name.img" >/dev/null
if [ "${NOBOOT:-0}" = 1 ]; then
	echo "$(date +%T) built $P/$name.img: $cmdline"
	exit 0
fi
echo "$(date +%T) built $name.img; waiting for fastboot"
until [ -n "$(fastboot devices)" ]; do sleep 2; done
devices=$(fastboot devices)
[ "$(printf '%s\n' "$devices" | wc -l | tr -d ' ')" = 1 ] || {
	echo "More than one fastboot device connected; refusing to select another port's phone." >&2
	exit 1
}
device=$(printf '%s\n' "$devices" | awk '{print $1}')
product=$(fastboot -s "$device" getvar product 2>&1 | awk '$1 == "product:" {print $2}')
[ "$product" = redfin ] || {
	echo "Connected fastboot device is not redfin; refusing to boot." >&2
	exit 1
}
fastboot -s "$device" boot "$P/$name.img"
echo "$(date +%T) booted $name: $cmdline"
