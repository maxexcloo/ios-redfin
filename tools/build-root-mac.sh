#!/bin/bash
# Build the iOS 16.7.16 (iPhone X, 20H392) root volume for the Pixel 5 port, on macOS.
# Self-contained: mounts the three IPSW images, makes the HFS+ volume, copies,
# tweaks, fsck's, and leaves a raw image at work/rootimg/iosroot.img.
#
#   sudo bash tools/build-root-mac.sh [SIZE]      SIZE default 32g
#
# Needs root: the volume carries files owned by root, _logd (272) and mobile (501),
# and an HFS+ volume made as your user cannot hold those owners. One prompt, no
# re-prompting: everything below runs in this one root process.
#
# Writes only inside this repo. Detaches every image it mounts, including on failure.
# Everything is also logged to work/rootimg/build.log.
set -euo pipefail
cd "$(dirname "$0")/.."

OS=research/ipsw-x/dmg/087-86698-044.dmg      # root filesystem (compressed UDIF)
SYSOS=research/ipsw-x/dmg/087-86593-047.dmg   # SystemOS cryptex (raw APFS)
APPOS=research/ipsw-x/dmg/087-86715-047.dmg   # AppOS cryptex (raw APFS)
SIZE=${1:-32g}
OUT=work/rootimg/iosroot.img

mkdir -p work/rootimg
exec > >(tee work/rootimg/build.log) 2>&1

say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $(id -u) == 0 ]] || die "run with sudo"
for f in "$OS" "$SYSOS" "$APPOS"; do
	[[ -f $f ]] || die "missing $f"
done
[[ -f tools/sweet-root-tweaks.py ]] || die "missing tools/sweet-root-tweaks.py"

# A previous failed run leaves these behind; they are never valid input.
rm -f "$OUT" "$OUT.dmg"
mkdir -p work/rootimg

say "host"
sw_vers | sed 's/^/  /'
echo "  free space: $(df -h . | awk 'NR==2{print $4}')"
echo "  volume size requested: $SIZE"

# The source set expands to roughly 13-14 GiB; anything under 20g cannot hold it.
case $SIZE in
	*[gG]) ;;
	*) die "SIZE must end in g, e.g. 32g" ;;
esac
GIB=${SIZE%[gG]}
[[ $GIB =~ ^[0-9]+$ ]] || die "SIZE must be a number followed by g, e.g. 32g"
(( GIB >= 20 )) || die "SIZE $SIZE is too small: the iOS root needs about 14 GiB. Use 32g."

WORK=$(mktemp -d "${TMPDIR:-/tmp}/mkiosroot.XXXXXX")
echo "  work dir: $WORK"

# bash 3.2 on macOS: expanding an empty array under `set -u` is an error,
# so every expansion of MOUNTS uses the ${arr[@]+"${arr[@]}"} idiom.
MOUNTS=()
cleanup() {
	rc=$?
	for m in ${MOUNTS[@]+"${MOUNTS[@]}"}; do
		hdiutil detach -force -quiet "$m" 2>/dev/null || true
	done
	if (( rc != 0 )); then
		printf '\n\033[31mstopped with status %d\033[0m\n' "$rc" >&2
		echo "  mounts detached; source work dir left at $WORK" >&2
		echo "  partial image (if any): $(ls -lh "$OUT" "$OUT.dmg" 2>/dev/null | tr '\n' ' ')" >&2
	fi
	exit $rc
}
trap cleanup EXIT INT TERM

attach() {	# IMAGE NAME [hdiutil opts...]
	mkdir -p "$WORK/$2"
	hdiutil attach -nobrowse -owners on -mountpoint "$WORK/$2" "${@:3}" "$1" >/dev/null ||
		die "could not attach $1"
	MOUNTS=("$WORK/$2" ${MOUNTS[@]+"${MOUNTS[@]}"})
}

say "attach IPSW images (read-only)"
attach "$OS"    os    -readonly
attach "$SYSOS" sysos -readonly -imagekey diskimage-class=CRawDiskImage
attach "$APPOS" appos -readonly -imagekey diskimage-class=CRawDiskImage

say "create $SIZE case-sensitive journaled HFS+ volume"
hdiutil create -quiet -size "$SIZE" -type UDIF -layout NONE \
	-fs "Case-sensitive Journaled HFS+" -volname iOSRoot "$OUT.dmg" ||
	die "hdiutil create failed"
attach "$OUT.dmg" root
R=$WORK/root
mdutil -i off "$R" >/dev/null 2>&1 || true
df -h "$R" | sed 's/^/  /'

copy() {
	printf '  copying %-10s ' "$(basename "$1")"
	ditto --norsrc --noextattr --noqtn --noacl --nopreserveHFSCompression "$1" "$2" ||
		die "ditto failed copying $1"
	df -h "$2" | awk 'NR==2{printf "-> done, %s used, %s free\n", $3, $4}'
}
say "copy the OS and both cryptexes"
mkdir -p "$R"
copy "$WORK/os"    "$R"
copy "$WORK/sysos" "$R/private/preboot/Cryptexes/OS"
copy "$WORK/appos" "$R/private/preboot/Cryptexes/App"
rm -rf "$R"/private/preboot/Cryptexes/*/.fseventsd

say "link the shared cache and cryptex files into place"
DSC=$R/private/preboot/Cryptexes/OS/System/Library/Caches/com.apple.dyld
mkdir -p "$R/System/Library/Caches/com.apple.dyld"
n=0
for f in "$DSC"/*; do ln -f "$f" "$R/System/Library/Caches/com.apple.dyld/${f##*/}" && n=$((n+1)); done
echo "  shared cache: $n files linked"
for c in OS App; do
	cnt=0
	(cd "$R/private/preboot/Cryptexes/$c" &&
	 find . ! -type d ! -path './System/Library/Caches/com.apple.dyld/*') |
	while IFS= read -r f; do
		f=${f#./}
		if [[ ! -e $R/$f && ! -L $R/$f ]]; then
			mkdir -p "$R/$(dirname "$f")"
			src=$R/private/preboot/Cryptexes/$c/$f
			ln -f "$src" "$R/$f" 2>/dev/null || cp -p "$src" "$R/$f"
		fi
	done
	echo "  cryptex $c: linked"
done

say "logd stores and the plain system keybag"
DB=$R/private/var/db
install -d -o 272 -g 272 -m 0751 "$DB/diagnostics"
install -d -o 272 -g 272 -m 0755 "$DB/uuidtext" "$DB/diagnostics/timesync"
for d in diagnostics uuidtext diagnostics/timesync; do
	install -o 272 -g 272 -m 0644 /dev/null "$DB/$d/.migrated"
done
install -d -m 0700 -o 0 -g 0 "$R/private/var/keybags"
printf '%s\n' '<?xml version="1.0" encoding="UTF-8"?>' \
	'<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">' \
	'<plist version="1.0"><dict><key>KeyBagKeys</key><data>U1dFRVQ=</data></dict></plist>' \
	>"$R/private/var/keybags/systembag.kb"
chown 0:0 "$R/private/var/keybags/systembag.kb"
chmod 0600 "$R/private/var/keybags/systembag.kb"
echo "  keybag written"

say "bring-up tweaks (Setup skip, activation, daemons)"
python3 -I tools/sweet-root-tweaks.py "$R" || die "sweet-root-tweaks.py failed"

say "prune daemons that crash-loop without hardware"
# fairplayd (relaunch loop + locationd deadlock) and vmd (CommCenter retry loop):
# both from bce31d1^:docs/redfin/disabled-services.md. Backups land beside each
# file as *.before-prune, so tools/prune-root.py --revert undoes it.
python3 -I tools/prune-root.py "$R" || die "prune-root.py failed"

rm -rf "$R/.fseventsd" "$R/.Spotlight-V100" "$R/.Trashes"
df -h "$R" | sed 's/^/  /'

say "detach and verify"
hdiutil detach -quiet "$R"
MOUNTS=("${MOUNTS[@]:1}")

DEV=$(hdiutil attach -nobrowse -nomount "$OUT.dmg" | awk 'NR==1{print $1}')
[[ -n $DEV ]] || die "could not attach $OUT.dmg for fsck"
fsck_hfs -fn "$DEV" | sed 's/^/  /' || echo "  (fsck reported issues; see above)"
hdiutil detach -quiet "$DEV"

# hdiutil's UDIF with layout NONE is plain raw: the file is the volume itself.
mv "$OUT.dmg" "$OUT"
SIG=$(xxd -s 1024 -l 2 -p "$OUT")
case $SIG in
	4858) echo "  HFS+ signature: HX (case-sensitive) OK" ;;
	482b) echo "  HFS+ signature: H+ (case-INsensitive - wrong for iOS)" ;;
	*)    die "no HFS+ signature at offset 1024 (got '$SIG')" ;;
esac
chown "${SUDO_UID:-0}:${SUDO_GID:-0}" "$OUT"

say "done"
ls -lh "$OUT" | sed 's/^/  /'
echo "  apparent size: $(stat -f %z "$OUT") bytes"
shasum -a 256 "$OUT" | sed 's/^/  sha256 /'
echo
echo "  Full log: work/rootimg/build.log"
echo "  Nothing was flashed. No device was touched."
