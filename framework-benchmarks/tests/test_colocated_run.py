"""Host-loss cleanup regression checks; no VM or workload required."""
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('colocated_run',
    Path(__file__).resolve().parents[1]/'scripts/colocated-run.py')
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class HostCleanupTest(unittest.TestCase):
    def load_evidence(self, config, first_outcome='success'):
        spec = importlib.util.spec_from_file_location(
            'portfolio_workload', runner.ROOT/'market-replay-portfolio/workload/run.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        rows = []
        for slot in range(5):
            due = slot / 5
            outcome = first_outcome if slot == 0 else 'success'
            row = dict(slot=slot, scheduled_seconds=due, operation='portfolio', outcome=outcome,
                       status='queue_full' if outcome == 'unsent' else '200', dispatch_lag_ms=0)
            if outcome != 'unsent':
                row.update(started_seconds=due, completed_seconds=due+.01,
                           queue_wait_ms=0, http_ms=10, end_to_end_ms=10)
            rows.append(row)
        aggregate = driver.summarize(rows)
        return dict(config=config, observations=rows, offered=5, **aggregate,
                    operations={op: driver.summarize(rows if op == 'portfolio' else [])
                                for op in config['operations']},
                    elapsed_including_drain_seconds=1, offered_requests_per_second=5,
                    submitted_requests_per_second=aggregate['submitted'],
                    achieved_requests_per_second_including_drain=aggregate['completed'],
                    successful_requests_per_second_including_drain=aggregate['successful'],
                    successful_requests_per_second_in_window=aggregate['successful'],
                    dropped_client_capacity=aggregate['unsent'], peak_in_flight=1,
                    generator_saturated=bool(aggregate['unsent']))

    def test_driver_evidence_validation_and_failure_status(self):
        for case, expected in [('valid', 'completed'), ('counts', 'incomplete'),
                               ('duration', 'incomplete'), ('drain', 'incomplete'),
                               ('timing', 'incomplete'), ('summary timing', 'incomplete'),
                               ('incorrect p99', 'incomplete'),
                               ('unsent', 'workload-failed'), ('failed', 'workload-failed'),
                               ('timeout', 'workload-failed')]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as temp:
                output = Path(temp)

                def driver(command, **kwargs):
                    config = json.loads((output/'load-config.json').read_text())
                    outcome = case if case in ('unsent', 'failed', 'timeout') else 'success'
                    evidence = self.load_evidence(config, outcome)
                    if case == 'counts':
                        evidence['completed'] = 4
                    if case == 'duration':
                        evidence['config']['duration_seconds'] = 2
                    if case == 'drain':
                        evidence['elapsed_including_drain_seconds'] = .9
                    if case == 'summary timing':
                        del evidence['operations']['portfolio']['latency_ms']['p99']
                    if case == 'incorrect p99':
                        evidence['latency_ms']['p99'] += 1
                    if case == 'timing':
                        del evidence['observations'][0]['http_ms']
                    (output/'load.json').write_text(json.dumps(evidence))
                    return subprocess.CompletedProcess(command, int(outcome in ('failed', 'timeout')))

                with patch.object(runner.sp, 'run', side_effect=driver), \
                        patch.object(runner.time, 'monotonic', side_effect=[0, 1.1, 1.2]):
                    if case == 'valid':
                        runner.run_load(output, 1)
                    else:
                        with self.assertRaises(RuntimeError):
                            runner.run_load(output, 1)
                self.assertTrue((output/'load.json').exists())
                status = json.loads((output/'load-status.json').read_text())
                self.assertEqual(status['status'], expected)
                if case == 'incorrect p99':
                    self.assertIn('aggregate latency p99', status['reason'])

    def test_light_process_deadline_preserves_failure_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            driver = root/'market-replay-portfolio/workload'
            driver.mkdir(parents=True)
            (driver/'default.json').write_text('{}')
            (driver/'run.py').write_text("import time\nprint('started', flush=True)\ntime.sleep(60)\n")
            real_run = subprocess.run

            def short_deadline(command, *, timeout, **kwargs):
                self.assertEqual(timeout, 16)
                return real_run(command, timeout=.5, **kwargs)

            with patch.object(runner, 'ROOT', root), patch.object(runner.sp, 'run', short_deadline):
                with self.assertRaises(subprocess.TimeoutExpired):
                    runner.run_load(root, 1)
            status = json.loads((root/'load-status.json').read_text())
            self.assertEqual(status['status'], 'incomplete')
            self.assertEqual(status['reason'], 'hard execution deadline exceeded')
            self.assertEqual((root/'load.log').read_text().strip(), 'started')

    def test_warmup_failure_never_acknowledges_measurement(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            log = output/'runner.log'
            log.write_text('LIGHT_READY\n')
            guest = Mock()
            guest.poll.return_value = None
            with patch.object(runner.sp, 'Popen') as start, \
                    patch.object(runner, 'run_load', side_effect=RuntimeError('invalid warm-up')), \
                    log.open('a') as handle:
                start.return_value.__enter__.return_value = guest
                with self.assertRaisesRegex(RuntimeError, 'invalid warm-up'):
                    runner.run_load_guest(['guest'], output, 185, 40, 8, 125, handle)
            guest.stdin.write.assert_not_called()
            guest.terminate.assert_called_once()

    def test_measurement_follows_warmup_handshake(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            log = output/'runner.log'
            log.write_text('LIGHT_READY\n')
            guest = Mock()
            guest.wait.return_value = 0

            def write(token):
                if token == 'WARMUP_DONE\n':
                    with log.open('a') as handle:
                        handle.write('MEASUREMENT_READY\n')

            guest.stdin.write.side_effect = write
            with patch.object(runner.sp, 'Popen') as start, \
                    patch.object(runner, 'run_load') as load, log.open('a') as handle:
                start.return_value.__enter__.return_value = guest
                runner.run_load_guest(['guest'], output, 185, 40, 8, 125, handle)
            self.assertEqual([call.args for call in load.call_args_list],
                             [(output, 125, 40, 8, 'warmup'), (output, 185, 40, 8)])
            self.assertEqual([call.args for call in guest.stdin.write.call_args_list],
                             [('WARMUP_DONE\n',), ('LIGHT_DONE\n',)])

    def test_auxiliary_ignoring_sigterm_is_killed_and_reaped(self):
        proc = Mock()
        proc.poll.return_value = None
        proc.wait.side_effect = [subprocess.TimeoutExpired('fixture', 10), -9]
        runner.stop_auxiliary(proc)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        self.assertEqual(proc.wait.call_count, 2)
        self.assertTrue(all(c.kwargs['timeout'] == 10 for c in proc.wait.call_args_list))

    def test_exited_auxiliary_is_reaped_without_signalling(self):
        proc = Mock()
        proc.poll.return_value = 0
        runner.stop_auxiliary(proc)
        proc.terminate.assert_not_called()
        proc.kill.assert_not_called()
        proc.wait.assert_called_once_with(timeout=10)

    def exercise_host_loss(self, stop_fails=False, loss=None):
        calls = []
        processes = [Mock(), Mock()]
        for proc in processes:
            proc.poll.return_value = None
        def execute(args, **kwargs):
            calls.append((args, kwargs))
            if 'systemd-run' in args:
                raise loss if loss is not None else KeyboardInterrupt()
            if 'show' in args:
                return subprocess.CompletedProcess(args, 0, 'LoadState=loaded\nActiveState=active\n', '')
            if 'stop' in args and stop_fails:
                raise subprocess.TimeoutExpired(args, 35)
            return Mock(stdout='/tmp/ssh.config\n')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'run'
            with patch.object(runner.sys, 'argv', ['colocated-run', '--bundle', '/bundle', '--output', str(output)]), \
                    patch.object(runner.sp, 'run', side_effect=execute), \
                    patch.object(runner.sp, 'Popen', side_effect=processes), \
                    patch.object(runner.time, 'sleep'), \
                    patch.object(runner.urllib.request, 'urlopen', return_value=Mock()):
                self.assertTrue(runner.main())
            summary = json.loads((output/'run.json').read_text())
            launch = json.loads((output/'command.json').read_text())
            self.assertEqual(summary['status'], 'failed')
            self.assertTrue(any('guest stop' in e for e in summary['errors']) == stop_fails)
        stop_index = next(i for i,(args,_) in enumerate(calls) if 'stop' in args)
        collect_index = next(i for i,(args,_) in enumerate(calls) if 'get' in args)
        self.assertLess(stop_index, collect_index)
        stop_args, stop_kw = calls[stop_index]
        self.assertEqual(stop_args[-1], launch['unit'])
        self.assertEqual(stop_kw['timeout'], 35)
        self.assertIn('--unit='+launch['unit'], launch['command'])
        self.assertIn('--property=KillMode=mixed', launch['command'])
        self.assertIn('--property=TimeoutStopSec=30s', launch['command'])
        for proc in processes:
            proc.terminate.assert_called_once()
            proc.wait.assert_called_once_with(timeout=10)

    def state(self, load='loaded', active='active', code=0):
        return subprocess.CompletedProcess([], code,
            f'LoadState={load}\nActiveState={active}\n', '')

    def test_collected_failed_unit_does_not_need_stop(self):
        with patch.object(runner.sp, 'run', return_value=self.state('not-found', 'inactive', 1)) as run:
            runner.stop_guest('vm', 'owned.service', io.StringIO())
        self.assertEqual(run.call_count, 1)
        self.assertIn('show', run.call_args.args[0])

    def test_finished_unit_does_not_need_stop(self):
        for state in ('inactive', 'failed'):
            with self.subTest(state=state), patch.object(runner.sp, 'run', return_value=self.state(active=state)) as run:
                runner.stop_guest('vm', 'owned.service', io.StringIO())
                self.assertEqual(run.call_count, 1)

    def test_collection_between_show_and_stop_is_success(self):
        with patch.object(runner.sp, 'run', side_effect=[self.state(),
                subprocess.CalledProcessError(5, ['systemctl', 'stop']),
                self.state('not-found', 'inactive', 1)]) as run:
            runner.stop_guest('vm', 'owned.service', io.StringIO())
        self.assertEqual(run.call_count, 3)

    def test_stop_failure_for_active_unit_is_preserved(self):
        failure = subprocess.CalledProcessError(1, ['systemctl', 'stop'])
        with patch.object(runner.sp, 'run', side_effect=[self.state(), failure, self.state()]):
            with self.assertRaises(subprocess.CalledProcessError) as raised:
                runner.stop_guest('vm', 'owned.service', io.StringIO())
        self.assertIs(raised.exception, failure)

    def test_state_transport_failure_is_preserved(self):
        with patch.object(runner.sp, 'run', return_value=subprocess.CompletedProcess([], 255, '', 'SSH failed')):
            with self.assertRaises(subprocess.CalledProcessError):
                runner.stop_guest('vm', 'owned.service', io.StringIO())

    def test_interruption_stops_owned_guest_before_collection(self):
        self.exercise_host_loss()

    def test_ssh_failure_stops_owned_guest_before_collection(self):
        self.exercise_host_loss(loss=subprocess.CalledProcessError(255, ['ssh']))

    def test_unreachable_guest_does_not_prevent_collection_or_host_cleanup(self):
        self.exercise_host_loss(stop_fails=True)


if __name__ == '__main__':
    unittest.main()
