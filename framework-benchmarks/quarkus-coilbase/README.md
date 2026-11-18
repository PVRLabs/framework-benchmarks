# Quarkus REST + CoilBase Portfolio

Market Replay Portfolio using Quarkus REST/Jackson 3.40.1, CoilBase Core
0.1.0-preview5 (Jdbi), PostgreSQL JDBC and Quarkus-managed Agroal (maximum four
connections, READ COMMITTED). Build with JDK 21 or newer:

```sh
mvn -f framework-benchmarks/quarkus-coilbase/pom.xml package
java -jar framework-benchmarks/quarkus-coilbase/target/quarkus-app/quarkus-run.jar
```

CoilBase preview artifacts resolve from the public PVR Labs Maven repository
`https://pvrlabs.github.io/maven/`, declared in the POM; they are not on Maven
Central. No credentials or local CoilBase installation are required. To verify
resolution independently of the normal local cache, use a new empty directory:

```sh
mvn -Dmaven.repo.local=/private/tmp/portfolio-quarkus-clean-cache \
  -f framework-benchmarks/quarkus-coilbase/pom.xml package
```

Choose a fresh cache path for each verification.

Deploy the complete `target/quarkus-app` directory. Configuration uses
`MARKET_DB_URL`, `MARKET_DB_USER`, `MARKET_DB_PASSWORD`, `SERVER_PORT`,
`MARKET_FIXTURE_URL`, `MARKET_POLL_ENABLED`, `MARKET_POLL_INTERVAL_MS` and
`MARKET_POLL_INITIAL_DELAY_MS`. Defaults match the reference, with a local
`fb_baseline` (Framework Benchmarks baseline) PostgreSQL database.
`PORTFOLIO_SEED_USERS` defaults to 1000.

CoilBase owns local transaction boundaries; datasource JTA enlistment is disabled.
No assumption is made that Quarkus JTA transactions participate in CoilBase
transactions. REST operations run on blocking workers. Edits lock the user row
through commit; valuation joins holdings/latest prices in one statement. Startup
creates the unchanged reference schema and seeds transactionally only without a
seed marker. Quarkus owns datasource shutdown. The reference JDK fixed-delay
poller starts on the Quarkus startup event after schema/seed initialization and
stops during CDI destruction. Poll failures retry on the next scheduled attempt.

`/readyz` checks the seed and persisted prices against the database each time.
`/actuator/health` provides a compatible operational DB-health route; this is an
application endpoint rather than a Spring Actuator dependency. Business errors
use problem JSON with equivalent status and meaning; diagnostic wording differs.

Reuse the existing prepared PostgreSQL 18 database and shared VM tunnel described
in [reproduction guide](../../README.md#postgresql-correctness), then run:

```sh
python3 framework-benchmarks/scripts/verify-postgres.py --quarkus \
  --output framework-benchmarks/evidence/quarkus-new-run
```

This resets the disposable `fb_baseline` database. The verifier runs the same
HTTP/SQL, controlled concurrency, ingestion-fault, restart, outage and reset
checks as the reference. These host-JVM checks establish functional behavior;
they do not establish colocated VM feasibility or performance.
