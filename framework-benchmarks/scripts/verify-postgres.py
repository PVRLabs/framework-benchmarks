#!/usr/bin/env python3
"""Portfolio PostgreSQL functional verification against a disposable database.

Requires a built Portfolio JAR and a prepared fb_baseline database. Use an
existing tools/vm.sh DB tunnel for Lima. Never use on shared application state.
"""
import argparse
import copy
from decimal import Decimal
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'framework-benchmarks/tests'))
from postgres_correctness import Database, check, eventually, request, seed
from http_correctness import check as http_check

# Reuse the real checked-in CSV/replay implementation for controlled HTTP input.
spec = importlib.util.spec_from_file_location('portfolio_fixture', ROOT/'market-replay-portfolio/fixture/server.py')
fixture_module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = fixture_module
spec.loader.exec_module(fixture_module)


CHOSEN_PORTS = set()


def port():
    # Stay outside macOS/Linux ephemeral client ranges: SQL preparation between
    # selection and app launch can otherwise reuse the chosen listener port.
    for candidate in range(18080,18180):
        if candidate in CHOSEN_PORTS:
            continue
        with socket.socket() as sock:
            try:
                sock.bind(('127.0.0.1',candidate))
            except OSError:
                continue
        CHOSEN_PORTS.add(candidate)
        return candidate
    raise RuntimeError('no free local test port in 18080..18179')


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def launch_process(command, env, log, summary, processes):
    # Snapshot each attempt after its variant settings have been applied.
    launch = {'command':list(command), 'application_env':{
        k:v for k,v in env.items() if k.startswith(('SPRING_','SERVER_','MARKET_','POOL_'))}}
    summary['launches'].append(launch)
    try:
        process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
    except Exception as error:
        launch['error'] = repr(error)
        raise
    launch['pid'] = process.pid
    processes.append(process)
    return process


def finish(summary, output, processes, server, admin):
    errors = []
    actions = [(f'stop process {process.pid}', lambda p=process: stop(p))
               for process in processes if process is not None]
    if server:
        actions.extend([('fixture shutdown', server.shutdown),
                        ('fixture close', server.server_close)])
    actions.append(('restore database connectivity',
                    lambda: admin.sql('ALTER DATABASE fb_baseline ALLOW_CONNECTIONS true;')))
    try:
        for action, cleanup in actions:
            try:
                cleanup()
            except Exception as error:
                errors.append({'action':action, 'error':repr(error)})
    finally:
        summary['cleanup'] = {'status':'failed' if errors else 'passed',
                              'errors':errors, 'database':'dedicated database retained'}
        if errors:
            summary['status'] = 'failed'
        summary['finished_at_utc']=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    candidate = parser.add_mutually_exclusive_group()
    candidate.add_argument('--jex', action='store_true', help='verify Avaje Jex + CoilBase')
    candidate.add_argument('--quarkus', action='store_true', help='verify the Quarkus REST + CoilBase package')
    candidate.add_argument('--micronaut', action='store_true', help='verify Micronaut HTTP + Data JDBC')
    parser.add_argument('--health-path', help='operational database-health route; defaults per target')
    database = parser.add_mutually_exclusive_group()
    database.add_argument('--vm', default='fb-512')
    database.add_argument('--local', action='store_true', help='PostgreSQL 18 is on this disposable Linux host')
    parser.add_argument('--db-port', type=int, help='defaults to 15432 with Lima or 5432 with --local')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    db_port = args.db_port if args.db_port is not None else (5432 if args.local else 15432)
    health_path = args.health_path or ('/healthz' if args.jex else '/actuator/health')
    args.output.mkdir(parents=True, exist_ok=False)
    jar = ROOT/'market-replay-portfolio/app/target/market-replay-portfolio-0.1.0-SNAPSHOT.jar'
    if args.quarkus:
        jar = ROOT/'framework-benchmarks/quarkus-coilbase/target/quarkus-app/quarkus-run.jar'
    if args.jex:
        jar = ROOT/'framework-benchmarks/jex-coilbase/target/portfolio-jex-coilbase.jar'
    if args.micronaut:
        jar = ROOT/'framework-benchmarks/micronaut-data-jdbc/target/distribution/portfolio-micronaut-data-jdbc.jar'
    assert jar.exists(), 'package the reference application first'
    db_command = [] if args.local else [str(ROOT/'tools/vm.sh'), 'exec', args.vm]
    admin = Database(db_command + ['sudo','-u','postgres','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-d','postgres'])
    db = Database(db_command + ['sudo','-u','postgres','psql','-X','-qAt','-v','ON_ERROR_STOP=1','-d','fb_baseline'])
    app_port, fixture_port = port(), port()
    base = f'http://127.0.0.1:{app_port}'
    env = {k:v for k,v in os.environ.items() if not k.startswith(('SPRING_','MARKET_','SEED_','POOL_','SERVER_','JAVA_TOOL_OPTIONS','JDK_JAVA_OPTIONS'))}
    env.update(SPRING_PROFILES_ACTIVE='postgres', SERVER_PORT=str(app_port),
        MARKET_DB_URL=f'jdbc:postgresql://127.0.0.1:{db_port}/fb_baseline',
        MARKET_DB_USER='fb_baseline', MARKET_DB_PASSWORD='fb_baseline',
        MARKET_FIXTURE_URL=f'http://127.0.0.1:{fixture_port}/quotes',
        MARKET_POLL_ENABLED='false', POOL_MAX_SIZE='4')
    app = fixture = server = None
    processes = []
    summary = {'status':'incomplete','purpose':'functional preparation, not performance or VM feasibility',
        'vm':None if args.local else args.vm,'database':'fb_baseline','db_port':db_port,
        'placement':'host JVM, fixture and PostgreSQL' if args.local else
                    'host JVM and fixture; PostgreSQL in existing VM',
        'target':'jex-coilbase' if args.jex else 'quarkus-coilbase' if args.quarkus else
                 'micronaut-data-jdbc' if args.micronaut else 'spring-jdbc',
        'health_path':health_path,
        'launches':[], 'checks':[]}
    def passed(message):
        summary['checks'].append(message)
        print('PASS: ' + message, flush=True)
    with (args.output/'processes.log').open('w') as log:
        def launch(poll=False, interval=60000):
            env.update(MARKET_POLL_ENABLED=str(poll).lower(), MARKET_POLL_INTERVAL_MS=str(interval))
            process = launch_process(['java','-jar',str(jar)], env, log, summary, processes)
            def listening():
                assert process.poll() is None, 'application exited; inspect processes.log'
                try:
                    request(base, '/readyz', expected=503 if not poll else 200)
                    return True
                except OSError:
                    return False
                except AssertionError:
                    if poll:
                        return False
                    raise
            if poll:
                eventually(listening, 40)
            else:
                # A persisted database may already be ready.
                def alive():
                    assert process.poll() is None
                    try:
                        import urllib.request
                        urllib.request.urlopen(base+health_path, timeout=2).close()
                        return True
                    except OSError:
                        return False
                eventually(alive, 40)
            return process
        try:
            settings = db.sql("SELECT name,setting,unit,boot_val,source FROM pg_settings WHERE name IN ('max_connections','superuser_reserved_connections','reserved_connections','jit','max_parallel_workers_per_gather','max_parallel_workers','shared_buffers','work_mem','maintenance_work_mem','io_method','io_workers','effective_io_concurrency','maintenance_io_concurrency','fsync','autovacuum','wal_level') ORDER BY name;")
            (args.output/'postgres-settings.txt').write_text(settings+'\n')
            assert db.sql("SELECT current_setting('max_connections')='10' AND current_setting('superuser_reserved_connections')='1' AND current_setting('io_method')='worker' AND current_setting('shared_buffers')='16MB' AND current_setting('work_mem')='1MB' AND current_setting('maintenance_work_mem')='16MB' AND current_setting('jit')='off' AND current_setting('max_parallel_workers')='0' AND current_setting('max_parallel_workers_per_gather')='0';") == 't'
            (args.output/'environment.txt').write_text(subprocess.check_output(db_command+['bash','-lc','uname -a; free -m; cat /proc/swaps; psql --version'],text=True))
            (args.output/'java.txt').write_text(subprocess.run(['java','-version'],capture_output=True,text=True,check=True).stderr)
            import hashlib
            summary['jar_sha256'] = hashlib.sha256(jar.read_bytes()).hexdigest()
            if args.quarkus or args.jex or args.micronaut:
                summary['package_sha256'] = {str(p.relative_to(jar.parent)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(jar.parent.rglob('*')) if p.is_file()}
            summary['started_at_utc'] = time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
            revision = subprocess.run(['git','rev-parse','--verify','HEAD'], cwd=ROOT,
                                      capture_output=True, text=True)
            summary['git_revision'] = revision.stdout.strip() if revision.returncode == 0 else None
            summary['postgres_version'] = db.sql('SELECT version();')
            db.sql((ROOT/'market-replay-portfolio/reset.sql').read_text())
            db.sql('DROP SEQUENCE IF EXISTS test_batch_attempts;')
            app = launch()
            seed(db)
            request(base,'/readyz',expected=503)
            request(base,'/users/1/portfolio',expected=503)
            assert db.sql('SELECT count(*) FROM quote_samples;') == '0'
            passed('fresh seed and readiness DOWN without prices')
            stop(app)
            fixture = subprocess.Popen(['python3',str(ROOT/'market-replay-portfolio/fixture/server.py'),
                '--port',str(fixture_port),'--step-seconds','3600'],stdout=log,stderr=log)
            def fixture_ready():
                try:
                    return request(f'http://127.0.0.1:{fixture_port}','/health')['status']=='UP'
                except OSError:
                    return False
            eventually(fixture_ready)
            app = launch(True)
            latest = request(base,'/api/quotes/latest')
            assert len(latest)==3 and latest[0]['price']==Decimal('332.00')
            assert db.sql('SELECT count(*) FROM quote_samples;') == '3'
            assert db.sql("SELECT count(*) FROM quote_samples WHERE cycle=0 AND sample_index=0 AND market_time='09:30' AND fetched_at IS NOT NULL;") == '3'
            initial = request(base,'/users/1/portfolio')
            request(base,'/users/1/holdings/AAPL',{'quantity':10.125},204)
            request(base,'/users/1/holdings/GOOG',{'quantity':0},204)
            before = request(base,'/users/1/portfolio')
            stop(app)
            stop(fixture)
            subprocess.run(db_command+['sudo','systemctl','restart','postgresql@18-main'],check=True,timeout=30)
            app = launch()
            assert request(base,'/users/1/portfolio') == before
            assert request(base,'/api/quotes/latest') == latest
            http_check(base)
            check(base,db)
            passed('real CSV HTTP ingestion; app and PostgreSQL restart without fixture; shared HTTP and independent SQL concurrency/snapshot checks')

            # Fill the ordinary slots left by the live pool, whose idle
            # connection count can be lower than its configured maximum.
            capacity = """import psycopg2
connections = []
try:
 for _ in range(10):
  try:
   connections.append(psycopg2.connect(
    dbname='fb_baseline', user='fb_baseline', password='fb_baseline',
    host='127.0.0.1'))
  except psycopg2.OperationalError as error:
   assert 'reserved' in str(error), str(error)
   break
 else:
  raise AssertionError('PostgreSQL admitted ten ordinary connections')

 admin = psycopg2.connect(dbname='postgres', user='postgres')
 try:
  with admin.cursor() as cursor:
   cursor.execute("SELECT count(*) FROM pg_stat_activity WHERE backend_type='client backend'")
   total = cursor.fetchone()[0]
  assert total == 10, f'Expected ten occupied client slots, found {total}'
 finally:
  admin.close()

 app_connections = total - len(connections) - 1
 assert 1 <= app_connections <= 4, f'Unexpected application pool size: {app_connections}'
 print(f'PASS: {app_connections} app + {len(connections)} ordinary clients + '
       '1 reserved superuser; extra ordinary client rejected')
finally:
 for connection in connections:
  connection.close()
"""
            capacity_result = subprocess.run(db_command+['sudo','-u','postgres','python3','-c',capacity],text=True,capture_output=True,check=True)
            (args.output/'connection-capacity.txt').write_text(capacity_result.stdout)
            passed('ordinary connection limit and reserved administration slot with the live application pool')

            admin.sql("ALTER DATABASE fb_baseline ALLOW_CONNECTIONS false; SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='fb_baseline';")
            request(base,'/readyz',expected=503)
            request(base,health_path,expected=503)
            admin.sql('ALTER DATABASE fb_baseline ALLOW_CONNECTIONS true;')
            def recovered():
                try:
                    return request(base,'/readyz')['status']=='UP'
                except (AssertionError,OSError):
                    return False
            eventually(recovered)
            passed('database connection outage: readiness/health DOWN, pool reconnect and readiness recovery')
            stop(app)

            # Controlled real HTTP responses test scheduler failure/retry and a
            # late DB failure after earlier rows were inserted in the batch.
            state = {'mode':'invalid','invalid':0,'requests':0,'step':0}
            samples = fixture_module.load_samples()
            replay = fixture_module.Replay(samples,step_seconds=1,monotonic=lambda:0,started_at=0)
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):
                    mode = state['mode']
                    payload = copy.deepcopy(replay.current())
                    status = 200
                    if mode=='invalid':
                        invalid=state['invalid']
                        if invalid==0: payload['quotes'][2]['price']=None
                        elif invalid==1: payload['quotes'][1]['symbol']='AAPL'
                        elif invalid==2: payload['quotes'].pop()
                        elif invalid==3: payload['cycle']=-1
                        elif invalid==4: payload['marketTime']='09:31'
                        elif invalid==5: payload['quotes'][2]['price']=-1
                        elif invalid==6: payload['quotes'][2]['price']=1.12345
                    elif mode=='write-failure':
                        payload['quotes'][2]['price'] = 123.4567
                    elif mode=='wrap':
                        step=state['step']
                        if step>=391:
                            status=503
                        else:
                            payload=fixture_module.Replay(samples,1,monotonic=lambda:step,started_at=0).current()
                            state['step']+=1
                    elif mode=='unavailable':
                        status=503
                    body=json.dumps(payload).encode()
                    self.send_response(status)
                    self.send_header('Content-Length',str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    state['requests']+=1
                def log_message(self,fmt,*values):
                    log.write('controlled fixture: '+fmt % values+'\n')
                    log.flush()
            server=ThreadingHTTPServer(('127.0.0.1',fixture_port),Handler)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            count=db.sql('SELECT count(*) FROM quote_samples;')
            app=launch(True,100)
            for invalid in range(7):
                state['invalid']=invalid
                n=state['requests']
                eventually(lambda: state['requests']>=n+3)
                assert db.sql('SELECT count(*) FROM quote_samples;') == count
            db.sql("CREATE SEQUENCE test_batch_attempts; GRANT USAGE ON SEQUENCE test_batch_attempts TO fb_baseline; ALTER TABLE quote_samples ADD CONSTRAINT test_late_failure CHECK (CASE WHEN symbol='NVDA' AND price=123.4567 THEN nextval('test_batch_attempts')<0 ELSE true END);")
            state['mode']='write-failure'
            n=state['requests']
            eventually(lambda: state['requests']>=n+3)
            assert db.sql('SELECT count(*) FROM quote_samples;') == count
            # Sequence increments survive rollback: establish that the third-row
            # DB fault really happened, rather than validation rejecting early.
            assert db.sql('SELECT is_called FROM test_batch_attempts;')=='t'
            db.sql('ALTER TABLE quote_samples DROP CONSTRAINT test_late_failure;')
            db.sql('DROP SEQUENCE test_batch_attempts;')
            state['mode']='unavailable'
            n=state['requests']
            eventually(lambda: state['requests']>=n+3)
            # There can be one in-flight valid batch at the mode transition;
            # record stable state only after all earlier responses are drained.
            count=db.sql('SELECT count(*) FROM quote_samples;')
            state['mode']='wrap'
            eventually(lambda: state['step']==391,90)
            eventually(lambda: int(db.sql('SELECT count(*) FROM quote_samples;')) == int(count)+1173)
            history=request(base,'/api/quotes/history')
            assert len(history)==1170
            assert [q['id'] for q in history]==sorted(q['id'] for q in history)
            assert all(len([q for q in history if q['symbol']==s])==390 for s in ('AAPL','GOOG','NVDA'))
            assert all(q['cycle']==1 and q['sampleIndex']==0 for q in request(base,'/api/quotes/latest'))
            passed('invalid HTTP batch rejected; injected third-row SQL failure rolls back; HTTP failure retried; 391 HTTP batches cross replay wrap and bound history')
            stop(app)
            server.shutdown()
            server.server_close()
            server=None
            db.sql((ROOT/'market-replay-portfolio/reset.sql').read_text())
            assert db.sql("SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")=='0'
            fixture=subprocess.Popen(['python3',str(ROOT/'market-replay-portfolio/fixture/server.py'),'--port',str(fixture_port),'--step-seconds','3600'],stdout=log,stderr=log)
            eventually(fixture_ready)
            app=launch(True)
            seed(db)
            assert request(base,'/users/1/portfolio') == initial
            assert db.sql('SELECT count(*) FROM quote_samples;')=='3'
            passed('database reset removes all tables; fresh restart reseeds and ingests original state')
            summary['status']='passed'
        except BaseException as error:
            summary.update(status='failed',error=repr(error))
            raise
        finally:
            was_passed = summary['status']=='passed'
            errors = finish(summary, args.output, [fixture]+processes, server, admin)
            if errors and was_passed:
                raise RuntimeError('cleanup failed; see summary.json')


if __name__=='__main__':
    main()
