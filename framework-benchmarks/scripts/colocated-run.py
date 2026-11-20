#!/usr/bin/env python3
"""Host orchestration; bundle must contain complete candidate runtime + guest script."""
import argparse
import json
import hashlib
import math
import resource
from pathlib import Path
import signal
import subprocess as sp
import sys
import time
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
VM = ROOT/'tools/vm.sh'
PREPARATION_IDLE_SECONDS = 4
FIXTURE = ROOT/'market-replay-portfolio/fixture'
WORKLOAD = Path('market-replay-portfolio/workload/run.py')

def stop_auxiliary(proc):
    """Reap our own child, escalating if SIGTERM is ignored."""
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=10)
    except sp.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


def stop_guest(vm, unit, log):
    """Stop a possibly surviving run; --collect may already have unloaded it."""
    prefix = [str(VM), 'exec', vm, 'sudo', 'systemctl']

    def stopped():
        result = sp.run([*prefix, 'show', '--property=LoadState',
                         '--property=ActiveState', unit],
                        check=False, text=True, timeout=5, capture_output=True)
        log.write(result.stdout)
        log.write(result.stderr)
        state = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
        # Missing-unit show can exit nonzero, but transport/other failures must
        # remain visible. Require systemd's structured missing-unit evidence.
        if result.returncode in (0, 1, 4) and state.get('LoadState') == 'not-found':
            return True
        result.check_returncode()
        if 'LoadState' not in state or 'ActiveState' not in state:
            raise RuntimeError('missing systemd unit state during guest cleanup')
        return state['ActiveState'] in ('inactive', 'failed')

    if stopped():
        return
    try:
        sp.run([*prefix, 'stop', unit], check=True, text=True, timeout=35,
               stdout=log, stderr=sp.STDOUT)
    except sp.CalledProcessError:
        # --collect may unload the unit between show and stop.
        if not stopped():
            raise


def validate_load(evidence, config, wall_seconds):
    def number(value):
        return type(value) in (int, float) and math.isfinite(value) and value >= 0

    def require(condition, message):
        if not condition:
            raise ValueError(message)

    def counts(summary, rows):
        outcomes = [row['outcome'] for row in rows]
        unsent = outcomes.count('unsent')
        completed = len(rows) - unsent
        successful = outcomes.count('success')
        expected = dict(scheduled=len(rows), submitted=completed, completed=completed,
                        requests=completed, successful=successful, failed=outcomes.count('failed'),
                        timed_out=outcomes.count('timeout'), unsent=unsent, errors=completed-successful)
        for key, value in expected.items():
            require(type(summary[key]) is int and summary[key] == value,
                    f'{key}: expected {value}, got {summary[key]!r}')
        for key, count in [('dispatch_lag_ms', len(rows)), ('queue_wait_ms', completed),
                           ('latency_ms', successful), ('http_ms', successful),
                           ('unsuccessful_latency_ms', completed-successful)]:
            timing = summary[key]
            if not count:
                require(timing is None, f'{key}: expected null')
                continue
            values = [timing[p] for p in ('p50', 'p95', 'p99')]
            require(all(map(number, values)) and values == sorted(values),
                    f'{key}: invalid percentiles')

    duration = config['duration_seconds']
    rate = config['rate']
    expected = math.ceil(duration * rate)
    require(all(evidence['config'][k] == v for k, v in config.items()), 'configuration mismatch')
    require(wall_seconds >= duration, 'driver exited before the offering window ended')
    rows = evidence['observations']
    require(isinstance(rows, list) and len(rows) == expected, 'unexpected observation count')
    require(type(evidence['offered']) is int and evidence['offered'] == expected, 'offered count mismatch')
    by_operation = {op: [] for op in config['operations']}
    latest = duration
    for slot, row in enumerate(rows):
        require(type(row['slot']) is int and row['slot'] == slot, f'invalid slot {slot}')
        due = row['scheduled_seconds']
        require(number(due) and math.isclose(due, slot / rate, abs_tol=1e-9),
                f'invalid schedule at slot {slot}')
        require(number(row['dispatch_lag_ms']), f'invalid dispatch lag at slot {slot}')
        by_operation[row['operation']].append(row)
        outcome = row['outcome']
        require(outcome in ('success', 'failed', 'timeout', 'unsent'), f'invalid outcome at slot {slot}')
        if outcome != 'unsent':
            keys = ('started_seconds', 'completed_seconds', 'queue_wait_ms', 'http_ms', 'end_to_end_ms')
            require(all(number(row[key]) for key in keys), f'invalid HTTP timing at slot {slot}')
            start, end = row['started_seconds'], row['completed_seconds']
            require(due <= start <= end <= wall_seconds, f'invalid HTTP interval at slot {slot}')
            latest = max(latest, end)
    counts(evidence, rows)
    latencies = sorted(row['end_to_end_ms'] for row in rows if row['outcome'] == 'success')
    if latencies:
        for percentile in (50, 95, 99):
            expected_latency = latencies[math.ceil(len(latencies) * percentile / 100) - 1]
            key = f'p{percentile}'
            require(evidence['latency_ms'][key] == expected_latency,
                    f'aggregate latency {key}: expected {expected_latency}, got {evidence["latency_ms"][key]}')
    require(set(evidence['operations']) == set(by_operation), 'operation summaries mismatch')
    for op, observed in by_operation.items():
        counts(evidence['operations'][op], observed)
    elapsed = evidence['elapsed_including_drain_seconds']
    require(number(elapsed) and math.isclose(elapsed, latest), 'invalid duration including drain')
    rates = dict(offered_requests_per_second=expected / duration,
                 submitted_requests_per_second=evidence['submitted'] / duration,
                 achieved_requests_per_second_including_drain=evidence['completed'] / elapsed,
                 successful_requests_per_second_including_drain=evidence['successful'] / elapsed,
                 successful_requests_per_second_in_window=sum(
                     row['outcome'] == 'success' and row['completed_seconds'] < duration
                     for row in rows) / duration)
    for key, value in rates.items():
        require(number(evidence[key]) and math.isclose(evidence[key], value), f'invalid {key}')
    require(evidence['generator_saturated'] is bool(evidence['unsent']), 'invalid saturation flag')
    queue_full = sum(row['outcome'] == 'unsent' and row['status'] == 'queue_full' for row in rows)
    require(type(evidence['dropped_client_capacity']) is int and
            evidence['dropped_client_capacity'] == queue_full, 'invalid queue-full count')
    peak = evidence['peak_in_flight']
    require(type(peak) is int and bool(peak) == bool(evidence['submitted']) and
            0 <= peak <= config['concurrency'], 'invalid peak in flight')


def host_activity():
    return {name: Path('/proc', name).read_text() for name in ('stat', 'loadavg', 'pressure/cpu')
            if Path('/proc', name).exists()}


def run_load(output, seconds, rate=5, workers=8, name='load'):
    driver = ROOT/WORKLOAD
    config_path = output/f'{name}-config.json'
    config = json.loads(driver.with_name('default.json').read_text())
    config.update(base_url='http://127.0.0.1:18080', rate=rate, duration_seconds=seconds,
                  concurrency=workers, pending_capacity=workers)
    config_path.write_text(json.dumps(config, indent=2)+'\n')
    result_path = output/f'{name}.json'
    command = [sys.executable, str(driver), '--config', str(config_path), '--output', str(result_path)]
    deadline = seconds + 15
    status = dict(command=command, deadline_seconds=deadline, status='incomplete',
                  driver_sha256=hashlib.sha256(driver.read_bytes()).hexdigest())
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    status['host_before'] = host_activity()
    started = time.monotonic()
    try:
        with (output/f'{name}.log').open('w') as log:
            result = sp.run(command, stdout=log, stderr=sp.STDOUT, timeout=deadline)
        status['exit_code'] = result.returncode
        try:
            evidence = json.loads(result_path.read_text())
            validate_load(evidence, config, time.monotonic() - started)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            status['reason'] = f'invalid load evidence: {exc}'
            raise RuntimeError(status['reason']) from exc
        if evidence['errors'] or evidence['unsent'] or result.returncode:
            status['status'] = 'workload-failed'
            status['reason'] = (f"driver exit {result.returncode}, {evidence['errors']} errors, "
                                f"{evidence['unsent']} unsent")
            raise RuntimeError(status['reason'])
        status['status'] = 'completed'
    except sp.TimeoutExpired:
        status['reason'] = 'hard execution deadline exceeded'
        raise
    finally:
        after = resource.getrusage(resource.RUSAGE_CHILDREN)
        status.update(wall_seconds=time.monotonic()-started,
                      driver_cpu_seconds=after.ru_utime+after.ru_stime-before.ru_utime-before.ru_stime,
                      host_after=host_activity())
        (output/f'{name}-status.json').write_text(json.dumps(status, indent=2)+'\n')


def run_load_guest(command, output, seconds, rate, workers, warmup, log, suite_light=None):
    with sp.Popen(command, stdin=sp.PIPE, stdout=log, stderr=sp.STDOUT, text=True) as guest:
        try:
            def wait_for(marker, timeout):
                deadline = time.monotonic() + timeout
                while marker not in (output/'runner.log').read_text().splitlines():
                    if guest.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError(f'guest did not signal {marker}')
                    time.sleep(.1)

            wait_for('LIGHT_READY', 150)
            if suite_light:
                run_load(output, suite_light, 5, workers, 'light')
                guest.stdin.write('LIGHT_DONE\n')
                guest.stdin.flush()
                wait_for('SUSTAINED_READY', 10)
            if warmup:
                run_load(output, warmup, rate, workers, 'warmup')
                guest.stdin.write('WARMUP_DONE\n')
                guest.stdin.flush()
                wait_for('MEASUREMENT_READY', 10)
            run_load(output, seconds, rate, workers)
            guest.stdin.write('LIGHT_DONE\n')
            guest.stdin.flush()
            code = guest.wait(timeout=45)
            if code:
                raise sp.CalledProcessError(code, command)
        except BaseException:
            if guest.poll() is None:
                stop_auxiliary(guest)
            raise


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--vm',default='fb-512')
    p.add_argument('--bundle',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--guest-run-root', default='/tmp/fb-runs',
                   help='guest directory under which run evidence is created')
    p.add_argument('--candidate',default='jex-coilbase',choices=['jex-coilbase','quarkus-coilbase','spring-boot', 'micronaut-data-jdbc'])
    p.add_argument('--failure-probe',action='store_true',help='deliberately unreachable fixture; readiness must fail')
    p.add_argument('--preparation',action='store_true')
    load = p.add_mutually_exclusive_group()
    load.add_argument('--light-seconds', type=int, choices=range(1, 61), metavar='1..60')
    load.add_argument('--duration-seconds', type=int)
    p.add_argument('--rate', type=int, default=20)
    p.add_argument('--warmup-seconds', type=int, default=0)
    p.add_argument('--workers', type=int, default=8)
    p.add_argument('--suite-light-seconds', type=int, choices=range(1, 61), metavar='1..60')
    a = p.parse_args(argv)
    if a.suite_light_seconds and not (a.duration_seconds and a.warmup_seconds):
        p.error('suite light load requires sustained load with warm-up')
    if a.duration_seconds is not None and a.duration_seconds <= 0:
        p.error('--duration-seconds must be positive')
    if a.rate <= 0 or a.workers <= 0 or a.warmup_seconds < 0:
        p.error('rate and workers must be positive and warm-up must be nonnegative')
    if a.duration_seconds is None and (a.warmup_seconds or a.rate != 20 or a.workers != 8):
        p.error('rate, warm-up and workers require --duration-seconds')
    seconds = a.light_seconds or a.duration_seconds
    rate = 5 if a.light_seconds else a.rate
    a.output.mkdir(parents=True,exist_ok=False)
    guest = str(Path(a.guest_run_root)/a.output.name)
    processes, errors, logs = [], [], []
    unit = 'fb-smoke-' + uuid.uuid4().hex + '.service'
    guest_attempted = False
    interruption = None
    def interrupted(signum, frame):
        raise InterruptedError('host received signal '+str(signum))
    previous_term = signal.signal(signal.SIGTERM, interrupted)
    def call(*args,**kw):
        return sp.run(args,check=True,text=True,**kw)
    try:
        inputs = (FIXTURE/'server.py', FIXTURE/'data/quotes-2026-09-30.csv', ROOT/WORKLOAD)
        (a.output/'inputs.json').write_text(json.dumps({
            path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in inputs
        }, indent=2)+'\n')
        fixture_log = (a.output/'fixture.log').open('w'); logs.append(fixture_log)
        fixture = sp.Popen([sys.executable,str(FIXTURE/'server.py'),
                           '--port','18090','--step-seconds','3600'],stdout=fixture_log,stderr=sp.STDOUT)
        processes.append(fixture)
        for attempt in range(50):
            try:
                urllib.request.urlopen('http://127.0.0.1:18090/health',timeout=1).close()
                break
            except OSError:
                if fixture.poll() is not None: raise RuntimeError('fixture exited')
                time.sleep(.1)
        else: raise RuntimeError('fixture readiness timeout')
        config = call('limactl','list','--format={{.SSHConfigFile}}',a.vm,stdout=sp.PIPE).stdout.strip()
        tunnel_log = (a.output/'reverse-tunnel.log').open('w'); logs.append(tunnel_log)
        forward = ['-L','127.0.0.1:18080:127.0.0.1:8080'] if seconds else []
        tunnel = sp.Popen(['ssh','-F',config,'-o','ExitOnForwardFailure=yes','-o','ControlMaster=no',
                          '-o','ControlPath=none','-N','-R','127.0.0.1:8090:127.0.0.1:18090',*forward,'lima-'+a.vm],
                         stdout=tunnel_log,stderr=sp.STDOUT)
        processes.append(tunnel)
        time.sleep(1)
        if tunnel.poll() is not None: raise RuntimeError('reverse tunnel exited')
        call(str(VM),'exec',a.vm,'curl','-fsS','--max-time','2','--retry','9',
             '--retry-delay','1','--retry-connrefused','http://127.0.0.1:8090/health',
             stdout=sp.DEVNULL,timeout=20)
        call(str(ROOT/'tools/capture-env.sh'),a.vm,str(a.output/'environment'),a.bundle)
        command = [str(VM),'exec',a.vm,'sudo','systemd-run',
                   '--unit='+unit,'--collect','--wait','--service-type=exec',
                   '--property=KillMode=mixed','--property=TimeoutStopSec=30s',
                   'python3',a.bundle+'/colocated-guest.py','--bundle',a.bundle,
                   '--output',guest,'--candidate',a.candidate]
        if a.failure_probe: command += ['--fixture-url','http://127.0.0.1:1/quotes']
        if a.preparation:
            idle_seconds = PREPARATION_IDLE_SECONDS if a.suite_light_seconds else 2
            command += ['--idle-seconds',str(idle_seconds),'--stabilize-seconds','1']
        if seconds:
            command.insert(command.index('--wait'), '--pipe')
            command.append('--light-load')
            if a.duration_seconds:
                command += ['--measurement-seconds', str(seconds), '--warmup-seconds', str(a.warmup_seconds)]
            if a.suite_light_seconds:
                command += ['--suite-light-seconds', str(a.suite_light_seconds)]
        (a.output/'command.json').write_text(json.dumps(dict(command=command,unit=unit,fixture='host CSV replay via SSH reverse forwarding; 3600-second step',preparation=a.preparation),indent=2)+'\n')
        guest_attempted = True
        with (a.output/'runner.log').open('w') as f:
            if seconds:
                run_load_guest(command, a.output, seconds, rate, a.workers, a.warmup_seconds, f,
                               a.suite_light_seconds)
            else:
                call(*command,stdout=f,stderr=sp.STDOUT)
    except BaseException as e:
        errors.append(repr(e))
        if isinstance(e, (KeyboardInterrupt, InterruptedError)):
            interruption = e
    finally:
        # Stop the unique service before collecting after lost host control. The
        # guest gets SIGTERM to run its finally; systemd bounds surviving children.
        if errors and guest_attempted:
            try:
                with (a.output/'guest-stop.log').open('w') as log:
                    stop_guest(a.vm, unit, log)
            except BaseException as e:
                errors.append('guest stop (best effort): '+repr(e))
        try:
            call(str(VM),'get',a.vm,guest,str(a.output/'guest'))
        except BaseException as e:
            errors.append('collection: '+repr(e))
        for proc in reversed(processes):
            try:
                stop_auxiliary(proc)
            except BaseException as e:
                errors.append('host cleanup: '+repr(e))
        for log in logs: log.close()
        signal.signal(signal.SIGTERM, previous_term)
        status = 'failed' if errors else 'completed'
        (a.output/'run.json').write_text(json.dumps(dict(status=status,errors=errors,interrupted=interruption is not None),indent=2)+'\n')
    return bool(errors)

if __name__ == '__main__':
    raise SystemExit(main())
