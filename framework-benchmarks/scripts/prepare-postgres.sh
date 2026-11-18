#!/usr/bin/env bash
# Disposable functional preparation on the existing PostgreSQL experiment VM.
# Replaces that VM's experiment profile; does not delete previous databases.
set -euo pipefail
cat > /etc/postgresql/18/main/conf.d/experiment.conf <<'CONF'
max_connections = 10
superuser_reserved_connections = 1
jit = off
max_parallel_workers_per_gather = 0
max_parallel_workers = 0
shared_buffers = '16MB'
work_mem = '1MB'
maintenance_work_mem = '16MB'
CONF
systemctl restart postgresql@18-main
sudo -u postgres psql -X -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
 IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='fb_baseline') THEN
  CREATE ROLE fb_baseline LOGIN PASSWORD 'fb_baseline';
 END IF;
END $$;
SELECT 'CREATE DATABASE fb_baseline OWNER fb_baseline'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='fb_baseline')
\gexec
SQL
