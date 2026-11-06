#!/bin/bash
# Write the iOS root image to the Pixel 5's userdata partition, over adb from TWRP.
#
#   bash tools/redfin-install-root.sh [IMG]           write, then verify every GiB
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
SUMS=work/rootimg/iosroot.gib.sha256
MODE=${1:-write}

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }
sh_() { adb shell "$@" </dev/null | tr -d '\r'; }

[[ -f $IMG ]] || die "no image at $IMG"
[[ $MODE == write || $MODE == verify ]] || die "usage: $0 [verify] [IMG]"

say "phone"
[[ $(adb get-state 2>/dev/null | tr -d '\r') == recovery ]] ||
	die "phone is not in TWRP/recovery (adb get-state != recovery)"
[[ $(sh_ getprop ro.product.device) == redfin ]] || die "not a redfin: $(sh_ getprop ro.product.device)"
[[ $(sh_ id) == *uid=0* ]] || die "adb is not root in recovery"

TARGET=$(sh_ readlink -f /dev/block/by-name/userdata)
[[ $TARGET == "$PART" ]] || die "userdata is $TARGET, expected $PART - refusing to write"
PSIZE=$(sh_ blockdev --getsize64 "$PART")
ISIZE=$(stat -f %z "$IMG")
(( PSIZE >= ISIZE )) || die "partition ($PSIZE) is smaller than the image ($ISIZE)"
printf '  device    %s\n  userdata  %s (%s bytes)\n  image     %s bytes (%s GiB)\n  remainder %s bytes left untouched\n' \
	"$(sh_ getprop ro.product.device)" "$PART" "$PSIZE" "$ISIZE" $((ISIZE >> 30)) $((PSIZE - ISIZE))

verify() {
	say "verify: SHA-256 of each GiB on the phone vs the image"
	[[ -f $SUMS ]] || die "no $SUMS (rebuild its hashes with tools/root-hashes.sh)"
	local bad=0 i want got
	while read -r i want <&3; do
		got=$(sh_ "dd if=$PART bs=4194304 skip=$((i * 256)) count=256 2>/dev/null | sha256sum" | cut -d' ' -f1)
		if [[ $got == "$want" ]]; then
			printf '  GiB %-3s ok\n' "$i"
		else
			printf '  GiB %-3s MISMATCH\n' "$i"; bad=1
		fi
	done 3< "$SUMS"
	(( bad == 0 )) || die "verify failed"
	echo "  all $(wc -l < "$SUMS" | tr -d ' ') GiB match"
}

if [[ $MODE == verify ]]; then verify; exit 0; fi

echo
echo "This overwrites the first $((ISIZE >> 30)) GiB of $PART - Android's apps, photos and settings."
die_marker=1

say "unmount anything holding /data"
sh_ 'umount /data 2>/dev/null; umount /sdcard 2>/dev/null; true'
sh_ 'grep " /data " /proc/mounts || echo "  /data not mounted"'

say "write $((ISIZE >> 20)) MiB over adb (5-15 min, do not unplug)"
adb exec-in "dd of=$PART bs=4194304 conv=notrunc" < "$IMG" 2>&1 | tail -2
sh_ sync
sleep 2

verify
say "done"
echo "  Reboot to fastboot: adb reboot bootloader"
echo "  Then: fastboot boot out/r-k1.img"
