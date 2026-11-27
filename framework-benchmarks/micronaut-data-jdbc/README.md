# Micronaut HTTP + Micronaut Data JDBC

This Market Replay Portfolio v1 candidate serves HTTP with Micronaut and Netty.
Micronaut Data JDBC provides compile-time PostgreSQL repository implementations
and HikariCP manages up to four connections. The pool grows on demand and waits
up to two seconds to acquire a connection. The Data JDBC dependency brings in
the Jakarta Persistence API transitively. The app uses Micronaut Data JDBC for
all persistence.

| Component | Version |
| --- | --- |
| Micronaut Platform | 5.2.1 |
| Micronaut Framework and HTTP Server Netty | 5.2.11 |
| Micronaut Data JDBC | 5.2.0 |
| Micronaut SQL JDBC Hikari integration | 7.2.0 |
| HikariCP | 7.1.0 |
| PostgreSQL JDBC | 42.7.13 |
| Netty | 4.2.18.Final |
| Jackson Databind | 3.2.3 |
| Logback | 1.5.37 |

The [Maven POM](pom.xml) uses the Micronaut platform to align dependency
versions and pins PostgreSQL JDBC to the driver version used by Spring Boot
and Quarkus in the pre-release comparison.

The build packages the reference PostgreSQL schema. Seed initialization is
transactional and uses the same row-by-row seed formula as the reference.
Holding edits lock the user row through commit and use a PostgreSQL upsert for
nonzero quantities. Valuation reads join holdings to the latest prices in one
statement. Each validated quote set commits in one transaction. The poller uses
the shared fixed-delay JDK scheduler and retries on its next interval after an
ingestion failure. HTTP handlers that use JDBC run on Micronaut's blocking
executor.

From the repository root with JDK 25 and Maven 3.9:

```sh
mvn -B -f framework-benchmarks/micronaut-data-jdbc/pom.xml clean package
```

The deployable distribution is `target/distribution/` inside this module.
Keep `portfolio-micronaut-data-jdbc.jar` with its adjacent `lib/` directory
and launch with `java -jar portfolio-micronaut-data-jdbc.jar`. The app binds to
loopback and uses the suite's `SERVER_PORT`, `MARKET_DB_*`,
`PORTFOLIO_SEED_USERS` and `MARKET_POLL_*` inputs. It also accepts
`MARKET_FIXTURE_URL`. See the [shared PostgreSQL verification instructions](../../README.md#postgresql-correctness)
and the [v2 suite guide](../suite-v2.md).
