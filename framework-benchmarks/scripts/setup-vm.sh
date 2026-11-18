#!/usr/bin/env bash
# Run as root in the dedicated fb-512 guest; preparation only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
bash "$here/postgres-setup.sh"
bash "$here/prepare-postgres.sh"
swapoff -a
sed -i.bak '/^[^#].*[[:space:]]swap[[:space:]]/s/^/# framework-benchmarks no swap: /' /etc/fstab
mkdir -p /opt/boot27
echo '95fc37eb3a18a27a26d5904c2d89d52bace8dafa9a078ca27f4747fbc4bf070b  /tmp/fb-jdk.tar.gz' | sha256sum -c -
tar -xzf /tmp/fb-jdk.tar.gz -C /opt/boot27 --strip-components=1
# Start explicitly in each run, so baseline contains no PostgreSQL processes.
echo manual > /etc/postgresql/18/main/start.conf
systemctl disable postgresql.service postgresql@18-main.service
systemctl stop postgresql@18-main
# Package installation is complete; manual apt remains available.
systemctl disable --now apt-daily.timer apt-daily-upgrade.timer
python3 "$here/benchmark-preflight.py" --cpus 1 --min-mem-kib 440001 --max-mem-kib 524287
/opt/boot27/bin/java -version
