#!/usr/bin/env python3
"""Browser-level publish gate: catch runtime JS errors that pytest cannot see.

起本地静态服务，用无头 Chromium 加载正式构建产物，断言：
console 零错误、CAPEX 表格已填充、四时钟卡片齐全、核心图表 SVG 数量达标。
任何一项失败即退出非零，阻止发布（2026-08-23 CAPEX 消失事故的永久防线）。
"""

from __future__ import annotations

import json
import re
import socketserver
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8931
sys.path.insert(0, str(ROOT / "html_dashboard"))

from site_tools import _external_view_market  # noqa: E402


def _event_toggle_works(page) -> bool:
    before = page.locator(".event-marker").count()
    if before == 0:
        return False
    button = page.locator("#toggle-events")
    pressed_before = button.get_attribute("aria-pressed")
    button.click()
    hidden = page.locator(".event-marker").count() == 0
    pressed_off = button.get_attribute("aria-pressed")
    button.click()
    restored = page.locator(".event-marker").count() > 0
    pressed_on = button.get_attribute("aria-pressed")
    return hidden and restored and pressed_before == "true" and pressed_off == "false" and pressed_on == "true"


def _sandbox_redraws(page) -> bool:
    select = page.locator("#sandbox-series-a")
    if select.count() != 1:
        return False
    before = page.locator("#sandbox-chart svg path").first.get_attribute("d")
    select.select_option(index=1)
    page.wait_for_timeout(200)
    after = page.locator("#sandbox-chart svg path").first.get_attribute("d")
    chip = page.locator("#sandbox-correlation").inner_text()
    axis_text = page.locator("#sandbox-chart svg text").count()
    return bool(before and after and before != after and "n=" in chip and axis_text >= 8)


def _sandbox_correlation_is_symmetric(page) -> bool:
    """左右对调序列 A/B，相关系数必须不变；否则配对算法偏向某一侧。"""
    def r_value() -> str | None:
        text = page.locator("#sandbox-correlation").inner_text()
        match = re.search(r"r=(-?\d+\.\d+)", text)
        return match.group(1) if match else None

    page.locator("#sandbox-series-a").select_option(index=0)
    page.locator("#sandbox-series-b").select_option(index=3)
    page.wait_for_timeout(120)
    first = r_value()
    page.locator("#sandbox-series-a").select_option(index=3)
    page.locator("#sandbox-series-b").select_option(index=0)
    page.wait_for_timeout(120)
    second = r_value()
    page.locator("#sandbox-series-a").select_option(index=0)
    page.locator("#sandbox-series-b").select_option(index=3)
    if first is None or second is None:
        return False
    return abs(float(first) - float(second)) < 0.001


def _sandbox_respects_range(page) -> bool:
    before = page.locator("#sandbox-correlation").inner_text()
    page.locator('#presets button[data-days="90"]').click()
    page.wait_for_timeout(220)
    during = page.locator("#sandbox-correlation").inner_text()
    page.locator('#presets button[data-days="0"]').click()
    page.wait_for_timeout(220)
    after = page.locator("#sandbox-correlation").inner_text()
    return before == after and before != during


def _mobile_price_chart_fits(page) -> bool:
    """390px 下 GPU 价格图的 viewBox 宽度必须跟随容器，不能被 1000px 下限压扁。"""
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(350)
    dims = page.evaluate(
        """() => {
            const host = document.querySelector('#gpu-price-h100');
            const svg = host && host.querySelector('svg');
            if (!host || !svg) return null;
            return {host: host.clientWidth, viewBox: svg.viewBox.baseVal.width, height: svg.viewBox.baseVal.height};
        }"""
    )
    mobile_nav = page.locator(".mobile-nav")
    nav_ok = mobile_nav.count() == 1 and mobile_nav.is_visible() and mobile_nav.locator("a").count() >= 5
    page.set_viewport_size({"width": 1280, "height": 720})
    page.wait_for_timeout(250)
    return bool(dims) and abs(dims["viewBox"] - dims["host"]) <= 2 and dims["height"] >= 300 and nav_ok


def _landscape_works(page) -> bool:
    card = page.locator("#landscape-card")
    markets = page.locator("#landscape-market button")
    if card.count() != 1 or markets.count() != 6:
        return False
    if page.locator("#landscape-all-body tr").count() < 8:
        return False
    before = page.locator("#landscape-chart svg path").first.get_attribute("d")
    card.select_option(index=2)
    page.wait_for_timeout(250)
    after = page.locator("#landscape-chart svg path").first.get_attribute("d")
    kpi = page.locator("#landscape-kpis").inner_text()
    page.locator('#landscape-market button[data-market="spot"]').click()
    page.wait_for_timeout(250)
    spot = page.locator("#landscape-kpis").inner_text()
    url_ok = "gpu=B200" in page.url and "market=spot" in page.url
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.locator("#landscape-card").select_option(index=0)
    page.wait_for_timeout(200)
    return bool(before and after and before != after and len(kpi) > 20 and "Spot" in spot and url_ok)


def _landscape_table_click(page) -> bool:
    """The all-card table is on-demand; clicking a row must reset a previously selected market."""
    page.locator("#landscape-card").select_option("L40S")
    page.locator('#landscape-market button[data-market="reserved"]').click()
    page.wait_for_timeout(150)
    page.locator('#landscape-all-body tr[data-card="B200"]').click()
    page.wait_for_timeout(200)
    return (
        page.locator("#landscape-card").input_value() == "B200"
        and page.locator("#landscape-market button.active").inner_text() == "On-demand"
        and "正规 on-demand" in page.locator(".landscape-kpi").first.inner_text()
    )


def _landscape_stale_not_repeated(page) -> bool:
    """全局滞后只提示一次；逐行不再重复 11 个“滞后”，但市场自己的状态仍要保留。"""
    return bool(
        page.evaluate(
            """() => {
                const prevFresh = LANDSCAPE_DATA.dataFreshness;
                const prevAge = LANDSCAPE_DATA.dataAgeDays;
                LANDSCAPE_DATA.dataFreshness = 'stale';
                LANDSCAPE_DATA.dataAgeDays = 5;
                renderLandscape();
                const body = document.querySelector('#landscape-all-body');
                const repeated = [...body.querySelectorAll('tr td:last-child')]
                    .some(td => /滞后/.test(td.textContent || ''));
                const summary = document.querySelector('.landscape-all>summary').textContent || '';
                LANDSCAPE_DATA.dataFreshness = prevFresh;
                LANDSCAPE_DATA.dataAgeDays = prevAge;
                renderLandscape();
                return !repeated && /全局数据滞后 5 天/.test(summary);
            }"""
        )
    )


def _landscape_market_status_visible(page) -> bool:
    """市场级 unconfirmed 不能被全局状态或空状态列吞掉。"""
    return bool(
        page.evaluate(
            """() => {
                landscapeCardSelect.value = 'A100';
                _landscapeSetMarket('marketplace');
                const card = _landscapeCard();
                const market = card && card.markets.marketplace;
                if (!market || !market.latest) return false;
                const prev = market.status;
                market.status = 'unconfirmed';
                renderLandscape();
                const row = document.querySelector('#landscape-market-table tr[data-market="marketplace"]');
                const evidence = document.querySelector('#landscape-evidence').textContent || '';
                const ok = !!row && /待确认/.test(row.textContent || '') && /该市场：待确认/.test(evidence);
                market.status = prev;
                landscapeCardSelect.value = 'H100';
                _landscapeSetMarket('on_demand');
                return ok;
            }"""
        )
    )


def _landscape_cheapest_toggle(page) -> bool:
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(200)
    toggle = page.locator("#landscape-cheapest-toggle")
    if toggle.count() != 1:
        return False
    line = page.locator("#landscape-chart svg path.cheapest-line")
    before = line.count()
    pressed_before = toggle.get_attribute("aria-pressed")
    toggle.click()
    page.wait_for_timeout(180)
    hidden = line.count() == 0
    pressed_off = toggle.get_attribute("aria-pressed")
    toggle.click()
    page.wait_for_timeout(180)
    restored = line.count() == before
    pressed_on = toggle.get_attribute("aria-pressed")
    return before >= 1 and hidden and restored and pressed_before == "true" and pressed_off == "false" and pressed_on == "true"


def _landscape_offers_rows(page) -> bool:
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(200)
    details = page.locator("#landscape-offers")
    if details.count() != 1:
        return False
    details.locator("summary").first.click()
    page.wait_for_timeout(150)
    rows = page.locator("#landscape-offers-body tr")
    row_count = rows.count()
    cells = rows.first.locator("td").count() if row_count else 0
    hrefs = page.eval_on_selector_all(
        "#landscape-offers-body a", "els => els.map(e => e.getAttribute('href'))"
    )
    links_ok = bool(hrefs) and all(str(href).startswith(("http://", "https://")) for href in hrefs)
    header = page.locator("#landscape-offers thead").inner_text()
    note = page.locator("#landscape-offers-note").inner_text()
    page.locator("#landscape-card").select_option("MI300X")
    page.locator('#landscape-market button[data-market="spot"]').click()
    page.wait_for_timeout(200)
    empty_ok = "该市场暂无报价" in page.locator("#landscape-offers-body").inner_text()
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(180)
    return (
        row_count >= 10
        and cells == 7
        and links_ok
        and empty_ok
        and "市场" in header
        and "市场风险" in header
        and "日期与市场风险为市场级" in note
    )


def _landscape_monthly_rows(page) -> bool:
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(200)
    rows = page.locator("#landscape-monthly-body tr")
    if rows.count() < 4:
        return False
    cells = rows.first.locator("td").count()
    statuses = page.eval_on_selector_all(
        "#landscape-monthly-body tr", "els => els.map(e => e.dataset.status)"
    )
    vintages = page.eval_on_selector_all(
        "#landscape-monthly-body tr", "els => els.map(e => e.dataset.vintage)"
    )
    stage_text = page.eval_on_selector_all(
        "#landscape-monthly-body tr", "els => els.map(e => e.children[6].textContent.trim())"
    )
    page.locator("#landscape-monthly > summary").click()
    page.wait_for_timeout(120)
    monthly_note = page.locator("#landscape-monthly .panel-note").inner_text()
    note_ok = "日频近似" in monthly_note and "不是不可变快照" in monthly_note
    header = page.locator("#landscape-monthly thead").inner_text()
    return (
        cells == 8
        and "published" in statuses
        and "withheld" in statuses
        and "provisional" in vintages
        and "final" in vintages
        and any("进行中" in text or "暂定" in text for text in stage_text)
        and any("已结束" in text for text in stage_text)
        and "阶段" in header
        and note_ok
    )


def _landscape_crosscheck_table(page) -> bool:
    page.wait_for_function(
        "() => document.querySelectorAll('#landscape-crosscheck-body tr').length >= 11",
        timeout=5000,
    )
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(250)
    page.locator("#landscape-crosscheck > summary").click()
    page.wait_for_timeout(150)
    rows = page.locator("#landscape-crosscheck-body tr")
    markets = page.eval_on_selector_all(
        "#landscape-crosscheck-body tr", "els => [...new Set(els.map(e => e.dataset.market))]"
    )
    h100 = page.locator('#landscape-crosscheck-body tr[data-card="H100"]').first
    h100_rows = page.locator('#landscape-crosscheck-body tr[data-card="H100"]').count()
    h100_bench = page.locator('#landscape-crosscheck-body tr[data-card="H100"][data-benchmark="1"]').count()
    a100 = page.locator('#landscape-crosscheck-body tr[data-card="A100"]')
    if a100.count() != 1:
        return False
    a100_text = a100.inner_text()
    a100_diff = a100.locator("td").nth(4).inner_text().strip()
    selected = page.locator("#landscape-crosscheck-selected").inner_text()
    header = page.locator("#landscape-crosscheck thead").inner_text()
    return (
        rows.count() >= 11
        and markets == ["on_demand"]
        and h100_rows == 2
        and h100_bench == 1
        and "SKU 混合" in h100.inner_text()
        and "型号不一致" in a100_text
        and a100_diff == "—"
        and "口径差" in header
        and "我方/外部" in header
        and "GPU Economy 中位" in selected
        and "暂不可用" not in selected
    )


def _landscape_crosscheck_own_sample(page) -> bool:
    """Table and selected row must show our provider sample and thin status."""
    page.wait_for_function(
        "() => typeof LANDSCAPE_CROSSCHECK !== 'undefined' && !!LANDSCAPE_CROSSCHECK.data",
        timeout=5000,
    )
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(250)
    info = page.evaluate(
        """() => {
            const rows = LANDSCAPE_CROSSCHECK.data.rows;
            const h = rows.find(r => r.card_id === 'H100' && r.market === 'on_demand');
            const g = rows.find(r => r.card_id === 'GH200' && r.market === 'on_demand');
            const tr = id => [...document.querySelectorAll('#landscape-crosscheck-body tr')]
                .find(row => row.dataset.card === id);
            const gRow = tr('GH200');
            return {
                hOwn: h.own_providers,
                hExt: h.ext_providers,
                hOverlap: h.overlap_count,
                hText: tr('H100').textContent,
                gText: gRow.textContent,
                gDiff: gRow.children[4].textContent.trim(),
                gCoverageText: gRow.children[7].textContent.trim(),
                gCoverage: g.coverage,
                selected: document.querySelector('#landscape-crosscheck-selected').textContent,
                header: document.querySelector('#landscape-crosscheck thead').textContent,
            };
        }"""
    )
    counts_ok = f"{info['hOwn']} / {info['hExt']}" in info["hText"]
    selected_ok = (
        f"我方 {info['hOwn']} 家 / 外部 {info['hExt']} 家 / 重叠 {info['hOverlap']}"
        in info["selected"]
    )
    gh200_ok = (
        info["gCoverage"] == "thin"
        and info["gCoverageText"] == "样本偏薄"
        and "可比" not in info["gCoverageText"]
        and info["gDiff"] == "—"
    )
    return counts_ok and selected_ok and gh200_ok and "我方/外部" in info["header"]


def _landscape_crosscheck_license(page) -> bool:
    """Attribution text and CC BY 4.0 links must come from crosscheck.json."""
    page.wait_for_function(
        "() => typeof LANDSCAPE_CROSSCHECK !== 'undefined' && !!LANDSCAPE_CROSSCHECK.data",
        timeout=5000,
    )
    info = page.evaluate(
        """() => {
            const d = LANDSCAPE_CROSSCHECK.data;
            const href = sel => {
                const a = document.querySelector(sel);
                return a ? a.getAttribute('href') : null;
            };
            return {
                version: d.methodology_version,
                date: (d.data_updated_at || '').slice(0, 10),
                license: d.license_url,
                metaText: document.querySelector('#landscape-crosscheck-meta').textContent,
                metaHref: href('#landscape-crosscheck-meta a[href*="creativecommons"]'),
                noteHref: href('#landscape-crosscheck-note a[href*="creativecommons"]'),
                selectedHref: href('#landscape-crosscheck-selected a[href*="creativecommons"]'),
            };
        }"""
    )
    if not info["license"]:
        return False
    return (
        info["license"] == "https://creativecommons.org/licenses/by/4.0/"
        and info["metaHref"] == info["license"]
        and info["noteHref"] == info["license"]
        and info["selectedHref"] == info["license"]
        and f"methodology {info['version']}" in info["metaText"]
        and f"data {info['date']}" in info["metaText"]
    )


def _landscape_crosscheck_market_guard(page) -> bool:
    """SXM is on-demand only; thin markets must not show a diff."""
    page.locator("#landscape-card").select_option("H100")
    page.locator('#landscape-market button[data-market="spot"]').click()
    page.wait_for_timeout(250)
    spot_text = page.locator("#landscape-crosscheck-selected").inner_text()
    spot_ok = "SXM 基准" not in spot_text and "SKU 混合" in spot_text
    page.locator('#landscape-market button[data-market="reserved"]').click()
    page.wait_for_timeout(250)
    reserved_text = page.locator("#landscape-crosscheck-selected").inner_text()
    reserved_ok = (
        "SXM 基准" not in reserved_text
        and "样本偏薄" in reserved_text
        and "口径差 —" in reserved_text
    )
    page.locator('#landscape-market button[data-market="on_demand"]').click()
    page.wait_for_timeout(250)
    on_text = page.locator("#landscape-crosscheck-selected").inner_text()
    on_ok = "SXM 基准" in on_text and "SKU 混合" in on_text and "口径差 —" not in on_text
    return spot_ok and reserved_ok and on_ok


def _mobile_full_page_no_overflow(page) -> bool:
    page.set_viewport_size({"width": 390, "height": 844})
    page.wait_for_timeout(300)
    page.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    page.wait_for_timeout(600)
    dims = page.evaluate(
        "() => ({doc: document.documentElement.scrollWidth, win: window.innerWidth})"
    )
    page.set_viewport_size({"width": 1280, "height": 720})
    page.wait_for_timeout(300)
    return dims["doc"] <= dims["win"]


def _nav_has_clocks(page) -> bool:
    return (
        page.locator('.nav a[href="#clocks"]').count() == 1
        and page.locator('.mobile-nav a[href="#clocks"]').count() == 1
    )


def _scroll_through(page) -> None:
    """滚动一遍触发 IntersectionObserver 懒渲染，确保全页图表都真正构建过。"""
    page.evaluate(
        """async () => {
            const root = document.documentElement;
            const prev = root.style.scrollBehavior;
            root.style.scrollBehavior = 'auto';
            const step = Math.max(280, Math.round(window.innerHeight * 0.45));
            for (let y = 0; y < root.scrollHeight; y += step) {
                window.scrollTo(0, y);
                await new Promise(resolve => setTimeout(resolve, 90));
            }
            await new Promise(resolve => setTimeout(resolve, 250));
            window.scrollTo(0, 0);
            root.style.scrollBehavior = prev;
            await new Promise(resolve => setTimeout(resolve, 120));
        }"""
    )
    page.wait_for_timeout(150)


def _landscape_receipt_csv(page) -> bool:
    with page.expect_download() as download:
        page.locator("#landscape-receipt").click()
    path = download.value.path()
    if not path:
        return False
    header = Path(path).read_text(encoding="utf-8").splitlines()[0]
    return all(key in header for key in ("methodology_version", "published_median", "published_index", "quotes", "excluded_by"))


def _event_markers_reach_primary_charts(page) -> bool:
    return (
        page.locator("#gpu-price-h100 .event-marker").count() > 0
        and page.locator("#or-volume .event-marker").count() > 0
        and page.locator(".event-label").count() <= page.locator(".event-marker").count()
    )


def _event_tooltip_on_price_chart(page) -> bool:
    marker = page.locator("#gpu-price-h100 .event-marker").first
    if marker.count() == 0:
        return False
    event_date = marker.get_attribute("data-date") or ""
    line = marker.locator("line").first
    line.scroll_into_view_if_needed()
    page.wait_for_timeout(100)
    box = line.bounding_box()
    if not box:
        return False
    page.mouse.move(box["x"] + box["width"] / 2, box["y"] + 40)
    page.wait_for_timeout(150)
    tooltip = page.locator("#gpu-price-h100 .tooltip").inner_text()
    return bool(event_date) and event_date in tooltip


def _site_pages_smoke(browser, base_url: str):
    """Load the standalone data pages in fresh tabs and return their checks.

    Each page is opened and closed independently so the existing dashboard
    checks keep their own console/pageerror state.
    """
    checks: dict[str, bool] = {}
    problems: list[str] = []
    all_errors: list[str] = []

    def open_page(path: str, width: int = 1280, height: int = 900):
        page = browser.new_page(viewport={"width": width, "height": height})
        errors: list[str] = []
        page.on(
            "console",
            lambda msg, sink=errors: sink.append(f"console: {msg.text}")
            if msg.type == "error" else None,
        )
        page.on("pageerror", lambda exc, sink=errors: sink.append(f"pageerror: {exc}"))
        response = page.goto(base_url + path, wait_until="networkidle")
        return page, response, errors

    def record(name: str, ok: bool, detail: str = "") -> None:
        checks[name] = bool(ok)
        if not ok and detail:
            problems.append(f"{name}: {detail}")

    # Expected row/offer counts come from the committed slices, not a frozen
    # snapshot.  Daily refreshes may legitimately change providers or offers.
    site_check_names = [
        "site_landscape_page",
        "site_providers_page",
        "site_card_page",
        "site_provider_page",
        "site_compare_page",
        "site_spread_page",
        "site_cheapest_page",
        "site_mobile_no_overflow",
        "site_pages_console_zero",
    ]

    def load_public_json(relative: str):
        return json.loads((ROOT / "public" / relative).read_text(encoding="utf-8"))

    try:
        site_index = load_public_json("data/site-index.json")
        crosscheck = load_public_json("data/crosscheck.json")
        h100_slice = load_public_json("data/cards/h100.json")
        external_prices = load_public_json("data/external/prices.json")
        providers = site_index.get("providers") or {}
        expected_landscape_rows = len(crosscheck.get("rows") or [])
        crosscheck_pairs = {
            (str(row.get("card_id")), str(row.get("market"))): row
            for row in crosscheck.get("rows") or []
        }
        expected_provider_rows = len(providers.get("own") or []) + len(
            providers.get("external") or []
        )
        expected_compare_cards = len(site_index.get("cards") or [])
        h100_card = h100_slice.get("card") or {}
        h100_markets = h100_card.get("markets") or {}
        expected_h100_tabs = len(h100_markets)
        expected_h100_offers = len(
            ((h100_markets.get("on_demand") or {}).get("latest") or {}).get("offers")
            or []
        )
        key_card_ids = {
            str(row.get("match_id")) for row in crosscheck.get("rows") or []
            if row.get("match_id")
        }
        extra_gpu_ids = set()
        for row in external_prices.get("prices") or []:
            if row.get("status") != "live":
                continue
            if row.get("listed_currency") != "USD":
                continue
            if not _external_view_market(row):
                continue
            gpu_id = str(row.get("gpu_id") or "")
            if not gpu_id or gpu_id in key_card_ids:
                continue
            try:
                float(row.get("usd_per_gpu_hour"))
            except (TypeError, ValueError):
                continue
            extra_gpu_ids.add(gpu_id)
        expected_extra_card_options = len(extra_gpu_ids)
    except Exception as exc:  # noqa: BLE001 - missing data is a publish failure
        message = f"site data unavailable: {exc}"
        for name in site_check_names:
            record(name, False, message)
        return checks, [message]

    # Landscape: one row per crosscheck card × market.
    page = None
    try:
        page, response, errors = open_page("/landscape.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#landscape-table tbody tr').length === "
            f"{expected_landscape_rows}",
            timeout=10000,
        )
        rows = page.locator("#landscape-table tbody tr").count()
        record(
            "site_landscape_page",
            response is not None
            and response.ok
            and rows == expected_landscape_rows
            and not errors,
            f"status={getattr(response, 'status', None)} rows={rows} "
            f"expected={expected_landscape_rows} errors={errors[:2]}",
        )
        all_errors.extend(f"landscape: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001 - report as a smoke failure
        record("site_landscape_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # Providers: own + external summaries from site-index.
    page = None
    try:
        page, response, errors = open_page("/providers.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#providers-table tbody tr').length === "
            f"{expected_provider_rows}",
            timeout=10000,
        )
        rows = page.locator("#providers-table tbody tr").count()
        record(
            "site_providers_page",
            response is not None
            and response.ok
            and rows == expected_provider_rows
            and not errors,
            f"status={getattr(response, 'status', None)} rows={rows} "
            f"expected={expected_provider_rows} errors={errors[:2]}",
        )
        all_errors.extend(f"providers: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_providers_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # H100 card: market tabs, KPIs and on-demand offers from the card slice.
    page = None
    try:
        page, response, errors = open_page("/gpu/h100.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#market-panel-on_demand [data-offers] tbody tr').length === "
            f"{expected_h100_offers}",
            timeout=10000,
        )
        offers = page.locator(
            "#market-panel-on_demand [data-offers] tbody tr"
        ).count()
        kpis = page.locator(".kpi-grid .kpi").count()
        tabs = page.locator("[data-market-tab]").count()
        heading = page.locator("h1").inner_text()
        record(
            "site_card_page",
            response is not None
            and response.ok
            and offers == expected_h100_offers
            and expected_h100_offers > 0
            and kpis >= 6
            and tabs == expected_h100_tabs
            and "H100" in heading
            and not errors,
            f"status={getattr(response, 'status', None)} offers={offers} "
            f"expectedOffers={expected_h100_offers} kpis={kpis} tabs={tabs} "
            f"expectedTabs={expected_h100_tabs} errors={errors[:2]}",
        )
        all_errors.extend(f"card: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_card_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # External provider: attribution, license and quote rows.
    page = None
    try:
        page, response, errors = open_page("/providers/ext-runpod.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#quotes-host tbody tr').length > 0",
            timeout=10000,
        )
        quotes = page.locator("#quotes-host tbody tr").count()
        text = page.locator("body").inner_text()
        license_links = page.locator('a[href*="creativecommons.org/licenses/by/4.0"]').count()
        record(
            "site_provider_page",
            response is not None and response.ok
            and "GPU Economy · CC BY 4.0" in text
            and license_links >= 1 and quotes > 0 and not errors,
            f"status={getattr(response, 'status', None)} quotes={quotes} "
            f"licenseLinks={license_links} errors={errors[:2]}",
        )
        all_errors.extend(f"provider: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_provider_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # Compare: selector, chart and table after picking two cards.
    page = None
    try:
        page, response, errors = open_page("/compare.html")
        selectors = page.locator("[data-card-toggle]").count()
        page.locator("[data-card-toggle]").nth(0).check()
        page.locator("[data-card-toggle]").nth(1).check()
        page.wait_for_function(
            "() => document.querySelectorAll('#compare-chart svg path').length >= 2"
            " && document.querySelectorAll('#compare-table tbody tr').length === 2",
            timeout=10000,
        )
        paths = page.locator("#compare-chart svg path").count()
        rows = page.locator("#compare-table tbody tr").count()
        hint = page.locator("#compare-hint").inner_text()

        # B300 + GH200: GH200 has only one indexed week, so it must be marked
        # as insufficient coverage instead of showing a 0.0% change.
        for value in ("H100", "H200"):
            toggle = page.locator(f'[data-card-toggle][value="{value}"]')
            if toggle.is_checked():
                toggle.uncheck()
        page.locator('[data-card-toggle][value="B300"]').check()
        page.locator('[data-card-toggle][value="GH200"]').check()
        page.wait_for_function(
            "() => document.querySelectorAll('#compare-table tbody tr').length === 2",
            timeout=10000,
        )
        gh_row = page.locator("#compare-table tbody tr").filter(has_text="GH200").first
        gh_text = gh_row.inner_text() if gh_row.count() else ""
        coverage_ok = "覆盖不足" in gh_text and "0.0%" not in gh_text

        record(
            "site_compare_page",
            response is not None
            and response.ok
            and selectors == expected_compare_cards
            and paths >= 2
            and rows == 2
            and "共同起点" in hint
            and coverage_ok
            and not errors,
            f"status={getattr(response, 'status', None)} selectors={selectors} "
            f"expected={expected_compare_cards} paths={paths} rows={rows} "
            f"gh200Coverage={coverage_ok} errors={errors[:2]}",
        )
        all_errors.extend(f"compare: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_compare_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # Spread: grouped rows, filters and dynamically expanded card options.
    page = None
    try:
        page, response, errors = open_page("/spread.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#spread-table tbody tr').length > 0",
            timeout=10000,
        )
        rows = page.locator("#spread-table tbody tr").count()
        filters = page.locator("#spread-filters [data-filter]").count()
        extra_cards = page.locator('#spread-card option[value^="gpu:"]').count()
        filtered_rows = 0
        if extra_cards:
            extra_value = page.locator(
                '#spread-card option[value^="gpu:"]'
            ).first.get_attribute("value")
            page.select_option("#spread-card", value=extra_value)
            page.wait_for_timeout(200)
            filtered_rows = page.locator("#spread-table tbody tr").count()

        # Numeric contract: external medians must match crosscheck's
        # one-cheapest-row-per-provider market view, not quote-row medians.
        numeric_cases = [
            ("A100", "on_demand"),
            ("RTX 5090", "community"),
            ("RTX 4090", "community"),
            ("B300", "spot"),
            ("A100", "marketplace"),
        ]
        numeric_ok = True
        numeric_detail = {}
        for card, market in numeric_cases:
            expected = crosscheck_pairs.get((card, market)) or {}
            expected_median = expected.get("ext_median")
            expected_providers = expected.get("ext_providers")
            page.select_option("#spread-card", value=card)
            page.select_option("#spread-market", value=market)
            page.select_option("#spread-layer", value="gpueconomy")
            page.wait_for_timeout(120)
            case_rows = page.locator("#spread-table tbody tr")
            if case_rows.count() != 1 or expected_median is None:
                numeric_ok = False
                numeric_detail[f"{card}/{market}"] = "missing row or crosscheck median"
                continue
            row = case_rows.first
            median_text = row.locator("td").nth(4).inner_text().strip()
            provider_text = row.locator("td").nth(8).inner_text().strip()
            try:
                actual_median = float(median_text.replace("$", "").replace(",", ""))
                actual_providers = int(provider_text.replace(",", "").strip())
            except ValueError:
                numeric_ok = False
                numeric_detail[f"{card}/{market}"] = (
                    f"unparsable median={median_text!r} providers={provider_text!r}"
                )
                continue
            median_ok = abs(actual_median - float(expected_median)) <= 0.011
            providers_ok = (
                expected_providers is None
                or actual_providers == int(expected_providers)
            )
            floor_ok = (
                market != "marketplace"
                or "floor，不是 rate card" in row.inner_text()
            )
            if not (median_ok and providers_ok and floor_ok):
                numeric_ok = False
            numeric_detail[f"{card}/{market}"] = (
                f"{actual_median:.2f}/{float(expected_median):.3f} "
                f"n={actual_providers}/{expected_providers} "
                f"floor={floor_ok}"
            )

        record(
            "site_spread_page",
            response is not None
            and response.ok
            and rows > 0
            and filters == 3
            and extra_cards == expected_extra_card_options
            and (extra_cards == 0 or filtered_rows > 0)
            and numeric_ok
            and not errors,
            f"status={getattr(response, 'status', None)} rows={rows} "
            f"filters={filters} extraCardOptions={extra_cards} "
            f"expectedExtra={expected_extra_card_options} "
            f"filteredRows={filtered_rows} numeric={numeric_detail} "
            f"errors={errors[:2]}",
        )
        all_errors.extend(f"spread: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_spread_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # Cheapest: grouped rows, provider/card links and dynamic card options.
    page = None
    try:
        page, response, errors = open_page("/cheapest.html")
        page.wait_for_function(
            "() => document.querySelectorAll('#cheapest-table tbody tr').length > 0",
            timeout=10000,
        )
        rows = page.locator("#cheapest-table tbody tr").count()
        provider_links = page.locator('#cheapest-table a[href^="providers/"]').count()
        card_links = page.locator('#cheapest-table a[href^="gpu/"]').count()
        filters = page.locator("#cheapest-filters [data-filter]").count()
        extra_cards = page.locator('#cheapest-card option[value^="gpu:"]').count()
        filtered_rows = 0
        if extra_cards:
            extra_value = page.locator(
                '#cheapest-card option[value^="gpu:"]'
            ).first.get_attribute("value")
            page.select_option("#cheapest-card", value=extra_value)
            page.wait_for_timeout(200)
            filtered_rows = page.locator("#cheapest-table tbody tr").count()
        record(
            "site_cheapest_page",
            response is not None
            and response.ok
            and rows > 0
            and provider_links > 0
            and card_links > 0
            and filters == 3
            and extra_cards == expected_extra_card_options
            and (extra_cards == 0 or filtered_rows > 0)
            and not errors,
            f"status={getattr(response, 'status', None)} rows={rows} "
            f"providerLinks={provider_links} cardLinks={card_links} "
            f"extraCardOptions={extra_cards} expectedExtra={expected_extra_card_options} "
            f"filteredRows={filtered_rows} errors={errors[:2]}",
        )
        all_errors.extend(f"cheapest: {item}" for item in errors)
    except Exception as exc:  # noqa: BLE001
        record("site_cheapest_page", False, str(exc))
    finally:
        if page is not None:
            page.close()

    # 390px: element-level overflow audit across the generated site.
    page = None
    mobile_errors: list[str] = []
    try:
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.on(
            "console",
            lambda msg, sink=mobile_errors: sink.append(f"console: {msg.text}")
            if msg.type == "error" else None,
        )
        page.on(
            "pageerror",
            lambda exc, sink=mobile_errors: sink.append(f"pageerror: {exc}"),
        )
        audit_js = """() => {
            const win = window.innerWidth;
            const bad = [];
            const containers = document.querySelectorAll(
                'main, .shell, .panel, .hero, .section, .panel-head, .kpi, ' +
                '.kpi-grid, .filters, .field, .chart, .topbar-inner, .nav, .footer-inner'
            );
            containers.forEach((el) => {
                if (el.closest('.table-wrap')) { return; }
                const rect = el.getBoundingClientRect();
                if (!rect.width && !rect.height) { return; }
                if (rect.right > win + 2 || rect.left < -2) {
                    bad.push({
                        tag: el.tagName.toLowerCase(),
                        cls: String(el.className || ''),
                        left: Math.round(rect.left),
                        right: Math.round(rect.right)
                    });
                }
            });
            return {
                doc: document.documentElement.scrollWidth,
                body: document.body.scrollWidth,
                win: win,
                bad: bad.slice(0, 8)
            };
        }"""
        dims = {}
        for path in (
            "/landscape.html",
            "/providers.html",
            "/gpu/h100.html",
            "/providers/ext-runpod.html",
            "/compare.html",
            "/spread.html",
            "/cheapest.html",
        ):
            page.goto(base_url + path, wait_until="networkidle")
            if path == "/landscape.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#landscape-table tbody tr').length === "
                    f"{expected_landscape_rows}",
                    timeout=10000,
                )
            elif path == "/providers.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#providers-table tbody tr').length === "
                    f"{expected_provider_rows}",
                    timeout=10000,
                )
            elif path == "/gpu/h100.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#market-panel-on_demand [data-offers] tbody tr').length === "
                    f"{expected_h100_offers}",
                    timeout=10000,
                )
            elif path == "/providers/ext-runpod.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#quotes-host tbody tr').length > 0",
                    timeout=10000,
                )
            elif path == "/compare.html":
                page.locator("[data-card-toggle]").nth(0).check()
                page.locator("[data-card-toggle]").nth(1).check()
                page.wait_for_function(
                    "() => document.querySelectorAll('#compare-table tbody tr').length === 2",
                    timeout=10000,
                )
            elif path == "/spread.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#spread-table tbody tr').length > 0",
                    timeout=10000,
                )
            elif path == "/cheapest.html":
                page.wait_for_function(
                    "() => document.querySelectorAll('#cheapest-table tbody tr').length > 0",
                    timeout=10000,
                )
            page.wait_for_timeout(150)
            dims[path] = page.evaluate(audit_js)
        no_overflow = all(
            item["doc"] <= item["win"] + 2
            and item["body"] <= item["win"] + 2
            and not item["bad"]
            for item in dims.values()
        )
        record(
            "site_mobile_no_overflow",
            no_overflow and not mobile_errors,
            json.dumps(
                {"pages": dims, "errors": mobile_errors[:3]},
                ensure_ascii=False,
            ),
        )
        all_errors.extend(f"mobile: {item}" for item in mobile_errors)
    except Exception as exc:  # noqa: BLE001
        record("site_mobile_no_overflow", False, str(exc))
    finally:
        if page is not None:
            page.close()

    record("site_pages_console_zero", not all_errors, "; ".join(all_errors[:5]))
    if problems:
        all_errors.extend(problems)
    return checks, all_errors[:20]


def main() -> int:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(json.dumps({"ok": False, "error": "playwright 未安装"}))
        return 1

    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT / "public"))
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        errors: list[str] = []
        checks: dict[str, bool] = {}
        diagnostics: dict = {"errors": [], "guidanceMismatches": [], "duplicateLabels": []}
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            page.wait_for_timeout(500)
            legacy = page.locator("details.gpu-legacy")
            gpu_legacy_collapsed = legacy.count() == 1 and not legacy.evaluate("el => el.open")
            if legacy.count() == 1:
                legacy.locator("summary").first.click()
                page.wait_for_timeout(350)
            _scroll_through(page)

            # 指引条与 CAPEX 溯源表必须指向同一版修订：
            # chip 数字取自 payload，表格数字取自同一批底表行，二者不一致即页面自相矛盾。
            consistency = page.evaluate(
                """() => {
                    const gs = (typeof DATA !== 'undefined' && DATA.meta && DATA.meta.capexGuidance) || [];
                    const rows = [...document.querySelectorAll('#capex-body tr')].map(tr =>
                        [...tr.querySelectorAll('td')].map(td => td.textContent.trim()));
                    const mismatches = [];
                    for (const g of gs) {
                        const mine = rows.filter(r => r[1] === g.company);
                        if (!mine.length) { mismatches.push(`${g.company}: 表中无任何行`); continue; }
                        if (g.low === g.high) {
                            // 单值指引：表中应有一条"自然年指引"行且数值相同
                            const single = mine.filter(r => /自然年指引/.test(r[2] || ''));
                            if (!single.length) { mismatches.push(`${g.company}: 表中无自然年指引行`); continue; }
                            const v = parseFloat(single[0][5]);
                            if (Math.abs(v - g.low) > 1e-6)
                                mismatches.push(`${g.company} 单值 chip=${g.low} 表=${v}`);
                            continue;
                        }
                        // 区间指引：取该公司的"指引下限/上限"（排除"上调前"）最新日期
                        const bounds = mine.filter(r => /指引(下限|上限)/.test(r[2] || '') && !/上调前/.test(r[2] || ''));
                        if (!bounds.length) { mismatches.push(`${g.company}: 表中无指引区间行`); continue; }
                        const latest = bounds.map(r => r[0]).sort().reverse()[0];
                        const sameDay = bounds.filter(r => r[0] === latest);
                        const lowRow = sameDay.find(r => /指引下限/.test(r[2]));
                        const highRow = sameDay.find(r => /指引上限/.test(r[2]));
                        if (!lowRow || !highRow) { mismatches.push(`${g.company}: ${latest} 区间不成对`); continue; }
                        const lv = parseFloat(lowRow[5]), hv = parseFloat(highRow[5]);
                        if (Math.abs(lv - g.low) > 1e-6) mismatches.push(`${g.company} 下限 chip=${g.low} 表=${lv}(${latest})`);
                        if (Math.abs(hv - g.high) > 1e-6) mismatches.push(`${g.company} 上限 chip=${g.high} 表=${hv}(${latest})`);
                    }
                    return { mismatches, chipCount: gs.length };
                }"""
            )
            # 同一张图内标注不得重复渲染（叠字）。只查橙色标注（fill=#d76b00），
            # 坐标轴刻度与末端标签数值相同属正常，不算缺陷。
            duplicate_labels = page.evaluate(
                """() => {
                    const dupes = [];
                    for (const svg of document.querySelectorAll('.chart svg')) {
                        const seen = new Set();
                        for (const t of svg.querySelectorAll('text.annot')) {
                            const key = (t.textContent || '').trim();
                            if (!key) continue;
                            if (seen.has(key)) dupes.push(key); else seen.add(key);
                        }
                    }
                    return [...new Set(dupes)];
                }"""
            )
            # 末端标签颜色必须指向它自己那条线。曾经图例关掉一条后，
            # 标签用 states 索引着色、线条用 names 索引着色，两者错位（标签指错线）。
            color_mismatch = page.evaluate(
                """() => {
                    const bad = [];
                    for (const host of document.querySelectorAll('.chart')) {
                        const svg = host.querySelector('svg');
                        const legend = document.querySelector('#' + host.id + '-legend');
                        if (!svg || !legend) continue;
                        const btns = [...legend.querySelectorAll('button')];
                        if (btns.length < 2) continue;
                        const read = () => ({
                            lines: [...svg.querySelectorAll('path')].map(p => p.getAttribute('stroke')).filter(Boolean),
                            labels: [...svg.querySelectorAll('text')]
                                .filter(t => (t.getAttribute('style') || '').includes('700'))
                                .map(t => t.getAttribute('fill')).filter(Boolean),
                        });
                        btns[0].click();
                        const after = read();
                        btns[0].click();
                        for (const col of after.labels) {
                            if (after.lines.length && !after.lines.includes(col)) {
                                bad.push(host.id + ': 标签色 ' + col + ' 不属于剩余线 ' + after.lines.join(','));
                            }
                        }
                    }
                    return [...new Set(bad)];
                }"""
            )
            checks = {
                "console_zero_errors": len(errors) == 0,
                "capex_table_filled": page.locator("#capex-body tr").count() > 0,
                "four_clock_cards": page.locator(".clock-card").count() >= 4,
                "charts_have_svg": page.locator(".chart svg").count() >= 10,
                "guidance_matches_source_table": not consistency["mismatches"],
                "no_duplicate_svg_labels": not duplicate_labels,
                "end_label_colors_match_lines": not color_mismatch,
                "executive_card_visible": page.locator("#executive-summary").count() == 1
                and len(page.locator("#executive-summary").inner_text()) > 40,
                "price_asof_visible": page.locator(".price-asof").count() == 1
                and "价格截至" in page.locator(".price-asof").inner_text(),
                "nav_has_clocks": _nav_has_clocks(page),
                "gpu_legacy_collapsed": gpu_legacy_collapsed,
                "event_toggle_hides_markers": _event_toggle_works(page),
                "event_markers_on_primary_charts": _event_markers_reach_primary_charts(page),
                "event_tooltip_on_price_chart": _event_tooltip_on_price_chart(page),
                "landscape_switches": _landscape_works(page),
                "landscape_table_click": _landscape_table_click(page),
                "landscape_stale_not_repeated": _landscape_stale_not_repeated(page),
                "landscape_market_status": _landscape_market_status_visible(page),
                "landscape_receipt_csv": _landscape_receipt_csv(page),
                "landscape_cheapest_toggle": _landscape_cheapest_toggle(page),
                "landscape_offers_rows": _landscape_offers_rows(page),
                "landscape_monthly_rows": _landscape_monthly_rows(page),
                "landscape_crosscheck_table": _landscape_crosscheck_table(page),
                "landscape_crosscheck_own_sample": _landscape_crosscheck_own_sample(page),
                "landscape_crosscheck_license": _landscape_crosscheck_license(page),
                "landscape_crosscheck_market_guard": _landscape_crosscheck_market_guard(page),
                "sandbox_redraws": _sandbox_redraws(page),
                "sandbox_correlation_symmetric": _sandbox_correlation_is_symmetric(page),
                "sandbox_respects_range": _sandbox_respects_range(page),
                "mobile_price_chart_fits": _mobile_price_chart_fits(page),
                "mobile_full_page_no_overflow": _mobile_full_page_no_overflow(page),
            }
            site_checks, site_errors = _site_pages_smoke(
                browser, f"http://127.0.0.1:{PORT}"
            )
            checks.update(site_checks)
            diagnostics = {
                "errors": errors[:5],
                "guidanceMismatches": consistency["mismatches"],
                "duplicateLabels": duplicate_labels,
                "labelColorMismatches": color_mismatch,
                "siteErrors": site_errors[:5],
            }
            browser.close()

    result = {"ok": all(checks.values()), "checks": checks, "diagnostics": diagnostics}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
