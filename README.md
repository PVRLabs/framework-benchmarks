# Framework Benchmarks

Framework Benchmarks is an extensible, cross-language project for comparing
application frameworks under realistic resource constraints. It measures readiness,
memory consumption, throughput, and latency with equivalent applications, shared
workloads, and documented environments. Correctness checks establish comparable
behavior before measurement.

## Featured benchmark

The accepted v1 comparison is the project's first benchmark.
[Avaje Jex](https://avaje.io/jex/) + [CoilBase](https://github.com/PVRLabs/coilbase),
[Quarkus REST](https://quarkus.io/guides/rest/) + [CoilBase](https://github.com/PVRLabs/coilbase),
and [Spring Boot](https://spring.io/projects/spring-boot/) +
[Spring JDBC](https://docs.spring.io/spring-framework/reference/data-access/jdbc.html)
implement the same Market Replay Portfolio application and share a PostgreSQL schema, replay
fixture, correctness contract, and measurement protocol.

[Market Replay Portfolio](market-replay-portfolio/README.md) simulates an
investment portfolio service with portfolio reads and updates, valuations,
and periodic market price ingestion. These operations exercise HTTP, database
access, transactions, and background processing.

The runs used a Linux host (AMD Ryzen 7 4700U) running a QEMU/KVM Ubuntu VM
with 1 vCPU, 512 MiB RAM, and no swap. The application and PostgreSQL shared
the VM. Both rounds used OpenJDK 27 (build `27+35-2325`) and PostgreSQL
18.7 (Ubuntu package `18.7-1.pgdg24.04+2`). Sustained load was offered at 40 RPS.

| Target | HTTP framework | Persistence | Connection pool | PostgreSQL JDBC | Artifact manifests |
| --- | --- | --- | --- | --- | --- |
| Jex + CoilBase | Avaje Jex 3.6, Avaje HTTP 3.12.1 | CoilBase Core and CoilBase Jex adapter (both 0.1.0-preview5) | HikariCP 7.0.2 | 42.7.8 | [R1](framework-benchmarks/evidence/v1-accepted/round-01/jex-coilbase/environment/artifacts.txt), [R2](framework-benchmarks/evidence/v1-accepted/round-02/jex-coilbase/environment/artifacts.txt) |
| Quarkus + CoilBase | Quarkus REST 3.40.1 | CoilBase Core 0.1.0-preview5 | Agroal 3.2.1 | 42.7.13 | [R1](framework-benchmarks/evidence/v1-accepted/round-01/quarkus-coilbase/environment/artifacts.txt), [R2](framework-benchmarks/evidence/v1-accepted/round-02/quarkus-coilbase/environment/artifacts.txt) |
| Spring Boot + JDBC | Spring Boot 4.1.1, Spring MVC 7.0.9, Tomcat 11.0.24 | Spring JDBC 7.0.9 | HikariCP 7.0.2 | 42.7.13 | [R1](framework-benchmarks/evidence/v1-accepted/round-01/spring-boot/environment/artifacts.txt), [R2](framework-benchmarks/evidence/v1-accepted/round-02/spring-boot/environment/artifacts.txt) |

### Why CoilBase instead of Hibernate in Quarkus?

Spring Boot + Spring JDBC is the reference implementation. This benchmark
compares lightweight, SQL-first applications with equivalent functionality.
Quarkus REST handles HTTP, Quarkus supplies JDBC connectivity, and Agroal
manages the connection pool. The Quarkus target uses only `coilbase-core`
from CoilBase, with Jdbi for SQL access and explicit transaction management.
Neither `coilbase-jex` nor Avaje Jex is part of this target. We expect
CoilBase itself to add negligible overhead, but have not measured it separately.

In the earlier [Hibernate isolation experiment](https://pvrlabs.xyz/java-performance/experiments/jpa-memory-experiment-revisited.html),
the same demo app used either Jdbi or direct Hibernate without Spring Data JPA.
Under the mixed workload, the Jdbi implementation used about 55–58 MiB less
process RSS (95.2–96.4 MiB versus 151.8–153.6 MiB). That is an application-level
difference, not an isolated measurement of Hibernate's library overhead. It
motivates keeping Hibernate ORM outside the current SQL-first comparison.

Readers interested in Hibernate or another persistence approach are welcome to
reproduce the benchmark and submit a proposal or PR with supporting measurements.
Additions should answer a specific comparison question.

![Accepted v1 results for Jex, Quarkus, and Spring Boot in rounds 1 and 2. Jex had the fastest readiness and lowest sampled peak app RSS in both rounds. Sustained p99 ranged from 9.40 to 10.19 ms.](docs/featured-v1.svg)

Readiness is time to the first successful database-backed readiness check.
RSS is the sampled peak for the application during sustained measurement.
Sustained p99 includes client scheduling and SSH transport.

See the [full HTML report](framework-benchmarks/evidence/v1-accepted/report.html),
[recorded evidence](framework-benchmarks/evidence/v1-accepted/), and
[frozen v1 protocol](framework-benchmarks/protocol-v1.md).

The maintainer manually selects the featured benchmark from local or CI runs.
CI provides independent reproduction and verification. Its results do not
automatically replace the featured measurements.

Each target is one evolving implementation. An improvement such as Spring Boot
AOT can replace its current configuration within the same target. Historical
results stay tied to the exact component versions and configuration used.

The accepted v1 runs used historical market prices. The public checkout uses
synthetic prices with the same symbols, sample count, and replay cadence.
The public evidence omits historical prices and derived valuations from the
post-load portfolio snapshots. The accepted performance measurements are
unchanged. Runs with the public fixture produce separate measurements.

The archived evidence retains slot observations, memory samples, pressure
counters, and artifact hashes. Host identifiers and local paths were redacted,
and infrastructure captures unrelated to report regeneration were omitted.

## Reproducing results

Run commands from the checkout root. Build with JDK 25 and Maven 3.9:

```sh
mvn -B -f market-replay-portfolio/app/pom.xml package
mvn -B -f framework-benchmarks/quarkus-coilbase/pom.xml package
mvn -B -f framework-benchmarks/jex-coilbase/pom.xml package
python3 -m unittest discover -s framework-benchmarks/tests
```

### Correctness CI

[GitHub Actions](.github/workflows/ci.yml) runs on pushes and pull requests.
It builds all three applications on Ubuntu with Temurin 25.0.4.1 and
Maven 3.9.9, runs the available Java tests, checks the Linux distributions,
and runs the fixture, workload and harness tests. It also compares a freshly
generated offline report byte for byte with the accepted HTML.

### VM setup

Use an x86-64 Linux host with working `/dev/kvm`, QEMU, Lima 2.2+, OpenSSH,
Python 3, Bash and standard archive and checksum tools. The pinned Ubuntu image
allocates one vCPU and 512 MiB. Setup disables swap and update timers, installs
PostgreSQL 18, and verifies the pinned OpenJDK archive before extraction.

```sh
tools/vm.sh create fb-512 framework-benchmarks/vm-linux.yaml
tools/vm.sh start fb-512
curl -fL -o fb-jdk.tar.gz https://download.java.net/java/GA/jdk27/55ce5470a6294008af0057ff4626d0e5/35/GPL/openjdk-27_linux-x64_bin.tar.gz
printf '%s  %s\n' 95fc37eb3a18a27a26d5904c2d89d52bace8dafa9a078ca27f4747fbc4bf070b fb-jdk.tar.gz | sha256sum -c -
tools/vm.sh put fb-512 fb-jdk.tar.gz /tmp/fb-jdk.tar.gz
tools/vm.sh put fb-512 framework-benchmarks/scripts /tmp/fb-setup
tools/vm.sh exec fb-512 sudo bash /tmp/fb-setup/setup-vm.sh
```

The v1 PostgreSQL profile adapts Theory A from the
[PostgreSQL 18 low-memory experiment](https://pvrlabs.xyz/java-performance/experiments/postgresql-low-memory.html)
to leave more memory for the application sharing the VM. That experiment used
a read-only workload with no colocated application. Here, PostgreSQL allows
10 connections instead of five, including one reserved superuser slot.
See the [v1 PostgreSQL settings](framework-benchmarks/scripts/prepare-postgres.sh).

### PostgreSQL correctness

Use the dedicated disposable database created above. The checks reset its
tables and temporarily change its availability. Start PostgreSQL and leave
the SSH tunnel running in a separate terminal:

```sh
tools/vm.sh exec fb-512 sudo systemctl start postgresql@18-main
tools/vm.sh tunnel fb-512 15432 5432
```

Run the checks sequentially, with a new output path each time:

```sh
python3 framework-benchmarks/scripts/verify-postgres.py --output work/spring
python3 framework-benchmarks/scripts/verify-postgres.py --quarkus --output work/quarkus
python3 framework-benchmarks/scripts/verify-postgres.py --jex --output work/jex
tools/vm.sh exec fb-512 sudo systemctl stop postgresql@18-main
```

### Benchmark execution

Run performance reproductions manually on a dedicated Linux QEMU/KVM host
with stable resources for the guest, replay server, and load driver. Use the
VM and runtime settings in the [frozen v1 protocol](framework-benchmarks/protocol-v1.md).
Check the installed PostgreSQL package before reproducing the accepted
environment. The setup script installs PostgreSQL 18 from PGDG, whose default
package can change. The following check must pass for the accepted package
version.

```sh
test "$(tools/vm.sh exec fb-512 dpkg-query -W -f='${Version}' postgresql-18)" = 18.7-1.pgdg24.04+2
```

Build fresh packages on Linux and pass the PostgreSQL correctness checks above
before measuring. Keep the preparation and measured outputs under separate
new paths in `work/`. Review the new suite against the protocol's acceptance
criteria. The accepted report and measurements remain in
`framework-benchmarks/evidence/v1-accepted/`.

Create three bundle directories. Each includes `colocated-guest.py` from
`framework-benchmarks/scripts/` and `benchmark-preflight.py` from `tools/`.
Copy the Jex JAR and its adjacent `lib/` together. Copy the entire Quarkus
`quarkus-app/` directory. For Spring, extract the Boot layout with
`java -Djarmode=tools -jar market-replay-portfolio/app/target/market-replay-portfolio-0.1.0-SNAPSHOT.jar extract --destination work/spring-bundle`.
Name the extracted launcher `application.jar` and keep its adjacent libraries.

Use `tools/prepare.sh fb-512 LOCAL_BUNDLE GUEST_BUNDLE NEW_CAPTURE_DIR` for
each bundle. The following command checks both rounds with short windows.
Use a fresh output directory and omit `--preparation` for measurement.

```sh
python3 framework-benchmarks/scripts/colocated-suite.py run --vm fb-512 \
  --protocol v1 --preparation --output work/preparation \
  --bundle jex-coilbase=/tmp/fb-jex --bundle quarkus-coilbase=/tmp/fb-quarkus \
  --bundle spring-boot=/tmp/fb-spring
```

### Offline report

```sh
python3 framework-benchmarks/scripts/colocated-suite.py report framework-benchmarks/evidence/v1-accepted/suite.json
```

The report uses Python's standard library and writes HTML beside the manifest.

## Future comparisons

The project will support additional framework implementations, runtimes,
languages, and benchmark configurations (flavors). Possible comparisons
include Helidon, additional Quarkus configurations, OpenJ9, and GraalVM Native
Image. How flavors will be organized and selected is still open.
