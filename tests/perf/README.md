# Performance Tests

## Overview

Artillery-based load tests for Checkr with result persistence and regression detection.

## How It Works

### Running Tests

```bash
make perf-test
```

This starts a mock LLM server and Checkr, runs the Artillery load test, saves results to `latest.json`, and compares against the baseline (if one exists).

### Saving a Baseline

```bash
make perf-baseline
```

Copies `latest.json` to `baseline.json`. Commit `baseline.json` to the repo so future runs compare against it.

### Comparison

After each test run, `compare.py` automatically compares `latest.json` against `baseline.json` and prints a table:

```
Metric                       Baseline    Current     Change
────────────────────────────────────────────────────────────
response_time.min                2092       2050      -2.0%
response_time.median             2144        210     -90.2%
response_time.p95                2369        380     -84.0%
response_time.p99                2369        420     -82.3%
requests                           20         20       0.0%
failed                              0          0         —
```

If no baseline exists, comparison is skipped.

### Regression Detection

The test exits with code 1 if **p99 response time** regresses by more than 20%. Override the threshold with:

```bash
PERF_REGRESSION_THRESHOLD=30 make perf-test
```

## Typical Workflow

1. `make perf-test` — first run, "No baseline found"
2. `make perf-baseline` — save the result as baseline
3. `git add tests/perf/baseline.json && git commit` — commit it
4. Make changes to the codebase
5. `make perf-test` — compare against baseline, see regressions or improvements
6. `make perf-baseline` — update baseline after intentional changes

## Files

| File | Tracked | Purpose |
|---|---|---|
| `artillery.yml` | Yes | Artillery test scenario configuration |
| `compare.py` | Yes | Baseline vs. latest comparison script |
| `baseline.json` | Yes | Committed reference result |
| `latest.json` | No | Ephemeral result from the last run (gitignored) |
| `mock_llm_server.py` | Yes | Fake LLM server used during tests |
| `run.sh` | Yes | Test runner orchestrating all steps |
