#!/usr/bin/env python3
"""Bounded, rate-paced HTTP workload; standard library only, outside the app JVM."""
import argparse
from collections import Counter
import json
import http.client
import math
from pathlib import Path
import queue
import random
import threading
import time
import urllib.error
import urllib.request
import urllib.parse


def percentiles(values):
    ordered = sorted(values)
    if not ordered:
        return None
    return {f'p{p}': ordered[math.ceil(len(ordered) * p / 100) - 1]
            for p in (50, 95, 99)}


def summarize(rows):
    statuses = Counter(row['status'] for row in rows)
    submitted = [row for row in rows if row['outcome'] != 'unsent']
    successful = [row for row in submitted if row['outcome'] == 'success']
    return dict(
        scheduled=len(rows), submitted=len(submitted), completed=len(submitted),
        requests=len(submitted), successful=len(successful),
        failed=sum(row['outcome'] == 'failed' for row in rows),
        timed_out=sum(row['outcome'] == 'timeout' for row in rows),
        unsent=len(rows) - len(submitted), errors=len(submitted) - len(successful),
        statuses=dict(statuses),
        latency_ms=percentiles(row['end_to_end_ms'] for row in successful),
        http_ms=percentiles(row['http_ms'] for row in successful),
        unsuccessful_latency_ms=percentiles(row['end_to_end_ms'] for row in submitted
                                           if row['outcome'] != 'success'),
        dispatch_lag_ms=percentiles(row['dispatch_lag_ms'] for row in rows),
        queue_wait_ms=percentiles(row['queue_wait_ms'] for row in submitted),
    )


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def run(config):
    config = {'concurrency': 8, **config}
    config.setdefault('pending_capacity', config['concurrency'])
    for key in ('rate', 'duration_seconds', 'timeout_seconds'):
        value = config[key]
        if not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
            raise ValueError(f'{key} must be finite and positive')
    for key in ('users', 'concurrency', 'pending_capacity'):
        if not isinstance(config[key], int) or isinstance(config[key], bool) or config[key] < 1:
            raise ValueError(f'{key} must be a positive integer')
    parsed_url = urllib.parse.urlsplit(config['base_url'])
    if parsed_url.scheme not in ('http', 'https') or not parsed_url.hostname or parsed_url.query or parsed_url.fragment:
        raise ValueError('base_url must be an HTTP(S) URL without query or fragment')
    _ = parsed_url.port  # Validate an explicitly supplied port before starting threads.
    operations = config['operations']
    allowed = {'portfolio', 'edit', 'valuation', 'latest', 'history'}
    if not operations or set(operations) - allowed:
        raise ValueError('unknown or empty operations')
    if any(not isinstance(w, (int, float)) or not math.isfinite(w) or w < 0 for w in operations.values()) or sum(operations.values()) <= 0:
        raise ValueError('operation weights must be finite, nonnegative and sum to more than zero')
    rng = random.Random(config['seed'])
    jobs = queue.Queue(maxsize=config['pending_capacity'])
    slots = math.ceil(config['rate'] * config['duration_seconds'])
    # Plan the full sequence before starting the clock. Skips never change the RNG.
    plan = []
    for slot in range(slots):
        operation = rng.choices(list(operations), weights=list(operations.values()))[0]
        user = rng.randint(1, config['users'])
        symbol = rng.choice(['AAPL', 'GOOG', 'NVDA'])
        quantity = rng.randint(0, 10000) / 100
        path = {'portfolio': f'/users/{user}/portfolio', 'valuation': f'/users/{user}/valuation',
                'edit': f'/users/{user}/holdings/{symbol}', 'latest': '/api/quotes/latest',
                'history': '/api/quotes/history'}[operation]
        body = json.dumps({'quantity': quantity}).encode() if operation == 'edit' else None
        request = urllib.request.Request(config['base_url'].rstrip('/') + path, data=body,
                                         headers={'Content-Type': 'application/json'},
                                         method='PUT' if body is not None else 'GET')
        plan.append((dict(slot=slot, operation=operation, path=path,
                          quantity=quantity if body is not None else None), request))

    def worker():
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        while True:
            job = jobs.get()
            if job is None:
                return
            row, request, due, dispatched = job
            began = time.monotonic()
            outcome, status = 'failed', 'transport_error'
            try:
                with opener.open(request, timeout=config['timeout_seconds']) as response:
                    response.read()
                    status = str(response.status)
                    expected = '204' if row['operation'] == 'edit' else '200'
                    if status == expected:
                        outcome = 'success'
            except urllib.error.HTTPError as error:
                status = str(error.code)
                error.close()
            except (OSError, http.client.HTTPException, ValueError) as error:
                reason = getattr(error, 'reason', error)
                if isinstance(reason, TimeoutError):
                    outcome, status = 'timeout', 'timeout'
                row['error'] = str(error)
            ended = time.monotonic()
            row.update(outcome=outcome, status=status,
                       started_seconds=began - started, completed_seconds=ended - started,
                       queue_wait_ms=(began - dispatched) * 1000,
                       http_ms=(ended - began) * 1000,
                       end_to_end_ms=(ended - due) * 1000)

    workers = [threading.Thread(target=worker) for _ in range(config['concurrency'])]
    for thread in workers:
        thread.start()
    started = time.monotonic()
    deadline = started + config['duration_seconds']
    interval = 1 / config['rate']
    try:
        for row, request in plan:
            due = started + row['slot'] * interval
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            dispatched = time.monotonic()
            row.update(scheduled_seconds=row['slot'] * interval,
                       dispatch_lag_ms=(dispatched - due) * 1000)
            reason = None
            if dispatched >= min(deadline, due + interval):
                reason = 'missed_slot'
            else:
                try:
                    jobs.put_nowait((row, request, due, dispatched))
                except queue.Full:
                    reason = 'queue_full'
            if reason:
                row.update(outcome='unsent', status=reason)
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(remaining)
    finally:
        for _ in workers:
            jobs.put(None)
        for thread in workers:
            thread.join()

    rows = [row for row, _ in plan]
    aggregate = summarize(rows)
    sent = [row for row in rows if row['outcome'] != 'unsent']
    events = [(row[key], delta) for row in sent
              for key, delta in [('started_seconds', 1), ('completed_seconds', -1)]]
    peak = inflight = 0
    for _, delta in sorted(events):
        inflight += delta
        peak = max(peak, inflight)
    duration = config['duration_seconds']
    elapsed = max(duration, max((row['completed_seconds'] for row in sent), default=0))
    return dict(
        config=config, **aggregate, offered=slots,
        dropped_client_capacity=aggregate['statuses'].get('queue_full', 0),
        elapsed_including_drain_seconds=elapsed,
        offered_requests_per_second=slots / duration,
        submitted_requests_per_second=len(sent) / duration,
        achieved_requests_per_second_including_drain=len(sent) / elapsed,
        successful_requests_per_second_including_drain=aggregate['successful'] / elapsed,
        successful_requests_per_second_in_window=sum(
            row['outcome'] == 'success' and row['completed_seconds'] < duration
            for row in sent) / duration,
        peak_in_flight=peak, generator_saturated=bool(aggregate['unsent']),
        operations={operation: summarize([row for row in rows if row['operation'] == operation])
                    for operation in operations},
        observations=rows,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('default.json'))
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = run(json.loads(args.config.read_text()))
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + '\n')
    print(rendered)
    if result['unsent'] or result['errors']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
