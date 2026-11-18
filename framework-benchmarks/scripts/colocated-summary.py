#!/usr/bin/env python3
"""Regenerate compact memory observations from raw guest samples (KiB)."""
import json
from pathlib import Path
import statistics
import sys

PHASE_MARKERS = {'idle': 'idle', 'light-load': 'light', 'warmup': 'warmup',
                 'measurement': 'measurement'}

def fields(text):
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts)>1 and parts[1].isdigit(): result[parts[0].rstrip(':')] = int(parts[1])
    return result

def read_samples(out):
    phases = {}
    with (out/'samples.jsonl').open() as samples:
        for line in samples:
            row = json.loads(line)
            phases.setdefault(row['phase'], []).append(row)
    return phases


def summarize_phase(rows):
    available = [fields(row['meminfo'])['MemAvailable'] for row in rows]
    item = dict(samples=len(rows), mem_available_min_kib=min(available),
                mem_available_median_kib=statistics.median(available))
    for kind in ('app', 'postgres'):
        procs = [p for row in rows for p in row['processes'] if p['kind'] == kind]
        if not procs:
            continue
        item[kind] = dict(process_rss_max_kib=max(fields(p['smaps_rollup'])['Rss'] for p in procs),
                          process_hwm_max_kib=max(fields(p['status']).get('VmHWM', 0) for p in procs),
                          process_pss_max_kib=max(fields(p['smaps_rollup'])['Pss'] for p in procs))
        if kind == 'postgres':
            # Sum PSS per sample to apportion shared pages.
            item[kind]['sampled_pss_sum_max_kib'] = max(
                sum(fields(p['smaps_rollup'])['Pss'] for p in row['processes'] if p['kind'] == kind)
                for row in rows)
    return item


def samples_within(rows, start, end):
    return [row for row in rows if start <= row['monotonic'] <= end]


def summarize(out):
    result = {}
    for phase, rows in sorted(read_samples(out).items()):
        prefix = PHASE_MARKERS.get(phase)
        if prefix:
            start = out/f'{prefix}-start.json'
            end = out/f'{prefix}-end.json'
            if start.is_file() and end.is_file():
                rows = samples_within(rows, json.loads(start.read_text())['monotonic'],
                                      json.loads(end.read_text())['monotonic'])
        if rows:
            result[phase] = summarize_phase(rows)
    return result


if __name__ == "__main__":
    out = Path(sys.argv[1])
    result = summarize(out)
    (out/'memory-summary.json').write_text(json.dumps(result,indent=2)+'\n')
