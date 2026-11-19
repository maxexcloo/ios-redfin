#!/bin/bash
# Write the iOS root image to the Pixel 5's userdata partition, over adb from TWRP.
#
#   bash tools/redfin-install-root.sh [write] [IMG]   write, then verify every GiB
#   bash tools/redfin-install-root.sh verify [IMG]    only compare
#
# THIS ERASES ANDROID'S USER DATA (apps, photos, settings). Android's system,
# boot and vendor partitions are not touched, and neither is anything past the
# end of the image (the port keeps its kernel log in the last ~17 MiB of
# userdata, so leaving that alone matters).
#
# Only writes if the phone identifies as redfin, the resolved userdata device
# matches the expected one, and the partition is big enough.
set -euo pipefail
cd "$(dirname "$0")/.."

IMG=${2:-${IMG:-work/rootimg/iosroot.img}}
PART=/dev/block/sda19          # verified in TWRP 2026-11-06 via /dev/block/by-name/userdata
MODE=${1:-write}
BLOCK_SIZE=$((1 << 22))
CHUNK_SIZE=$((1 << 30))

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }
device_adb() { adb -s "$SERIAL" "$@"; }
sh_() { device_adb shell "$@" </dev/null | tr -d '\r'; }

[[ -f $IMG ]] || die "no image at $IMG"
[[ $MODE == write || $MODE == verify ]] || die "usage: $0 [write|verify] [IMG]"

say "phone"
SERIAL=$(adb get-serialno 2>/dev/null | tr -d '\r') || die "select a single adb device"
[[ -n $SERIAL && $SERIAL != unknown ]] || die "select a single adb device"
[[ $(device_adb get-state 2>/dev/null | tr -d '\r') == recovery ]] ||
	die "phone is not in TWRP/recovery (adb get-state != recovery)"
[[ $(sh_ getprop ro.product.device) == redfin ]] || die "not a redfin: $(sh_ getprop ro.product.device)"
[[ $(sh_ id) == *uid=0* ]] || die "adb is not root in recovery"

TARGET=$(sh_ readlink -f /dev/block/by-name/userdata)
[[ $TARGET == "$PART" ]] || die "userdata is $TARGET, expected $PART - refusing to write"
PSIZE=$(sh_ blockdev --getsize64 "$PART")
ISIZE=$(python3 -c 'import os, sys; print(os.path.getsize(sys.argv[1]))' "$IMG")
(( PSIZE >= ISIZE )) || die "partition ($PSIZE) is smaller than the image ($ISIZE)"
printf '  device    %s\n  userdata  %s (%s bytes)\n  image     %s bytes (%s GiB)\n  remainder %s bytes left untouched\n' \
	"$(sh_ getprop ro.product.device)" "$PART" "$PSIZE" "$ISIZE" $((ISIZE / CHUNK_SIZE)) $((PSIZE - ISIZE))

say "hash the selected image"
HASHES=$(python3 - "$IMG" "$BLOCK_SIZE" "$CHUNK_SIZE" <<'PY'
import hashlib
import sys

block, chunk = map(int, sys.argv[2:])
with open(sys.argv[1], "rb") as image:
    index = 0
    while data := image.read(block):
        digest = hashlib.sha256(data)
        size = len(data)
        while size < chunk and (data := image.read(block)):
            digest.update(data)
            size += len(data)
        print(index, size, digest.hexdigest())
        index += 1
PY
)
[[ -n $HASHES ]] || die "empty image"

verify() {
	say "verify: SHA-256 of each GiB on the phone vs the image"
	local bad=0 i size want got skip count
	while read -r i size want; do
		skip=$((i * CHUNK_SIZE / BLOCK_SIZE))
		count=$(((size + BLOCK_SIZE - 1) / BLOCK_SIZE))
		got=$(sh_ "dd if=$PART bs=$BLOCK_SIZE skip=$skip count=$count 2>/dev/null | head -c $size | sha256sum" | cut -d' ' -f1)
		if [[ $got == "$want" ]]; then
			printf '  GiB %-3s ok\n' "$i"
		else
			printf '  GiB %-3s MISMATCH\n' "$i"; bad=1
		fi
	done <<< "$HASHES"
	(( bad == 0 )) || die "verify failed"
	echo "  all $(wc -l <<< "$HASHES" | tr -d ' ') chunks match"
}

if [[ $MODE == verify ]]; then verify; exit 0; fi

echo
echo "This overwrites the first $ISIZE bytes of $PART - Android's apps, photos and settings."

say "unmount anything holding /data"
sh_ 'umount /data 2>/dev/null; umount /sdcard 2>/dev/null; true'
sh_ 'grep " /data " /proc/mounts || echo "  /data not mounted"'

say "write $((ISIZE >> 20)) MiB over adb (5-15 min, do not unplug)"
device_adb exec-in "dd of=$PART bs=$BLOCK_SIZE conv=notrunc" < "$IMG" 2>&1 | tail -2
sh_ sync
sleep 2

verify
say "done"
printf '  Reboot to fastboot: adb -s %q reboot bootloader\n' "$SERIAL"
echo "  Then follow Device Workflow in README.md."
