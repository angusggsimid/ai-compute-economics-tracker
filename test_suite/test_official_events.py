import os
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import duckdb
import yaml

TRACKER_V2 = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TRACKER_V2))

from tracker_v2 import Database  # noqa: E402


def _default_yaml_path():
    return TRACKER_V2 / "data" / "manual_official_events.yml"


def _fetcher_from_yaml(yaml_path):
    from data_sources.official_events import SourceFetchResult  # noqa: E402

    payload = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    pages = {}
    for entry in payload["events"]:
        pages.setdefault(entry["source_url"], []).append(entry["source_excerpt"])
    pages = {
        url: (
            "<html><body><article>"
            + "".join(f"<p>{excerpt}</p>" for excerpt in excerpts)
            + "</article></body></html>"
        ).encode("utf-8")
        for url, excerpts in pages.items()
    }

    def fetcher(url):
        return SourceFetchResult(
            status_code=200,
            final_url=url,
            body=pages[url],
            content_type="text/html; charset=utf-8",
        )

    return fetcher


def _write_yaml(path, events):
    path.write_text(yaml.safe_dump({"events": events}, sort_keys=False), encoding="utf-8")


def test_source_backed_yaml_produces_provenanced_official_events(tmp_path):
    from data_sources.official_events import collect_official_events  # noqa: E402

    yaml_path = _default_yaml_path()
    result = collect_official_events(
        yaml_path=yaml_path,
        snapshot_dir=tmp_path / "snapshots",
        fetcher=_fetcher_from_yaml(yaml_path),
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert result.rejected_events == []
    assert len(result.source_backed_events) == 6
    assert {event.company for event in result.source_backed_events} >= {
        "Amazon",
        "Meta",
        "Alphabet",
        "Oracle",
        "Microsoft",
    }
    assert {event.collector_name for event in result.source_backed_events} == {
        "manual_sourcebacked_yaml"
    }

    event_types = {event.event_type for event in result.production_events}
    assert {
        "capex_guidance_revision",
        "rpo",
        "management_capacity_comment",
        "capacity_comment",
    } <= event_types

    metrics = {event.metric for event in result.production_events}
    assert "fy2026_capex_guidance_low" in metrics
    assert "fy2026_capex_guidance_previous_high" in metrics

    for event in result.production_events:
        assert event.source_url.startswith("https://")
        assert event.collection_method == "manual_sourcebacked_yaml"
        assert event.source_type == "official"
        assert event.snapshot_path
        assert Path(event.snapshot_path).exists()
        assert event.raw_payload_hash.startswith("sha256:")
        assert event.is_production_eligible is True
        assert event.value is not None


def test_loader_rejects_missing_source_proof_before_fetch(tmp_path):
    from data_sources.official_events import collect_official_events  # noqa: E402

    bad_yaml = tmp_path / "bad.yml"
    _write_yaml(
        bad_yaml,
        [
            {
                "event_id": "bad_missing_proof",
                "ticker": "MSFT",
                "company": "Microsoft",
                "announcement_date": "2026-01-28",
                "event_type": "rpo",
                "metric": "remaining_performance_obligations",
                "unit": "USD_B",
                "collector_name": "manual_sourcebacked_yaml",
            }
        ],
    )

    def forbidden_fetch(_url):
        raise AssertionError("missing proof must be rejected before network fetch")

    result = collect_official_events(
        yaml_path=bad_yaml,
        snapshot_dir=tmp_path / "snapshots",
        fetcher=forbidden_fetch,
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert result.production_events == []
    assert [item.reason for item in result.rejected_events] == ["MISSING_SOURCE_PROOF"]
    assert [event.error_code for event in result.quality_events] == ["MISSING_SOURCE_PROOF"]


def test_loader_marks_source_unavailable_and_does_not_trust_yaml(tmp_path):
    from data_sources.official_events import SourceFetchResult, collect_official_events  # noqa: E402

    source_url = "https://www.microsoft.com/en-us/investor/events/fy-2026/earnings-fy-2026-q2"
    fixture = tmp_path / "events.yml"
    _write_yaml(
        fixture,
        [
            {
                "event_id": "msft_unavailable",
                "ticker": "MSFT",
                "company": "Microsoft",
                "announcement_date": "2026-01-28",
                "fiscal_period": "Q2 FY2026",
                "event_type": "management_capacity_comment",
                "metric": "customer_demand_exceeds_supply",
                "value": 1,
                "unit": "evidence_flag",
                "source_url": source_url,
                "source_excerpt": "Our customer demand continues to exceed our supply.",
                "collector_name": "manual_sourcebacked_yaml",
            }
        ],
    )

    def unavailable_fetch(_url):
        return SourceFetchResult(
            status_code=429,
            final_url=source_url,
            body=b"<html><title>Just a moment...</title></html>",
            content_type="text/html",
        )

    result = collect_official_events(
        yaml_path=fixture,
        snapshot_dir=tmp_path / "snapshots",
        fetcher=unavailable_fetch,
        fetched_at="2026-07-05T10:00:00Z",
    )

    assert result.production_events == []
    assert [item.reason for item in result.rejected_events] == ["SOURCE_UNAVAILABLE"]
    assert [event.error_code for event in result.quality_events] == ["SOURCE_UNAVAILABLE"]
    assert Path(result.rejected_events[0].snapshot_path).exists()


def test_source_backed_events_insert_through_production_store(tmp_path):
    from data_sources.official_events import collect_official_events, insert_official_events  # noqa: E402
    from production_store import ProductionStore  # noqa: E402

    yaml_path = _default_yaml_path()
    result = collect_official_events(
        yaml_path=yaml_path,
        snapshot_dir=tmp_path / "snapshots",
        fetcher=_fetcher_from_yaml(yaml_path),
        fetched_at="2026-07-05T10:00:00Z",
    )
    db = Database(str(tmp_path / "tracker.db"))
    counts = insert_official_events(result, ProductionStore(db))

    assert counts == {"events_inserted": len(result.production_events), "quality_events_inserted": 0}

    conn = db.get_connection()
    try:
        row_count = conn.execute("SELECT COUNT(*) FROM production_official_events").fetchone()[0]
        source_types = {
            row[0]
            for row in conn.execute(
                "SELECT DISTINCT source_type FROM production_official_events"
            ).fetchall()
        }
    finally:
        conn.close()

    assert row_count == len(result.production_events)
    assert source_types == {"official"}


def test_cli_official_events_loads_source_backed_events_only(tmp_path):
    html_dir = tmp_path / "html"
    html_dir.mkdir()
    page = html_dir / "source.html"
    excerpt = "Our customer demand continues to exceed our supply."
    page.write_text(f"<html><body>{excerpt}</body></html>", encoding="utf-8")

    class QuietHandler(SimpleHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa: A002
            return

    handler = partial(QuietHandler, directory=str(html_dir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    thread = threading.Thread(
        target=server.serve_forever,
        daemon=True,
    )
    thread.start()

    try:
        yaml_path = tmp_path / "events.yml"
        _write_yaml(
            yaml_path,
            [
                {
                    "event_id": "local_msft",
                    "ticker": "MSFT",
                    "company": "Microsoft",
                    "announcement_date": "2026-01-28",
                    "fiscal_period": "Q2 FY2026",
                    "event_type": "management_capacity_comment",
                    "metric": "customer_demand_exceeds_supply",
                    "value": 1,
                    "unit": "evidence_flag",
                    "source_url": f"http://127.0.0.1:{port}/source.html",
                    "source_excerpt": excerpt,
                    "collector_name": "manual_sourcebacked_yaml",
                }
            ],
        )

        env = {
            **os.environ,
            "TRACKER_OFFICIAL_EVENTS_YAML": str(yaml_path),
            "TRACKER_OFFICIAL_EVENTS_SNAPSHOT_DIR": str(tmp_path / "snapshots"),
        }
        result = subprocess.run(
            [
                sys.executable,
                str(TRACKER_V2 / "tracker_v2.py"),
                "update",
                "--production",
                "--only",
                "official-events",
            ],
            cwd=tmp_path,
            env=env,
            text=True,
            capture_output=True,
        )
    finally:
        server.shutdown()

    assert result.returncode == 0, result.stderr
    assert "OFFICIAL_EVENTS_LOADED" in result.stdout

    conn = duckdb.connect(str(tmp_path / "ai_compute_tracker.db"))
    try:
        event_count = conn.execute("SELECT COUNT(*) FROM production_official_events").fetchone()[0]
        quality_count = conn.execute("SELECT COUNT(*) FROM production_data_quality_events").fetchone()[0]
    finally:
        conn.close()

    assert event_count == 1
    assert quality_count == 0
