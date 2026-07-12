#!/usr/bin/env python3
"""Backfill weekly listed token prices from auditable LiteLLM Git history."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from datetime import date, timedelta
from pathlib import Path


REPOSITORY = "https://github.com/BerriAI/litellm.git"
PRICE_FILE = "model_prices_and_context_window.json"
MODELS = {
    "OpenAI GPT-4o": "gpt-4o",
    "OpenAI GPT-4.1": "gpt-4.1",
    "Anthropic Claude Sonnet 4": "claude-sonnet-4-20250514",
    "Google Gemini 2.5 Flash": "gemini-2.5-flash",
    "DeepSeek Chat": "deepseek-chat",
}


def _git(repo: Path, *args: str) -> bytes:
    return subprocess.check_output(["git", "-C", str(repo), *args])


def _monday(value: date) -> date:
    return value - timedelta(days=value.weekday())


def build_history(repo: Path, start: date, end: date) -> dict:
    weeks = []
    current = _monday(start)
    final = _monday(end)
    while current <= final:
        sha = _git(
            repo,
            "log",
            "-1",
            "--format=%H",
            f"--before={current.isoformat()} 23:59:59",
            "--",
            PRICE_FILE,
        ).decode().strip()
        if not sha:
            current += timedelta(days=7)
            continue
        catalog = json.loads(_git(repo, "show", f"{sha}:{PRICE_FILE}"))
        observations = []
        for label, key in MODELS.items():
            model = catalog.get(key) or {}
            input_cost = model.get("input_cost_per_token")
            output_cost = model.get("output_cost_per_token")
            if input_cost is None and output_cost is None:
                continue
            observations.append(
                {
                    "model": label,
                    "catalog_key": key,
                    "input_usd_per_1m": None if input_cost is None else float(input_cost) * 1_000_000,
                    "output_usd_per_1m": None if output_cost is None else float(output_cost) * 1_000_000,
                    "litellm_provider": model.get("litellm_provider"),
                }
            )
        weeks.append({"date": current.isoformat(), "commit": sha, "observations": observations})
        current += timedelta(days=7)
    return {
        "source": {
            "label": "LiteLLM model price catalog Git history",
            "repository": "https://github.com/BerriAI/litellm",
            "file": PRICE_FILE,
            "definition": "Weekly as-of snapshots of exact catalog keys. Missing models remain missing; values are listed API prices, not provider inference cost.",
        },
        "models": MODELS,
        "weeks": weeks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", default="2025-07-07")
    parser.add_argument("--end", default=date.today().isoformat())
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "tracker_data" / "backfills" / "litellm_key_model_prices_1y.json",
    )
    parser.add_argument("--repo", type=Path)
    args = parser.parse_args()

    if args.repo:
        payload = build_history(args.repo, date.fromisoformat(args.start), date.fromisoformat(args.end))
    else:
        with tempfile.TemporaryDirectory(prefix="litellm-price-history-") as temp:
            repo = Path(temp) / "litellm"
            subprocess.check_call(["git", "clone", "--filter=blob:none", "--no-checkout", "--quiet", REPOSITORY, str(repo)])
            payload = build_history(repo, date.fromisoformat(args.start), date.fromisoformat(args.end))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output), "weeks": len(payload["weeks"])}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
