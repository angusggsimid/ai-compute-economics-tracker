"""Immutable weekly index snapshots for closed (final) ISO weeks.

The module is deliberately explicit about I/O: callers must invoke
``apply_weekly_freezes()`` after ``full_landscape()``.  ``full_landscape`` never
touches the filesystem, so synthetic test rows cannot pollute the repository
snapshots.

Snapshot layout::

    tracker_data/index_snapshots/<ISO_WEEK>.json
    {
      "isoWeek": "2026-W44",
      "frozenAt": "2026-11-04T00:00:00Z",
      "methodologyVersion": "2026-11-04.1",
      "cards": {
        "H100": {
          "week": {...},      # entry from card.weekly.weeks
          "receipt": {...}    # entry from card.weekly.receipts
        }
      }
    }

Only ``vintage == "final"`` weeks are frozen.  Provisional weeks are never
written to snapshots; their in-memory index chain is re-linked from the frozen
final anchors after each apply.  Snapshots written under a different
``methodologyVersion`` are rejected instead of being silently mixed, and a
snapshot card that disappeared from the current landscape is a hard error rather
than a silent history drop.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timezone
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set


ROOT = Path(__file__).resolve().parents[1]
INDEX_SNAPSHOT_DIR = ROOT / "tracker_data" / "index_snapshots"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _snapshot_path(snapshot_dir: Path, iso_week: str) -> Path:
    return Path(snapshot_dir) / f"{iso_week}.json"


def _load_snapshot(path: Path, iso_week: str) -> Optional[Dict[str, Any]]:
    """Load one week snapshot.  A corrupt file is an error, never silently replaced."""
    if not path.exists():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid index snapshot JSON at {path}: {exc}") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("cards"), dict):
        raise ValueError(f"invalid index snapshot structure at {path}")
    if doc.get("isoWeek") not in (None, iso_week):
        raise ValueError(
            f"index snapshot {path} says isoWeek={doc.get('isoWeek')!r}, expected {iso_week!r}"
        )
    doc["isoWeek"] = iso_week
    return doc


def _validate_entry(entry: Any, path: Path, card_id: str, iso_week: str) -> None:
    if not isinstance(entry, dict):
        raise ValueError(f"invalid index snapshot entry for {card_id} at {path}")
    week = entry.get("week")
    receipt = entry.get("receipt")
    if not isinstance(week, dict) or not isinstance(receipt, dict):
        raise ValueError(f"index snapshot entry for {card_id} at {path} needs week and receipt")
    if week.get("isoWeek") != iso_week:
        raise ValueError(
            f"index snapshot entry for {card_id} at {path} has week={week.get('isoWeek')!r}"
        )


def _write_snapshot(path: Path, doc: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _load_all_snapshots(
    snapshot_dir: Path, current_version: Any
) -> Dict[str, Dict[str, Any]]:
    """Load every existing weekly snapshot before touching ``full``.

    A snapshot written by a different methodology version is a hard error: the
    build must not silently mix old frozen weeks with a new method.
    """
    docs: Dict[str, Dict[str, Any]] = {}
    if not snapshot_dir.exists():
        return docs
    for path in sorted(snapshot_dir.glob("*.json")):
        iso_week = path.stem
        doc = _load_snapshot(path, iso_week)
        if doc is None:
            continue
        snapshot_version = doc.get("methodologyVersion")
        if snapshot_version != current_version:
            raise ValueError(
                f"index snapshot {path} methodologyVersion={snapshot_version!r} "
                f"does not match current {current_version!r}; migrate or remove it before building"
            )
        for card_id, entry in doc["cards"].items():
            _validate_entry(entry, path, str(card_id), iso_week)
            for part in ("week", "receipt"):
                entry_version = entry[part].get("methodologyVersion")
                if entry_version is not None and entry_version != current_version:
                    raise ValueError(
                        f"index snapshot {path} card {card_id} {part} methodologyVersion="
                        f"{entry_version!r} does not match current {current_version!r}; "
                        "migrate or remove it before building"
                    )
        docs[iso_week] = doc
    return docs


def _apply_snapshots(
    full: Dict[str, Any], snapshots: Dict[str, Dict[str, Any]]
) -> Dict[str, Set[str]]:
    """Overwrite current weeks with snapshots and inject missing snapshot weeks.

    A closed week is never dropped just because the current source no longer
    contains it: missing weeks are inserted back and sorted by ``weekStart``.
    Returns the per-card set of isoWeeks that came from an existing snapshot.
    """
    frozen_by_card: Dict[str, Set[str]] = {}
    for iso_week, doc in snapshots.items():
        for card_id in doc["cards"]:
            frozen_by_card.setdefault(str(card_id), set()).add(iso_week)

    ordered_weeks = sorted(snapshots)
    for card in full.get("cards") or []:
        weekly = card.get("weekly")
        if not isinstance(weekly, dict):
            continue
        card_id = str(card.get("id"))
        weeks = weekly.get("weeks")
        if not isinstance(weeks, list):
            weeks = []
            weekly["weeks"] = weeks
        receipts = weekly.get("receipts")
        if not isinstance(receipts, dict):
            receipts = {}
            weekly["receipts"] = receipts

        current_index = {str(week.get("isoWeek") or ""): index for index, week in enumerate(weeks)}
        injected = False
        for iso_week in ordered_weeks:
            entry = snapshots[iso_week]["cards"].get(card_id)
            if entry is None:
                continue
            if iso_week in current_index:
                weeks[current_index[iso_week]] = deepcopy(entry["week"])
            else:
                weeks.append(deepcopy(entry["week"]))
                current_index[iso_week] = len(weeks) - 1
                injected = True
            receipts[iso_week] = deepcopy(entry["receipt"])
        if injected:
            weeks.sort(
                key=lambda week: (
                    str(week.get("weekStart") or ""),
                    str(week.get("isoWeek") or ""),
                )
            )
    return frozen_by_card


def _refresh_latest(full: Dict[str, Any], card: Dict[str, Any]) -> None:
    """Recompute weekly.latest (last non-None index + ageDays) after a freeze."""
    weekly = card["weekly"]
    published = [week for week in weekly.get("weeks", []) if week.get("index") is not None]
    latest = deepcopy(published[-1]) if published else None
    if latest is not None:
        try:
            latest["ageDays"] = (
                date.fromisoformat(str(full["asOf"]))
                - date.fromisoformat(str(latest["weekStart"]))
            ).days
        except (KeyError, TypeError, ValueError):
            latest["ageDays"] = None
    weekly["latest"] = latest
    # trim_landscape / the page headline read card["weeklyIndex"], so keep it in sync.
    card["weeklyIndex"] = latest


def _receipt_provider_values(receipt: Dict[str, Any]) -> Dict[str, float]:
    """Provider values used by the chain: ``receipt.included`` keyed by providerId."""
    values: Dict[str, float] = {}
    for item in receipt.get("included") or []:
        provider_id = item.get("providerId")
        if provider_id is None:
            provider_id = item.get("provider")
        value = item.get("value")
        if provider_id is None or not isinstance(value, (int, float)):
            continue
        values[str(provider_id)] = float(value)
    return values


def _rechain_card(
    full: Dict[str, Any], card: Dict[str, Any], frozen_weeks: Set[str]
) -> None:
    """Re-chain weeks after the first existing snapshot week.

    Only isoWeeks in ``frozen_weeks`` are immutable anchors.  A current
    ``vintage == "final"`` week that has no snapshot yet is treated exactly like
    a provisional week here: it must be recomputed from the frozen anchor before
    it is first written.  It becomes an anchor only in the second pass, after
    its snapshot exists.

    ``full`` is kept in the signature for the documented interface; latest
    refresh happens once after all re-chain passes.
    """
    weekly = card["weekly"]
    weeks = weekly.get("weeks")
    if not isinstance(weeks, list):
        return
    receipts = weekly.get("receipts")
    if not isinstance(receipts, dict):
        receipts = {}
        weekly["receipts"] = receipts

    first_frozen = next(
        (
            index
            for index, week in enumerate(weeks)
            if str(week.get("isoWeek") or "") in frozen_weeks
        ),
        None,
    )
    if first_frozen is None:
        return

    last_index: Optional[float] = None
    last_providers: Optional[Dict[str, float]] = None
    for week in weeks[first_frozen:]:
        iso_week = str(week.get("isoWeek") or "")
        receipt = receipts.get(iso_week) if iso_week else None
        if not isinstance(receipt, dict):
            raise ValueError(
                f"missing weekly receipt for card {card.get('id')} week {iso_week}"
            )

        if iso_week in frozen_weeks:
            # Existing snapshot: never rewrite it.  Its own index (if any) is the anchor;
            # a withheld snapshot never moves the anchor even if the file is inconsistent.
            if week.get("index") is not None and week.get("status") != "withheld":
                last_index = float(week["index"])
                last_providers = _receipt_provider_values(receipt)
            continue

        providers = _receipt_provider_values(receipt)
        status = week.get("status")
        if status == "withheld":
            index: Optional[float] = None
            link_pairs = 0
        elif last_index is None:
            index = 100.0
            link_pairs = 0
        else:
            anchor = last_providers or {}
            shared = set(providers) & set(anchor)
            link_pairs = len(shared)
            if link_pairs >= 2:
                ratios = [providers[provider] / anchor[provider] for provider in sorted(shared)]
                geom = 1.0
                for ratio in ratios:
                    geom *= ratio
                geom = geom ** (1.0 / len(ratios))
                index = round(last_index * geom, 4)
            else:
                index = None

        week["index"] = index
        week["linkPairs"] = link_pairs
        receipt["index"] = index
        receipt["linkPairs"] = link_pairs
        if index is not None:
            last_index = index
            last_providers = providers


def _collect_new_final_weeks(
    full: Dict[str, Any], frozen_by_card: Dict[str, Set[str]]
) -> Dict[str, Dict[str, Dict[str, Any]]]:
    """Current final weeks that have no snapshot entry yet.

    Values are read after the first re-chain, so a new final week is frozen with
    the index chained from older frozen snapshots, never with the raw
    recomputation that still used revised older-source values.
    """
    new_weeks: Dict[str, Dict[str, Dict[str, Any]]] = {}
    for card in full.get("cards") or []:
        weekly = card.get("weekly")
        if not isinstance(weekly, dict):
            continue
        card_id = str(card.get("id"))
        frozen = frozen_by_card.get(card_id, set())
        receipts = weekly.get("receipts") or {}
        for week in weekly.get("weeks") or []:
            if week.get("vintage") != "final":
                continue
            iso_week = str(week.get("isoWeek") or "")
            if not iso_week or iso_week in frozen:
                continue
            receipt = receipts.get(iso_week)
            if not isinstance(receipt, dict):
                raise ValueError(
                    f"missing weekly receipt for card {card_id} week {iso_week}"
                )
            new_weeks.setdefault(iso_week, {})[card_id] = {
                "week": deepcopy(week),
                "receipt": deepcopy(receipt),
            }
    return new_weeks


def _write_new_snapshots(
    snapshot_dir: Path,
    snapshots: Dict[str, Dict[str, Any]],
    new_weeks: Dict[str, Dict[str, Dict[str, Any]]],
    current_version: Any,
    frozen_by_card: Dict[str, Set[str]],
) -> None:
    """Append missing card entries to weekly snapshot files, one write per week."""
    for iso_week in sorted(new_weeks):
        doc = snapshots.get(iso_week)
        if doc is None:
            doc = {
                "isoWeek": iso_week,
                "frozenAt": _utc_now(),
                "methodologyVersion": current_version,
                "cards": {},
            }
            snapshots[iso_week] = doc
        dirty = False
        for card_id, entry in new_weeks[iso_week].items():
            if card_id in doc["cards"]:
                continue
            doc["cards"][card_id] = entry
            dirty = True
            frozen_by_card.setdefault(card_id, set()).add(iso_week)
        if dirty:
            if not doc.get("frozenAt"):
                doc["frozenAt"] = _utc_now()
            _write_snapshot(_snapshot_path(snapshot_dir, iso_week), doc)


def _refresh_all_latest(full: Dict[str, Any]) -> None:
    for card in full.get("cards") or []:
        if isinstance(card.get("weekly"), dict):
            _refresh_latest(full, card)


def apply_weekly_freezes(
    full: Dict[str, Any], snapshot_dir: Path = INDEX_SNAPSHOT_DIR
) -> Dict[str, Any]:
    """Apply immutable snapshots and freeze newly closed weeks in the right order.

    Ordering matters: older snapshots must be applied *before* any new final
    week is written, otherwise a revised older week would produce a wrong
    permanent index for the new week.

    1. Load all existing snapshots and reject methodology mismatches.
    2. Refuse if a snapshot card id is absent from the current landscape: silently
       dropping a frozen card is not allowed, and snapshots lack name/vram/markets
       metadata to rebuild a whole card.
    3. Apply snapshots (including weeks missing from the current source).
    4. Re-chain non-snapshot weeks from frozen anchors; a current final week
       without a snapshot is recomputed here as if it were provisional.
    5. Write snapshots for those new final weeks using the re-chained values,
       then re-chain again with the new weeks as anchors.
    6. Refresh ``weekly.latest`` / ``card.weeklyIndex``.

    Works in place and returns the same ``full`` dict.
    """
    if not isinstance(full, dict):
        raise TypeError("apply_weekly_freezes expects the full landscape dict")
    cards = full.get("cards") or []
    if cards and not any(isinstance(card.get("weekly"), dict) for card in cards):
        raise ValueError(
            "apply_weekly_freezes needs the full landscape (call it before trim_landscape); "
            "no card has weekly receipts"
        )
    snapshot_dir = Path(snapshot_dir)
    current_version = full.get("methodologyVersion")

    # 1. Load every existing snapshot first; a version mismatch fails before any write.
    snapshots = _load_all_snapshots(snapshot_dir, current_version)

    # 2. A snapshot card that disappeared from the current landscape would silently
    #    drop frozen history.  Refuse instead of rebuilding a partial card (snapshots
    #    have no name/vram/markets metadata).
    snapshot_cards = {
        str(card_id)
        for doc in snapshots.values()
        for card_id in doc["cards"]
    }
    current_cards = {str(card.get("id")) for card in cards}
    missing_cards = sorted(snapshot_cards - current_cards)
    if missing_cards:
        raise ValueError(
            "index snapshots contain card(s) absent from the current landscape: "
            f"{', '.join(missing_cards)}. "
            "拒绝静默丢弃冻结历史，请恢复底表或显式迁移快照。"
        )

    # 3. Existing snapshots win, even when the week is missing from current source data.
    frozen_by_card = _apply_snapshots(full, snapshots)

    # 4. Re-chain from existing frozen anchors.  New final weeks are still treated
    #    as provisional here so they cannot freeze an index based on revised history.
    for card in cards:
        if isinstance(card.get("weekly"), dict):
            _rechain_card(full, card, frozen_by_card.get(str(card.get("id")), set()))

    # 5. Freeze new final weeks using the re-chained values, then anchor them too.
    new_weeks = _collect_new_final_weeks(full, frozen_by_card)
    if new_weeks:
        _write_new_snapshots(snapshot_dir, snapshots, new_weeks, current_version, frozen_by_card)
        for card in cards:
            if isinstance(card.get("weekly"), dict):
                _rechain_card(full, card, frozen_by_card.get(str(card.get("id")), set()))

    # 6. Latest is always the last non-None index after both passes.
    _refresh_all_latest(full)
    return full


def build_receipt_index(full: Dict[str, Any]) -> Dict[str, Any]:
    """Build ``public/data/receipts/index.json`` (written by the build, not here).

    ``available_via`` is ``page_latest`` only for the single receipt retained on
    the public site (the latest published week per card); every other week is
    reproducible with the CLI.
    """
    weeks: List[Dict[str, Any]] = []
    for card in full.get("cards") or []:
        weekly = card.get("weekly") or {}
        latest_week = (weekly.get("latest") or {}).get("receipt")
        for week in weekly.get("weeks") or []:
            iso_week = week.get("isoWeek")
            weeks.append(
                {
                    "card_id": card.get("id"),
                    "card_name": card.get("name"),
                    "iso_week": iso_week,
                    "week_start": week.get("weekStart"),
                    "vintage": week.get("vintage"),
                    "status": week.get("status"),
                    "provider_count": week.get("providerCount"),
                    "methodology_version": week.get("methodologyVersion")
                    or full.get("methodologyVersion"),
                    "available_via": "page_latest" if iso_week == latest_week else "cli",
                }
            )

    template = (
        'python3 scripts/reproduce_receipt.py --card "{card_id}" '
        '--week {iso_week} --out "{card_id}-{iso_week}-receipt.csv"'
    )
    commands: Dict[str, Any] = {
        "reproduce_receipt": template,
        "note": (
            "The public site keeps only the latest published week per card. "
            "Run the command above for every other week listed here."
        ),
    }
    if weeks:
        sample = next(
            (item for item in weeks if item["available_via"] == "page_latest"), weeks[0]
        )
        commands["example"] = template.format(
            card_id=sample["card_id"], iso_week=sample["iso_week"]
        )

    return {
        "name": "AI Compute Economics - reproducible weekly receipts",
        "description": (
            "Every card x ISO week receipt is reproducible from the tracked neocloud "
            "history. Frozen final weeks replay the stored snapshot; provisional weeks "
            "are recomputed. The public site serves the latest published week only."
        ),
        "methodology_version": full.get("methodologyVersion"),
        "as_of": full.get("asOf"),
        "count": len(weeks),
        "weeks": weeks,
        "commands": commands,
    }
