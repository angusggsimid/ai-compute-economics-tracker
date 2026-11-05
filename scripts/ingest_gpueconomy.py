#!/usr/bin/env python3
"""Ingest a GPU Economy public data snapshot into ``tracker_data/external``.

The dashboard must build offline, so the committed snapshot is the only source the
build reads.  This script validates the upstream JSON, writes deterministic gzip
files (``gzip -9 -n`` semantics: no filename, no mtime), and records checksums and
counts in ``metadata.json``.

Usage:
    python3 scripts/ingest_gpueconomy.py \
        --from-dir /tmp/gpu-research --date 2026-11-03 \
        --out tracker_data/external/gpueconomy

    python3 scripts/ingest_gpueconomy.py \
        --url https://gpueconomy.com/data --date 2026-11-03 \
        --out tracker_data/external/gpueconomy

``--url`` downloads the seven JSON files over HTTPS (``urllib`` with a User-Agent
and timeout), then runs the same validation/gzip/metadata path as ``--from-dir``.
The build itself never downloads: it reads the committed snapshot only.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "tracker_data" / "external" / "gpueconomy"
SOURCE = "gpueconomy"
SOURCE_URL = "https://gpueconomy.com/data"
LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/"
GZIP_NOTE = "gzip -9 -n semantics: GzipFile(compresslevel=9, mtime=0), no stored filename"
METHODOLOGY_RE = re.compile(r"^\d+\.\d+\.\d+$")
USER_AGENT = "ai-compute-economics/1.0 (gpueconomy snapshot ingest)"
DEFAULT_TIMEOUT = 30.0
REQUIRED_FILES: Tuple[str, ...] = (
    "prices.json",
    "gpus.json",
    "providers.json",
    "history.json",
    "token-cost.json",
    "changelog.json",
    "price-index.json",
)


def _fail(message: str) -> None:
    raise SystemExit(f"ingest_gpueconomy: {message}")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _gzip_bytes(raw: bytes) -> bytes:
    """Deterministic gzip: no mtime, no filename (same contract as ``gzip -9 -n``)."""
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, compresslevel=9, mtime=0) as handle:
        handle.write(raw)
    return buffer.getvalue()


def _gunzip_bytes(payload: bytes) -> bytes:
    with gzip.GzipFile(fileobj=io.BytesIO(payload), mode="rb") as handle:
        return handle.read()


def _parse_time(value: Any, field: str, name: str) -> datetime:
    if not isinstance(value, str) or not value:
        _fail(f"{name}: missing {field}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        _fail(f"{name}: {field} is not ISO-8601: {value!r}")
    if parsed.tzinfo is None:
        _fail(f"{name}: {field} has no timezone: {value!r}")
    return parsed


def _count_prices(doc: Dict[str, Any]) -> int:
    return len(doc.get("prices") or [])


def _count_gpus(doc: Dict[str, Any]) -> int:
    return len(doc.get("gpus") or [])


def _count_providers(doc: Dict[str, Any]) -> int:
    return len(doc.get("providers") or [])


def _count_history(doc: Dict[str, Any]) -> int:
    return sum(
        len(series.get("weeks") or [])
        for model in doc.get("models") or []
        for series in model.get("series") or []
    )


def _count_token_cost(doc: Dict[str, Any]) -> int:
    return sum(len(card.get("runs") or []) for card in doc.get("cards") or [])


def _count_changelog(doc: Dict[str, Any]) -> int:
    return len(doc.get("moves") or [])


def _count_price_index(doc: Dict[str, Any]) -> int:
    return len(doc.get("series") or [])


# file -> (computed count, unit, declared-count key or None)
COUNT_SPECS: Dict[str, Tuple[Callable[[Dict[str, Any]], int], str, str | None]] = {
    "prices.json": (_count_prices, "rows", "count"),
    "gpus.json": (_count_gpus, "gpus", "count"),
    "providers.json": (_count_providers, "providers", "count"),
    "history.json": (_count_history, "model-weeks", None),
    "token-cost.json": (_count_token_cost, "benchmark-runs", None),
    "changelog.json": (_count_changelog, "moves", "count"),
    "price-index.json": (_count_price_index, "weekly-points", None),
}

# token-cost.json upstream carries no attribution field; it inherits the snapshot
# attribution and is documented in metadata.notes instead of being silently filled.
ATTRIBUTION_OPTIONAL = {"token-cost.json"}

PRICE_ROW_FIELDS = (
    "provider_id",
    "gpu_id",
    "market",
    "status",
    "price_scope",
    "usd_per_gpu_hour",
    "listed_currency",
    "source_url",
    "scraped_at",
)


def _validate_price_rows(doc: Dict[str, Any]) -> None:
    rows = doc.get("prices") or []
    if not rows:
        _fail("prices.json: prices[] is empty")
    bad: List[str] = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            bad.append(f"row {index} is not an object")
            continue
        missing = [field for field in PRICE_ROW_FIELDS if row.get(field) in (None, "")]
        if missing:
            bad.append(f"row {index} missing {missing}")
            continue
        price = row.get("usd_per_gpu_hour")
        listed = row.get("listed_price_hour")
        count = row.get("gpu_count")
        fx = row.get("fx_rate")
        if not isinstance(price, (int, float)) or price <= 0:
            bad.append(f"row {index} has invalid usd_per_gpu_hour")
            continue
        if not isinstance(listed, (int, float)) or not isinstance(count, (int, float)) or count <= 0:
            bad.append(f"row {index} has invalid listed_price_hour/gpu_count")
            continue
        expected = listed / count * (fx if isinstance(fx, (int, float)) else 1.0)
        if abs(expected - float(price)) > 0.01:
            bad.append(
                f"row {index} normalization mismatch: usd={price} expected={expected:.6f}"
            )
        if len(bad) >= 8:
            break
    if bad:
        _fail("prices.json row validation failed: " + "; ".join(bad))


def _validate_document(name: str, doc: Any) -> int:
    if not isinstance(doc, dict):
        _fail(f"{name}: top-level JSON is not an object")
    license_text = doc.get("license")
    if not isinstance(license_text, str) or not license_text.strip():
        _fail(f"{name}: missing license")
    _parse_time(doc.get("data_updated_at"), "data_updated_at", name)
    if name not in ATTRIBUTION_OPTIONAL:
        attribution = doc.get("attribution")
        if not isinstance(attribution, str) or not attribution.strip():
            _fail(f"{name}: missing attribution")
    if name == "prices.json":
        version = doc.get("methodology_version")
        if not isinstance(version, str) or not METHODOLOGY_RE.match(version):
            _fail(
                f"{name}: missing or invalid methodology_version "
                f"(expected N.N.N, got {version!r})"
            )

    counter, _unit, declared_key = COUNT_SPECS[name]
    count = counter(doc)
    if count <= 0:
        _fail(f"{name}: computed count is zero")
    if declared_key:
        declared = doc.get(declared_key)
        if declared != count:
            _fail(f"{name}: declared {declared_key}={declared!r} but file contains {count}")
    if name == "providers.json":
        listed = len(doc.get("not_listed") or [])
        if listed <= 0:
            _fail("providers.json: not_listed[] is empty")
    return count


def _decode_documents(
    raw_documents: Dict[str, bytes],
) -> Dict[str, Tuple[bytes, Dict[str, Any], int]]:
    """Validate raw JSON bytes from a directory or a URL download."""
    loaded: Dict[str, Tuple[bytes, Dict[str, Any], int]] = {}
    missing = [name for name in REQUIRED_FILES if name not in raw_documents]
    if missing:
        _fail(f"missing source files: {missing}")
    for name in REQUIRED_FILES:
        raw = raw_documents[name]
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            _fail(f"{name}: invalid UTF-8 JSON ({exc})")
        count = _validate_document(name, doc)
        loaded[name] = (raw, doc, count)

    prices = loaded["prices.json"][1]
    _validate_price_rows(prices)
    methodology = prices["methodology_version"]
    data_updated_at = prices["data_updated_at"]
    for name, (_raw, doc, _count) in loaded.items():
        if doc.get("data_updated_at") != data_updated_at:
            _fail(
                f"{name}: data_updated_at={doc.get('data_updated_at')!r} "
                f"differs from prices.json {data_updated_at!r}"
            )
        if not str(doc.get("license") or "").startswith("CC BY 4.0"):
            _fail(f"{name}: unexpected license {doc.get('license')!r}")
        declared = doc.get("methodology_version")
        if declared is not None and declared != methodology:
            _fail(
                f"{name}: methodology_version={declared!r} differs from "
                f"prices.json {methodology!r}"
            )
    providers = loaded["providers.json"][1]
    scraped = sum(1 for item in providers.get("providers") or [] if item.get("scraped"))
    if prices.get("providers") != scraped:
        _fail(
            "prices.json providers count does not match the scraped=true providers "
            f"in providers.json ({prices.get('providers')} != {scraped})"
        )
    if prices.get("gpus") != _count_gpus(loaded["gpus.json"][1]):
        _fail("prices.json gpus count does not match gpus.json")
    return loaded


def _load_source_dir(source_dir: Path) -> Dict[str, Tuple[bytes, Dict[str, Any], int]]:
    missing = [name for name in REQUIRED_FILES if not (source_dir / name).is_file()]
    if missing:
        _fail(f"missing source files in {source_dir}: {missing}")
    raw_documents = {name: (source_dir / name).read_bytes() for name in REQUIRED_FILES}
    return _decode_documents(raw_documents)


def _data_file_urls(url: str) -> Dict[str, str]:
    """Turn a data-page/base URL into the seven file URLs.

    ``https://gpueconomy.com/data`` -> ``https://gpueconomy.com/prices.json``.
    A direct ``.../prices.json`` input is accepted by taking its parent.
    """
    parsed = urllib.parse.urlparse(str(url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        _fail(f"--url must be an http(s) URL, got {url!r}")
    path = parsed.path.rstrip("/")
    if path.endswith(".json"):
        path = path.rsplit("/", 1)[0]
    if path.endswith("/data"):
        path = path[: -len("/data")]
    base = urllib.parse.urlunparse((parsed.scheme, parsed.netloc, path, "", "", "")).rstrip("/")
    return {name: f"{base}/{name}" for name in REQUIRED_FILES}


def _fetch_url(url: str, timeout: float) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = response.read()
    if not payload:
        raise OSError(f"empty response from {url}")
    return payload


def _download_documents(url: str, timeout: float = DEFAULT_TIMEOUT) -> Dict[str, bytes]:
    urls = _data_file_urls(url)
    raw_documents: Dict[str, bytes] = {}
    for name in REQUIRED_FILES:
        try:
            raw_documents[name] = _fetch_url(urls[name], timeout)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError) as exc:
            _fail(f"failed to download {urls[name]}: {exc}")
    return raw_documents


def _count_detail(name: str, doc: Dict[str, Any], count: int) -> Dict[str, int]:
    if name == "prices.json":
        return {
            "rows": count,
            "providers": int(doc.get("providers") or 0),
            "gpus": int(doc.get("gpus") or 0),
        }
    if name == "providers.json":
        providers = doc.get("providers") or []
        return {
            "providers": count,
            "scraped": sum(1 for item in providers if item.get("scraped")),
            "not_listed": len(doc.get("not_listed") or []),
        }
    if name == "history.json":
        models = doc.get("models") or []
        return {
            "models": len(models),
            "series": sum(len(model.get("series") or []) for model in models),
            "model_weeks": count,
        }
    if name == "token-cost.json":
        return {"cards": len(doc.get("cards") or []), "runs": count}
    if name == "price-index.json":
        return {
            "weekly_points": count,
            "months": len(doc.get("monthly") or []),
            "current_constituents": len((doc.get("current") or {}).get("constituents") or []),
        }
    return {}


def _build_metadata(
    loaded: Dict[str, Tuple[bytes, Dict[str, Any], int]],
    fetched_at: str,
    source_url: str = SOURCE_URL,
) -> Dict[str, Any]:
    prices = loaded["prices.json"][1]
    files: List[Dict[str, Any]] = []
    for name in REQUIRED_FILES:
        raw, doc, count = loaded[name]
        packed = _gzip_bytes(raw)
        counter, unit, _declared = COUNT_SPECS[name]
        files.append(
            {
                "path": f"{name}.gz",
                "source": name,
                "url": f"https://gpueconomy.com/{name}",
                "count": count,
                "count_unit": unit,
                "count_detail": _count_detail(name, doc, count),
                "bytes_raw": len(raw),
                "bytes_gz": len(packed),
                "sha256_raw": _sha256(raw),
                "sha256_gz": _sha256(packed),
            }
        )
    notes = [
        "Archived files are the raw upstream JSON, gzip-compressed without modification. "
        "The dashboard filters and recomputes medians for cross-checking; those derived "
        "values are not figures published by GPU Economy.",
        "prices.json 'providers' (121) counts scraped=true providers only; "
        "providers.json has 127 entries, including 6 unscraped providers with no quotes.",
        "token-cost.json has no attribution field upstream; it inherits the snapshot "
        "attribution and its throughput figures remain NVIDIA's (CC BY 4.0 selection/formula).",
    ]
    return {
        "source": SOURCE,
        "source_url": source_url,
        "fetched_at": fetched_at,
        "data_updated_at": prices["data_updated_at"],
        "methodology_version": prices.get("methodology_version"),
        "methodology_version_source": "prices.json",
        "methodology_version_format": "N.N.N",
        "methodology_changelog": prices.get("methodology_changelog"),
        "license": prices.get("license"),
        "license_url": LICENSE_URL,
        "attribution": prices.get("attribution"),
        "compression": GZIP_NOTE,
        "files": files,
        "file_count": len(files),
        "total_bytes_raw": sum(item["bytes_raw"] for item in files),
        "total_bytes_gz": sum(item["bytes_gz"] for item in files),
        "counts": {item["source"]: item["count"] for item in files},
        "notes": notes,
    }


def _resolve_snapshot_day(
    loaded: Dict[str, Tuple[bytes, Dict[str, Any], int]], day: str
) -> str:
    data_day = str(loaded["prices.json"][1]["data_updated_at"])[:10]
    if day != data_day:
        _fail(f"--date {day} does not match data_updated_at date {data_day}")
    return day


def _write_snapshot(
    loaded: Dict[str, Tuple[bytes, Dict[str, Any], int]],
    out_dir: Path,
    day: str,
    fetched_at: str,
    source_url: str,
) -> Dict[str, Any]:
    _resolve_snapshot_day(loaded, day)
    metadata = _build_metadata(loaded, fetched_at, source_url=source_url)
    target = out_dir / day
    target.mkdir(parents=True, exist_ok=True)
    for item in metadata["files"]:
        name = item["source"]
        raw = loaded[name][0]
        (target / item["path"]).write_bytes(_gzip_bytes(raw))
    (target / "metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    metadata["snapshot_dir"] = str(target)
    return metadata


def ingest_from_documents(
    loaded: Dict[str, Tuple[bytes, Dict[str, Any], int]],
    out_dir: Path,
    day: str,
    fetched_at: str,
    source_url: str = SOURCE_URL,
) -> Dict[str, Any]:
    return _write_snapshot(loaded, out_dir, day, fetched_at, source_url)


def ingest_from_dir(source_dir: Path, out_dir: Path, day: str, fetched_at: str) -> Dict[str, Any]:
    loaded = _load_source_dir(source_dir)
    return _write_snapshot(loaded, out_dir, day, fetched_at, SOURCE_URL)


def ingest_from_url(
    url: str,
    out_dir: Path,
    day: str,
    fetched_at: str,
    timeout: float = DEFAULT_TIMEOUT,
) -> Dict[str, Any]:
    loaded = _decode_documents(_download_documents(url, timeout))
    return _write_snapshot(loaded, out_dir, day, fetched_at, url)


def verify_snapshot(snapshot_dir: Path) -> Dict[str, Any]:
    metadata_path = snapshot_dir / "metadata.json"
    if not metadata_path.is_file():
        _fail(f"missing metadata: {metadata_path}")
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    for field in (
        "source",
        "source_url",
        "fetched_at",
        "data_updated_at",
        "methodology_version",
        "methodology_changelog",
        "license",
        "attribution",
        "files",
    ):
        if not metadata.get(field):
            _fail(f"metadata.json: missing {field}")
    _parse_time(metadata.get("fetched_at"), "fetched_at", "metadata.json")
    _parse_time(metadata.get("data_updated_at"), "data_updated_at", "metadata.json")
    errors: List[str] = []
    checked: List[Dict[str, Any]] = []
    metadata_version = metadata.get("methodology_version")
    if not isinstance(metadata_version, str) or not METHODOLOGY_RE.match(metadata_version):
        errors.append(f"metadata methodology_version is not N.N.N: {metadata_version!r}")
    if "CC BY 4.0" not in str(metadata.get("license") or ""):
        errors.append(f"metadata license is not CC BY 4.0: {metadata.get('license')!r}")
    prices_doc: Dict[str, Any] | None = None
    files = metadata.get("files") or []
    names = {str(item.get("source") or "") for item in files}
    missing = [name for name in REQUIRED_FILES if name not in names]
    if missing:
        _fail(f"metadata.json: missing file entries {missing}")
    if metadata.get("file_count") != len(files):
        errors.append(f"file_count {metadata.get('file_count')} != {len(files)}")
    for item in files:
        path = snapshot_dir / str(item.get("path") or "")
        if not path.is_file():
            errors.append(f"missing {path.name}")
            continue
        payload = path.read_bytes()
        if len(payload) != item.get("bytes_gz"):
            errors.append(f"{path.name}: bytes_gz {len(payload)} != {item.get('bytes_gz')}")
        if _sha256(payload) != item.get("sha256_gz"):
            errors.append(f"{path.name}: sha256_gz mismatch")
        try:
            raw = _gunzip_bytes(payload)
        except OSError as exc:
            errors.append(f"{path.name}: cannot gunzip ({exc})")
            continue
        if len(raw) != item.get("bytes_raw"):
            errors.append(f"{path.name}: bytes_raw {len(raw)} != {item.get('bytes_raw')}")
        if _sha256(raw) != item.get("sha256_raw"):
            errors.append(f"{path.name}: sha256_raw mismatch")
        name = str(item.get("source") or "")
        if name in COUNT_SPECS:
            try:
                doc = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                errors.append(f"{path.name}: invalid JSON ({exc})")
                continue
            count = COUNT_SPECS[name][0](doc)
            if count != item.get("count"):
                errors.append(f"{path.name}: count {count} != {item.get('count')}")
            declared_version = doc.get("methodology_version")
            if declared_version is not None and declared_version != metadata_version:
                errors.append(
                    f"{path.name}: methodology_version {declared_version!r} != "
                    f"metadata {metadata_version!r}"
                )
            declared_license = doc.get("license")
            if declared_license is not None and "CC BY 4.0" not in str(declared_license):
                errors.append(
                    f"{path.name}: license {declared_license!r} is not compatible with "
                    f"metadata license {metadata.get('license')!r}"
                )
            declared_updated = doc.get("data_updated_at")
            if declared_updated is not None and declared_updated != metadata.get("data_updated_at"):
                errors.append(
                    f"{path.name}: data_updated_at {declared_updated!r} != "
                    f"metadata {metadata.get('data_updated_at')!r}"
                )
            if name == "prices.json":
                prices_doc = doc
        checked.append({"path": path.name, "bytes_gz": len(payload), "count": item.get("count")})
    if prices_doc is None:
        errors.append("prices.json was not parsed")
    if errors:
        _fail("snapshot verification failed: " + "; ".join(errors))
    return {
        "snapshot_dir": str(snapshot_dir),
        "files": checked,
        "file_count": len(checked),
        "total_bytes_gz": sum(item["bytes_gz"] for item in checked),
        "data_updated_at": metadata.get("data_updated_at"),
        "license": metadata.get("license"),
        "attribution": metadata.get("attribution"),
    }


def parse_args(argv: Iterable[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--from-dir", type=Path, help="directory containing the seven source JSON files")
    parser.add_argument(
        "--url",
        help="data page or base URL to download the seven JSON files (HTTPS; e.g. https://gpueconomy.com/data)",
    )
    parser.add_argument("--date", help="snapshot date (YYYY-MM-DD); defaults to data_updated_at date")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help=f"snapshot root (default: {DEFAULT_OUT})")
    parser.add_argument("--fetched-at", help="ISO-8601 fetch time; defaults to now (UTC)")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT, help="download timeout per file in seconds"
    )
    parser.add_argument("--verify", type=Path, help="verify an existing snapshot directory and exit")
    return parser.parse_args(argv)


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(argv)
    if args.verify:
        print(json.dumps(verify_snapshot(args.verify), ensure_ascii=False, indent=1))
        return 0
    if args.url and args.from_dir:
        _fail("use either --url or --from-dir, not both")
    if not args.url and not args.from_dir:
        _fail("one of --url, --from-dir, or --verify is required")
    fetched_at = args.fetched_at or _utc_now()
    _parse_time(fetched_at, "--fetched-at", "arguments")

    if args.url:
        loaded = _decode_documents(_download_documents(args.url, args.timeout))
        source_url = args.url
    else:
        source_dir = args.from_dir.expanduser().resolve()
        if not source_dir.is_dir():
            _fail(f"--from-dir is not a directory: {source_dir}")
        loaded = _load_source_dir(source_dir)
        source_url = SOURCE_URL

    data_updated_at = loaded["prices.json"][1]["data_updated_at"]
    day = args.date or str(data_updated_at)[:10]
    try:
        datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        _fail(f"--date must be YYYY-MM-DD, got {day!r}")
    _resolve_snapshot_day(loaded, day)

    metadata = _write_snapshot(
        loaded, args.out.expanduser().resolve(), day, fetched_at, source_url
    )
    print(
        json.dumps(
            {
                "snapshot_dir": metadata["snapshot_dir"],
                "file_count": metadata["file_count"],
                "total_bytes_raw": metadata["total_bytes_raw"],
                "total_bytes_gz": metadata["total_bytes_gz"],
                "data_updated_at": metadata["data_updated_at"],
                "methodology_version": metadata["methodology_version"],
            },
            ensure_ascii=False,
            indent=1,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
