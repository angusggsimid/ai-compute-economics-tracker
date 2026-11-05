#!/usr/bin/env python3
"""Reproduce the page receipt CSV for one card x ISO week.

The CSV columns and quoting match the dashboard's ``_landscapeReceipt`` download
exactly, so a historical receipt can be replayed without keeping every week in
``public/data``.

Examples::

    python3 scripts/reproduce_receipt.py --card H100 --week 2026-W44 --out /tmp/h100-w44.csv
    python3 scripts/reproduce_receipt.py --card "RTX PRO 6000" --week 2026-W43 --out /tmp/rtx.csv

Final weeks are read through the same immutable snapshots as the build.  If a
snapshot does not exist yet, the current tracked value is frozen first.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_landscape import full_landscape  # noqa: E402
from index_freeze import INDEX_SNAPSHOT_DIR, apply_weekly_freezes  # noqa: E402


DEFAULT_DATA = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"

# Must stay in sync with _landscapeReceipt in build_time_series_dashboard.py.
CSV_COLUMNS = [
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


def _js_cell(value: Any) -> str:
    """Quote a value like the page's JS ``cell()`` helper.

    Every field is quoted, quotes are doubled, ``None`` becomes an empty string,
    and whole-number floats drop the trailing ``.0`` (JS ``String(100.0)`` is
    ``"100"``).
    """
    if value is None:
        text = ""
    elif isinstance(value, bool):
        text = "true" if value else "false"
    elif isinstance(value, float):
        if value != value:  # NaN
            text = "NaN"
        elif value.is_integer():
            text = str(int(value))
        else:
            text = repr(value)
    else:
        text = str(value)
    return '"' + text.replace('"', '""') + '"'


def _load_rows(data_path: Path) -> List[Dict[str, Any]]:
    payload = json.loads(Path(data_path).read_text(encoding="utf-8"))
    rows = payload.get("rows") if isinstance(payload, dict) else payload
    if not isinstance(rows, list) or not rows:
        raise ValueError(f"no rows found in {data_path}")
    return rows


def _find_card(full: Dict[str, Any], card_id: str) -> Optional[Dict[str, Any]]:
    target = str(card_id).strip().lower()
    for card in full.get("cards") or []:
        if str(card.get("id")).strip().lower() == target:
            return card
    return None


def _find_week(card: Dict[str, Any], iso_week: str) -> Optional[Dict[str, Any]]:
    weekly = card.get("weekly") or {}
    for week in weekly.get("weeks") or []:
        if str(week.get("isoWeek") or "").upper() == iso_week:
            return week
    return None


def render_csv(card_id: str, week: Dict[str, Any], receipt: Dict[str, Any]) -> str:
    """Render one receipt using the exact page columns and quoting."""
    iso_week = week.get("isoWeek")
    meta = [
        card_id,
        iso_week,
        receipt.get("vintage"),
        receipt.get("methodologyVersion"),
        receipt.get("median"),
        receipt.get("index"),
        receipt.get("p25"),
        receipt.get("p75"),
        receipt.get("providerCount"),
    ]
    lines = [",".join(CSV_COLUMNS)]
    for item in receipt.get("included") or []:
        row = meta + [
            item.get("provider"),
            item.get("providerId"),
            item.get("value"),
            item.get("date"),
            item.get("sourceUrl"),
            item.get("quotes"),
            "true",
            "",
        ]
        lines.append(",".join(_js_cell(value) for value in row))
    for item in receipt.get("excluded") or []:
        quotes = item.get("quotes")
        row = meta + [
            item.get("provider"),
            item.get("providerId"),
            item.get("value"),
            item.get("date"),
            item.get("sourceUrl"),
            1 if quotes is None else quotes,
            "false",
            item.get("rule") or "",
        ]
        lines.append(",".join(_js_cell(value) for value in row))
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Reproduce a dashboard receipt CSV for one card x ISO week."
    )
    parser.add_argument("--card", required=True, help='Card id, e.g. "H100" or "RTX PRO 6000".')
    parser.add_argument("--week", required=True, help="ISO week, e.g. 2026-W44.")
    parser.add_argument("--out", required=True, type=Path, help="CSV output path.")
    parser.add_argument(
        "--data",
        type=Path,
        default=DEFAULT_DATA,
        help=f"Neocloud history JSON (default: {DEFAULT_DATA}).",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=INDEX_SNAPSHOT_DIR,
        help="Immutable week snapshot directory (default: tracker_data/index_snapshots).",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = _parser().parse_args(argv)
    iso_week = str(args.week).strip().upper()

    try:
        rows = _load_rows(args.data)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot read {args.data}: {exc}", file=sys.stderr)
        return 2

    try:
        full = full_landscape(rows)
        apply_weekly_freezes(full, args.snapshot_dir)
    except (OSError, ValueError) as exc:
        print(f"error: cannot build weekly index: {exc}", file=sys.stderr)
        return 2

    card = _find_card(full, args.card)
    if card is None:
        available = ", ".join(str(item.get("id")) for item in full.get("cards") or [])
        print(
            f"error: card {args.card!r} not found in {args.data}. Available cards: {available}",
            file=sys.stderr,
        )
        return 1

    week = _find_week(card, iso_week)
    if week is None:
        available_weeks = ", ".join(
            str(item.get("isoWeek")) for item in (card.get("weekly") or {}).get("weeks") or []
        )
        print(
            f"error: week {iso_week!r} not found for card {card['id']}. "
            f"Available weeks: {available_weeks}",
            file=sys.stderr,
        )
        return 1

    receipt = ((card.get("weekly") or {}).get("receipts") or {}).get(week.get("isoWeek"))
    if not isinstance(receipt, dict):
        print(
            f"error: receipt not available for card {card['id']} week {week.get('isoWeek')}",
            file=sys.stderr,
        )
        return 2

    csv_text = render_csv(str(card["id"]), week, receipt)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(csv_text, encoding="utf-8")
    print(
        f"wrote {out_path} ({len(csv_text.splitlines()) - 1} quote rows, "
        f"{card['id']} {week.get('isoWeek')})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
