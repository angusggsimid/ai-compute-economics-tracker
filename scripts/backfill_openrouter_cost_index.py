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


def build(start_date: date, output: Path, *, reuse_commits: bool = False) -> dict[str, Any]:
    session = requests.Session()
    session.headers.update({"User-Agent": "ai-compute-economics-monitor/1.0"})
    if os.environ.get("GITHUB_TOKEN"):
        session.headers.update({"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}"})
    openrouter_payload, openrouter_raw, openrouter_url = _fetch_json(session, OPENROUTER_CHART)
    chart = openrouter_payload.get("data") or {}
    points = [point for point in chart.get("data") or [] if date.fromisoformat(point["x"]) >= start_date]
    if not points:
        raise RuntimeError("OpenRouter model rankings chart returned no points in the requested window")

    prior_weeks: dict[str, dict[str, Any]] = {}
    if reuse_commits and output.exists():
        prior = json.loads(output.read_text(encoding="utf-8"))
        prior_weeks = {row["date"]: row for row in prior.get("weeks", [])}

    weeks: list[dict[str, Any]] = []
    provider_rows: list[dict[str, Any]] = []
    for point in points:
        week = date.fromisoformat(point["x"])
        price_date = min(week + timedelta(days=6), datetime.now(timezone.utc).date())
        prior_week = prior_weeks.get(week.isoformat())
        if prior_week:
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

    artifact = {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "window": {"start": weeks[0]["date"], "end": weeks[-1]["date"], "frequency": "weekly"},
        "method": {
            "volume": "Sum of source-provided named model rows and Others for each OpenRouter chart week.",
            "provider_share": "Named top-model provider tokens divided by total tokens including Others; providers below the visible leaderboard are not separately identified.",
            "weighted_cost": "Token-volume-weighted listed input/output price among named models matched to the LiteLLM price map at that week; total_tokens do not split prompt and completion, so the same volume weight is used for both price legs.",
        },
        "sources": {
            "openrouter": {
                "url": openrouter_url,
                "cached_at": chart.get("cachedAt"),
                "raw_sha256": "sha256:" + hashlib.sha256(openrouter_raw).hexdigest(),
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
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
