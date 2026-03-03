# Performance Tests

## Overview

Artillery-based load tests for Checkr with result persistence and regression detection.

## How It Works

### Running Tests

```bash
make perf-test
```

This assembles the Artillery config from modular scenario files, starts a mock LLM server and Checkr, runs the Artillery load test, saves results to `latest.json`, and compares against the baseline (if one exists).

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

## Large-Payload Test

A ~10MB synthetic dataset is generated before each test run to verify Checkr handles large HTTP request bodies. The generated scenario file (`scenarios/20_large_validate_generated.yml`) is cleaned up automatically after the test.

### Configuration

| Variable | Default | Description |
|---|---|---|
| `LARGE_PAYLOAD_ENABLED` | `1` | Set to `0` to skip the large-payload test |
| `LARGE_PAYLOAD_SIZE_MB` | `10` | Target JSON body size in MB |
| `LARGE_PAYLOAD_ITEMS` | `200` | Number of DataItems in the dataset |
| `LARGE_PAYLOAD_MSGS` | `10` | Messages per DataItem (even number) |
| `LARGE_PAYLOAD_RATE` | `1` | arrivalRate (must be unique across scenarios) |

### Examples

```bash
# Skip large-payload test
LARGE_PAYLOAD_ENABLED=0 make perf-test

# Use a 5MB payload instead of the default 10MB
LARGE_PAYLOAD_SIZE_MB=5 make perf-test
```

## Project Structure

```
tests/perf/
├── config.yml              # Base config (target, phases, thresholds)
├── scenarios/              # One file per endpoint group
│   ├── 00_metadata.yml     # GET: health, list, info, raw
│   ├── 01_gate1_structure.yml
│   ├── 02_gate2_deduplication.yml
│   ├── 03_gate3_availability.yml
│   ├── 04_gate4_language.yml
│   ├── 05_gate5_balance.yml
│   ├── 06_gate6_quantity.yml
│   ├── 07_gate8_guardrail.yml
│   ├── 08_multi_gate.yml
│   ├── 09_submit.yml
│   ├── 10_geval.yml
│   └── 20_large_validate_generated.yml  # GENERATED (gitignored)
├── assemble.py             # Merges config + scenarios → artillery.yml
├── gen_large_payload.py    # Generates large-payload scenario
├── artillery.yml           # GENERATED (gitignored)
├── run.sh                  # Orchestrates generate, assemble, artillery, compare
├── compare.py              # Baseline vs. latest comparison
├── baseline.json           # Committed reference result
├── latest.json             # Ephemeral last-run result (gitignored)
└── mock_llm_server.py      # Fake LLM server for tests
```

## Files

| File | Tracked | Purpose |
|---|---|---|
| `config.yml` | Yes | Base Artillery config (target, phases, thresholds) |
| `scenarios/*.yml` | Yes | Modular scenario fragments, one per endpoint group |
| `scenarios/*_generated.yml` | No | Generated scenarios (gitignored, cleaned up after test) |
| `assemble.py` | Yes | Merges config + scenarios into `artillery.yml` |
| `gen_large_payload.py` | Yes | Generates large-payload scenario (~10MB) |
| `artillery.yml` | No | Generated Artillery config (gitignored) |
| `compare.py` | Yes | Baseline vs. latest comparison script |
| `baseline.json` | Yes | Committed reference result |
| `latest.json` | No | Ephemeral result from the last run (gitignored) |
| `mock_llm_server.py` | Yes | Fake LLM server used during tests |
| `run.sh` | Yes | Test runner orchestrating all steps |

## Adding a New Scenario

1. Create a new file in `scenarios/` with the next numeric prefix (e.g. `11_new_endpoint.yml`)
2. Add a YAML list of Artillery flow steps (see existing files for examples)
3. Run `make perf-test` — the new scenario is automatically picked up
