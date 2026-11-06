#!/bin/bash
# Verify the phone's copy of the root image in small batches, restarting TWRP
# when it dies (it does, on long reads on this device). Prints one line per GiB.
#
#   bash tools/redfin-verify-batches.sh [FROM] [TO]
set -uo pipefail
cd "$(dirname "$0")/.."
IMG=work/rootimg/iosroot.img
PART=/dev/block/sda19
SUMS=work/rootimg/iosroot.gib.sha256
FROM=${1:-0}; TO=${2:-31}

ensure_twrp() {
	for _ in $(seq 20); do
		if [[ $(adb get-state 2>/dev/null | tr -d '\r') == recovery ]]; then return 0; fi
		if fastboot devices 2>/dev/null | grep -q fastboot; then
			echo "  (TWRP gone, rebooting it)"
			fastboot boot recovery/twrp.img >/dev/null 2>&1
		fi
		sleep 8
	done
	return 1
}

bad=0
for i in $(seq "$FROM" "$TO"); do
	ensure_twrp || { echo "  GiB $i  NO DEVICE"; bad=1; continue; }
	want=$(awk -v k="$i" '$1==k{print $2}' "$SUMS")
	got=$(adb shell "dd if=$PART bs=4194304 skip=$((i*256)) count=256 2>/dev/null | sha256sum" </dev/null | tr -d '\r' | cut -d' ' -f1)
	if [[ $got == "$want" ]]; then
		printf '  GiB %-3s ok\n' "$i"
	else
		printf '  GiB %-3s MISMATCH\n' "$i"; bad=1
	fi
done
(( bad == 0 )) && echo "ALL GOOD $FROM-$TO" || echo "ISSUES in $FROM-$TO"
