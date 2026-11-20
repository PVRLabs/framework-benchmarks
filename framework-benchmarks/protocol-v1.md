# Framework Benchmarks protocol v1

The v1 comparison includes Spring Boot + Spring JDBC, Quarkus REST + CoilBase,
Avaje Jex + CoilBase, and Micronaut HTTP + Micronaut Data JDBC. Each must pass
the shared [Portfolio correctness contract](foundation.md#shared-correctness-requirements).
The measurement method was frozen on 2026-11-17. The accepted three-candidate
pre-release archive used historical market prices. The initial v1 comparison
uses the public synthetic CSV for all four candidates. See the
[v1 suite guide](suite-v1.md).

## Environment and inputs

Use a dedicated [Ubuntu QEMU/KVM guest](vm-linux.yaml) with one vCPU,
512 MiB RAM, and no swap. Colocate one candidate and PostgreSQL 18.7. Use the
[compact PostgreSQL settings](scripts/prepare-postgres.sh) and a four-connection
application pool limit for every candidate. Use OpenJDK HotSpot 27+35-2325,
G1, `-Xms16m -Xmx80m`, and UTC. Record effective flags and settings and pin
the package hashes, database schema, seed, replay data, fixture and driver
revisions for each comparison.

Run the load driver and CSV replay on the Linux host outside the guest budget.
The driver reaches the guest via SSH forwarding and uses a fresh HTTP connection
per request. The guest reaches replay through reverse SSH forwarding. Seed 1,000
users. Poll quotes every 60 seconds and use the fixture's 3,600-second replay step.
Each load phase starts a fresh driver process using seed 42, eight workers, eight
pending slots, a five-second socket timeout, and weights of 40/25/25/8/2 for
portfolio reads, edits, valuations, latest quotes and quote history. The host
deadline is the offering window plus 15 seconds. Retain failed requests and
unsent slots in the accounting.

## Execution

Run two rounds on the same guest and physical host, in Jex, Quarkus, Spring Boot,
Micronaut order each round. Before every candidate run, reset the disposable PostgreSQL
database and seed, restart replay, and launch a fresh app. The guest stays up
between runs and OS caches can remain warm. Preserve separate output directories
for preparation and each candidate repetition. Smoke the combined command for
all four candidates with shortened windows before the first accepted round.

| Phase | Frozen settings |
| --- | --- |
| Startup | Guest monotonic time from app launch to first successful DB-backed `/readyz`. Retain readiness attempts and the subsequent portfolio check. |
| Stabilization and idle | Wait 10 seconds after the post-readiness check, then sample idle for 30 seconds with quote polling active. Label the post-idle connection check separately. |
| Light load | Offer 5 RPS for 30 seconds. |
| Sustained warm-up | Offer 40 RPS for 125 seconds. |
| Sustained measurement | Offer 40 RPS for 185 seconds. |

Light-load edits, warm-up edits, compiled code, and caches carry forward inside
each candidate run. Deploy verified bundles to fresh guest paths. The reproduction guide documents the
suite command and offline report regeneration. Preparation runs both rounds with
shortened windows and uses a separate output directory. The suite retains each
candidate under its round directory and reports per-round p95 and p99.

## Measurements and acceptance

Expect 150 light-load, 5,000 warm-up, and 7,400 sustained slots per run. Validate
slot schedule, outcomes, and accounting, and retain failure or incomplete status.
Report achieved throughput as completed requests divided by offering time plus
drain. Compute nearest-rank p95 and p99 from successful scheduled-to-completion
observations. Report dispatch, queue and HTTP timing separately, retain
per-operation counts, and treat sparse per-operation tails as descriptive.
Compare candidate repetitions individually and report their observed spread.
Require identical captured artifact paths and hashes for each candidate across
rounds before reporting its spread.
Latency includes SSH transport and client scheduling.

Take guest samples at about 1 Hz. Retain application RSS/PSS, PostgreSQL aggregate
PSS, guest MemAvailable, CPU, reclaim and OOM counters, GC and quote-poll logs.
Aggregate memory within the recorded phase markers. Require at least two samples,
at least one per two seconds of configured duration, and gaps of at most three
seconds including at either boundary. Label sampled peaks and process lifetime
RSS high-water marks separately.

Accept a phase only with verified artifacts and environment, correct behavior,
adequate evidence, and complete request delivery without workload errors,
timeouts, or unsent slots. Verify normal cleanup and examine OOMs, dispatch
delays, worker occupancy, and within-run memory and p99 drift before accepting
the comparison. Preserve completed phases and failed attempts. Record material
deviations and rerun affected phases when comparability requires it.

Calibration supported 512 MiB
at this load. Spring Boot saw direct reclaim and allocation stalls, with stable
memory headroom over the measured windows and no throughput loss or rising
tail latency. Use 1 GiB as a separately identified environment if guest pressure
later compromises comparison. Assign a new protocol version to any material change.
