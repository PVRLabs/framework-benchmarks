# V2 reference measurements

The reference dataset is the successful Lenovo eight-run suite recorded on November 27, 2026 UTC. It used 100 RPS, eight workers, 32 pending slots, Xmx80m and strict zero-drop acceptance. Every 185-second sustained window completed 18,500 requests without errors, timeouts or unsent slots. The four stacks ran in two sequential rounds on the same one-vCPU, 512 MiB, no-swap Debian 13 guest with colocated PostgreSQL.

| Round | Stack | Readiness (s) | Peak app RSS (MiB) | Min guest available (MiB) | Sustained p99 (ms) | Guest CPU idle (%) |
|---|---|---:|---:|---:|---:|---:|
| 1 | Jex | 5.10 | 149.91 | 197.59 | 8.35 | 64.4 |
| 1 | Quarkus | 6.04 | 208.14 | 138.15 | 9.12 | 60.4 |
| 1 | Spring Boot | 10.96 | 231.27 | 109.58 | 10.40 | 57.9 |
| 1 | Micronaut | 7.54 | 217.11 | 125.28 | 8.97 | 63.6 |
| 2 | Jex | 5.06 | 156.97 | 189.57 | 10.48 | 60.9 |
| 2 | Quarkus | 5.89 | 209.69 | 133.31 | 8.99 | 66.0 |
| 2 | Spring Boot | 11.07 | 232.27 | 112.77 | 10.09 | 64.5 |
| 2 | Micronaut | 7.99 | 219.26 | 123.66 | 8.75 | 62.4 |

CPU idle is the mean of 185–186 one-second **external guest vmstat** samples aligned to the recorded sustained measurement markers. The dataset predates the v2 runner’s phase-boundary `/proc/stat` counters; those counters are absent, not reconstructed. Current v2 runs require them. The first-second Quarkus warm-up transition spikes reached 373.70 and 522.62 ms without drops; their cause remains unresolved.

The original suite manifest calls the protocol `v1` because the isolated runner was derived from v1. Its recorded rate was 100 RPS and its workload files record a 32-slot queue; the original label and evidence have not been rewritten. Its retained runner hashes were: host load runner `a6fd728082680600e88d7e4900c4d397542a17e35192309230ea2d42d390c19c`, suite runner `ecb9d454be04563ba6043e58cd765b1dd5f4497bd1194a52a27e716aff4e81ee`, guest runner `c3fb1fb6cf5f48fd45e68164084503d40e460036d2e12e1769549553b94a53b3`, and workload driver `92d145a17cb6bec5a5da8a819f1a49abcc168a57a2346c029d92da528670e992`. These identify the execution files; they do not imply the run used the later v2 source revision.

The [machine-readable summary](measurements.json) records source hashes and unrounded suite measurements. The [original suite manifest](source-suite.json) is preserved without changes. Original suite and external CPU captures are retained in `.local-experiments/issue-1-100-rps/issue1-queue32-detached-20261126/` and `.local-experiments/issue-1-100-rps/issue1-queue32-detached-cpu-20261126.txt` in the originating checkout; those raw files are not included in this repository. The original Lenovo output is `/home/ejboy/issue1-queue32-detached-20261126/`. The current report generator does not regenerate this historical manifest; use the retained original report and runner for it.

These results are an observed two-round comparison, not a guarantee of long-term stability. The previously published v1 results remain available separately.
