import contextlib
import http.server
import threading
import time
import unittest

from run import percentiles, run


@contextlib.contextmanager
def endpoint(delay):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(delay)
            self.send_response(200)
            self.end_headers()

        def do_PUT(self):
            self.rfile.read(int(self.headers['Content-Length']))
            self.send_response(204)
            self.end_headers()

        def log_message(self, *args):
            pass

    with http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler) as server:
        thread = threading.Thread(target=server.serve_forever, kwargs={'poll_interval': .01})
        thread.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}'
        finally:
            server.shutdown()
            thread.join()


def config(url, **overrides):
    return dict(dict(base_url=url, seed=42, users=1000, rate=5,
                     duration_seconds=.6, timeout_seconds=2,
                     operations={'portfolio': 40, 'edit': 25, 'valuation': 25,
                                 'latest': 8, 'history': 2}), **overrides)


class WorkloadTest(unittest.TestCase):
    def test_percentiles(self):
        self.assertIsNone(percentiles([]))
        self.assertEqual(percentiles(reversed(range(1, 101))), {'p50': 50, 'p95': 95, 'p99': 99})

    def test_schedule_and_determinism(self):
        with endpoint(.02) as url:
            first = run(config(url))
            second = run(config(url))
        self.assertEqual(first['config']['concurrency'], 8)
        self.assertEqual(first['peak_in_flight'], 1)
        self.assertEqual(first['successful'], 3)
        rows = first['observations']
        self.assertEqual([r['scheduled_seconds'] for r in rows], [0, .2, .4])
        keys = ('operation', 'path', 'quantity')
        self.assertEqual([[r[k] for k in keys] for r in rows],
                         [[r[k] for k in keys] for r in second['observations']])

    def test_overlap_and_bounded_saturation(self):
        with endpoint(.25) as url:
            result = run(config(url, rate=80, duration_seconds=.4,
                                pending_capacity=2, operations={'portfolio': 1}))
        self.assertEqual(result['peak_in_flight'], 8)
        self.assertGreater(result['dropped_client_capacity'], 0)
        self.assertTrue(result['generator_saturated'])
        self.assertEqual(result['scheduled'], result['submitted'] + result['unsent'])
        self.assertEqual(result['submitted'], result['completed'])
        self.assertEqual(result['completed'], result['successful'])
        queued = [r for r in result['observations'] if r.get('queue_wait_ms', 0) > 10]
        self.assertTrue(queued)
        for row in queued:
            self.assertAlmostEqual(row['end_to_end_ms'], sum(row[k] for k in
                                   ('http_ms', 'dispatch_lag_ms', 'queue_wait_ms')))

    def test_timeout_and_shutdown(self):
        with endpoint(.15) as url:
            result = run(config(url, rate=5, duration_seconds=.1, timeout_seconds=.025,
                                concurrency=1, operations={'portfolio': 1}))
        self.assertEqual(result['timed_out'], 1)
        self.assertEqual(result['completed'], 1)
        self.assertEqual(result['failed'], 0)
        self.assertIsNone(result['latency_ms'])
        self.assertIsNotNone(result['unsuccessful_latency_ms'])


if __name__ == '__main__':
    unittest.main()
