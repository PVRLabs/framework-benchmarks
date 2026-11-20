# Framework Benchmarks v1 suite

Run Jex, Quarkus, Spring Boot, and Micronaut in that order in each of two rounds.
Every run uses the public synthetic replay. The runner records and checks the
fixture and workload hashes. The [pre-release archive](evidence/v1-accepted/)
contains the earlier three-candidate comparison using historical prices.

Follow the [v1 protocol](protocol-v1.md) for JVM flags, PostgreSQL settings,
pool cap, phases, traffic, sampling, and acceptance criteria. All four
candidates run sequentially on one Linux QEMU/KVM Ubuntu guest with one vCPU,
512 MiB, no swap, PostgreSQL 18.7 and OpenJDK HotSpot 27+35-2325.

## Prepare on the Linux host

Use the [VM setup and correctness instructions](../README.md#vm-setup). Build
all four packages fresh on Linux and run the shared PostgreSQL verifier for each.
Confirm that the exact PostgreSQL package and JDK are installed:

```sh
test "$(tools/vm.sh exec fb-512 dpkg-query -W -f='${Version}' postgresql-18)" = 18.7-1.pgdg24.04+2
tools/vm.sh exec fb-512 /opt/boot27/bin/java -version
```

Prepare local bundles and choose a fresh guest release prefix. The commands
below use `work/bundles` and `/tmp/fb-v1-review`.

```sh
mkdir -p work/bundles/{jex-coilbase,quarkus-coilbase,micronaut-data-jdbc}
cp -a framework-benchmarks/jex-coilbase/target/{portfolio-jex-coilbase.jar,lib} work/bundles/jex-coilbase/
cp -a framework-benchmarks/quarkus-coilbase/target/quarkus-app work/bundles/quarkus-coilbase/
cp -a framework-benchmarks/micronaut-data-jdbc/target/distribution/. work/bundles/micronaut-data-jdbc/

java -Djarmode=tools -jar market-replay-portfolio/app/target/market-replay-portfolio-0.1.0-SNAPSHOT.jar \
  extract --destination work/bundles/spring-boot
mv work/bundles/spring-boot/{market-replay-portfolio-0.1.0-SNAPSHOT,application}.jar

for candidate in jex-coilbase quarkus-coilbase spring-boot micronaut-data-jdbc; do
  cp framework-benchmarks/scripts/colocated-guest.py tools/benchmark-preflight.py "work/bundles/$candidate/"
  tools/prepare.sh fb-512 "work/bundles/$candidate" "/tmp/fb-v1-review/$candidate" "work/capture-$candidate"
done
```

Stop the correctness tunnel once finished. Smoke both rounds with short windows:

```sh
python3 framework-benchmarks/scripts/colocated-suite.py run --vm fb-512 \
  --protocol v1 --preparation --output work/v1-preparation \
  --bundle jex-coilbase=/tmp/fb-v1-review/jex-coilbase \
  --bundle quarkus-coilbase=/tmp/fb-v1-review/quarkus-coilbase \
  --bundle spring-boot=/tmp/fb-v1-review/spring-boot \
  --bundle micronaut-data-jdbc=/tmp/fb-v1-review/micronaut-data-jdbc
```

Review the phase completion, inputs, runtime and cleanup in the generated
preparation report before authorizing measurement.

## Run after review

Run the same suite command without `--preparation` and with a fresh output
directory such as `--output work/v1-001`. This uses 30 seconds
of idle, 30 seconds at 5 RPS, 125 seconds of warm-up at 40 RPS and 185 seconds
of sustained measurement at 40 RPS after the v1 startup and stabilization
steps. Keep the eight run directories and the suite manifest together.

Check the v1 acceptance criteria and review polling, resource pressure and
normal cleanup. Regenerate the report offline and compare it byte for byte
before selecting any new evidence for publication.

```sh
python3 framework-benchmarks/scripts/colocated-suite.py report work/v1-001/suite.json
```
