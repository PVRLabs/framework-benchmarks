#!/usr/bin/env python3
"""Read-only Debian and Ubuntu benchmark guest preflight; run after provisioning and before baseline."""
import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

def storage_errors(memory_kib, max_memory_kib, evidence_paths, check):
    paths = ['/var/tmp', *evidence_paths]
    if min(memory_kib, max_memory_kib) <= 512 * 1024:
        paths.append('/tmp')
    errors = []
    for path in dict.fromkeys(paths):
        mount = check('findmnt', '-n', '-o', 'FSTYPE', '-T', path)
        if mount.returncode or mount.stdout.strip() not in {
                'ext4', 'ext3', 'ext2', 'xfs', 'btrfs', 'f2fs', 'zfs'}:
            errors.append(f'{path} must be disk-backed')
    return errors


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cpus', type=int)
    p.add_argument('--min-mem-kib', type=int)
    p.add_argument('--max-mem-kib', type=int)
    p.add_argument('--evidence-path', action='append', default=[],
                   help='Additional existing guest directory to check for disk backing')
    p.add_argument('--require-debian-13', action='store_true')
    p.add_argument('--storage-only', action='store_true',
                   help='Check disk backing without distribution-specific package checks')
    p.add_argument('--allocated-mem-kib', type=int,
                   help='Allocated VM memory, if known')
    a = p.parse_args()
    if not a.storage_only and None in (a.cpus, a.min_mem_kib, a.max_mem_kib):
        p.error('--cpus, --min-mem-kib and --max-mem-kib are required for full preflight')
    mem = {line.split()[0].rstrip(':'): int(line.split()[1])
           for line in Path('/proc/meminfo').read_text().splitlines() if len(line.split()) >= 2}

    def check(*cmd):
        result = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        print('$', ' '.join(cmd), '\n', result.stdout, sep='')
        return result

    memory_limit = a.allocated_mem_kib or a.max_mem_kib or mem['MemTotal']
    errors = storage_errors(mem['MemTotal'], memory_limit, a.evidence_path, check)
    if errors or a.storage_only:
        print('PREFLIGHT:', 'FAILED: ' + '; '.join(errors) if errors else 'PASS')
        return int(bool(errors))
    os_release = dict(line.split('=', 1) for line in Path('/etc/os-release').read_text().splitlines() if '=' in line)
    if a.require_debian_13 and (os_release.get('ID') != 'debian' or
                                os_release.get('VERSION_ID', '').strip('"') != '13'):
        sys.exit('PREFLIGHT: FAILED: expected Debian 13, found ' +
                 os_release.get('PRETTY_NAME', 'unknown OS'))
    for timer in ('apt-daily.timer', 'apt-daily-upgrade.timer'):
        active = check('systemctl', 'is-active', timer)
        enabled = check('systemctl', 'is-enabled', timer)
        state, policy = active.stdout.strip(), enabled.stdout.strip()
        if policy not in ('disabled', 'masked') or (state != 'inactive' and (state, policy) != ('failed', 'masked')):
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
    if os_release.get('ID') == 'debian':
        if os_release.get('VERSION_ID', '').strip('"') != '13':
            errors.append('expected Debian 13')
        for package in ('postgresql-18', 'postgresql-client-18', 'python3-psycopg2', 'cloud-init', 'openssh-server'):
            result = check('dpkg-query', '-W', '-f=${db:Status-Status} ${Version}', package)
            if result.returncode or not result.stdout.startswith('installed '):
                errors.append('missing package: ' + package)
            elif package.startswith('postgresql-') and not result.stdout.startswith('installed 18.7-'):
                errors.append('expected PostgreSQL 18.7: ' + package)
        java = check('/opt/boot27/bin/java', '-version')
        if java.returncode or '27+35-2325' not in java.stdout:
            errors.append('unexpected OpenJDK build')
        periodic = check('apt-config', 'shell', 'PERIODIC', 'APT::Periodic::Enable')
        if periodic.returncode or periodic.stdout.strip() != "PERIODIC='0'":
            errors.append('APT periodic maintenance is enabled')
        # The harness itself runs as a transient service during this check.
        own_unit = Path('/proc/self/cgroup').read_text().splitlines()[0].rsplit('/', 1)[-1]
        allowed = {
            'cloud-config.service', 'cloud-final.service', 'cloud-init.service',
            'cloud-init-local.service', 'cloud-init-main.service', 'cloud-init-network.service',
            'dbus.service', 'getty@tty1.service', 'serial-getty@ttyS0.service', 'serial-getty@hvc0.service',
            'ssh.service', 'systemd-journald.service', 'systemd-logind.service',
            'systemd-networkd.service', 'systemd-resolved.service',
            # Environment capture queries timedatectl immediately before launch.
            'systemd-timedated.service', 'systemd-timesyncd.service', 'systemd-udevd.service', 'systemd-userdbd.service',
        }
        if re.fullmatch(r'fb-smoke-[0-9a-f]{32}\.service', own_unit):
            allowed.add(own_unit)
        for kind in ('service', 'timer'):
            units = check('systemctl', 'list-units', '--type='+kind, '--state=running,waiting',
                          '--plain', '--no-legend', '--no-pager')
            if units.returncode:
                errors.append('cannot enumerate active ' + kind + ' units')
            for row in units.stdout.splitlines():
                unit = row.split()[0]
                if unit not in allowed and not (kind == 'service' and unit.startswith('user@')):
                    errors.append('unexpected active unit: ' + unit)
        check('systemctl', 'list-timers', '--all', '--no-pager')
        check('ps', '-eo', 'pid,ppid,comm,rss,time,args', '--sort=-rss')
        for name in ('/proc/pressure/memory', '/proc/meminfo'):
            print(name, Path(name).read_text())
    print('PREFLIGHT:', 'FAILED: ' + '; '.join(errors) if errors else 'PASS')
    sys.exit(bool(errors))


if __name__ == '__main__':
    sys.exit(main())
