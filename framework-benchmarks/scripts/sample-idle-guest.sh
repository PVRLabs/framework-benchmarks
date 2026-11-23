#!/usr/bin/env bash
# Sample the operating-system baseline with PostgreSQL and all apps stopped.
set -euo pipefail
if pgrep -x java || pgrep -x postgres; then
    exit 1
fi
cat /proc/sys/kernel/random/boot_id
for ((i=0; i<30; i++)); do
    date -u +%FT%TZ
    awk '/^(MemTotal|MemAvailable|SwapTotal):/' /proc/meminfo
    cat /proc/pressure/{cpu,memory,io}
    awk '/^(oom_kill|allocstall_|pgscan_direct)/' /proc/vmstat
    if ((i < 29)); then sleep 1; fi
done
