# Market Replay Portfolio

Market Replay Portfolio is a sample backend application used by
[Framework Benchmarks](../README.md) to compare application frameworks. It
simulates an investment portfolio service where users own shares and their
portfolio values change as market prices update.

- **Portfolio reads:** Retrieve a user's holdings.
- **Portfolio updates:** Buy or sell shares by changing holdings.
- **Valuations:** Calculate portfolio value using the latest stock prices.
- **Market data:** Periodically fetch prices from a simulated market feed.
- **Price history:** Retrieve recent and historical market prices.

These operations combine HTTP requests, database reads and writes,
transactions, JSON responses, and background processing. The benchmark
measures startup, memory use, throughput, and latency under a shared workload.

The Spring Boot implementation is in `app/`. The CSV fixture serves successive
quote snapshots at the configured replay interval. Each application polls that
fixture, persists quote history in PostgreSQL, and uses persisted prices to
value portfolios. See the [main README](../README.md) for results, methodology, and
build and test commands.
