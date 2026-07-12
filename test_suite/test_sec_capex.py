import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import duckdb

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from company_config import decision_universe_configs, get_company_config  # noqa: E402
from production_store import ProductionStore  # noqa: E402
from tracker_v2 import Database  # noqa: E402
from data_sources.sec_capex import (  # noqa: E402
    DEFAULT_SEC_USER_AGENT,
    SEC_TAG_NOT_FOUND,
    SEC_SOURCE_UNAVAILABLE,
    SecCompanyfactsClient,
    SecCompanyfactsUnavailable,
    collect_sec_capex_actuals,
    companyfacts_url,
    hash_raw_payload,
)


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "sec_companyfacts"


class FixtureCompanyfactsClient:
    def __init__(self, fixture_dir=FIXTURE_DIR):
        self.fixture_dir = Path(fixture_dir)
        self.calls = []

    def fetch_companyfacts(self, config):
        self.calls.append(config.ticker)
        return json.loads((self.fixture_dir / f"{config.ticker}.json").read_text(encoding="utf-8"))


def _collect_from_fixtures(tmp_path, configs=None):
    return collect_sec_capex_actuals(
        configs=configs or decision_universe_configs(),
        client=FixtureCompanyfactsClient(),
        snapshot_dir=tmp_path / "tracker_snapshots" / "sec_capex",
        run_id="test-sec-capex-run",
        fetched_at="2026-07-05T10:00:00Z",
    )


def test_collects_latest_official_capex_actuals_from_sec_companyfacts_fixtures(tmp_path):
    result = _collect_from_fixtures(tmp_path)

    assert result.quality_events == []
    by_ticker = {actual.ticker: actual for actual in result.actuals}
    assert set(by_ticker) == {"MSFT", "AMZN", "GOOGL", "META", "ORCL"}

    assert by_ticker["MSFT"].period_start == "2026-01-01"
    assert by_ticker["MSFT"].period_end == "2026-03-31"
    assert by_ticker["MSFT"].fiscal_period == "FY2026 Q3"
    assert by_ticker["MSFT"].filed_at == "2026-04-29"
    assert by_ticker["MSFT"].accession_no == "0000789019-26-000060"
    assert by_ticker["MSFT"].capex_value == 30.876

    assert by_ticker["AMZN"].xbrl_tag == "PaymentsToAcquireProductiveAssets"
    assert by_ticker["AMZN"].capex_value == 44.203
    assert by_ticker["GOOGL"].capex_value == 35.674
    assert by_ticker["META"].capex_value == 18.997
    assert by_ticker["ORCL"].fiscal_period == "FY2026"
    assert by_ticker["ORCL"].capex_value == 55.663

    for ticker, actual in by_ticker.items():
        config = get_company_config(ticker)
        assert actual.source_type == "official"
        assert actual.collection_method == "sec_companyfacts_api"
        assert actual.source_url == companyfacts_url(config.cik)
        assert config.cik in actual.source_id
        assert actual.unit == "USD_B"
        assert actual.form_type in {"10-Q", "10-K"}
        assert actual.snapshot_path
        snapshot_path = Path(actual.snapshot_path)
        assert snapshot_path.exists()
        snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        assert snapshot["metadata"]["ticker"] == ticker
        assert snapshot["metadata"]["cik"] == config.cik
        assert snapshot["metadata"]["xbrl_tag"] == config.capex_xbrl_tag
        assert snapshot["metadata"]["raw_unit"] == "USD"
        assert snapshot["metadata"]["raw_value"] == snapshot["selected_fact"]["val"]
        assert snapshot["raw_companyfacts"]["facts"]
        assert actual.raw_payload_hash == hash_raw_payload(snapshot["raw_companyfacts"])


def test_quarter_availability_is_exposed_without_trend_label(tmp_path):
    result = _collect_from_fixtures(tmp_path)

    assert result.trend_availability["MSFT"]["sequential_quarter_count"] == 4
    assert result.trend_availability["MSFT"]["can_evaluate_trend"] is True
    assert result.trend_availability["MSFT"]["trend_label"] is None

    assert result.trend_availability["META"]["sequential_quarter_count"] == 3
    assert result.trend_availability["META"]["can_evaluate_trend"] is False
    assert result.trend_availability["META"]["trend_label"] is None


def test_missing_tag_returns_quality_event_without_fabricated_actual(tmp_path):
    config = dataclasses.replace(
        get_company_config("MSFT"),
        capex_xbrl_tag="MissingCapexTag",
    )

    result = collect_sec_capex_actuals(
        configs=[config],
        client=FixtureCompanyfactsClient(),
        snapshot_dir=tmp_path / "tracker_snapshots" / "sec_capex",
        run_id="test-missing-tag",
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert result.actuals == []
    assert len(result.quality_events) == 1
    event = result.quality_events[0]
    assert event.error_code == SEC_TAG_NOT_FOUND
    assert event.is_production_eligible is False
    assert event.is_blocking is True
    assert "MissingCapexTag" in event.message
    assert Path(event.snapshot_path).exists()


def test_sec_403_or_429_returns_source_unavailable_quality_event(tmp_path):
    class UnavailableClient:
        def fetch_companyfacts(self, config):
            raise SecCompanyfactsUnavailable(
                "SEC rate limited test response",
                status_code=429,
                source_url=companyfacts_url(config.cik),
            )

    result = collect_sec_capex_actuals(
        configs=[get_company_config("MSFT")],
        client=UnavailableClient(),
        snapshot_dir=tmp_path / "tracker_snapshots" / "sec_capex",
        run_id="test-sec-unavailable",
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert result.actuals == []
    assert len(result.quality_events) == 1
    event = result.quality_events[0]
    assert event.error_code == SEC_SOURCE_UNAVAILABLE
    assert event.is_production_eligible is False
    assert event.confidence == 0.0
    assert "429" in event.message
    assert Path(event.snapshot_path).exists()


def test_sec_client_sends_compliant_user_agent_without_network():
    class FakeResponse:
        status_code = 200
        text = "{}"

        def json(self):
            return {"facts": {"us-gaap": {}}}

    class FakeSession:
        def __init__(self):
            self.headers_seen = None

        def get(self, url, headers=None, timeout=None):
            self.headers_seen = headers
            return FakeResponse()

    session = FakeSession()
    user_agent = "AI Compute Tracker/2.0 contact@example.com"
    client = SecCompanyfactsClient(user_agent=user_agent, session=session)
    payload = client.fetch_companyfacts(get_company_config("MSFT"))

    assert payload == {"facts": {"us-gaap": {}}}
    assert session.headers_seen["User-Agent"] == user_agent
    assert "python-requests" not in session.headers_seen["User-Agent"].lower()
    assert "@" in DEFAULT_SEC_USER_AGENT


def test_collected_capex_actuals_insert_into_production_store_as_usd_b(tmp_path):
    result = _collect_from_fixtures(tmp_path)
    db_path = tmp_path / "tracker.db"
    db = Database(str(db_path))
    store = ProductionStore(db)

    inserted = store.insert_capex_actuals(result.actuals)
    assert inserted == 5

    conn = duckdb.connect(str(db_path))
    rows = conn.execute(
        """
        SELECT ticker, capex_value, unit, source_type, collection_method, xbrl_tag,
               source_url, snapshot_path, raw_payload_hash, error_code
        FROM production_capex_actuals
        ORDER BY ticker
        """
    ).fetchall()
    conn.close()

    assert len(rows) == 5
    by_ticker = {row[0]: row for row in rows}
    assert by_ticker["AMZN"][1] == 44.203
    assert by_ticker["AMZN"][2] == "USD_B"
    assert by_ticker["AMZN"][5] == "PaymentsToAcquireProductiveAssets"
    for row in rows:
        assert row[3] == "official"
        assert row[4] == "sec_companyfacts_api"
        assert row[6].startswith("https://data.sec.gov/api/xbrl/companyfacts/CIK")
        assert Path(row[7]).exists()
        assert row[8].startswith("sha256:")
        assert row[9] is None


def test_hash_raw_payload_is_canonical_and_stable():
    payload = {"b": 2, "a": {"nested": True}}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    expected = "sha256:" + hashlib.sha256(canonical).hexdigest()

    assert hash_raw_payload(payload) == expected
