"""Deterministic suite and offline report checks."""
import importlib
import importlib.util
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch
import sys

SCRIPTS = Path(__file__).resolve().parents[1]/'scripts'
with patch.object(sys, 'path', [str(SCRIPTS), *sys.path]):
    suite = importlib.import_module('colocated-suite')


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data if isinstance(data, str) else json.dumps(data))


class SuiteTest(unittest.TestCase):
    def test_regeneration_revalidates_raw_latency(self):
        spec = importlib.util.spec_from_file_location(
            'portfolio_workload', suite.runner.ROOT/'market-replay-portfolio/workload/run.py')
        driver = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(driver)
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            settings = suite.protocol()
            settings.update(sustained_rate=1, sustained_seconds=1)
            candidate = dict(id='jex-coilbase', stack=suite.STACKS['jex-coilbase'],
                             evidence='jex', execution='finished')
            manifest = root/'suite.json'
            other_candidates = [dict(id=key, stack=suite.STACKS[key], evidence=key, execution='pending')
                                for key in list(suite.STACKS)[1:]]
            write(manifest, dict(id='fixture', protocol=settings, created_utc='2026-11-17',
                                 host='benchmark-host', vm='fixture', candidates=[candidate, *other_candidates]))
            config = dict(rate=1, duration_seconds=1, seed=42, users=1000,
                          operations=settings['operations'], concurrency=8, pending_capacity=8)
            observation = dict(slot=0, scheduled_seconds=0, operation='portfolio',
                               outcome='success', status='200', dispatch_lag_ms=0,
                               started_seconds=0, completed_seconds=.01, queue_wait_ms=0,
                               http_ms=10, end_to_end_ms=10)
            data = dict(config=config, observations=[observation], offered=1,
                        **driver.summarize([observation]), elapsed_including_drain_seconds=1,
                        operations={op: driver.summarize([observation] if op == 'portfolio' else [])
                                    for op in config['operations']},
                        offered_requests_per_second=1, submitted_requests_per_second=1,
                        achieved_requests_per_second_including_drain=1,
                        successful_requests_per_second_including_drain=1,
                        successful_requests_per_second_in_window=1,
                        dropped_client_capacity=0, peak_in_flight=1, generator_saturated=False)
            write(root/'jex/load-status.json', dict(status='completed', wall_seconds=1, exit_code=0))
            write(root/'jex/load-config.json', config)
            write(root/'jex/load.json', data)
            result = suite.regenerate(manifest)['candidates'][0]['phases']['sustained']
            self.assertEqual(result['status'], 'incomplete')  # Guest evidence is absent.
            self.assertEqual(result['p99_ms'], 10)
            data['latency_ms']['p99'] = 99
            write(root/'jex/load.json', data)
            result = suite.regenerate(manifest)['candidates'][0]['phases']['sustained']
            self.assertEqual(result['status'], 'incomplete')
            self.assertIn('aggregate latency p99', result['reason'])
            self.assertNotIn('p99_ms', result)

    def test_sequential_failure_preserves_completed_phases_and_regenerates(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'mvp'
            calls = []

            def run_candidate(args):
                key = args[args.index('--candidate')+1]
                calls.append(key)
                self.assertEqual(args[args.index('--warmup-seconds')+1], '15')
                self.assertEqual(args[args.index('--duration-seconds')+1], '30')
                self.assertEqual(args[args.index('--rate')+1], '40')
                self.assertEqual(args[args.index('--suite-light-seconds')+1], '30')
                self.assertEqual(args[args.index('--guest-run-root')+1], '/runs/mvp')
                evidence = output/key
                write(evidence/'run.json', dict(status='failed', errors=['transfer <failed>']))
                if key == 'jex-coilbase':
                    write(evidence/'guest/summary.json', dict(candidate=key, ready_seconds=1.5,
                          postgres_start_seconds=2, status='failed'))
                    write(evidence/'guest/ready.json', dict(status='UP'))
                    write(evidence/'load-status.json', dict(status='incomplete', reason='hard deadline'))
                return True

            with patch.object(suite.platform, 'node', return_value='benchmark-host'), \
                 patch.object(suite.platform, 'system', return_value='Linux'), \
                 patch.object(suite.runner, 'main', side_effect=run_candidate):
                self.assertTrue(suite.run_suite(output, {key: '/'+key for key in reversed(suite.STACKS)},
                                                'vm', '/runs'))
            self.assertEqual(calls, list(suite.STACKS))
            manifest = output/'suite.json'
            original_manifest = manifest.read_bytes()
            recorded = json.loads(original_manifest)
            self.assertEqual(recorded['status'], 'failed')
            phases = recorded['candidates'][0]['phases']
            self.assertEqual(phases['startup']['status'], 'completed')
            self.assertEqual(phases['idle']['status'], 'missing')
            self.assertEqual(phases['sustained']['status'], 'incomplete')
            self.assertNotIn('p99_ms', phases['sustained'])
            html = (output/'report.html').read_text()
            self.assertIn('transfer &lt;failed&gt;', html)
            self.assertIn('hard deadline', html)
            self.assertIn('Unavailable', html)
            self.assertIn('<svg ', html)
            self.assertIn('1.50', html)
            self.assertIn('Bundle hashes unavailable', html)
            self.assertTrue(all((output/link).exists() for link in re.findall(r'href="([^"]+)"', html)))
            (output/'report.html').unlink()
            with patch.object(suite.runner, 'main', side_effect=AssertionError('benchmark launched')):
                suite.regenerate(manifest)
            self.assertEqual((output/'report.html').read_text(), html)
            self.assertEqual(manifest.read_bytes(), original_manifest)

    def test_v1_rounds_use_frozen_settings_and_unique_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'v1'
            expected = [(number, key) for number in (1, 2) for key in suite.STACKS]
            calls = []

            def run_candidate(args):
                options = dict(zip(args[::2], args[1::2]))
                evidence = Path(options['--output'])
                calls.append((evidence.parent.name, options['--candidate']))
                self.assertEqual(options['--guest-run-root'], f'/runs/v1/{evidence.parent.name}')
                self.assertEqual(options['--suite-light-seconds'], '30')
                self.assertEqual(options['--warmup-seconds'], '125')
                self.assertEqual(options['--duration-seconds'], '185')
                write(evidence/'run.json', dict(status='failed', errors=[]))
                return True

            with patch.object(suite.platform, 'node', return_value='benchmark-host'), \
                 patch.object(suite.platform, 'system', return_value='Linux'), \
                 patch.object(suite.runner, 'main', side_effect=run_candidate):
                self.assertTrue(suite.run_suite(output, {key: '/'+key for key in suite.STACKS},
                                                'vm', '/runs', version='v1'))
            self.assertEqual(calls, [(f'round-{number:02d}', key) for number, key in expected])
            manifest = output/'suite.json'
            original = manifest.read_bytes()
            html = (output/'report.html').read_bytes()
            with patch.object(suite.runner, 'main', side_effect=AssertionError('benchmark launched')):
                recorded = suite.regenerate(manifest)
            self.assertEqual([(c['round'], c['id']) for c in recorded['candidates']], expected)
            self.assertEqual(manifest.read_bytes(), original)
            self.assertEqual((output/'report.html').read_bytes(), html)
            self.assertIn('jex-coilbase · Round 2'.encode(), html)
            recorded['candidates'][-1]['evidence'] = recorded['candidates'][2]['evidence']
            write(manifest, recorded)
            with self.assertRaisesRegex(ValueError, 'Unexpected protocol v1 evidence directory'):
                suite.regenerate(manifest)
            recorded = json.loads(original)
            recorded['protocol']['warmup_seconds'] = 15
            write(manifest, recorded)
            with self.assertRaisesRegex(ValueError, 'Manifest settings differ from protocol v1'):
                suite.regenerate(manifest)

    def test_cross_round_artifact_drift_excludes_both_runs(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            runs = [dict(id='jex-coilbase', evidence=f'round-{number:02d}/jex-coilbase',
                         compatible=True, status='completed', failures=[])
                    for number in (1, 2)]
            first, second = [root/run['evidence']/'environment/artifacts.txt' for run in runs]
            app = f"{'a'*64}  ./app.jar"
            dependency = f"{'b'*64}  ./lib/dependency.jar"
            write(first, f'2026-11-17T00:00:00Z\n{app}\n{dependency}\n')
            write(second, f'2026-11-17T00:01:00Z\n{dependency}\n{app}\n')
            suite.verify_round_artifacts(root, runs)
            self.assertTrue(all(run['status'] == 'completed' for run in runs))

            changed_dependency = f"{'c'*64}  ./lib/dependency.jar"
            write(second, f'{app}\n{changed_dependency}\n')
            suite.verify_round_artifacts(root, runs)
            for run in runs:
                self.assertEqual(run['status'], 'failed')
                self.assertFalse(run['compatible'])
                self.assertIn('./lib/dependency.jar', run['failures'][0])

    def test_interruption_stops_before_next_candidate(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'mvp'

            def interrupt(args):
                evidence = Path(args[args.index('--output')+1])
                write(evidence/'run.json', dict(status='failed', errors=['interrupted'], interrupted=True))
                return True

            with patch.object(suite.platform, 'node', return_value='benchmark-host'), \
                 patch.object(suite.platform, 'system', return_value='Linux'), \
                 patch.object(suite.runner, 'main', side_effect=interrupt) as runner:
                self.assertTrue(suite.run_suite(output, {key: '/'+key for key in suite.STACKS},
                                                'vm', '/runs'))
                runner.assert_called_once()
            recorded = suite.read_json(output/'suite.json')
            self.assertEqual(recorded['status'], 'incomplete')
            self.assertEqual([c['execution'] for c in recorded['candidates']],
                             ['interrupted', 'pending', 'pending'])
            html = (output/'report.html').read_text()
            self.assertIn('interrupted', html)
            self.assertIn('Raw evidence directory unavailable', html)
            self.assertNotIn('href="quarkus-coilbase/', html)

    def test_partial_suite_is_rejected_before_execution_or_regeneration(self):
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)/'mvp'
            with self.assertRaisesRegex(ValueError, 'Expected exactly one'):
                suite.run_suite(output, {'jex-coilbase': '/jex'}, 'vm', '/runs')
            self.assertFalse(output.exists())
            manifest = output/'suite.json'
            for ids in (['jex-coilbase'], ['jex-coilbase', 'quarkus-coilbase', 'quarkus-coilbase']):
                with self.subTest(ids=ids):
                    write(manifest, dict(candidates=[dict(id=key) for key in ids]))
                    with self.assertRaisesRegex(ValueError, 'Expected exactly one'):
                        suite.regenerate(manifest)
                    self.assertFalse((output/'report.html').exists())

    def test_matching_sample_counts_do_not_hide_sparse_or_gapped_idle_coverage(self):
        settings = suite.protocol()
        candidate = dict(id='jex-coilbase', evidence='jex', execution='finished')
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            guest = root/'jex/guest'
            write(guest/'connections-after-idle.txt', 'checked')
            write(guest/'idle-start.json', dict(monotonic=100))
            write(guest/'idle-end.json', dict(monotonic=130))
            for stamps, expected in [([115], 'incomplete'),
                                     ([*range(101, 114), *range(119, 130)], 'incomplete'),
                                     (list(range(105, 130)), 'incomplete'),
                                     (list(range(99, 127)), 'incomplete'),
                                     ([99, 115, 131], 'incomplete'),
                                     (list(range(99, 132)), 'completed'),
                                     (list(range(101, 130)), 'completed')]:
                with self.subTest(stamps=stamps):
                    write(guest/'summary.json', dict(candidate=candidate['id'], idle_seconds=30,
                                                     sample_counts={'idle': len(stamps)}))
                    rows = []
                    for stamp in stamps:
                        inside = 100 <= stamp <= 130
                        rss = 1024 if inside else 8192
                        available = 1024 if inside else 256
                        processes = [dict(kind=kind, status='', smaps_rollup=f'Rss: {rss}\nPss: {rss}')
                                     for kind in ('app', 'postgres')]
                        rows.append(dict(phase='idle', monotonic=stamp, processes=processes,
                                         meminfo=f'MemAvailable: {available}'))
                    write(guest/'samples.jsonl', ''.join(json.dumps(row)+'\n' for row in rows))
                    idle = suite.inspect_candidate(root, candidate, settings)['phases']['idle']
                    self.assertEqual(idle['status'], expected)
                    self.assertEqual('available_mib' in idle, expected == 'completed')
                    if expected == 'completed':
                        for key in ('app_rss_mib', 'postgres_pss_mib', 'available_mib'):
                            self.assertEqual(idle[key], 1)
                        self.assertEqual(idle['samples'], sum(100 <= t <= 130 for t in stamps))
                        self.assertEqual(suite.memory.summarize(guest)['idle']['samples'], idle['samples'])

    def test_preparation_idle_covers_two_samples_with_collection_overhead(self):
        seconds = suite.protocol(preparation=True)['idle_seconds']
        self.assertEqual(seconds, 4)
        suite.validate_sample_coverage([101.3, 102.6, 103.9], seconds, (100, 100+seconds))


if __name__ == '__main__':
    unittest.main()
