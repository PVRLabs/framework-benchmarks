# Avaje Jex + CoilBase Portfolio

Market Replay Portfolio using Avaje Jex 3.6, Avaje HTTP 3.12.1 generated
controllers, CoilBase Core/Jex 0.1.0-preview5, HikariCP 7.0.2 and PostgreSQL
JDBC 42.7.8. JDK 21+ is required. CoilBase resolves through the public repository
`https://pvrlabs.github.io/maven/` declared in the POM.

```sh
mvn -f framework-benchmarks/jex-coilbase/pom.xml package
java -jar framework-benchmarks/jex-coilbase/target/portfolio-jex-coilbase.jar
```

Keep `target/lib/` beside the JAR when deploying. Services/repositories are
ordinary Java objects wired explicitly through constructors; no DI runtime or
Spring/Quarkus adapter is used. CoilBase owns local transactions over a Hikari
pool capped at four, with READ COMMITTED isolation. The unchanged reference
schema, seed formula and marker preserve edited data across restart. User-row
locks serialize edits, while valuation reads one SQL snapshot.

Configuration: `SERVER_PORT` (8080), `MARKET_DB_URL`
(`jdbc:postgresql://127.0.0.1:15432/fb_baseline`), `MARKET_DB_USER` and
`MARKET_DB_PASSWORD` (both `fb_baseline`, Framework Benchmarks baseline),
`PORTFOLIO_SEED_USERS` (1000), `MARKET_FIXTURE_URL`
(`http://127.0.0.1:8090/quotes`), `MARKET_POLL_ENABLED` (true),
`MARKET_POLL_INTERVAL_MS` (60000) and `MARKET_POLL_INITIAL_DELAY_MS` (0).
The application uses the same fixed-delay JDK poller and fixture validation as
the reference. The CoilBase Jex lifecycle owns the pool; Jex shutdown stops the
poller. Operational DB health is provided at `/healthz`;
the endpoint uses CoilBase’s `DatabaseHealth` probe on the same pool.
Readiness at `/readyz` additionally requires the seed marker and persisted prices.
Business failures use CoilBase’s built-in error mappings: HTTP 400/404/503 with
`invalid_holding`, `user_not_found` or `market_prices_unavailable` error codes.
These framework-specific bodies differ from Spring’s problem-detail payloads. Framework JSON
parsing failures use CoilBase Jex's safe bad-request response; unexpected errors
are sanitized and logged.

With the existing PostgreSQL 18 VM and tunnel from
[reproduction guide](../../README.md#postgresql-correctness), run the shared suite:

```sh
python3 framework-benchmarks/scripts/verify-postgres.py --jex \
  --output framework-benchmarks/evidence/jex-new-run
```

This destructively resets the dedicated disposable database, reuses the same
HTTP/SQL assertions and fixture, and retains logs, settings, package hashes and
per-launch configuration. Functional host-JVM verification does not establish
colocated 512 MiB feasibility or performance. No monitoring is enabled.

Application logging uses `System.Logger`. HikariCP's transitive SLF4J API is
routed to JUL through runtime `slf4j-jdk14` 2.0.17; no logging configuration is
required.
