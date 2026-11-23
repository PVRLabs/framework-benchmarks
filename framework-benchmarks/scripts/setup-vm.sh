#!/usr/bin/env bash
# Run as root in the dedicated Debian 13 guest; preparation only.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
. /etc/os-release
[[ $ID == debian && $VERSION_ID == 13 ]]
export DEBIAN_FRONTEND=noninteractive
# Mask first so package installation cannot schedule maintenance.
systemctl mask --now apt-daily.timer apt-daily-upgrade.timer apt-daily.service apt-daily-upgrade.service \
    unattended-upgrades.service fwupd.service fwupd-refresh.service fwupd-refresh.timer \
    man-db.timer apt-listchanges.timer systemd-tmpfiles-clean.timer logrotate.timer \
    fstrim.timer e2scrub_all.timer dpkg-db-backup.timer \
    cron.service anacron.service anacron.timer
cat > /etc/apt/apt.conf.d/99-framework-benchmarks <<'APT'
APT::Periodic::Enable "0";
APT
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl gnupg python3-psycopg2 sudo
install -d /usr/share/postgresql-common/pgdg
curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc |
    gpg --batch --yes --dearmor -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg
key=/usr/share/postgresql-common/pgdg/apt.postgresql.org.gpg
printf 'deb [signed-by=%s] https://apt.postgresql.org/pub/repos/apt trixie-pgdg main\n' "$key" > /etc/apt/sources.list.d/pgdg.list
apt-get update
pg_version=18.7-1.pgdg13+5
apt-get install -y --no-install-recommends "postgresql-18=$pg_version" "postgresql-client-18=$pg_version"
apt-mark hold postgresql-18 postgresql-client-18
bash "$here/prepare-postgres.sh"
swapoff -a
sed -i.bak '/^[^#].*[[:space:]]swap[[:space:]]/s/^/# framework-benchmarks no swap: /' /etc/fstab
mkdir -p /opt/boot27
echo '95fc37eb3a18a27a26d5904c2d89d52bace8dafa9a078ca27f4747fbc4bf070b  /tmp/fb-jdk.tar.gz' | sha256sum -c -
tar -xzf /tmp/fb-jdk.tar.gz -C /opt/boot27 --strip-components=1
echo manual > /etc/postgresql/18/main/start.conf
systemctl disable --now postgresql.service postgresql@18-main.service
python3 "$here/benchmark-preflight.py" --require-debian-13 --cpus 1 --min-mem-kib 440001 --max-mem-kib 524287
