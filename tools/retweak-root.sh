#!/bin/bash
# Re-apply the bring-up tweaks + daemon pruning to an ALREADY BUILT root image,
# without redoing the 20-minute copy from the IPSW.
#
#   sudo bash tools/retweak-root.sh work/rootimg/iosroot.img
#
# Mounts the image read-write, reruns tools/redfin-root-tweaks.py and
# tools/prune-root.py, fsck's it, detaches. Both scripts are idempotent and both
# leave backups (*.before-prune) so prune-root.py --revert undoes it later.
set -euo pipefail
cd "$(dirname "$0")/.."

IMG=${1:-work/rootimg/iosroot.img}
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
die() { printf '\n\033[31mFAILED: %s\033[0m\n' "$*" >&2; exit 1; }

[[ $(id -u) == 0 ]] || die "run with sudo"
[[ -f $IMG ]] || die "no image at $IMG"
mkdir -p work/rootimg
exec > >(tee -a work/rootimg/retweak.log) 2>&1

MNT=$(mktemp -d "${TMPDIR:-/tmp}/retweak.XXXXXX")
MOUNTS=()
cleanup() {
	rc=$?
	for m in ${MOUNTS[@]+"${MOUNTS[@]}"}; do
		hdiutil detach -force -quiet "$m" 2>/dev/null || true
	done
	(( rc != 0 )) && echo "  mount point kept: $MNT" >&2
	exit $rc
}
trap cleanup EXIT INT TERM

say "attach $IMG (read-write)"
hdiutil attach -nobrowse -owners on -mountpoint "$MNT" "$IMG" >/dev/null ||
	die "could not attach $IMG (is it already mounted?)"
MOUNTS=("$MNT")
df -h "$MNT" | sed 's/^/  /'

say "bring-up tweaks (idempotent)"
python3 -I tools/redfin-root-tweaks.py "$MNT" || die "redfin-root-tweaks.py failed"

say "prune daemons that crash-loop without hardware"
python3 -I tools/prune-root.py "$MNT" || die "prune-root.py failed"

say "detach and verify"
hdiutil detach -quiet "$MNT"
MOUNTS=()
DEV=$(hdiutil attach -nobrowse -nomount "$IMG" | awk 'NR==1{print $1}')
[[ -n $DEV ]] || die "could not attach for fsck"
fsck_hfs -fn "$DEV" | sed 's/^/  /' || echo "  (fsck reported issues; see above)"
hdiutil detach -quiet "$DEV"

say "done"
shasum -a 256 "$IMG" | sed 's/^/  sha256 /'
echo "  log: work/rootimg/retweak.log"
