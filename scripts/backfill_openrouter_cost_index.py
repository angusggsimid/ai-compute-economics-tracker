#!/usr/bin/env python3
"""Build a source-backed weekly OpenRouter usage and listed-cost history."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "tracker_data" / "backfills" / "openrouter_cost_index.json"
OPENROUTER_CHART = "https://openrouter.ai/api/frontend/v1/rankings/model-rankings-chart"
GITHUB_COMMITS = "https://api.github.com/repos/BerriAI/litellm/commits"
LITELLM_RAW = "https://raw.githubusercontent.com/BerriAI/litellm/{sha}/model_prices_and_context_window.json"
LITELLM_PATH = "model_prices_and_context_window.json"
MIN_COMPLETE_WEEKS = 52
WEEK_REQUIRED_KEYS = ("date", "total_tokens", "named_tokens", "model_rows", "price_snapshot")
PRICE_SNAPSHOT_REQUIRED_KEYS = ("sha", "committed_at", "commit_url")
PROVIDER_SHARE_REQUIRED_KEYS = ("date", "provider", "tokens", "share_pct")


def _fetch_json(session: requests.Session, url: str, **kwargs: Any) -> tuple[dict[str, Any], bytes, str]:
    response = session.get(url, timeout=90, **kwargs)
    response.raise_for_status()
    return response.json(), response.content, response.url


def _model_candidates(slug: str) -> list[str]:
    raw = slug.strip()
    base = raw.split(":", 1)[0]
    undated = re.sub(r"-20\d{6}$", "", base)
    short_name = undated.split("/", 1)[-1]
    candidates = [
        f"openrouter/{raw}", f"openrouter/{base}", f"openrouter/{undated}",
        raw, base, undated, short_name,
    ]
    return list(dict.fromkeys(candidates))


def _price_for_model(price_map: dict[str, Any], slug: str) -> tuple[float | None, float | None, str | None]:
    if slug.endswith(":free"):
        return 0.0, 0.0, "free_variant"
    for key in _model_candidates(slug):
        row = price_map.get(key)
        if not isinstance(row, dict):
            continue
        input_cost = row.get("input_cost_per_token")
        output_cost = row.get("output_cost_per_token")
        try:
            input_per_million = float(input_cost) * 1_000_000 if input_cost is not None else None
            output_per_million = float(output_cost) * 1_000_000 if output_cost is not None else None
        except (TypeError, ValueError):
            continue
        if input_per_million is not None or output_per_million is not None:
            return input_per_million, output_per_million, key
    return None, None, None


def _commit_before(session: requests.Session, until: date) -> dict[str, str]:
    payload, _, _ = _fetch_json(
        session,
        GITHUB_COMMITS,
        params={"path": LITELLM_PATH, "until": until.isoformat() + "T23:59:59Z", "per_page": 1},
    )
    if not isinstance(payload, list) or not payload:
        raise RuntimeError(f"No LiteLLM price-map commit found on or before {until.isoformat()}")
    commit = payload[0]
    return {
        "sha": str(commit["sha"]),
        "committed_at": str(commit["commit"]["author"]["date"]),
        "commit_url": str(commit["html_url"]),
    }


def is_complete_week(week_start: date, as_of: date) -> bool:
    """A week is complete only when its last day is strictly before as_of (UTC date)."""
    return week_start + timedelta(days=6) < as_of


def filter_complete_chart_points(
    points: list[dict[str, Any]],
    *,
    start_date: date,
    as_of: date,
) -> list[dict[str, Any]]:
    """Keep only complete OpenRouter chart weeks on or after start_date."""
    filtered: list[dict[str, Any]] = []
    for point in points:
        week = date.fromisoformat(str(point["x"]))
        if week >= start_date and is_complete_week(week, as_of):
            filtered.append(point)
    return filtered


def _validate_week_row(week: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(week, dict):
        raise RuntimeError(f"{context}: week row must be an object")
    missing = [key for key in WEEK_REQUIRED_KEYS if key not in week]
    if missing:
        raise RuntimeError(f"{context}: week missing required keys {missing}")
    try:
        date.fromisoformat(str(week["date"]))
    except ValueError as exc:
        raise RuntimeError(f"{context}: invalid week date {week.get('date')!r}") from exc
    if not isinstance(week.get("model_rows"), list):
        raise RuntimeError(f"{context}: model_rows must be a list")
    price_snapshot = week.get("price_snapshot")
    if not isinstance(price_snapshot, dict):
        raise RuntimeError(f"{context}: price_snapshot must be an object")
    missing_ps = [key for key in PRICE_SNAPSHOT_REQUIRED_KEYS if key not in price_snapshot]
    if missing_ps:
        raise RuntimeError(f"{context}: price_snapshot missing required keys {missing_ps}")
    try:
        float(week["total_tokens"])
        float(week["named_tokens"])
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{context}: total_tokens/named_tokens must be numeric") from exc
    return week


def load_prior_history(path: Path) -> dict[str, Any]:
    """Load retained local history.

    Missing file is first-run empty history. Existing file that is corrupt or schema-
    invalid must raise — never silently treat as empty success.
    """
    if not path.exists():
        return {"weeks": [], "provider_shares": []}
    try:
        raw = path.read_text(encoding="utf-8")
        prior = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"OpenRouter cost-index cache is corrupt and cannot be merged: {path}"
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"OpenRouter cost-index cache cannot be read: {path}"
        ) from exc
    if not isinstance(prior, dict):
        raise RuntimeError(
            f"OpenRouter cost-index cache schema mismatch (root must be object): {path}"
        )
    if "weeks" not in prior:
        raise RuntimeError(
            f"OpenRouter cost-index cache schema mismatch (missing weeks): {path}"
        )
    weeks = prior["weeks"]
    if not isinstance(weeks, list):
        raise RuntimeError(
            f"OpenRouter cost-index cache schema mismatch (weeks must be list): {path}"
        )
    validated_weeks: list[dict[str, Any]] = []
    for index, week in enumerate(weeks):
        validated_weeks.append(_validate_week_row(week, context=f"{path} weeks[{index}]"))
    provider_shares = prior.get("provider_shares", [])
    if not isinstance(provider_shares, list):
        raise RuntimeError(
            f"OpenRouter cost-index cache schema mismatch (provider_shares must be list): {path}"
        )
    for index, row in enumerate(provider_shares):
        if not isinstance(row, dict):
            raise RuntimeError(
                f"{path} provider_shares[{index}]: must be an object"
            )
        missing = [key for key in PROVIDER_SHARE_REQUIRED_KEYS if key not in row]
        if missing:
            raise RuntimeError(f"{path} provider_shares[{index}]: missing required keys {missing}")
        try:
            date.fromisoformat(str(row["date"]))
            float(row["tokens"])
            if row["share_pct"] is not None:
                float(row["share_pct"])
        except (TypeError, ValueError) as exc:
            raise RuntimeError(
                f"{path} provider_shares[{index}]: invalid date/tokens/share_pct"
            ) from exc
        if not isinstance(row["provider"], str) or not row["provider"].strip():
            raise RuntimeError(f"{path} provider_shares[{index}]: provider must be non-empty")
    return {
        "generated_at": prior.get("generated_at") if isinstance(prior.get("generated_at"), str) else None,
        "weeks": validated_weeks,
        "provider_shares": provider_shares,
        "sources": prior.get("sources") if isinstance(prior.get("sources"), dict) else {},
        "method": prior.get("method") if isinstance(prior.get("method"), dict) else {},
        "window": prior.get("window") if isinstance(prior.get("window"), dict) else {},
    }


def merge_week_history(
    prior_weeks: list[dict[str, Any]],
    upstream_weeks: list[dict[str, Any]],
    *,
    start_date: date,
    as_of: date,
) -> list[dict[str, Any]]:
    """Merge retained local complete weeks with the latest upstream complete window.

    Upstream rows win on the same date. Incomplete weeks and rows before start_date
    (the retention-window lower bound) are dropped. This keeps real history that falls
    off OpenRouter's rolling window without fabricating points or promoting incomplete weeks.
    """
    by_date: dict[str, dict[str, Any]] = {}
    for week in prior_weeks:
        week_date = date.fromisoformat(str(week["date"]))
        if week_date < start_date or not is_complete_week(week_date, as_of):
            continue
        by_date[week_date.isoformat()] = week
    for week in upstream_weeks:
        week_date = date.fromisoformat(str(week["date"]))
        if week_date < start_date or not is_complete_week(week_date, as_of):
            continue
        by_date[week_date.isoformat()] = week
    return [by_date[key] for key in sorted(by_date)]


def merge_provider_shares(
    prior_shares: list[dict[str, Any]],
    upstream_shares: list[dict[str, Any]],
    week_dates: set[str],
) -> list[dict[str, Any]]:
    """Keep provider rows only for retained week dates; upstream overwrites same date."""
    by_date: dict[str, list[dict[str, Any]]] = {}
    for row in prior_shares:
        week_date = str(row.get("date") or "")
        if week_date in week_dates:
            by_date.setdefault(week_date, []).append(row)
    upstream_dates = {str(row.get("date") or "") for row in upstream_shares}
    for week_date in upstream_dates:
        if week_date in week_dates:
            by_date[week_date] = []
    for row in upstream_shares:
        week_date = str(row.get("date") or "")
        if week_date in week_dates:
            by_date.setdefault(week_date, []).append(row)
    rows: list[dict[str, Any]] = []
    for week_date in sorted(by_date):
        rows.extend(by_date[week_date])
    return rows


def _history_provenance(
    prior: dict[str, Any],
    upstream_weeks: list[dict[str, Any]],
    merged_weeks: list[dict[str, Any]],
    *,
    start_date: date,
    as_of: date,
) -> dict[str, Any]:
    prior_dates = {
        str(week["date"])
        for week in prior["weeks"]
        if date.fromisoformat(str(week["date"])) >= start_date
        and is_complete_week(date.fromisoformat(str(week["date"])), as_of)
    }
    upstream_dates = {str(week["date"]) for week in upstream_weeks}
    merged_dates = {str(week["date"]) for week in merged_weeks}
    retained_from_local = sorted(merged_dates - upstream_dates)
    overlap = sorted(merged_dates & upstream_dates)
    prior_openrouter = (prior.get("sources") or {}).get("openrouter") or {}
    return {
        "retention_start": start_date.isoformat(),
        "as_of_utc": as_of.isoformat(),
        "min_complete_weeks": MIN_COMPLETE_WEEKS,
        "prior_complete_weeks_in_window": len(prior_dates),
        "upstream_complete_weeks": len(upstream_dates),
        "retained_complete_weeks": len(merged_dates),
        "local_only_weeks": retained_from_local,
        "local_only_week_count": len(retained_from_local),
        "upstream_overwrite_week_count": len(overlap),
        "retained_cache_generated_at": prior.get("generated_at") if retained_from_local else None,
        "retained_cache_openrouter_url": prior_openrouter.get("url") if retained_from_local else None,
        "retained_cache_openrouter_raw_sha256": (
            prior_openrouter.get("raw_sha256") if retained_from_local else None
        ),
        "rule": (
            "Upstream complete weeks overwrite same dates; local complete weeks are kept "
            "only when they fall off the upstream rolling window but remain on/after "
            "retention_start and are still complete as_of UTC."
        ),
    }


def build(start_date: date, output: Path, *, reuse_commits: bool = False) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "ai-compute-economics-monitor/1.0"})
    if os.environ.get("GITHUB_TOKEN"):
        session.headers.update({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"})
    openrouter_payload, openrouter_raw, openrouter_url = _fetch_json(session, OPENROUTER_CHART)
    chart = openrouter_payload.get("data") or {}
    today_utc = datetime.now(timezone.utc).date()
    points = filter_complete_chart_points(
        list(chart.get("data") or []),
        start_date=start_date,
        as_of=today_utc,
    )
    if not points:
        raise RuntimeError("OpenRouter model rankings chart returned no points in the requested window")

    prior = load_prior_history(output)
    prior_weeks_by_date = {row["date"]: row for row in prior["weeks"]}

    weeks: list[dict[str, Any]] = []
    provider_rows: list[dict[str, Any]] = []
    for point in points:
        week = date.fromisoformat(point["x"])
        price_date = min(week + timedelta(days=6), today_utc)
        prior_week = prior_weeks_by_date.get(week.isoformat()) if reuse_commits else None
        if prior_week and prior_week.get("price_snapshot"):
            snapshot = prior_week["price_snapshot"]
            commit = {key: snapshot[key] for key in ("sha", "committed_at", "commit_url")}
        else:
            commit = _commit_before(session, price_date)
        raw_url = LITELLM_RAW.format(sha=commit["sha"])
        price_map, price_raw, resolved_raw_url = _fetch_json(session, raw_url)
        values = {str(key): float(value) for key, value in (point.get("ys") or {}).items()}
        total_tokens = sum(values.values())
        named_tokens = sum(value for key, value in values.items() if key != "Others")

        weighted_input = 0.0
        weighted_output = 0.0
        input_weight = 0.0
        output_weight = 0.0
        mapped_tokens = 0.0
        provider_tokens: dict[str, float] = defaultdict(float)
        model_rows: list[dict[str, Any]] = []
        for model_slug, tokens in values.items():
            if model_slug == "Others":
                continue
            provider = model_slug.split("/", 1)[0]
            provider_tokens[provider] += tokens
            input_price, output_price, matched_key = _price_for_model(price_map, model_slug)
            if matched_key is not None:
                mapped_tokens += tokens
            if input_price is not None:
                weighted_input += tokens * input_price
                input_weight += tokens
            if output_price is not None:
                weighted_output += tokens * output_price
                output_weight += tokens
            model_rows.append({
                "model": model_slug,
                "provider": provider,
                "tokens": tokens,
                "share_pct": round(tokens / total_tokens * 100, 4) if total_tokens else None,
                "input_usd_per_1m": input_price,
                "output_usd_per_1m": output_price,
                "matched_price_key": matched_key,
            })

        for provider, tokens in provider_tokens.items():
            provider_rows.append({
                "date": week.isoformat(),
                "provider": provider,
                "tokens": tokens,
                "share_pct": round(tokens / total_tokens * 100, 4) if total_tokens else None,
            })
        provider_rows.append({
            "date": week.isoformat(),
            "provider": "Others",
            "tokens": values.get("Others", 0.0),
            "share_pct": round(values.get("Others", 0.0) / total_tokens * 100, 4) if total_tokens else None,
        })

        weeks.append({
            "date": week.isoformat(),
            "total_tokens": total_tokens,
            "named_tokens": named_tokens,
            "named_coverage_pct": round(named_tokens / total_tokens * 100, 2) if total_tokens else None,
            "price_mapped_coverage_pct": round(mapped_tokens / named_tokens * 100, 2) if named_tokens else None,
            "weighted_input_usd_per_1m": round(weighted_input / input_weight, 6) if input_weight else None,
            "weighted_output_usd_per_1m": round(weighted_output / output_weight, 6) if output_weight else None,
            "model_rows": model_rows,
            "price_snapshot": {
                **commit,
                "raw_url": resolved_raw_url,
                "raw_sha256": "sha256:" + hashlib.sha256(price_raw).hexdigest(),
            },
        })

    upstream_weeks = list(weeks)
    weeks = merge_week_history(
        list(prior["weeks"]),
        upstream_weeks,
        start_date=start_date,
        as_of=today_utc,
    )
    week_dates = {row["date"] for row in weeks}
    provider_rows = merge_provider_shares(
        list(prior.get("provider_shares") or []),
        provider_rows,
        week_dates,
    )
    provenance = _history_provenance(
        prior,
        upstream_weeks,
        weeks,
        start_date=start_date,
        as_of=today_utc,
    )
    if len(weeks) < MIN_COMPLETE_WEEKS:
        raise RuntimeError(
            f"OpenRouter complete-week history has only {len(weeks)} weeks after merge; "
            f"need at least {MIN_COMPLETE_WEEKS} retained complete weeks of real source-backed history"
        )
    local_only_dates = set(provenance["local_only_weeks"])
    if local_only_dates:
        retained_share_dates = {str(row["date"]) for row in provider_rows}
        missing_share_dates = sorted(local_only_dates - retained_share_dates)
        if missing_share_dates:
            raise RuntimeError(
                "Retained OpenRouter local-only weeks lack provider-share history: "
                f"{missing_share_dates}"
            )
        if not provenance["retained_cache_openrouter_raw_sha256"]:
            raise RuntimeError(
                "Retained OpenRouter local-only weeks lack prior raw source hash provenance"
            )

    artifact = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "window": {"start": weeks[0]["date"], "end": weeks[-1]["date"], "frequency": "weekly"},
        "method": {
            "volume": "Sum of source-provided named model rows and Others for each OpenRouter chart week.",
            "provider_share": "Named top-model provider tokens divided by total tokens including Others; providers below the visible leaderboard are not separately identified.",
            "weighted_cost": "Token-volume-weighted listed input/output price among named models matched to the LiteLLM price map at that week; total_tokens do not split prompt and completion, so the same volume weight is used for both price legs.",
            "history_retention": (
                "Upstream OpenRouter chart is a rolling window. Local complete weeks that fall off "
                "the window but remain on/after --start-date (retention lower bound) are retained and "
                "merged by week date; incomplete current weeks are never promoted into the formal series. "
                "Upstream rows overwrite the same date. Corrupt or schema-invalid local cache fails hard."
            ),
        },
        "sources": {
            "openrouter": {
                "url": openrouter_url,
                "cached_at": chart.get("cachedAt"),
                "raw_sha256": "sha256:" + hashlib.sha256(openrouter_raw).hexdigest(),
                "upstream_complete_weeks": len(points),
                "retained_complete_weeks": len(weeks),
                "history_provenance": provenance,
            },
            "litellm": {
                "repository": "https://github.com/BerriAI/litellm",
                "path": LITELLM_PATH,
            },
        },
        "weeks": weeks,
        "provider_shares": provider_rows,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(artifact, ensure_ascii=False, indent=2), encoding="utf-8")
    return artifact


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start-date", type=date.fromisoformat, default=date(2026, 3, 2))
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--reuse-commits", action="store_true")
    args = parser.parse_args()
    artifact = build(args.start_date, args.output, reuse_commits=args.reuse_commits)
    print(json.dumps({
        "output": str(args.output),
        "weeks": len(artifact["weeks"]),
        "start": artifact["window"]["start"],
        "end": artifact["window"]["end"],
        "local_only_weeks": artifact["sources"]["openrouter"]["history_provenance"]["local_only_weeks"],
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
