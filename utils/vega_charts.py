"""Vega-Lite chart spec builders. Returns plain dicts — no external dependencies."""


def vega_histogram(
    values: list[float],
    title: str = "Distribution",
    threshold: float | None = None,
) -> dict:
    """Build a Vega-Lite histogram spec.

    Args:
        values: Numeric values to plot.
        title: Chart title.
        threshold: Optional threshold rendered as a red vertical rule.

    Returns:
        A Vega-Lite specification dict ready for vegaEmbed.
    """
    data = [{"value": v} for v in values]

    histogram_layer = {
        "mark": "bar",
        "encoding": {
            "x": {
                "bin": True,
                "field": "value",
                "type": "quantitative",
                "title": title,
            },
            "y": {
                "aggregate": "count",
                "type": "quantitative",
                "title": "Count",
            },
        },
    }

    layers = [histogram_layer]

    if threshold is not None:
        rule_layer = {
            "mark": {"type": "rule", "color": "red", "strokeWidth": 2},
            "encoding": {
                "x": {"datum": threshold, "type": "quantitative"},
            },
        }
        layers.append(rule_layer)

    n = len(values)
    mean = sum(values) / n if n else 0
    sorted_vals = sorted(values)
    median = sorted_vals[n // 2] if n else 0
    subtitle = f"n={n}  mean={mean:.1f}  median={median:.1f}"

    spec = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": {"text": title, "subtitle": subtitle},
        "width": 360,
        "height": 200,
        "data": {"values": data},
        "layer": layers,
    }

    return spec
