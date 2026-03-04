"""Compare Artillery perf results against saved baselines.

Iterates over all latest_*rps.json files and compares each against its
corresponding baseline_*rps.json.
"""

import glob
import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

THRESHOLD = float(os.environ.get("PERF_REGRESSION_THRESHOLD", "20"))
MIN_ABSOLUTE_MS = float(os.environ.get("PERF_MIN_ABSOLUTE_MS", "50"))

SUMMARY_METRICS = ["min", "max", "median", "p95", "p99"]
ENDPOINT_METRICS = ["median", "p95", "p99"]
COUNTER_KEYS = ["http.requests", "vusers.failed"]
ENDPOINT_PREFIX = "plugins.metrics-by-endpoint.response_time."


def load_json(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


def get_summary(data: dict, metric: str) -> float | None:
    return data.get("aggregate", {}).get("summaries", {}).get(
        "http.response_time", {}
    ).get(metric)


def get_counter(data: dict, key: str) -> int:
    return data.get("aggregate", {}).get("counters", {}).get(key, 0)


def fmt_change(baseline: float, current: float) -> str:
    if baseline == 0:
        return "—"
    pct = (current - baseline) / baseline * 100
    if max(baseline, current) < MIN_ABSOLUTE_MS:
        return f"~{pct:+.1f}%"
    return f"{pct:+.1f}%"


def compare_pair(tag: str, baseline_path: str, latest_path: str) -> bool:
    """Compare a single baseline/latest pair. Returns True if regression."""
    baseline = load_json(baseline_path)
    latest = load_json(latest_path)

    header = f"{'Metric':<28} {'Baseline':>10} {'Current':>10} {'Change':>10}"
    sep = "─" * len(header)

    print(f"\n=== {tag} ===")
    print(header)
    print(sep)

    regression = False

    for m in SUMMARY_METRICS:
        b = get_summary(baseline, m)
        c = get_summary(latest, m)
        if b is None or c is None:
            continue
        change = fmt_change(b, c)
        print(f"{'response_time.' + m:<28} {b:>10.0f} {c:>10.0f} {change:>10}")

        if m == "p99" and b > 0 and c > MIN_ABSOLUTE_MS:
            pct = (c - b) / b * 100
            if pct > THRESHOLD:
                regression = True

    for key in COUNTER_KEYS:
        label = key.split(".")[-1]
        b = get_counter(baseline, key)
        c = get_counter(latest, key)
        change = fmt_change(float(b), float(c)) if b != 0 else "—"
        print(f"{label:<28} {b:>10} {c:>10} {change:>10}")

    # Per-endpoint breakdown
    endpoint_rows = _endpoint_rows(baseline, latest)
    if endpoint_rows:
        print(f"\n  {'med Base':>8} {'med Cur':>8} {'p95 Base':>8} {'p95 Cur':>8} {'p99 Base':>8} {'p99 Cur':>8} {'Change':>8}  Endpoint")
        print("  " + "─" * 106)
        for row in endpoint_rows:
            print(
                f"  {row['b_med']:>8.0f} {row['c_med']:>8.0f}"
                f" {row['b_p95']:>8.0f} {row['c_p95']:>8.0f}"
                f" {row['b_p99']:>8.0f} {row['c_p99']:>8.0f}"
                f" {row['change']:>8}  {row['endpoint']}"
            )

    return regression


def _endpoint_rows(baseline: dict, latest: dict) -> list[dict]:
    """Extract per-endpoint comparison rows (median, p95, p99)."""
    b_summaries = baseline.get("aggregate", {}).get("summaries", {})
    c_summaries = latest.get("aggregate", {}).get("summaries", {})

    endpoints: set[str] = set()
    for key in list(b_summaries) + list(c_summaries):
        if key.startswith(ENDPOINT_PREFIX):
            endpoints.add(key[len(ENDPOINT_PREFIX):])

    rows = []
    for ep in sorted(endpoints):
        full_key = ENDPOINT_PREFIX + ep
        b_data = b_summaries.get(full_key, {})
        c_data = c_summaries.get(full_key, {})
        b_p99 = b_data.get("p99")
        c_p99 = c_data.get("p99")
        if b_p99 is None or c_p99 is None:
            continue
        rows.append({
            "endpoint": ep,
            "b_med": b_data.get("median", 0),
            "c_med": c_data.get("median", 0),
            "b_p95": b_data.get("p95", 0),
            "c_p95": c_data.get("p95", 0),
            "b_p99": b_p99,
            "c_p99": c_p99,
            "change": fmt_change(b_p99, c_p99),
        })

    return rows


def main() -> int:
    latest_files = sorted(glob.glob(os.path.join(SCRIPT_DIR, "latest_*.json")))

    if not latest_files:
        print("No latest result files found.")
        return 1

    any_regression = False
    any_compared = False

    for latest_path in latest_files:
        # latest_5rps.json → baseline_5rps.json
        basename = os.path.basename(latest_path)
        tag = basename.replace("latest_", "").replace(".json", "")
        baseline_path = os.path.join(SCRIPT_DIR, f"baseline_{tag}.json")

        if not os.path.exists(baseline_path):
            print(f"\nNo baseline for {tag}, skipping comparison.")
            continue

        any_compared = True
        if compare_pair(tag, baseline_path, latest_path):
            any_regression = True

    if not any_compared:
        print("No baselines found, skipping comparison.")
        return 0

    print()
    if any_regression:
        print(
            f"REGRESSION: p99 response time increased by more than {THRESHOLD:.0f}%"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
