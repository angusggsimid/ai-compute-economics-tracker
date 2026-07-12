import json
from pathlib import Path


TRACKER = Path(__file__).resolve().parents[1]
ARTIFACT = TRACKER / "html_dashboard" / "v3" / "artifact.json"


def _artifact():
    return json.loads(ARTIFACT.read_text(encoding="utf-8"))


def test_phase6_has_exactly_six_investor_sections_and_no_mixed_frequency_filter():
    artifact = _artifact()
    bodies = [
        block.get("body", "")
        for block in artifact["manifest"]["blocks"]
        if block["type"] == "markdown"
    ]
    expected = [
        "01 · Compute Price",
        "02 · Market Depth",
        "03 · Cloud",
        "04 · Model Economics",
        "05 · Demand",
        "06 · Commitment",
    ]
    assert all(any(label in body for body in bodies) for label in expected)
    assert artifact["manifest"]["filters"] == []
    assert len(artifact["manifest"]["charts"]) == 6


def test_phase6_every_chart_has_title_axes_frequency_and_runnable_source():
    artifact = _artifact()
    sources = {source["id"]: source for source in artifact["sources"]}
    for chart in artifact["manifest"]["charts"]:
        assert chart["title"]
        assert chart["xAxisTitle"]
        assert chart["yAxisTitle"]
        assert chart["headerMarkdown"]
        source = sources[chart["sourceId"]]
        assert source["query"]["sql"].strip().lower().startswith(("select", "with"))
        assert source["query"]["tables_used"]


def test_phase6_withholds_fake_gpu_trend_until_history_threshold():
    rows = _artifact()["snapshot"]["datasets"]["gpu_progress"]
    observed = {row["gpu"]: row for row in rows if row["measure"] == "Observed history"}
    threshold = {row["gpu"]: row for row in rows if row["measure"] == "10-day chart threshold"}
    assert set(observed) == {"H100", "H200", "B200"}
    for gpu in observed:
        assert threshold[gpu]["days"] == 10
        if observed[gpu]["days"] < 10:
            assert observed[gpu]["chart_ready_series"] == 0
            assert observed[gpu]["blocker"] == "insufficient_daily_history"


def test_phase6_demand_and_commercialization_do_not_turn_snapshots_into_trends():
    datasets = _artifact()["snapshot"]["datasets"]
    demand = datasets["demand"]
    first_date = min(row["date"] for row in demand)
    first_rows = [row for row in demand if row["date"] == first_date]
    assert {row["series"] for row in first_rows} == {
        "Image processing · 4W MA",
        "Tool calls · 4W MA",
    }
    assert all(row["index_value"] == 100 for row in first_rows)
    commercialization = datasets["commercialization"][0]
    assert commercialization["public_series"] > 0
    assert commercialization["positive_revisions"] == 0
    assert commercialization["negative_revisions"] == 0


def test_phase6_keeps_capex_periods_and_product_scope_separate():
    artifact = _artifact()
    datasets = artifact["snapshot"]["datasets"]
    assert len({row["date"] for row in datasets["capex"]}) == 1
    assert {row["track"] for row in datasets["commitment"]} == {
        "cloud_capex_actual",
        "cloud_official_event",
        "china_cloud_capex",
    }
    forbidden = {"security_prices", "event_studies", "security_monitor", "stock_prices"}
    assert not forbidden.intersection(datasets)
    source_text = json.dumps(artifact["sources"], ensure_ascii=False).lower()
    assert "yahoo-finance" not in source_text
    assert "production_security" not in source_text
