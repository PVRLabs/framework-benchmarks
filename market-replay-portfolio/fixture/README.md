# Market replay fixture data

`data/quotes-2026-09-30.csv` contains 390 synthetic one-minute prices for each
of AAPL, GOOG, and NVDA, from 09:30 through 15:59 America/New_York. Independent seeded random walks are calibrated to broad characteristics of a
historical session, including starting levels and typical minute movements.
The paths are synthetic and do not reproduce historical price changes.
The [metadata](data/metadata.json) records the fixture shape and seed. Replay
uses only this CSV and needs no external data service.

See the [application README](../README.md) for the workload and reproduction guide.
