"""Compare Artillery perf results against a saved baseline."""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASELINE_PATH = os.path.join(SCRIPT_DIR, "baseline.json")
LATEST_PATH = os.path.join(SCRIPT_DIR, "latest.json")

THRESHOLD = float(os.environ.get("PERF_REGRESSION_THRESHOLD", "20"))

SUMMARY_METRICS = ["min", "max", "median", "p95", "p99"]
COUNTER_KEYS = ["http.requests", "vusers.failed"]


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
    return f"{pct:+.1f}%"


def main() -> int:
    if not os.path.exists(BASELINE_PATH):
        print("No baseline found, skipping comparison.")
        return 0

    baseline = load_json(BASELINE_PATH)
    latest = load_json(LATEST_PATH)

    header = f"{'Metric':<28} {'Baseline':>10} {'Current':>10} {'Change':>10}"
    sep = "─" * len(header)

    print()
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

        if m == "p99" and b > 0:
            pct = (c - b) / b * 100
            if pct > THRESHOLD:
                regression = True

    for key in COUNTER_KEYS:
        label = key.split(".")[-1]
        b = get_counter(baseline, key)
        c = get_counter(latest, key)
        change = fmt_change(float(b), float(c)) if b != 0 else "—"
        print(f"{label:<28} {b:>10} {c:>10} {change:>10}")

    print()

    if regression:
        print(
            f"REGRESSION: p99 response time increased by more than {THRESHOLD:.0f}%"
        )
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
