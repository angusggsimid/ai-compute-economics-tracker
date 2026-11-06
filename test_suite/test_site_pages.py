"""End-to-end build tests for the P2-3 standalone static site."""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "html_dashboard"))

from gpu_external import build_crosscheck, load_external  # noqa: E402
from gpu_landscape import full_landscape, public_prices  # noqa: E402
from site_build import write_site  # noqa: E402
from site_data import write_site_data  # noqa: E402
from site_shell import NAV  # noqa: E402
from build_time_series_dashboard import write_public_data  # noqa: E402


BACKFILL_PATH = ROOT / "tracker_data" / "backfills" / "neocloud_provider_price_history.json"
ROOT_PAGES = ["landscape.html", "providers.html", "compare.html", "spread.html", "cheapest.html"]


def _site_counts(public: Path) -> dict[str, int]:
    index = json.loads((public / "data" / "site-index.json").read_text(encoding="utf-8"))
    providers = index.get("providers") or {}
    return {
        "cards": len(index.get("cards") or []),
        "providers": len(providers.get("own") or []) + len(providers.get("external") or []),
        "markets": len(index.get("markets") or []),
    }


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    raw = json.loads(BACKFILL_PATH.read_text(encoding="utf-8"))
    full = full_landscape(raw.get("rows") or [])
    external = load_external()
    public = tmp_path_factory.mktemp("site-build")
    write_site_data(public, full, external)
    (public / "data" / "prices.json").write_text(
        json.dumps(public_prices(full), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    (public / "data" / "crosscheck.json").write_text(
        json.dumps(build_crosscheck(full, external), ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )
    written = write_site(public)
    return public, written


def test_write_site_returns_every_generated_file(built):
    public, written = built
    counts = _site_counts(public)
    expected_html = counts["cards"] + counts["providers"] + len(ROOT_PAGES)
    assert len(written) == expected_html + 2
    assert len(set(written)) == len(written)
    assert all(Path(path).is_absolute() for path in written)
    assert all(Path(path).is_file() for path in written)
    for path in written:
        assert Path(path).is_relative_to(public)

    html_files = [path for path in written if path.endswith(".html")]
    assert len(html_files) == expected_html
    assert sorted(Path(path).name for path in html_files if Path(path).parent == public) == sorted(ROOT_PAGES)


def test_page_counts_and_assets(built):
    public, _written = built
    counts = _site_counts(public)
    assert len(list((public / "gpu").glob("*.html"))) == counts["cards"]
    assert len(list((public / "providers").glob("*.html"))) == counts["providers"]
    assert len(list(public.glob("*.html"))) == len(ROOT_PAGES)
    assert not (public / "index.html").exists(), "index.html is copied by the main build, not write_site()"

    for asset in ("site.css", "site.js"):
        path = public / "assets" / asset
        assert path.is_file()
        assert path.stat().st_size > 5000

    for page in ROOT_PAGES:
        assert (public / page).is_file()
        assert (public / page).stat().st_size > 8000


def test_every_page_has_relative_shell_and_nav(built):
    public, _written = built
    root_pages = set(ROOT_PAGES)
    for path in public.rglob("*.html"):
        relative = path.relative_to(public)
        html = path.read_text(encoding="utf-8")
        expected_base = "." if relative.parent == Path(".") else ".."
        assert html.startswith("<!doctype html>"), relative
        assert html.rstrip().endswith("</html>"), relative
        assert f'<body data-base="{expected_base}">' in html, relative
        assert f'href="{expected_base}/assets/site.css"' in html, relative
        assert f'src="{expected_base}/assets/site.js"' in html, relative
        for href, _label in NAV:
            assert f'href="{expected_base}/{href}"' in html, (relative, href)
        assert '"/data/' not in html, relative
        assert "file://" not in html, relative
        assert path.stat().st_size > 3000, relative

        matches = re.findall(r'<body data-base="([^"]+)">', html)
        assert matches == [expected_base], relative
        if relative.parent == Path("."):
            assert relative.as_posix() in root_pages


def test_root_pages_have_active_nav_item(built):
    public, _written = built
    for page in ROOT_PAGES:
        html = (public / page).read_text(encoding="utf-8")
        assert f'href="./{page}" class="active" aria-current="page"' in html, page


def test_card_h100_page_contract(built):
    public, _written = built
    html = (public / "gpu" / "h100.html").read_text(encoding="utf-8")
    card = json.loads((public / "data" / "cards" / "h100.json").read_text(encoding="utf-8"))
    assert '<body data-base="..">' in html
    assert 'CC.get("cards/"' in html or "cards/h100.json" in html
    assert "cards/h100.json" in html
    assert html.count("data-market-tab=") == len(card["card"]["markets"])
    assert "H100" in html
    assert 'href="../landscape.html"' in html
    assert "GPU Economy" in html
    assert "CC BY 4.0" in html


def test_external_provider_page_contract(built):
    public, _written = built
    html = (public / "providers" / "ext-runpod.html").read_text(encoding="utf-8")
    assert '<body data-base="..">' in html
    assert "GPU Economy · CC BY 4.0" in html
    assert "https://creativecommons.org/licenses/by/4.0/" in html
    assert "providers/ext-runpod.json" in html
    assert "not published" in html


def test_tool_pages_are_in_the_build(built):
    public, _written = built
    compare = (public / "compare.html").read_text(encoding="utf-8")
    spread = (public / "spread.html").read_text(encoding="utf-8")
    cheapest = (public / "cheapest.html").read_text(encoding="utf-8")
    assert 'id="compare-card-options"' in compare
    assert 'id="spread-table"' in spread
    assert 'id="cheapest-table"' in cheapest
    for html in (compare, spread, cheapest):
        assert '<body data-base=".">' in html
        assert "data-filter=" in html or "data-card-toggle" in html


def test_write_public_data_keeps_site_slices_inside_out_dir(tmp_path):
    staging = tmp_path / "staging"
    staging.mkdir()
    out = staging / "custom-data"
    out.mkdir()
    (out / "price-index").mkdir()
    stale_index = out / "price-index" / "stale.json"
    stale_index.write_text("{}", encoding="utf-8")

    written = write_public_data(
        {"meta": {"generatedAt": "2026-11-06T00:00:00Z"}},
        out_dir=out,
        freeze=False,
        snapshot_dir=tmp_path / "snapshots",
    )
    assert (out / "data" / "site-index.json").is_file()
    assert (out / "data" / "cards" / "h100.json").is_file()
    assert (out / "data" / "providers").is_dir()
    for name in ("prices.json", "crosscheck.json", "gpus.json", "providers.json", "manifest.json"):
        assert (out / "data" / name).is_file(), name
    assert (out / "data" / "price-index" / "h100.json").is_file()
    assert not stale_index.exists(), "stale price-index slices must be pruned"
    assert not (staging / "data").exists(), "site slices must stay inside out_dir"
    for path in written.values():
        assert Path(path).resolve().is_relative_to(out.resolve()), path

    manifest = json.loads((out / "data" / "manifest.json").read_text(encoding="utf-8"))
    manifest_paths = {item["path"] for item in manifest["files"]}
    assert {
        "site-index.json",
        "cards/{gpu}.json",
        "providers/{layer}-{id}.json",
        "external/prices.json",
        "external/providers.json",
    } <= manifest_paths

    write_site(out)
    spread_html = (out / "spread.html").read_text(encoding="utf-8")
    landscape_html = (out / "landscape.html").read_text(encoding="utf-8")
    assert 'CC.get("prices.json")' in spread_html
    assert 'CC.get("external/prices.json")' in spread_html
    assert 'CC.get("crosscheck.json")' in landscape_html
    assert (out / "data" / "prices.json").is_file()
    assert (out / "data" / "crosscheck.json").is_file()


def test_write_site_removes_stale_card_and_provider_pages(built, tmp_path):
    source_public, _written = built
    target = tmp_path / "shrunk-public"
    shutil.copytree(source_public, target)
    index = json.loads((target / "data" / "site-index.json").read_text(encoding="utf-8"))
    removed_card = index["cards"].pop()
    removed_provider = index["providers"]["external"].pop()
    removed_card_page = target / "gpu" / f"{removed_card['slug']}.html"
    removed_provider_page = target / "providers" / f"{removed_provider['slug']}.html"
    assert removed_card_page.is_file()
    assert removed_provider_page.is_file()
    before = len(list(target.rglob("*.html")))
    (target / "data" / "site-index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=1) + "\n",
        encoding="utf-8",
    )

    write_site(target)

    assert not removed_card_page.exists()
    assert not removed_provider_page.exists()
    assert len(list(target.rglob("*.html"))) == before - 2
    assert (target / "assets" / "site.css").is_file()
    assert (target / "assets" / "site.js").is_file()
    for page in ROOT_PAGES:
        assert (target / page).is_file()


def test_write_site_fails_without_data(tmp_path):
    with pytest.raises(FileNotFoundError, match="site-index.json"):
        write_site(tmp_path)
