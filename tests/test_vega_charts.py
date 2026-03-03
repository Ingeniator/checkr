"""Tests for utils/vega_charts.py."""

from utils.vega_charts import vega_histogram


class TestVegaHistogram:
    def test_basic_spec_structure(self):
        spec = vega_histogram([1.0, 2.0, 3.0, 4.0, 5.0])
        assert spec["$schema"].startswith("https://vega.github.io/schema/vega-lite")
        assert "data" in spec
        assert "layer" in spec
        assert len(spec["layer"]) == 1  # no threshold → one layer
        assert spec["data"]["values"] == [{"value": v} for v in [1, 2, 3, 4, 5]]

    def test_threshold_adds_rule_layer(self):
        spec = vega_histogram([10, 20, 30], threshold=25.0)
        assert len(spec["layer"]) == 2
        rule = spec["layer"][1]
        assert rule["mark"]["type"] == "rule"
        assert rule["mark"]["color"] == "red"
        assert rule["encoding"]["x"]["datum"] == 25.0

    def test_title_and_subtitle(self):
        spec = vega_histogram([10, 20, 30], title="My Chart")
        assert spec["title"]["text"] == "My Chart"
        assert "n=3" in spec["title"]["subtitle"]

    def test_empty_values(self):
        spec = vega_histogram([])
        assert spec["data"]["values"] == []
        assert "n=0" in spec["title"]["subtitle"]
