#!/usr/bin/env bash
# Provision a dedicated systemd benchmark guest, then verify after a cold boot.
set -euo pipefail
[[ $# == 1 ]] || { echo "Usage: $0 VM" >&2; exit 2; }
vm=$1
helper=$(dirname "$0")/vm.sh
memory=$(limactl list --json "$vm" | python3 -c 'import json,sys; print(json.load(sys.stdin)["memory"])')
small=no
if (( memory <= 512 * 1024 * 1024 )); then small=yes; fi
"$helper" exec "$vm" sudo bash -s -- "$small" <<'GUEST'
set -euo pipefail
small=$1
case "$(findmnt -n -o FSTYPE -T /var/tmp)" in
    ext4|ext3|ext2|xfs|btrfs|f2fs|zfs) ;;
    *) echo '/var/tmp must be disk-backed' >&2; exit 1 ;;
esac
if [[ "$small" == yes ]]; then
    install -d -m 1777 /var/tmp/benchmark-tmp
    cat > /etc/systemd/system/tmp.mount <<'UNIT'
[Unit]
Description=Disk-backed benchmark temporary directory
RequiresMountsFor=/var/tmp/benchmark-tmp
Before=local-fs.target

[Mount]
What=/var/tmp/benchmark-tmp
Where=/tmp
Type=none
Options=bind

[Install]
WantedBy=local-fs.target
UNIT
    systemctl daemon-reload
    systemctl enable tmp.mount
fi
GUEST
"$helper" stop "$vm"
"$helper" start "$vm"
"$helper" exec "$vm" python3 - --storage-only --allocated-mem-kib "$(( memory / 1024 ))" \
    < "$(dirname "$0")/benchmark-preflight.py"
if [[ "$small" == yes ]]; then
    "$helper" exec "$vm" bash -c 'test "$(stat -c %a /tmp)" = 1777'
fi
