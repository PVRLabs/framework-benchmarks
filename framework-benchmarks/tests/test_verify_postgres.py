"""Focused regression checks for launch evidence and failure-safe finalization."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

SPEC = importlib.util.spec_from_file_location('verify_postgres',
    Path(__file__).resolve().parents[1]/'scripts/verify-postgres.py')
verify = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verify)


class VerificationEvidenceTest(unittest.TestCase):
    def test_each_launch_records_its_own_environment(self):
        summary = {'launches':[]}
        processes = []
        env = {'MARKET_POLL_ENABLED':'false', 'MARKET_POLL_INTERVAL_MS':'60000',
               'POOL_MAX_SIZE':'4', 'UNRELATED_SECRET':'do not record'}
        with patch.object(verify.subprocess, 'Popen', side_effect=[Mock(pid=1),Mock(pid=2),Mock(pid=3)]) as popen:
            for poll, interval in [('false','60000'),('true','60000'),('true','100')]:
                env.update(MARKET_POLL_ENABLED=poll, MARKET_POLL_INTERVAL_MS=interval)
                verify.launch_process(['java','-jar','app.jar'], env, None, summary, processes)
                self.assertEqual(popen.call_args.kwargs['env'], env)
        env['MARKET_POLL_INTERVAL_MS']='changed later'
        self.assertEqual([(item['application_env']['MARKET_POLL_ENABLED'],
                           item['application_env']['MARKET_POLL_INTERVAL_MS'])
                          for item in summary['launches']],
                         [('false','60000'),('true','60000'),('true','100')])
        self.assertTrue(all('UNRELATED_SECRET' not in item['application_env']
                            for item in summary['launches']))
        self.assertEqual([item['pid'] for item in summary['launches']], [1,2,3])

    def test_failed_launch_is_recorded(self):
        summary = {'launches':[]}
        with patch.object(verify.subprocess, 'Popen', side_effect=OSError('launch failed')):
            with self.assertRaises(OSError):
                verify.launch_process(['java'], {'MARKET_POLL_ENABLED':'true'}, None, summary, [])
        self.assertIn('launch failed', summary['launches'][0]['error'])

    def test_cleanup_failures_preserve_original_error_and_summary(self):
        summary = {'status':'failed','error':'original verification failure'}
        process = Mock(pid=123)
        server = Mock()
        server.shutdown.side_effect = OSError('fixture shutdown failed')
        admin = Mock()
        admin.sql.side_effect = subprocess.CalledProcessError(255, ['ssh'])
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(verify, 'stop', side_effect=OSError('process stop failed')):
                errors = verify.finish(summary, Path(directory), [process], server, admin)
            saved = json.loads((Path(directory)/'summary.json').read_text())
        self.assertEqual(len(errors), 3)
        self.assertEqual(saved['error'], 'original verification failure')
        self.assertEqual(saved['cleanup']['status'], 'failed')
        self.assertEqual(saved['status'], 'failed')
        self.assertIn('finished_at_utc', saved)
        server.server_close.assert_called_once()
        admin.sql.assert_called_once()

    def test_cleanup_failure_marks_previously_passed_run_failed(self):
        admin = Mock()
        admin.sql.side_effect = OSError('VM unavailable')
        with tempfile.TemporaryDirectory() as directory:
            verify.finish({'status':'passed'}, Path(directory), [], None, admin)
            saved = json.loads((Path(directory)/'summary.json').read_text())
        self.assertEqual(saved['status'], 'failed')
        self.assertIn('VM unavailable', saved['cleanup']['errors'][0]['error'])

    def test_successful_cleanup_is_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            errors = verify.finish({'status':'passed'}, Path(directory), [], None, Mock())
            saved = json.loads((Path(directory)/'summary.json').read_text())
        self.assertEqual(errors, [])
        self.assertEqual(saved['status'], 'passed')
        self.assertEqual(saved['cleanup']['status'], 'passed')


if __name__=='__main__':
    unittest.main()
