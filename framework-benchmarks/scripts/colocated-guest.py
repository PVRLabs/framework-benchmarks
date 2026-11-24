#!/usr/bin/env python3
"""One sequential startup/idle run; execute as root in the dedicated guest."""
import argparse
import base64
from collections import Counter
import json
import os
from pathlib import Path
import select
import signal
import subprocess as sp
import threading
import time
import urllib.request

def run(*args, **kw):
    return sp.run(args, check=True, text=True, **kw)

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bundle', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--candidate', choices=['jex-coilbase', 'quarkus-coilbase', 'spring-boot', 'micronaut-data-jdbc'], default='jex-coilbase')
    p.add_argument('--fixture-url', default='http://127.0.0.1:8090/quotes')
    p.add_argument('--java-command', required=True, help='encoded JVM command from the host runner')
    p.add_argument('--idle-seconds', type=int, default=30)
    p.add_argument('--stabilize-seconds', type=int, default=10)
    p.add_argument('--light-load', action='store_true')
    p.add_argument('--measurement-seconds', type=int)
    p.add_argument('--warmup-seconds', type=int, default=0)
    p.add_argument('--suite-light-seconds', type=int)
    p.add_argument('--require-debian-13', action='store_true')
    a = p.parse_args()
    java, *flags = json.loads(base64.urlsafe_b64decode(a.java_command))
    java_env = dict(os.environ)
    for variable in ('JAVA_TOOL_OPTIONS', 'JDK_JAVA_OPTIONS', '_JAVA_OPTIONS'):
        java_env.pop(variable, None)
    a.output.mkdir(parents=True, exist_ok=False)
    out = a.output
    errors = []
    sample_counts = Counter()
    app = None
    phase = 'baseline'
    postgres_cgroup = None
    done = threading.Event()
    def save(name, obj):
        (out/name).write_text(json.dumps(obj, indent=2)+'\n')
    def capture(name, *cmd, **kw):
        with (out/name).open('w') as f:
            run(*cmd, stdout=f, stderr=sp.STDOUT, **kw)
    def sample():
        row = dict(epoch=time.time(), monotonic=time.monotonic(), phase=phase,
                   meminfo=Path('/proc/meminfo').read_text(), vmstat=Path('/proc/vmstat').read_text(), processes=[])
        for d in Path('/proc').iterdir():
            if not d.name.isdigit():
                continue
            try:
                comm = (d/'comm').read_text().strip()
                if (app and int(d.name) == app.pid) or comm == 'postgres':
                    row['processes'].append(dict(pid=int(d.name), kind='app' if app and int(d.name)==app.pid else 'postgres',
                        status=(d/'status').read_text(), smaps_rollup=(d/'smaps_rollup').read_text(), stat=(d/'stat').read_text()))
            except (FileNotFoundError, ProcessLookupError):
                continue
        cg = postgres_cgroup
        row['postgres_cgroup'] = {n:(cg/n).read_text() for n in ['memory.current','memory.peak','memory.events'] if cg and (cg/n).exists()}
        with (out/'samples.jsonl').open('a') as f:
            f.write(json.dumps(row)+'\n')
        sample_counts[row['phase']] += 1
    def sampler():
        while not done.is_set():
            try:
                sample()
            except Exception as e:
                errors.append('sampler: '+repr(e))
                done.set()
            done.wait(1)
    summary = dict(candidate=a.candidate, flags=flags, idle_seconds=a.idle_seconds,
                   stabilize_seconds=a.stabilize_seconds, errors=errors)
    thread = None
    def interrupt(signum, frame):
        raise RuntimeError('interrupted '+str(signum))
    signal.signal(signal.SIGTERM, interrupt)
    signal.signal(signal.SIGINT, interrupt)
    try:
        # A guest-wide lock prevents any two runner candidates from overlapping.
        import fcntl
        lock = open('/run/framework-benchmarks.lock', 'w')
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        run('sha256sum', '--check', 'SHA256SUMS', cwd=a.bundle, stdout=sp.DEVNULL)
        if sp.check_output(['pgrep','-x','java'], text=True).strip():
            raise RuntimeError('another JVM is running')
    except sp.CalledProcessError as e:
        if e.cmd[0] != 'pgrep' or e.returncode != 1:
            errors.append(repr(e))
    except Exception as e:
        errors.append(repr(e))
    if errors:
        summary['status'] = 'failed'
        save('summary.json',summary)
        return True
    try:
        run('systemctl','stop','postgresql@18-main')
        assert not sp.run(['pgrep','-x','postgres'],stdout=sp.DEVNULL).returncode == 0
        os_check = ['--require-debian-13'] if a.require_debian_13 else []
        capture('preflight.txt','python3',str(a.bundle/'benchmark-preflight.py'),
                '--evidence-path',str(out),'--evidence-path',str(a.bundle),
                '--cpus','1','--min-mem-kib','440001','--max-mem-kib','524287',*os_check)
        mem = Path('/proc/meminfo').read_text()
        assert int(next(x.split()[1] for x in mem.splitlines() if x.startswith('SwapTotal:'))) == 0
        assert os.cpu_count() == 1
        assert 440000 < int(next(x.split()[1] for x in mem.splitlines() if x.startswith('MemTotal:'))) < 524288
        capture('environment.txt','bash','-c','uname -a; lscpu; free -k; cat /proc/swaps; cat /etc/os-release; df -h /')
        capture('java.txt',java,'-version',env=java_env)
        capture('effective-jvm-flags.txt',java,*flags,'-XX:+PrintFlagsFinal','-version',env=java_env)
        capture('kernel-before.log','journalctl','-k','--no-pager')
        capture('vmstat-before.txt','cat','/proc/vmstat')
        thread = threading.Thread(target=sampler)
        thread.start()
        time.sleep(3)
        phase = 'postgres-startup'
        t = time.monotonic()
        run('systemctl','start','postgresql@18-main')
        summary['postgres_start_seconds'] = time.monotonic()-t
        control_group = sp.check_output(['systemctl','show','postgresql@18-main','--property=ControlGroup','--value'],text=True).strip()
        postgres_cgroup = Path('/sys/fs/cgroup')/control_group.lstrip('/') if control_group else None
        summary['postgres_cgroup'] = str(postgres_cgroup) if postgres_cgroup else None
        # Reset only the dedicated disposable DB; preparation never carries data.
        run('sudo','-u','postgres','dropdb','--if-exists','fb_baseline')
        run('sudo','-u','postgres','createdb','-O','fb_baseline','fb_baseline')
        capture('postgres-settings.txt','sudo','-u','postgres','psql','-X','-c',
                "SELECT name,setting,unit,source FROM pg_settings ORDER BY name")
        phase = 'postgres-only'
        time.sleep(3)
        jars = {'jex-coilbase':'portfolio-jex-coilbase.jar','quarkus-coilbase':'quarkus-app/quarkus-run.jar','spring-boot':'application.jar',
                'micronaut-data-jdbc':'portfolio-micronaut-data-jdbc.jar'}
        command = [java,*flags,'-Xlog:gc:file='+str(out/'gc.log'),'-jar',str(a.bundle/jars[a.candidate])]
        env = dict(java_env, SERVER_PORT='8080', MARKET_DB_URL='jdbc:postgresql://127.0.0.1:5432/fb_baseline',
                   MARKET_DB_USER='fb_baseline', MARKET_DB_PASSWORD='fb_baseline', PORTFOLIO_SEED_USERS='1000',
                   MARKET_FIXTURE_URL=a.fixture_url, MARKET_POLL_ENABLED='true',
                   MARKET_POLL_INTERVAL_MS='60000', MARKET_POLL_INITIAL_DELAY_MS='0')
        save('launch.json',dict(command=command,environment={k:v for k,v in env.items() if k.startswith(('MARKET_','PORTFOLIO_','SERVER_'))}))
        phase = 'startup'
        started = time.monotonic()
        summary['launch_monotonic'] = started
        with (out/'app.log').open('w') as log:
            app = sp.Popen(command,env=env,stdout=log,stderr=sp.STDOUT)
        summary['pid'] = app.pid
        attempts = []
        while True:
            try:
                with urllib.request.urlopen('http://127.0.0.1:8080/readyz',timeout=1) as r:
                    body = json.load(r)
                assert body['status'] == 'UP'
                summary['ready_seconds'] = time.monotonic()-started
                save('ready.json',body)
                break
            except Exception as e:
                attempts.append(dict(seconds=time.monotonic()-started,error=str(e)))
                if app.poll() is not None or time.monotonic()-started > 90:
                    raise RuntimeError('application exited or readiness timed out')
                time.sleep(.1)
            finally:
                save('readiness-attempts.json',attempts)
        with urllib.request.urlopen('http://127.0.0.1:8080/users/1/portfolio',timeout=5) as r:
            portfolio = json.load(r)
        assert portfolio['userId'] == 1 and len(portfolio['holdings']) == 3
        save('portfolio.json',portfolio)
        phase = 'stabilize'
        time.sleep(a.stabilize_seconds)
        phase = 'idle'
        if a.suite_light_seconds:
            save('idle-start.json', dict(monotonic=time.monotonic()))
        time.sleep(a.idle_seconds)
        if a.suite_light_seconds:
            save('idle-end.json', dict(monotonic=time.monotonic()))
        phase = 'idle-check'
        assert app.poll() is None
        capture('connections-after-idle.txt','sudo','-u','postgres','psql','-X','-c',
                "SELECT usename,state,count(*) FROM pg_stat_activity GROUP BY usename,state ORDER BY usename,state")
        if a.light_load:
            def await_host(token, seconds):
                deadline = time.monotonic() + seconds
                while app.poll() is None and time.monotonic() < deadline:
                    if select.select([0], [], [], 1)[0]:
                        if input() != token:
                            raise RuntimeError(f'expected {token} from host')
                        return
                raise RuntimeError(f'{token} missing or app exited')

            if a.suite_light_seconds:
                phase = 'light-load'
                save('light-start.json', dict(monotonic=time.monotonic()))
                print('LIGHT_READY', flush=True)
                await_host('LIGHT_DONE', a.suite_light_seconds + 25)
                save('light-end.json', dict(monotonic=time.monotonic()))
            phase = 'warmup' if a.warmup_seconds else ('measurement' if a.measurement_seconds else 'light-load')
            if a.suite_light_seconds:
                save('warmup-start.json', dict(monotonic=time.monotonic()))
            print('SUSTAINED_READY' if a.suite_light_seconds else 'LIGHT_READY', flush=True)
            if a.warmup_seconds:
                await_host('WARMUP_DONE', a.warmup_seconds + 25)
                if a.suite_light_seconds:
                    save('warmup-end.json', dict(monotonic=time.monotonic()))
                phase = 'measurement'
            label = 'measurement' if a.measurement_seconds else 'light'
            save(f'{label}-start.json', dict(monotonic=time.monotonic()))
            if a.warmup_seconds:
                print('MEASUREMENT_READY', flush=True)
            await_host('LIGHT_DONE', a.measurement_seconds + 25 if a.measurement_seconds else 100)
            save(f'{label}-end.json', dict(monotonic=time.monotonic()))
            phase = 'post-load'
            with urllib.request.urlopen('http://127.0.0.1:8080/users/1/portfolio',timeout=5) as r:
                after = json.load(r)
            assert after['userId'] == 1 and after['holdings']
            save('portfolio-after-load.json', after)
    except BaseException as e:
        errors.append(repr(e))
    finally:
        phase = 'shutdown'
        if app is not None:
            try:
                app.terminate()
                app.wait(timeout=15)
                summary['app_exit'] = app.returncode
                summary['forced_shutdown'] = False
            except Exception as e:
                errors.append('app cleanup: '+repr(e))
                app.kill()
                app.wait()
                summary['forced_shutdown'] = True
        for label, action in [
            ('database stop',lambda:run('systemctl','stop','postgresql@18-main')),
            ('kernel capture',lambda:capture('kernel-after.log','journalctl','-k','--no-pager')),
            ('process capture',lambda:capture('processes-after.txt','ps','-eo','pid,comm,rss,args')),
            ('vmstat capture',lambda:capture('vmstat-after.txt','cat','/proc/vmstat'))]:
            try:
                action()
            except BaseException as e:
                errors.append(label+': '+repr(e))
        try:
            remaining = sp.run(['pgrep','-x','postgres'],stdout=sp.PIPE,text=True)
            summary['postgres_stopped'] = remaining.returncode == 1
            if remaining.returncode != 1:
                errors.append('PostgreSQL processes remain: '+remaining.stdout)
            before = dict(x.split() for x in (out/'vmstat-before.txt').read_text().splitlines())
            after = dict(x.split() for x in (out/'vmstat-after.txt').read_text().splitlines())
            summary['oom_kill_delta'] = int(after['oom_kill'])-int(before['oom_kill'])
            if summary['oom_kill_delta']:
                errors.append('guest OOM kill observed')
        except Exception as e:
            errors.append('final verification: '+repr(e))
        done.set()
        if thread:
            thread.join(timeout=5)
        summary['sample_counts'] = dict(sorted(sample_counts.items()))
        summary['status'] = 'failed' if errors else 'completed'
        save('summary.json',summary)
    return bool(errors)

if __name__ == '__main__':
    raise SystemExit(main())
