import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_landscape import full_landscape  # noqa: E402
from index_freeze import (  # noqa: E402
    INDEX_SNAPSHOT_DIR,
    apply_weekly_freezes,
    build_receipt_index,
)


PROVIDERS = ("a", "b", "c", "d", "e")


def _offer(day, provider, price, series="H100", kind="on-demand"):
    return {
        "date": day,
        "provider": provider,
        "series": series,
        "kind": kind,
        "usdPerGpuHour": price,
        "sourceUrl": f"https://example.com/{series}/{provider}/{day}",
    }


def _week_rows(day, base, series="H100", kind="on-demand"):
    return [_offer(day, provider, base + index, series=series, kind=kind) for index, provider in enumerate(PROVIDERS)]


def _flat_week_rows(day, price, series="H100"):
    return [_offer(day, provider, price, series=series) for provider in PROVIDERS]


def _card(full, card_id="H100"):
    return next(card for card in full["cards"] if card["id"] == card_id)


def _weeks(card):
    return {week["isoWeek"]: week for week in card["weekly"]["weeks"]}


def test_final_weeks_are_frozen_and_idempotent(tmp_path):
    rows = _week_rows("2026-09-21", 4.0) + _week_rows("2026-09-28", 5.0)
    full = full_landscape(rows, as_of="2026-10-05")
    card = _card(full)
    before = {iso: deepcopy(week) for iso, week in _weeks(card).items()}
    before_receipts = deepcopy(card["weekly"]["receipts"])
    before_latest = deepcopy(card["weekly"]["latest"])
    assert set(before) == {"2026-W39", "2026-W40"}
    assert all(week["vintage"] == "final" for week in before.values())

    apply_weekly_freezes(full, tmp_path)

    snapshot_path = tmp_path / "2026-W39.json"
    assert snapshot_path.exists()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert snapshot["isoWeek"] == "2026-W39"
    assert snapshot["frozenAt"].endswith("Z")
    assert snapshot["methodologyVersion"] == full["methodologyVersion"]
    assert snapshot["cards"]["H100"]["week"]["isoWeek"] == "2026-W39"
    assert snapshot["cards"]["H100"]["receipt"]["weekStart"] == before["2026-W39"]["weekStart"]
    assert (tmp_path / "2026-W40.json").exists()
    assert card["weekly"]["latest"] == before_latest

    # Change the tracked rows: every final week must replay the snapshot values.
    changed_rows = _week_rows("2026-09-21", 14.0) + _week_rows("2026-09-28", 5.0)
    changed = full_landscape(changed_rows, as_of="2026-10-05")
    changed_card = _card(changed)
    assert _weeks(changed_card)["2026-W39"]["median"] != before["2026-W39"]["median"]

    snapshot_text = snapshot_path.read_text(encoding="utf-8")
    apply_weekly_freezes(changed, tmp_path)
    frozen_card = _card(changed)
    assert _weeks(frozen_card) == before
    assert frozen_card["weekly"]["receipts"] == before_receipts
    assert frozen_card["weekly"]["latest"] == before_latest
    assert frozen_card["weeklyIndex"] == before_latest
    assert snapshot_path.read_text(encoding="utf-8") == snapshot_text

    # A second pass (fresh full dict) must not change values or rewrite the file.
    again = full_landscape(changed_rows, as_of="2026-10-05")
    apply_weekly_freezes(again, tmp_path)
    assert _weeks(_card(again)) == before
    assert snapshot_path.read_text(encoding="utf-8") == snapshot_text


def test_provisional_week_is_not_written_or_overwritten(tmp_path):
    rows = _week_rows("2026-09-21", 4.0) + _week_rows("2026-09-28", 5.0)
    full = full_landscape(rows, as_of="2026-10-01")
    card = _card(full)
    weeks = _weeks(card)
    assert weeks["2026-W39"]["vintage"] == "final"
    assert weeks["2026-W40"]["vintage"] == "provisional"
    frozen_w39 = deepcopy(weeks["2026-W39"])
    frozen_receipt = deepcopy(card["weekly"]["receipts"]["2026-W39"])

    apply_weekly_freezes(full, tmp_path)
    assert (tmp_path / "2026-W39.json").exists()
    assert not (tmp_path / "2026-W40.json").exists()

    # Provisional W40 moves with the tracked data.
    changed_rows = _week_rows("2026-09-21", 4.0) + _week_rows("2026-09-28", 50.0)
    changed = full_landscape(changed_rows, as_of="2026-10-01")
    changed_card = _card(changed)
    changed_w40 = deepcopy(_weeks(changed_card)["2026-W40"])
    assert changed_w40["median"] == 52.0

    apply_weekly_freezes(changed, tmp_path)
    frozen_card = _card(changed)
    assert _weeks(frozen_card)["2026-W39"] == frozen_w39
    assert frozen_card["weekly"]["receipts"]["2026-W39"] == frozen_receipt
    assert _weeks(frozen_card)["2026-W40"] == changed_w40
    assert frozen_card["weekly"]["latest"] == changed_w40
    assert not (tmp_path / "2026-W40.json").exists()


def test_provisional_week_is_rechained_from_frozen_final_anchor(tmp_path):
    """Critic P1-1: W39 frozen at median 4/index 100; W40 must chain to 125, not 500."""
    rows = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows("2026-09-28", 5.0)
    full = full_landscape(rows, as_of="2026-10-01")
    card = _card(full)
    weeks = _weeks(card)
    assert weeks["2026-W39"]["vintage"] == "final"
    assert weeks["2026-W39"]["index"] == 100.0
    assert weeks["2026-W40"]["vintage"] == "provisional"
    assert weeks["2026-W40"]["index"] == 125.0
    apply_weekly_freezes(full, tmp_path)
    assert (tmp_path / "2026-W39.json").exists()
    assert not (tmp_path / "2026-W40.json").exists()

    # Change the closed week after the first freeze.
    changed_rows = _flat_week_rows("2026-09-21", 1.0) + _flat_week_rows("2026-09-28", 5.0)
    changed = full_landscape(changed_rows, as_of="2026-10-01")
    changed_weeks = _weeks(_card(changed))
    assert changed_weeks["2026-W39"]["median"] == 1.0
    assert changed_weeks["2026-W39"]["index"] == 100.0
    assert changed_weeks["2026-W40"]["index"] == 500.0  # based on the un-frozen W39

    apply_weekly_freezes(changed, tmp_path)
    frozen = _card(changed)
    frozen_weeks = _weeks(frozen)
    assert frozen_weeks["2026-W39"]["median"] == 4.0
    assert frozen_weeks["2026-W39"]["index"] == 100.0
    assert frozen_weeks["2026-W40"]["median"] == 5.0
    assert frozen_weeks["2026-W40"]["index"] == 125.0
    assert frozen_weeks["2026-W40"]["linkPairs"] == 5
    receipt = frozen["weekly"]["receipts"]["2026-W40"]
    assert receipt["index"] == 125.0
    assert receipt["linkPairs"] == 5
    assert frozen["weekly"]["latest"]["isoWeek"] == "2026-W40"
    assert frozen["weekly"]["latest"]["index"] == 125.0
    assert frozen["weeklyIndex"]["index"] == 125.0
    assert not (tmp_path / "2026-W40.json").exists()


def test_rechain_uses_each_frozen_week_as_new_anchor(tmp_path):
    """Two frozen weeks: W41 must chain from W40's own frozen index, not the recomputed one."""
    rows = (
        _flat_week_rows("2026-09-21", 4.0)
        + _flat_week_rows("2026-09-28", 6.0)
        + _flat_week_rows("2026-10-05", 3.0)
    )
    full = full_landscape(rows, as_of="2026-10-07")
    weeks = _weeks(_card(full))
    assert weeks["2026-W39"]["vintage"] == "final"
    assert weeks["2026-W40"]["vintage"] == "final"
    assert weeks["2026-W41"]["vintage"] == "provisional"
    assert weeks["2026-W39"]["index"] == 100.0
    assert weeks["2026-W40"]["index"] == 150.0
    assert weeks["2026-W41"]["index"] == 75.0
    apply_weekly_freezes(full, tmp_path)
    assert (tmp_path / "2026-W40.json").exists()
    assert not (tmp_path / "2026-W41.json").exists()

    changed_rows = (
        _flat_week_rows("2026-09-21", 1.0)
        + _flat_week_rows("2026-09-28", 2.0)
        + _flat_week_rows("2026-10-05", 3.0)
    )
    changed = full_landscape(changed_rows, as_of="2026-10-07")
    changed_weeks = _weeks(_card(changed))
    assert changed_weeks["2026-W40"]["index"] == 200.0  # recomputed from changed W39
    assert changed_weeks["2026-W41"]["index"] == 300.0  # recomputed from changed W40

    apply_weekly_freezes(changed, tmp_path)
    frozen = _card(changed)
    frozen_weeks = _weeks(frozen)
    assert frozen_weeks["2026-W39"]["index"] == 100.0
    assert frozen_weeks["2026-W40"]["median"] == 6.0
    assert frozen_weeks["2026-W40"]["index"] == 150.0
    assert frozen_weeks["2026-W41"]["median"] == 3.0
    assert frozen_weeks["2026-W41"]["index"] == 75.0  # 150 * (3 / 6)
    assert frozen_weeks["2026-W41"]["linkPairs"] == 5
    receipt = frozen["weekly"]["receipts"]["2026-W41"]
    assert receipt["index"] == 75.0
    assert receipt["linkPairs"] == 5
    assert frozen["weekly"]["latest"]["index"] == 75.0
    assert frozen["weeklyIndex"]["index"] == 75.0


def test_new_final_week_is_rechained_before_its_first_freeze(tmp_path):
    """Challenger high-1: a new final week must not freeze the raw 500 from revised history."""
    first = full_landscape(_flat_week_rows("2026-09-21", 4.0), as_of="2026-09-28")
    assert _weeks(_card(first))["2026-W39"]["vintage"] == "final"
    apply_weekly_freezes(first, tmp_path)
    w39_snapshot = json.loads((tmp_path / "2026-W39.json").read_text(encoding="utf-8"))
    assert w39_snapshot["cards"]["H100"]["week"]["median"] == 4.0
    assert w39_snapshot["cards"]["H100"]["week"]["index"] == 100.0
    assert not (tmp_path / "2026-W40.json").exists()

    # W39 is revised and W40 closes for the first time in the same build.
    rows = _flat_week_rows("2026-09-21", 1.0) + _flat_week_rows("2026-09-28", 5.0)
    second = full_landscape(rows, as_of="2026-10-05")
    assert _weeks(_card(second))["2026-W40"]["index"] == 500.0  # raw, pre-snapshot

    apply_weekly_freezes(second, tmp_path)
    frozen_weeks = _weeks(_card(second))
    assert frozen_weeks["2026-W39"]["median"] == 4.0
    assert frozen_weeks["2026-W39"]["index"] == 100.0
    assert frozen_weeks["2026-W40"]["median"] == 5.0
    assert frozen_weeks["2026-W40"]["index"] == 125.0
    assert frozen_weeks["2026-W40"]["linkPairs"] == 5

    w40_snapshot = json.loads((tmp_path / "2026-W40.json").read_text(encoding="utf-8"))
    assert w40_snapshot["cards"]["H100"]["week"]["index"] == 125.0
    assert w40_snapshot["cards"]["H100"]["receipt"]["index"] == 125.0
    w40_text = (tmp_path / "2026-W40.json").read_text(encoding="utf-8")

    again = full_landscape(rows, as_of="2026-10-05")
    apply_weekly_freezes(again, tmp_path)
    assert _weeks(_card(again))["2026-W40"]["index"] == 125.0
    assert (tmp_path / "2026-W40.json").read_text(encoding="utf-8") == w40_text


def test_withheld_frozen_anchor_freezes_new_final_week_at_100(tmp_path):
    """A withheld frozen week has no index, so it must not anchor the next week."""
    withheld_rows = [_offer("2026-09-21", provider, 4.0) for provider in ("a", "b", "c")]
    first = full_landscape(withheld_rows, as_of="2026-09-28")
    w39 = _weeks(_card(first))["2026-W39"]
    assert w39["status"] == "withheld"
    assert w39["index"] is None
    apply_weekly_freezes(first, tmp_path)
    snapshot = json.loads((tmp_path / "2026-W39.json").read_text(encoding="utf-8"))
    assert snapshot["cards"]["H100"]["week"]["index"] is None

    # W39 is backfilled to published with median 1; W40 first closes at 5.
    rows = _flat_week_rows("2026-09-21", 1.0) + _flat_week_rows("2026-09-28", 5.0)
    second = full_landscape(rows, as_of="2026-10-05")
    assert _weeks(_card(second))["2026-W40"]["index"] == 500.0

    apply_weekly_freezes(second, tmp_path)
    frozen_weeks = _weeks(_card(second))
    assert frozen_weeks["2026-W39"]["status"] == "withheld"
    assert frozen_weeks["2026-W39"]["index"] is None
    assert frozen_weeks["2026-W40"]["index"] == 100.0
    assert frozen_weeks["2026-W40"]["linkPairs"] == 0
    w40_snapshot = json.loads((tmp_path / "2026-W40.json").read_text(encoding="utf-8"))
    assert w40_snapshot["cards"]["H100"]["week"]["index"] == 100.0


def test_existing_snapshot_wins_when_as_of_rolls_back_inside_the_week(tmp_path):
    """An existing W40 snapshot must be applied even when as_of makes it provisional again."""
    rows = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows("2026-09-28", 5.0)
    full = full_landscape(rows, as_of="2026-10-05")
    apply_weekly_freezes(full, tmp_path)
    original_w40 = deepcopy(_weeks(_card(full))["2026-W40"])
    assert original_w40["vintage"] == "final"
    assert original_w40["index"] == 125.0
    assert (tmp_path / "2026-W40.json").exists()

    changed_rows = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows("2026-09-28", 50.0)
    rolled = full_landscape(changed_rows, as_of="2026-10-01")
    rolled_w40 = _weeks(_card(rolled))["2026-W40"]
    assert rolled_w40["vintage"] == "provisional"
    assert rolled_w40["median"] == 50.0
    assert rolled_w40["index"] != original_w40["index"]

    apply_weekly_freezes(rolled, tmp_path)
    frozen_weeks = _weeks(_card(rolled))
    assert frozen_weeks["2026-W40"]["vintage"] == "final"
    assert frozen_weeks["2026-W40"]["median"] == 5.0
    assert frozen_weeks["2026-W40"]["index"] == 125.0
    assert frozen_weeks["2026-W40"]["linkPairs"] == 5


def test_missing_snapshot_week_is_injected_before_rechain(tmp_path):
    """A week that vanished from the current source is injected back and still anchors the chain."""
    first = full_landscape(_flat_week_rows("2026-09-21", 4.0), as_of="2026-09-28")
    apply_weekly_freezes(first, tmp_path)
    assert (tmp_path / "2026-W39.json").exists()
    assert not (tmp_path / "2026-W40.json").exists()

    second = full_landscape(_flat_week_rows("2026-09-28", 5.0), as_of="2026-10-05")
    second_card = _card(second)
    assert [week["isoWeek"] for week in second_card["weekly"]["weeks"]] == ["2026-W40"]
    assert _weeks(second_card)["2026-W40"]["index"] == 100.0  # raw base-100

    apply_weekly_freezes(second, tmp_path)
    card = _card(second)
    weeks = _weeks(card)
    assert list(weeks) == ["2026-W39", "2026-W40"]
    assert weeks["2026-W39"]["median"] == 4.0
    assert weeks["2026-W39"]["index"] == 100.0
    assert weeks["2026-W40"]["index"] == 125.0
    assert "2026-W39" in card["weekly"]["receipts"]
    assert card["weekly"]["latest"]["isoWeek"] == "2026-W40"
    assert card["weekly"]["latest"]["index"] == 125.0
    w40_snapshot = json.loads((tmp_path / "2026-W40.json").read_text(encoding="utf-8"))
    assert w40_snapshot["cards"]["H100"]["week"]["index"] == 125.0


def test_snapshot_card_missing_from_current_landscape_raises(tmp_path):
    """A whole card disappearing must fail instead of silently dropping frozen history."""
    both_cards = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows(
        "2026-09-21", 10.0, series="H200"
    )
    first = full_landscape(both_cards, as_of="2026-09-28")
    assert {card["id"] for card in first["cards"]} == {"H100", "H200"}
    apply_weekly_freezes(first, tmp_path)
    w39_path = tmp_path / "2026-W39.json"
    w39_text = w39_path.read_text(encoding="utf-8")
    assert set(json.loads(w39_text)["cards"]) == {"H100", "H200"}

    # Current source only has H100; W40 is a new final week that must not be written.
    only_h100 = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows("2026-09-28", 5.0)
    second = full_landscape(only_h100, as_of="2026-10-05")
    assert {card["id"] for card in second["cards"]} == {"H100"}

    with pytest.raises(ValueError) as excinfo:
        apply_weekly_freezes(second, tmp_path)
    message = str(excinfo.value)
    assert "H200" in message
    assert "拒绝静默丢弃冻结历史，请恢复底表或显式迁移快照" in message
    assert w39_path.read_text(encoding="utf-8") == w39_text
    assert not (tmp_path / "2026-W40.json").exists()


def test_snapshot_methodology_version_mismatch_raises(tmp_path):
    first = full_landscape(_flat_week_rows("2026-09-21", 4.0), as_of="2026-09-28")
    apply_weekly_freezes(first, tmp_path)
    path = tmp_path / "2026-W39.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    snapshot["methodologyVersion"] = "2099-01-01.1"
    path.write_text(json.dumps(snapshot), encoding="utf-8")
    before = path.read_text(encoding="utf-8")

    second = full_landscape(
        _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows("2026-09-28", 5.0),
        as_of="2026-10-05",
    )
    with pytest.raises(ValueError, match="methodologyVersion"):
        apply_weekly_freezes(second, tmp_path)
    assert path.read_text(encoding="utf-8") == before
    assert not (tmp_path / "2026-W40.json").exists()


def test_same_week_snapshot_merges_cards_without_losing_any(tmp_path):
    # Build 1: H100 closes W39; H200 only has W38. Both cards exist in the current landscape.
    first_rows = _flat_week_rows("2026-09-21", 4.0) + _flat_week_rows(
        "2026-09-14", 10.0, series="H200"
    )
    first = full_landscape(first_rows, as_of="2026-09-28")
    assert {card["id"] for card in first["cards"]} == {"H100", "H200"}
    apply_weekly_freezes(first, tmp_path)
    w39 = json.loads((tmp_path / "2026-W39.json").read_text(encoding="utf-8"))
    w38 = json.loads((tmp_path / "2026-W38.json").read_text(encoding="utf-8"))
    assert set(w39["cards"]) == {"H100"}
    assert set(w38["cards"]) == {"H200"}

    # Build 2: H200 also closes W39; the existing W39 file must gain H200, not lose H100.
    second_rows = first_rows + _flat_week_rows("2026-09-21", 12.0, series="H200")
    second = full_landscape(second_rows, as_of="2026-09-28")
    apply_weekly_freezes(second, tmp_path)
    w39 = json.loads((tmp_path / "2026-W39.json").read_text(encoding="utf-8"))
    assert set(w39["cards"]) == {"H100", "H200"}
    assert w39["cards"]["H100"]["week"]["median"] == 4.0
    assert w39["cards"]["H200"]["week"]["median"] == 12.0
    assert _weeks(_card(second, "H100"))["2026-W39"]["index"] == 100.0
    assert _weeks(_card(second, "H200"))["2026-W39"]["index"] == 120.0  # 100 * (12 / 10)

    # Build 3: changed row values still replay both frozen entries.
    changed_rows = (
        _flat_week_rows("2026-09-21", 40.0)
        + _flat_week_rows("2026-09-14", 100.0, series="H200")
        + _flat_week_rows("2026-09-21", 120.0, series="H200")
    )
    changed = full_landscape(changed_rows, as_of="2026-09-28")
    apply_weekly_freezes(changed, tmp_path)
    assert _weeks(_card(changed, "H100"))["2026-W39"]["median"] == 4.0
    assert _weeks(_card(changed, "H200"))["2026-W39"]["median"] == 12.0
    assert _weeks(_card(changed, "H200"))["2026-W39"]["index"] == 120.0


def test_snapshot_directory_is_created_when_missing(tmp_path):
    nested = tmp_path / "does" / "not" / "exist"
    full = full_landscape(_week_rows("2026-09-21", 4.0), as_of="2026-09-28")
    apply_weekly_freezes(full, nested)
    assert nested.is_dir()
    assert (nested / "2026-W39.json").exists()


def test_receipt_index_lists_all_weeks_and_marks_page_latest(tmp_path):
    rows = _week_rows("2026-09-21", 4.0) + _week_rows("2026-09-28", 5.0)
    full = full_landscape(rows, as_of="2026-10-01")
    apply_weekly_freezes(full, tmp_path)

    index = build_receipt_index(full)
    assert index["as_of"] == "2026-10-01"
    assert index["methodology_version"] == full["methodologyVersion"]
    assert index["count"] == len(index["weeks"]) == 2
    assert index["commands"]["reproduce_receipt"].startswith("python3 scripts/reproduce_receipt.py")
    assert "{card_id}" in index["commands"]["reproduce_receipt"]
    assert index["commands"]["example"].startswith("python3 scripts/reproduce_receipt.py")

    by_week = {item["iso_week"]: item for item in index["weeks"]}
    assert by_week["2026-W39"]["card_id"] == "H100"
    assert by_week["2026-W39"]["card_name"] == "H100 80GB"
    assert by_week["2026-W39"]["week_start"] == "2026-09-21"
    assert by_week["2026-W39"]["vintage"] == "final"
    assert by_week["2026-W39"]["available_via"] == "cli"
    assert by_week["2026-W40"]["available_via"] == "page_latest"
    for item in index["weeks"]:
        assert {
            "card_id",
            "card_name",
            "iso_week",
            "week_start",
            "vintage",
            "status",
            "provider_count",
            "methodology_version",
            "available_via",
        } == set(item)


def test_default_snapshot_dir_points_at_tracker_data():
    assert INDEX_SNAPSHOT_DIR == ROOT / "tracker_data" / "index_snapshots"
