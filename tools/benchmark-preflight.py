#!/usr/bin/env python3
"""Read-only Ubuntu benchmark guest preflight; run after provisioning and before baseline."""
import argparse
import os
from pathlib import Path
import subprocess
import sys

p = argparse.ArgumentParser()
p.add_argument('--cpus', type=int, required=True)
p.add_argument('--min-mem-kib', type=int, required=True)
p.add_argument('--max-mem-kib', type=int, required=True)
a = p.parse_args()
errors = []

def check(*cmd):
    result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    print('$', ' '.join(cmd), '\n', result.stdout, sep='')
    return result

for timer in ('apt-daily.timer', 'apt-daily-upgrade.timer'):
    active = check('systemctl', 'is-active', timer)
    enabled = check('systemctl', 'is-enabled', timer)
    if active.stdout.strip() != 'inactive' or enabled.stdout.strip() not in ('disabled', 'masked'):
        errors.append(timer + ' is not inactive and disabled')
for service in ('apt-daily.service', 'apt-daily-upgrade.service'):
    result = check('systemctl', 'is-active', service)
    if result.stdout.strip() not in ('inactive', 'failed'):
        errors.append(service + ' is active or unknown')
for proc in Path('/proc').iterdir():
    if not proc.name.isdigit() or int(proc.name) == os.getpid():
        continue
    try:
        args = (proc/'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
        comm = (proc/'comm').read_text().strip()
    except (OSError, ProcessLookupError):
        continue
    if comm in ('apt', 'apt-get', 'dpkg', 'unattended-upgr', 'apt.systemd.dai') and 'unattended-upgrade-shutdown' not in args:
        errors.append('package operation: ' + proc.name + ' ' + args)
mem = dict((line.split()[0].rstrip(':'), int(line.split()[1])) for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) >= 2)
print('cpus:', os.cpu_count(), 'MemTotal KiB:', mem['MemTotal'], 'SwapTotal KiB:', mem['SwapTotal'])
if os.cpu_count() != a.cpus or not a.min_mem_kib <= mem['MemTotal'] <= a.max_mem_kib or mem['SwapTotal'] != 0:
    errors.append('guest resource constraints differ')
audit = check('dpkg', '--audit')
if audit.returncode or audit.stdout.strip():
    errors.append('dpkg audit failed or reported incomplete packages')
if check('apt-get', 'check').returncode:
    errors.append('apt dependency check failed')
check('uname', '-a')
print(Path('/etc/os-release').read_text())
if check('dpkg-query', '-W', '-f=${binary:Package}\t${Version}\t${db:Status-Abbrev}\n').returncode:
    errors.append('package inventory failed')
print('PREFLIGHT:', 'FAILED: ' + '; '.join(errors) if errors else 'PASS')
sys.exit(bool(errors))
