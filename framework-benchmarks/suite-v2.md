# Framework Benchmarks v2 suite

Run Jex, Quarkus, Spring Boot, and Micronaut in that order in each of two rounds.
Every run uses the public synthetic replay. The runner records and checks the
fixture and workload hashes. The [pre-release archive](evidence/v1-accepted/)
contains the earlier three-candidate comparison using historical prices.

Follow the [v2 protocol](protocol-v2.md) for JVM flags, PostgreSQL settings,
pool cap, phases, traffic, sampling, and acceptance criteria. All four
candidates run sequentially on one Linux QEMU/KVM Debian 13 guest with one vCPU,
512 MiB, no swap, PostgreSQL 18.7 and OpenJDK HotSpot 27+35-2325.

The [v2 reference results](evidence/v2-reference/README.md) reuse the completed
eight-run Xmx80m dataset; its original external CPU sampling differs from the
current runner instrumentation.

## JVM heap selection

All four application stacks use the same JVM heap settings: `-Xms16m -Xmx80m`
with G1GC.

We evaluated a 70 MiB maximum heap over two rounds of the same 100 RPS
workload. All eight runs completed without request errors, timeouts, dropped
requests or OOM kills. Sampled peak application RSS fell by approximately
4–8 MiB per stack on average. Cumulative sustained-window GC pause time
increased for all four stacks on average, and the longest observed pause
increased for three stacks.

The table shows the longest observed GC pause across both 185-second sustained
measurement windows for each configuration.

| Stack | Longest pause at Xmx80m | Longest pause at Xmx70m |
|---|---:|---:|
| Jex | 10.88 ms | 13.46 ms |
| Quarkus | 20.79 ms | 15.06 ms |
| Spring Boot | 25.76 ms | 32.82 ms |
| Micronaut | 4.38 ms | 16.08 ms |

Sustained p99 latency remained broadly comparable. We retained the 80 MiB
maximum heap as a conservative trade-off between memory footprint, GC behavior
and application headroom. The 70 MiB runs included the new guest CPU counter
instrumentation, which the 80 MiB comparison runs did not; both used external
CPU sampling. These results demonstrate feasibility at 70 MiB under the tested
workload, not long-term stability or a minimum heap requirement.

## Prepare on the Linux host

Use the [VM setup and correctness instructions](../README.md#vm-setup). Build
all four packages fresh on Linux and run the shared PostgreSQL verifier for each.
Confirm that the exact PostgreSQL package and JDK are installed:

```sh
test "$(tools/vm.sh exec fb-debian-v1 dpkg-query -W -f='${Version}' postgresql-18)" = 18.7-1.pgdg13+5
tools/vm.sh exec fb-debian-v1 /opt/boot27/bin/java -version
```

With the database and applications stopped, run preflight and the 30-second
idle sampler. Repeat across two boots and retain both outputs.

```sh
tools/vm.sh exec fb-debian-v1 sudo python3 /tmp/fb-setup/benchmark-preflight.py \
  --require-debian-13 --cpus 1 --min-mem-kib 440001 --max-mem-kib 524287
tools/vm.sh exec fb-debian-v1 bash -s < framework-benchmarks/scripts/sample-idle-guest.sh
```

Review MemAvailable, memory PSI, direct reclaim, allocation stalls and OOM
counter deltas. Verify the deployed bundle hashes and stopped processes after
preparation, then regenerate the report and compare it byte for byte.

Prepare local bundles and choose a fresh guest release prefix. The commands
below use `work/bundles` and `/var/tmp/fb-v1-review`.
Prepare and deploy existing bundles again with the updated
`colocated-guest.py` under a fresh guest release prefix. The host runner now
passes the Java command to that script.

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
  tools/prepare.sh fb-debian-v1 "work/bundles/$candidate" "/var/tmp/fb-v1-review/$candidate" "work/capture-$candidate"
done
```

Stop the correctness tunnel once finished. Smoke both rounds with short windows:

```sh
python3 framework-benchmarks/scripts/colocated-suite.py run --vm fb-debian-v1 \
  --guest-run-root /var/tmp/fb-runs \
  --preparation --fail-fast --output work/v2-preparation \
  --bundle jex-coilbase=/var/tmp/fb-v1-review/jex-coilbase \
  --bundle quarkus-coilbase=/var/tmp/fb-v1-review/quarkus-coilbase \
  --bundle spring-boot=/var/tmp/fb-v1-review/spring-boot \
  --bundle micronaut-data-jdbc=/var/tmp/fb-v1-review/micronaut-data-jdbc
```

The runner checks that the guest evidence directory uses a supported disk
filesystem before starting. Debian mounts /tmp as tmpfs, so keep bundles and
evidence under /var/tmp.

Review the phase completion, inputs, runtime and cleanup in the generated
preparation report before authorizing measurement.

Before deploying bundles, run `tools/provision-benchmark-storage.sh fb-debian-v1`
against the started guest. This installs a persistent disk-backed `/tmp` on
the 512 MiB guest and verifies it after a cold boot. The helper accepts the
name of your benchmark VM if it differs.

## Run after review

The suite reads [the JVM defaults](config-v2.json) when run without
`--config`. See [custom benchmark runs](custom-runs.md) for JVM experiments.

Run the same suite command without `--preparation` and with a fresh output
directory such as `--output work/v2-001`. This uses 30 seconds
of idle, 30 seconds at 5 RPS, 125 seconds of warm-up at 100 RPS and 185 seconds
of sustained measurement at 100 RPS after the startup and stabilization
steps. Keep the eight run directories and the suite manifest together.

Check strict zero-drop acceptance and review polling, resource pressure and
normal cleanup. Regenerate the report offline and compare it byte for byte
before selecting any new evidence for publication.

```sh
python3 framework-benchmarks/scripts/colocated-suite.py report work/v2-001/suite.json
```
