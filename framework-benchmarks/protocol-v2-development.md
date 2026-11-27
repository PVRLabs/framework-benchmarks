# Protocol v2 development

This branch develops an experimental successor to v1. The published v1 code and
accepted evidence are preserved at the annotated `benchmark-v1` tag (commit
`8fd6df9`). The tag is a Git reference; protect it on the remote against deletion
or movement when publishing it.

The v2 starting point retains the v1 guest, fixture, database, JVM and workload
settings, including `-Xmx80m`, eight workers, 125-second warm-up, 185-second
measurement and zero-drop acceptance. It changes sustained rate to 100 RPS and
pending queue capacity to 32. These values match the completed two-round Lenovo
experiment. The experiment's vmstat samples established CPU headroom; v2 captures
aggregate guest `/proc/stat` counters at each existing phase marker and reports
idle and I/O-wait percentages from counter deltas. This boundary-counter method
is new instrumentation and needs live validation; it is not the sampler used by
the completed experiment.

The suite CLI runs v2 directly. Deploy bundles containing this branch's
`colocated-guest.py` and matching manifests before running: older guest scripts do
not record the required counters and v2 validation will mark the evidence
incomplete. Use `--preparation --fail-fast` first and use a fresh disk-backed
guest root and output directory. Pass `--fail-fast` for measured experiments.
Use a separate `--config` file for a later Xmx70m investigation; do not change
`config-v2.json` or treat custom runs as accepted results.

Raw captures belong in `.local-experiments/`, with experiment records in the
private journal. Do not replace published v1 evidence or featured results before
v2 is finalized and validated. Generated charts are experimental; do not promote them to published featured results.
