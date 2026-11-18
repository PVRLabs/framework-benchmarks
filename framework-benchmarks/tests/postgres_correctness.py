#!/usr/bin/env python3
"""Destructive framework-neutral HTTP/SQL checks on disposable PostgreSQL state.

SQL uses a supplied psql command (including transport if needed). The application
must be running with polling disabled and all prices persisted. No Spring APIs.
"""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from decimal import Decimal
import json
import subprocess
import time
import urllib.error
import urllib.request


def eventually(predicate, timeout=15):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.05)
    raise AssertionError('condition timed out')


def request(base, path, body=None, expected=200):
    req = urllib.request.Request(base + path,
        data=None if body is None else json.dumps(body).encode(),
        method='GET' if body is None else 'PUT', headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        assert response.status == expected, (path, response.status, raw)
        return json.loads(raw, parse_float=Decimal) if raw else None


class Database:
    def __init__(self, command):
        self.command = command

    def sql(self, statement):
        return subprocess.run(self.command, input=statement, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True, timeout=20).stdout.strip()

    @contextmanager
    def transaction(self, statement):
        # psql stays connected with its transaction open until the caller commits.
        process = subprocess.Popen(self.command, stdin=subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
        try:
            process.stdin.write('BEGIN;\n\\o /dev/null\n' + statement + "\n\\o\n\\echo LOCKED\n")
            process.stdin.flush()
            # Readiness comes from the DB after acquiring locks, never a guessed sleep.
            import selectors
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                assert selector.select(20), 'transaction did not acquire locks'
                assert process.stdout.readline().strip() == 'LOCKED'
            yield
            process.stdin.write('COMMIT;\n')
            process.stdin.flush()
            process.stdin.close()
            assert process.wait(timeout=20) == 0, process.stderr.read()
        finally:
            if process.poll() is None:
                process.stdin.close()  # EOF rolls back on failure.
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()


def seed(db):
    assert db.sql('SELECT count(*) FROM users;') == '1000'
    assert db.sql("SELECT count(*) FROM users WHERE name <> 'User ' || id;") == '0'
    assert db.sql('SELECT count(*) FROM portfolio_holdings;') == '3000'
    assert db.sql('SELECT id,user_count FROM portfolio_seed;') == '1|1000'
    assert db.sql("""SELECT count(*) FROM users u CROSS JOIN
        (VALUES ('AAPL',0),('GOOG',1),('NVDA',2)) s(symbol,ordinal)
        LEFT JOIN portfolio_holdings h ON h.user_id=u.id AND h.symbol=s.symbol
        WHERE h.quantity IS DISTINCT FROM (1+(u.id*7+s.ordinal*11)%100)::numeric;""") == '0'
    print('PASS: independent SQL seed counts, names, every quantity and marker', flush=True)


def check(base, db):
    def edit(user, symbol, quantity):
        return request(base, f'/users/{user}/holdings/{symbol}', {'quantity': quantity}, 204)

    # User 1 was emptied by the shared HTTP test. An absent holding still locks
    # the user; a second symbol must wait while another user remains editable.
    with ThreadPoolExecutor(max_workers=12) as executor:
        with db.transaction('SELECT id FROM users WHERE id=1 FOR UPDATE;'):
            blocked = executor.submit(edit, 1, 'AAPL', 7)
            other_symbol = executor.submit(edit, 1, 'GOOG', 3)
            eventually(lambda: int(db.sql("SELECT count(*) FROM pg_stat_activity WHERE usename='fb_baseline' AND wait_event_type='Lock';")) == 2)
            executor.submit(edit, 2, 'NVDA', 9).result(timeout=5)
            assert not blocked.done() and not other_symbol.done()
        blocked.result(timeout=5)
        other_symbol.result(timeout=5)
        assert db.sql("SELECT quantity FROM portfolio_holdings WHERE user_id=1 AND symbol='AAPL';") == '7.000000'

        # Commit ordering: the independent writer commits 8 before the queued
        # absolute assignment commits 11. Submission timing is not the oracle.
        with db.transaction("SELECT id FROM users WHERE id=1 FOR UPDATE; UPDATE portfolio_holdings SET quantity=8 WHERE user_id=1 AND symbol='AAPL';"):
            second = executor.submit(edit, 1, 'AAPL', 11)
            eventually(lambda: db.sql("SELECT count(*) FROM pg_stat_activity WHERE usename='fb_baseline' AND wait_event_type='Lock';") == '1')
            assert request(base, '/users/1/portfolio')['holdings'][0]['quantity'] == 7
        second.result(timeout=5)
        assert db.sql("SELECT quantity FROM portfolio_holdings WHERE user_id=1 AND symbol='AAPL';") == '11.000000'

        jobs = [executor.submit(edit, 1, ('AAPL','GOOG','NVDA')[i % 3], i % 5) for i in range(48)]
        for job in jobs:
            job.result(timeout=20)
        assert db.sql('SELECT count(*) FROM portfolio_holdings WHERE user_id=1;') in ('1','2','3')
        for symbol in ('AAPL','GOOG','NVDA'):
            edit(1, symbol, 1)
        assert db.sql('SELECT count(*) FROM portfolio_holdings WHERE user_id=1 AND quantity=1;') == '3'
        print('PASS: held user lock, different-user independence, commit order, concurrent insert/update/delete', flush=True)

        # Force all pool connections to be occupied by distinct blocked edits.
        with db.transaction('SELECT id FROM users WHERE id BETWEEN 10 AND 13 ORDER BY id FOR UPDATE;'):
            jobs = [executor.submit(edit, user, 'AAPL', 5) for user in range(10,14)]
            eventually(lambda: db.sql("SELECT count(*) FROM pg_stat_activity WHERE usename='fb_baseline' AND wait_event_type='Lock';") == '4')
            fifth = executor.submit(edit, 14, 'AAPL', 6)
            time.sleep(.2)
            assert not fifth.done()
            assert db.sql("SELECT count(*) FROM pg_stat_activity WHERE usename='fb_baseline';") == '4'
        for job in jobs + [fifth]:
            job.result(timeout=5)
        print('PASS: four occupied app connections, fifth request queued, administrative SQL remains available', flush=True)

    before = request(base, '/users/1/portfolio')
    # Stage a partial new quote batch, read while uncommitted, then commit all
    # three. Concurrent readers must see complete old or complete new totals.
    insert = """INSERT INTO quote_samples(fetched_at,cycle,sample_index,market_time,symbol,price)
        VALUES (now(),5,0,'09:30','AAPL',10),(now(),5,0,'09:30','GOOG',20),(now(),5,0,'09:30','NVDA',30);"""
    with ThreadPoolExecutor(max_workers=4) as executor:
        def reads():
            return [request(base, '/users/1/valuation')['totalValue'] for _ in range(40)]
        with db.transaction(insert):
            assert request(base, '/users/1/portfolio') == before
            readers = [executor.submit(reads) for _ in range(4)]
            assert request(base, '/users/1/valuation')['totalValue'] == before['totalValue']
        totals = [value for reader in readers for value in reader.result(timeout=15)]
        assert set(totals) <= {before['totalValue'], Decimal(60)}, set(totals)
    assert request(base, '/users/1/valuation')['totalValue'] == 60
    print('PASS: valuation sees committed quote snapshots across atomic batch commit', flush=True)
