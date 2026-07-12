import sys
from datetime import date, timedelta
from pathlib import Path


TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from tracker_v2 import Database  # noqa: E402


INSERT_SQL = """
INSERT INTO production_market_facts (
    date, track, entity, sub_entity, metric, value, unit, dimension,
    vendor, source_name, notes, run_id, source_id, source_url, snapshot_path,
    source_type, collection_method, observed_at, fetched_at, raw_payload_hash,
    is_production_eligible, confidence
) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
"""


def _fact(
    observed_date,
    *,
    track="gpu_rental_trend",
    entity="H100",
    sub_entity="ComputePrices public trend",
    metric="avg_price_per_gpu_hour",
    value=3.0,
    unit="USD/GPU hr",
    dimension="public_tier_7d",
    vendor="ComputePrices",
    source_id="computeprices-public-trend",
    source_url="https://example.com/source",
):
    timestamp = f"{observed_date} 09:00:00"
    return (
        str(observed_date), track, entity, sub_entity, metric, value, unit, dimension,
        vendor, "test source", "test", f"run-{observed_date}", source_id, source_url,
        f"snapshots/{observed_date}.json", "public_pricing_page", "api", timestamp,
        timestamp, f"hash-{observed_date}-{value}", True, 0.9,
    )


def test_series_id_is_stable_across_run_and_source_url_changes(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    conn.executemany(
        INSERT_SQL,
        [
            _fact("2026-07-01", source_url="https://example.com/old"),
            _fact("2026-07-02", source_url="https://example.com/new"),
        ],
    )

    rows = conn.execute(
        "SELECT date, series_id, natural_frequency, observation_type "
        "FROM canonical_observation ORDER BY date"
    ).fetchall()
    conn.close()

    assert rows[0][1] == rows[1][1]
    assert rows[0][1].startswith("ser_")
    assert rows[0][2:] == ("daily", "time_series")


def test_series_quality_enforces_chart_and_inflection_thresholds(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    start = date(2026, 7, 1)
    rows = [
        _fact(start + timedelta(days=offset), value=3.0 - offset * 0.02)
        for offset in range(10)
    ]
    rows.extend(
        _fact(
            start + timedelta(days=offset),
            track="gpu_rental",
            sub_entity="Provider A",
            metric="price_per_gpu_hour",
            dimension="on_demand",
            vendor="Provider A",
            source_id="provider-a",
            value=2.5,
        )
        for offset in range(10)
    )
    conn.executemany(INSERT_SQL, rows)

    quality = conn.execute(
        """
        SELECT track, valid_dates, coverage_ratio, eligible_for_chart,
               chart_reason_code, eligible_for_inflection, inflection_reason_code,
               eligible_for_90d
        FROM series_quality
        ORDER BY track
        """
    ).fetchall()
    conn.close()

    assert quality == [
        ("gpu_rental", 10, None, False, "unstable_configuration", False,
         "unstable_configuration", False),
        ("gpu_rental_trend", 10, 1.0, True, None, False,
         "insufficient_30d_history", False),
    ]


def test_event_observation_emits_initial_value_and_real_changes_only(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    rows = [
        _fact(
            "2026-07-01", track="token_price", entity="GPT-X", sub_entity="gpt-x",
            metric="output_price_per_1m_tokens", value=10.0, unit="USD/1M tokens",
            dimension="catalog", vendor="OpenAI", source_id="openai-catalog",
        ),
        _fact(
            "2026-07-02", track="token_price", entity="GPT-X", sub_entity="gpt-x",
            metric="output_price_per_1m_tokens", value=10.0, unit="USD/1M tokens",
            dimension="catalog", vendor="OpenAI", source_id="openai-catalog",
        ),
        _fact(
            "2026-07-03", track="token_price", entity="GPT-X", sub_entity="gpt-x",
            metric="output_price_per_1m_tokens", value=8.0, unit="USD/1M tokens",
            dimension="catalog", vendor="OpenAI", source_id="openai-catalog",
        ),
    ]
    conn.executemany(INSERT_SQL, rows)

    events = conn.execute(
        """
        SELECT date, event_type, value, prior_value, change_pct
        FROM event_observation
        ORDER BY date
        """
    ).fetchall()
    conn.close()

    assert events == [
        (date(2026, 7, 1), "initial_observation", 10.0, None, None),
        (date(2026, 7, 3), "price_change", 8.0, 10.0, -20.0),
    ]


def test_matched_panel_index_has_fixed_members_and_normalized_base(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    start = date(2026, 7, 1)
    rows = []
    for provider, base_value in (("Provider A", 10.0), ("Provider B", 20.0), ("Provider C", 30.0)):
        for offset in range(10):
            rows.append(
                _fact(
                    start + timedelta(days=offset),
                    track="gpu_rental",
                    sub_entity=provider,
                    metric="price_per_gpu_hour",
                    value=base_value * (1 - offset / 90.0),
                    dimension="billing=on_demand|variant=sxm|region=us|gpu_count=1",
                    vendor=provider,
                    source_id=provider.lower().replace(" ", "-"),
                )
            )
    conn.executemany(INSERT_SQL, rows)

    rows = conn.execute(
        """
        SELECT date, index_value, panel_member_count, observed_member_count,
               coverage_ratio, eligible_for_chart, eligible_for_inflection,
               eligible_for_market_inference, panel_reason_code, member_series_ids
        FROM matched_panel_index
        ORDER BY date
        """
    ).fetchall()
    conn.close()

    assert len(rows) == 10
    assert rows[0][1] == 100.0
    assert round(rows[-1][1], 6) == 90.0
    assert rows[-1][2:5] == (3, 3, 1.0)
    assert rows[-1][5:7] == (True, False)
    assert rows[-1][7:9] == (True, None)
    assert len(rows[-1][9].split(",")) == 3


def test_published_aggregate_trend_is_not_a_matched_panel_member(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    start = date(2026, 7, 1)
    conn.executemany(
        INSERT_SQL,
        [_fact(start + timedelta(days=offset), value=3.0) for offset in range(10)],
    )

    candidate = conn.execute(
        """
        SELECT eligible_for_matched_panel, panel_reason_code
        FROM matched_panel_candidate
        """
    ).fetchone()
    panel_count = conn.execute("SELECT count(*) FROM matched_panel_index").fetchone()[0]
    conn.close()

    assert candidate == (False, "aggregate_composition_not_fixed")
    assert panel_count == 0


def test_weekly_line_ready_excludes_incomplete_latest_period(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    start = date(2026, 4, 13)
    rows = []
    for offset in range(9):
        week = start + timedelta(days=offset * 7)
        rows.append(
            _fact(
                week,
                track="openrouter_usage",
                entity="Others",
                sub_entity="weekly_public_rankings",
                metric="tool_call_count",
                value=100 + offset,
                unit="count",
                dimension="weekly_frontend_public",
                vendor="OpenRouter",
                source_id="openrouter-rankings",
            )
        )
    conn.executemany(INSERT_SQL, rows)

    result = conn.execute(
        """
        SELECT q.valid_dates, q.eligible_for_chart, q.eligible_for_inflection,
               q.inflection_reason_code, max(l.date)
        FROM series_quality q
        JOIN line_ready_observation l USING (series_id)
        WHERE q.track = 'openrouter_usage'
        GROUP BY q.valid_dates, q.eligible_for_chart, q.eligible_for_inflection,
                 q.inflection_reason_code
        """
    ).fetchone()
    incomplete = conn.execute(
        """
        SELECT period_complete
        FROM canonical_observation
        WHERE track='openrouter_usage'
        ORDER BY date DESC
        LIMIT 1
        """
    ).fetchone()[0]
    conn.close()

    assert result == (
        8, True, False, "proxy_not_inflection_eligible", date(2026, 6, 1)
    )
    assert incomplete is False


def test_official_capex_tables_join_the_event_series_layer(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    conn.execute(
        """
        INSERT INTO production_capex_actuals (
            ticker, company, period_start, period_end, fiscal_period, fiscal_year,
            xbrl_tag, accession_no, capex_value, unit, filed_at, form_type,
            run_id, source_id, source_url, snapshot_path, source_type,
            collection_method, observed_at, fetched_at, raw_payload_hash,
            is_production_eligible, confidence
        ) VALUES (
            'META', 'Meta', '2026-01-01', '2026-03-31', 'FY2026 Q1', 2026,
            'PaymentsToAcquirePropertyPlantAndEquipment', '0001', 18.997, 'USD_B',
            '2026-04-29', '10-Q', 'capex-run', 'sec-meta-capex',
            'https://sec.example/meta', 'meta.json', 'official', 'sec_api',
            '2026-03-31 00:00:00', '2026-04-29 00:00:00', 'capex-hash', TRUE, 0.99
        )
        """
    )
    conn.execute(
        """
        INSERT INTO production_official_events (
            ticker, announcement_date, event_type, metric, value, unit,
            description, fiscal_period, run_id, source_id, source_url,
            snapshot_path, source_type, collection_method, observed_at,
            fetched_at, raw_payload_hash, is_production_eligible, confidence
        ) VALUES (
            'META', '2026-04-29', 'capex_guidance_revision',
            'fy2026_capex_guidance_high', 145, 'USD_B', 'Guidance raised', 'FY2026',
            'event-run', 'meta-guidance', 'https://meta.example/earnings', 'meta.html',
            'official', 'manual_verified', '2026-04-29 00:00:00',
            '2026-04-29 01:00:00', 'event-hash', TRUE, 0.95
        )
        """
    )

    definitions = conn.execute(
        """
        SELECT track, natural_frequency, observation_type, evidence_class
        FROM series_definition
        ORDER BY track
        """
    ).fetchall()
    events = conn.execute(
        "SELECT track, event_type, value FROM event_observation ORDER BY track"
    ).fetchall()
    conn.close()

    assert definitions == [
        ("cloud_capex_actual", "quarterly", "event", "official"),
        ("cloud_official_event", "event", "event", "official"),
    ]
    assert events == [
        ("cloud_capex_actual", "initial_observation", 18.997),
        ("cloud_official_event", "initial_observation", 145.0),
    ]


def test_source_freshness_exposes_fresh_stale_and_missing_policies(tmp_path):
    db = Database(str(tmp_path / "tracker.db"))
    conn = db.get_connection()
    row = list(
        _fact(
            "2026-07-11",
            track="gpu_available_offer",
            source_id="gpuperhour-offers-h100",
        )
    )
    row[17] = "2026-07-11 09:00:00"
    row[18] = "2026-07-11 09:00:00"
    conn.execute(INSERT_SQL, row)
    conn.execute(
        "UPDATE production_market_facts SET fetched_at = current_timestamp, observed_at = current_timestamp"
    )

    fresh = conn.execute(
        """
        SELECT status
        FROM source_freshness
        WHERE policy_id='gpuperhour_daily'
        """
    ).fetchone()[0]
    missing = conn.execute(
        """
        SELECT status
        FROM source_freshness
        WHERE policy_id='runpod_daily'
        """
    ).fetchone()[0]
    conn.execute(
        "UPDATE production_market_facts SET fetched_at = current_timestamp - INTERVAL 5 DAY"
    )
    stale = conn.execute(
        """
        SELECT status
        FROM source_freshness
        WHERE policy_id='gpuperhour_daily'
        """
    ).fetchone()[0]
    conn.close()

    assert fresh == "fresh"
    assert missing == "missing"
    assert stale == "stale"
