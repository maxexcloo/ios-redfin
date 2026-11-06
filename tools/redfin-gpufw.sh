#!/bin/bash
# Extract the Adreno 620 GPU firmware from a Pixel 5 factory image into fw-redfin/.
#
#   tools/redfin-gpufw.sh FACTORY.zip [OUT]
#
# FACTORY.zip is redfin's UP1A.231105.001.B2 (or any Android 11+ redfin factory zip) from
# https://developers.google.com/android/images#redfin . The four files are what xnu's
# bsd/dev/sweet_gpu.c asks a6_firmware() for; tools/mkpayload.py --gpufw DIR copies them into
# the ADT's /chosen/gpufw,* (see GPU_FW there). On redfin they sit in the vendor partition's
# /firmware. Nothing here touches a phone.
#
#   fw-redfin/a650_gmu.bin    GMU image (its PREALLOC_REQ blocks size the GMU's memory)
#   fw-redfin/a650_sqe.fw     SQE microcode
#   fw-redfin/a620_zap.mdt    boot authentication shader descriptor (names b02)
#   fw-redfin/a620_zap.b02    its one loadable segment: at pil_gpu_region's start
#
# 7zz reads the zips' members and the ext4 vendor.img in place (no 11 GiB unpack). The files are
# Google's and Qualcomm's: fw-redfin/ is git-ignored and never committed.
set -e -o pipefail
FACTORY_ARG=${1:?usage: tools/redfin-gpufw.sh FACTORY.zip [OUT]}
OUT_ARG=${2:-fw-redfin}
cd "$(dirname "$0")/.."
# Resolve against the caller's directory: this script cds to the repo root below.
case $FACTORY_ARG in /*) FACTORY=$FACTORY_ARG;; *) FACTORY=$OLDPWD/$FACTORY_ARG;; esac
case $OUT_ARG in /*) OUT=$OUT_ARG;; *) OUT=$OLDPWD/$OUT_ARG;; esac
FW='a650_gmu.bin a650_sqe.fw a620_zap.mdt a620_zap.b02'
command -v 7zz >/dev/null || { echo "7zz is missing: brew install sevenzip" >&2; exit 1; }
[ -f "$FACTORY" ] || { echo "no such file: $FACTORY" >&2; exit 1; }
mkdir -p "$OUT"

# 1. The outer factory zip holds image-redfin-*.zip; that holds vendor.img. 7zz extracts just
#    that one member, and the vendor.img inside it, so nothing else is written.
INNER=$(7zz l -ba "$FACTORY" | awk '$NF ~ /^image-.*\.zip$/ {print $NF; exit}')
[ -n "$INNER" ] || { echo "$FACTORY: no image-*.zip inside (is this the factory zip?)" >&2; exit 1; }
echo "factory image: $INNER"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/redfin-gpufw.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

7zz x -y -o"$WORK" "$FACTORY" "$INNER" >/dev/null
7zz x -y -o"$WORK" "$WORK/$INNER" vendor.img >/dev/null 2>&1 ||
	{ echo "$INNER: no vendor.img inside" >&2; exit 1; }
VENDOR=$WORK/vendor.img
[ -s "$VENDOR" ] || { echo "vendor.img is empty" >&2; exit 1; }
echo "vendor.img: $(du -h "$VENDOR" | cut -f1)"

# 2. Read the four files straight out of the ext4 (or sparse ext4) image. Try the paths the
#    partition has used across Android versions, then anywhere on it.
miss=0
for name in $FW; do
	found=
	rm -rf "$WORK/x"
	for dir in firmware etc/firmware; do
		# 7zz recreates the member's directories under the output dir, so extract into a
		# scratch tree and flatten the file into $OUT.
		if 7zz x -y -o"$WORK/x" "$VENDOR" "$dir/$name" >/dev/null 2>&1 && [ -s "$WORK/x/$dir/$name" ]; then
			mv -f "$WORK/x/$dir/$name" "$OUT/$name"; found=$dir; break
		fi
	done
	if [ -z "$found" ]; then
		# last resort: the member's full path, wherever 7zz lists it
		p=$(7zz l -ba "$VENDOR" 2>/dev/null | awk -v n="$name" '$NF ~ ("/" n "$") {print $NF; exit}' || true)
		if [ -n "$p" ] && 7zz x -y -o"$WORK/x" "$VENDOR" "$p" >/dev/null 2>&1 && [ -s "$WORK/x/$p" ]; then
			mv -f "$WORK/x/$p" "$OUT/$name"; found=$p
		fi
	fi
	if [ -n "$found" ]; then
		printf '%-16s %8s bytes  (%s)\n' "$name" "$(stat -f %z "$OUT/$name")" "$found"
	else
		echo "missing: $name" >&2; miss=$((miss + 1))
	fi
done
[ "$miss" = 0 ] || {
	# An empty listing means 7zz could not read the filesystem at all (not ext4, or sparse).
	if [ -z "$(7zz l -ba "$VENDOR" 2>/dev/null | head -1)" ]; then
		echo "$VENDOR: 7zz cannot read this filesystem image" >&2
	fi
	echo "$miss firmware file(s) not found in vendor.img" >&2; exit 1
}

# 3. a620_zap.mdt is a flash descriptor that must name b02: it is the only loadable segment, and
#    sweet_gpu.c puts it at pil_gpu_region's start. A mismatched pair fails the zap silently.
if ! LC_ALL=C grep -qa b02 "$OUT/a620_zap.mdt"; then
	echo "warning: a620_zap.mdt does not name b02, but the kernel loads mdt + b02" >&2
fi

echo
echo "$(ls "$OUT"/a650_* "$OUT"/a620_* | wc -l | tr -d ' ') files in ${OUT}/"
echo "next: python3 -I tools/mkpayload.py KERNEL ADT PAYLOAD --gpufw $(cd "$OUT" && pwd)"
