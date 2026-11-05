import csv
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))
sys.path.insert(0, str(ROOT / "scripts"))

import reproduce_receipt  # noqa: E402
from gpu_landscape import METHODOLOGY_VERSION  # noqa: E402


SCRIPT = ROOT / "scripts" / "reproduce_receipt.py"
PAGE_SOURCE = ROOT / "html_dashboard" / "build_time_series_dashboard.py"


def _offer(day, provider, price, kind="on-demand"):
    return {
        "date": day,
        "provider": provider,
        "series": "H100",
        "kind": kind,
        "usdPerGpuHour": price,
        "sourceUrl": f"https://example.com/{provider}/{day}",
    }


def _write_data(tmp_path):
    rows = []
    for index, provider in enumerate(("a", "b", "c", "d", "e")):
        rows.append(_offer("2026-09-21", provider, 4 + index))
        rows.append(_offer("2026-09-28", provider, 5 + index))
    rows.append(_offer("2026-09-21", "community-x", 1.0, kind="community"))
    path = tmp_path / "history.json"
    path.write_text(json.dumps({"rows": rows}), encoding="utf-8")
    return path


def _run(tmp_path, data_path, card="H100", week="2026-W39"):
    out = tmp_path / f"{card.replace(' ', '-')}-{week}.csv"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--data",
            str(data_path),
            "--snapshot-dir",
            str(tmp_path / "snapshots"),
            "--card",
            card,
            "--week",
            week,
            "--out",
            str(out),
        ],
        capture_output=True,
        text=True,
    )
    return proc, out


def _page_receipt_columns():
    source = PAGE_SOURCE.read_text(encoding="utf-8")
    match = re.search(r"\[('card'[^\]]*'excluded_by')\]\s*\.join\(\s*','\s*\)", source)
    assert match, "could not find the _landscapeReceipt CSV header in the page source"
    return re.findall(r"'([^']*)'", match.group(1))


def test_cli_columns_match_the_page_download():
    expected = [
        "card",
        "iso_week",
        "vintage",
        "methodology_version",
        "published_median",
        "published_index",
        "p25",
        "p75",
        "provider_count",
        "provider",
        "provider_id",
        "usd_per_gpu_hour",
        "date",
        "source_url",
        "quotes",
        "included",
        "excluded_by",
    ]
    assert _page_receipt_columns() == expected
    assert reproduce_receipt.CSV_COLUMNS == expected


def test_cli_writes_receipt_with_included_and_excluded_rows(tmp_path):
    data = _write_data(tmp_path)
    proc, out = _run(tmp_path, data)
    assert proc.returncode == 0, proc.stderr
    assert out.exists()

    with out.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    assert rows[0] == _page_receipt_columns()
    body = rows[1:]
    assert len(body) == 6  # 5 included providers + 1 community quote
    assert all(len(row) == len(rows[0]) for row in body)
    assert all(row[:9] == body[0][:9] for row in body)

    first = body[0]
    assert first[0] == "H100"
    assert first[1] == "2026-W39"
    assert first[2] == "final"
    assert first[3] == METHODOLOGY_VERSION
    assert first[4] == "6"  # median of 4..8, JS-style whole number
    assert first[5] == "100"  # base week, JS String(100.0) drops .0
    assert first[6] == "4.5"
    assert first[7] == "7.5"
    assert first[8] == "5"

    included = [row for row in body if row[15] == "true"]
    excluded = [row for row in body if row[15] == "false"]
    assert len(included) == 5
    assert len(excluded) == 1
    assert {row[10] for row in included} == {"a", "b", "c", "d", "e"}
    assert {row[11] for row in included} == {"4", "5", "6", "7", "8"}
    assert all(row[16] == "" for row in included)
    assert all(row[13].startswith("https://example.com/") for row in included)

    assert excluded[0][9] == "Community X"
    assert excluded[0][10] == "community-x"
    assert excluded[0][14] == "1"  # excluded rows default quotes to 1
    assert excluded[0][16] == "market_not_on_demand"


def test_cli_replays_the_frozen_final_week(tmp_path):
    data = _write_data(tmp_path)
    first_proc, out = _run(tmp_path, data)
    assert first_proc.returncode == 0, first_proc.stderr
    first_csv = out.read_text(encoding="utf-8")
    assert (tmp_path / "snapshots" / "2026-W39.json").exists()

    payload = json.loads(data.read_text(encoding="utf-8"))
    for row in payload["rows"]:
        if row["date"] == "2026-09-21":
            row["usdPerGpuHour"] += 10
    data.write_text(json.dumps(payload), encoding="utf-8")

    second_proc, out = _run(tmp_path, data)
    assert second_proc.returncode == 0, second_proc.stderr
    assert out.read_text(encoding="utf-8") == first_csv


def test_cli_missing_week_exits_nonzero(tmp_path):
    data = _write_data(tmp_path)
    proc, out = _run(tmp_path, data, week="2026-W99")
    assert proc.returncode == 1
    assert "not found" in proc.stderr.lower()
    assert "2026-W99" in proc.stderr
    assert not out.exists()


def test_cli_missing_card_exits_nonzero(tmp_path):
    data = _write_data(tmp_path)
    proc, out = _run(tmp_path, data, card="NOPE")
    assert proc.returncode == 1
    assert "not found" in proc.stderr.lower()
    assert "H100" in proc.stderr
    assert not out.exists()
