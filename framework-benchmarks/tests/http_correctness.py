#!/usr/bin/env python3
"""Destructive HTTP checks for a disposable, seeded Portfolio deployment.

Run with polling disabled and persisted prices, so separate requests see stable
prices. Adapted from market-replay-portfolio/tests/restart.py; no Spring dependency.
"""
import argparse
from decimal import Decimal
import json
import urllib.error
import urllib.request


def check(base, users=1000):
    def request(path, body=None, expected=200):
        data = None if body is None else body.encode()
        req = urllib.request.Request(base.rstrip('/') + path, data=data,
            method='GET' if body is None else 'PUT',
            headers={'Content-Type': 'application/json'})
        try:
            response = urllib.request.urlopen(req, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            assert response.code == expected, (path, response.code, raw)
            return json.loads(raw, parse_float=Decimal) if raw else None

    assert request('/readyz')['status'] == 'UP'
    latest = request('/api/quotes/latest')
    assert [q['symbol'] for q in latest] == ['AAPL', 'GOOG', 'NVDA']
    assert all(q['price'] > 0 for q in latest)
    history = request('/api/quotes/history')
    assert [q['id'] for q in history] == sorted(q['id'] for q in history)
    for symbol in ('AAPL', 'GOOG', 'NVDA'):
        samples = [q for q in history if q['symbol'] == symbol]
        assert 1 <= len(samples) <= 390
        assert samples[-1] == next(q for q in latest if q['symbol'] == symbol)
    assert len(request(f'/users/{users}/portfolio')['holdings']) == 3
    for quantity in ('10.125', '10.125', '12.345678'):
        request('/users/1/holdings/AAPL', '{"quantity":' + quantity + '}', 204)
        portfolio = request('/users/1/portfolio')
        assert portfolio['userId'] == 1
        assert portfolio['holdings'][0]['quantity'] == Decimal(quantity)
        assert portfolio['totalValue'] == sum(h['quantity'] * h['price'] for h in portfolio['holdings'])
        assert request('/users/1/valuation')['totalValue'] == portfolio['totalValue']
    for body in ('{}', 'null', '{', '{"quantity":null}', '{"quantity":-1}',
                 '{"quantity":0.0000001}', '{"quantity":10000000000000}'):
        request('/users/1/holdings/AAPL', body, 400)
    request('/users/1/holdings/MSFT', '{"quantity":1}', 400)
    request(f'/users/{users+1}/portfolio', expected=404)
    for symbol in ('AAPL', 'GOOG', 'NVDA'):
        request('/users/1/holdings/' + symbol, '{"quantity":0}', 204)
    assert request('/users/1/portfolio')['holdings'] == []
    assert request('/users/1/valuation')['totalValue'] == 0
    print('PASS: HTTP routes, decimals, validation, assignment/delete, latest/history')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', required=True)
    parser.add_argument('--users', type=int, default=1000)
    args = parser.parse_args()
    check(args.base_url, args.users)
