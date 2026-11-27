# Try your own JVM settings

Pick one question, such as “Does a smaller heap reduce memory without increasing
tail latency?” Change one setting at a time if you want to isolate its effect.

## Run with GitHub Actions

This is the easiest setup if you don’t have benchmark hardware. Hosted runner
hardware and load can vary, so use these results to explore an idea.

1. Open [PVRLabs/framework-benchmarks](https://github.com/PVRLabs/framework-benchmarks)
   and click **Fork**. Enable workflows in your fork’s **Actions** tab if prompted.
2. Run a baseline before editing the config. Open **Actions → JVM Benchmark →
   Run workflow**, select your branch, and start the run. If your fork already
   has custom settings, use a branch with the upstream config for the baseline.
3. In your fork, open `framework-benchmarks/config-v2.json`, click the pencil
   icon, edit the `jvm` array (see [Example JVM settings](#example-jvm-settings)),
   and commit. That commit starts **JVM Benchmark**
   automatically. You can also run it manually with any committed settings.
4. Open the benchmark run. Expand **Run preparation and benchmark measurements**
   for the results table. Under **Artifacts**, download
   `benchmark-results-<run number>-<attempt>` and open `measurement/report.html`
   after extraction. The chart, manifest, and evidence are alongside it.

Preparation gives an early check that the apps start with your JVM settings.
Full measurement takes about 49 minutes plus setup and preparation.
Your fresh measurements appear under `benchmark-results-…` in **JVM Benchmark**.
To reproduce a historical v1 report, use a checkout of the `benchmark-v1` tag.

## Run locally

For a controlled comparison, use any checkout on an x86-64 Linux host with
KVM. Follow the [v2 suite guide](suite-v2.md) to prepare the VM and deploy the
applications once. Rebuild and redeploy reused bundles after pulling runner
changes so they contain the guest runner from your current checkout.

From the repository root, make a config copy for the variant:

```sh
mkdir -p work
cp framework-benchmarks/config-v2.json work/my-jvm.json
```

Edit the copy (see [Example JVM settings](#example-jvm-settings)). Start with
a short baseline preparation run using the upstream config.

```sh
python3 framework-benchmarks/scripts/colocated-suite.py run --vm fb-debian-v1 \
  --guest-run-root /var/tmp/fb-runs --preparation --output work/v1-baseline-prep \
  --bundle jex-coilbase=/var/tmp/fb-v1-review/jex-coilbase \
  --bundle quarkus-coilbase=/var/tmp/fb-v1-review/quarkus-coilbase \
  --bundle spring-boot=/var/tmp/fb-v1-review/spring-boot \
  --bundle micronaut-data-jdbc=/var/tmp/fb-v1-review/micronaut-data-jdbc
```

For variant preparation, repeat with `--config work/my-jvm.json` and
`--output work/v1-variant-prep`. Once both checks pass, repeat each command
without `--preparation` using fresh output directories `work/v1-baseline`
and `work/v1-variant`. Reuse the same host, guest, and bundles.

Regenerate reports only from your own experiment outputs under `work/`.
For example, run
`python3 framework-benchmarks/scripts/colocated-suite.py report work/v1-variant/suite.json`.

## Example JVM settings

Keep the stock arguments and add the four options below to try them together.

```json
[
  "-Xms16m",
  "-Xmx80m",
  "-XX:+UseG1GC",
  "-Duser.timezone=UTC",
  "-XX:TrimNativeHeapInterval=10000",
  "-XX:MinHeapFreeRatio=5",
  "-XX:MaxHeapFreeRatio=10",
  "-XX:G1PeriodicGCInterval=10000"
]
```

`TrimNativeHeapInterval` requires HotSpot on Linux with glibc.
`G1PeriodicGCInterval` requires G1. Both intervals are in milliseconds.
The free ratios guide heap resizing and are percentages. Check the JVM arguments
in the report or in each run’s `guest/effective-jvm-flags.txt`.
[OpenJDK Java options](https://github.com/openjdk/jdk/blob/master/src/java.base/share/man/java.md)
· [JEP 346](https://openjdk.org/jeps/346)

The upstream [config-v2.json](config-v2.json) holds the frozen JVM defaults.
For local runs with another JDK build, install it inside the Debian benchmark
VM. Set `java_executable` to its absolute path inside that VM and `jdk_build`
to the identifier reported by `<java_executable> -version` inside the VM.
GitHub Actions provisions its
own Debian VM with the pinned JDK. Testing a different build there requires
changing the workflow’s VM setup as well as the config.

## Compare results

Compare the baseline and variant for the same application in each round.
Check for errors, timeouts, unsent requests, and OOMs first. Then compare
readiness, peak app RSS, sustained p99 latency, and minimum guest MemAvailable.
Save both reports and their evidence, and note any changes in host or runner
hardware or JDK. The manifest records `java_executable`, `jdk_build`, and
`jvm` and their combined SHA-256 hash.

## Share results

Share your question, config diff, report links, and what you observed in a
[GitHub issue](https://github.com/PVRLabs/framework-benchmarks/issues) or
[pull request](https://github.com/PVRLabs/framework-benchmarks/pulls).

## Optional: add an application

Adding an app requires changes to the application code and runner. Use an existing candidate such as
[Micronaut](micronaut-data-jdbc/README.md) as a starting point. Implement the
[shared correctness contract](foundation.md#shared-correctness-requirements)
against the same PostgreSQL schema and replay fixture. First build the app
and pass the correctness checks. Then wire its bundle and launch command into
the suite and guest runner, and add its build and deployment steps to the
[benchmark workflow](../.github/workflows/benchmark.yml) if you want to run it
on GitHub. Run preparation before collecting measurements and share the runner
changes along with the results.
