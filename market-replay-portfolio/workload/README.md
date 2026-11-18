# Portfolio load driver

Run on the load generator host with Python 3. Copy and edit
[default.json](default.json) to select the base URL, rate, duration, seed and
user count. From the repository root:

```sh
python3 market-replay-portfolio/workload/run.py --config market-replay-portfolio/workload/default.json --output /tmp/portfolio-load.json
python3 -m unittest discover -s market-replay-portfolio/workload
```

The default weights are 40% portfolio, 25% edit, 25% valuation, 8% latest
quotes and 2% history. The realized mix varies with the seeded draw. User IDs
are selected uniformly from 1 through `users`. The workload assigns absolute
holding quantities through the existing PUT endpoint. The seed determines the
planned sequence, while concurrent execution can change edit commit order.

Slots are spaced at `1 / rate` on a monotonic clock. Eight workers are
available by default. `concurrency` sets the worker limit and
`pending_capacity` sets the queue limit, which defaults to the worker count.
The scheduler submits one request per slot regardless of response completion.
It skips slots that have fallen a full interval behind or are past the
offering window (`missed_slot`) and records full-queue rejections
(`queue_full`). Neither outcome is retried. The driver drains accepted work
and joins the workers before returning. The command exits nonzero for any
unsent request, timeout or failure, after emitting results.

The JSON retains an observation per slot. Dispatch lag is the time from the
scheduled slot to the submission decision. Queue wait runs from that decision
to worker start. HTTP time runs from worker start through response body
consumption for successful requests, or until an error is handled. End-to-end
time starts at the scheduled slot and includes all three durations. HTTP
includes connection setup and transport. The driver uses a new connection per
request and disables redirects and environment proxies. The timeout is a
socket I/O timeout, so it does not impose a total deadline on a response that
keeps producing data.

Aggregate and per-operation summaries use nearest-rank p50/p95/p99 and output
null when there are no qualifying observations. Successful latencies require
204 for edits and 200 for reads. The JSON summarizes unsuccessful attempt
latencies separately and retains the status and timing of each attempt. An
unsent slot has no response latency. Inspect unsent counts, dispatch lag and
queue wait before interpreting successful tail latency. Even with no unsent
slots, long dispatch or queue delays can materially affect the results.
Small per-operation counts, especially for history, make tail estimates coarse.

Scheduled equals submitted plus unsent. After drain, submitted equals
completed, and completed equals successful plus failed plus timed out. Offered
and submitted rates use the scheduled window. The output also records
successful completions within that window and rates through the end of drain.
The peak in-flight count covers overlapping HTTP attempts and excludes queued
work. All intervals can be recovered from the observations. The request plan
and observations are kept in memory, with space proportional to the number of
scheduled slots.
