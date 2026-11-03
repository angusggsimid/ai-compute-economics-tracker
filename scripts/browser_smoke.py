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
                "sandbox_redraws": _sandbox_redraws(page),
                "sandbox_correlation_symmetric": _sandbox_correlation_is_symmetric(page),
                "sandbox_respects_range": _sandbox_respects_range(page),
                "mobile_price_chart_fits": _mobile_price_chart_fits(page),
            }
            diagnostics = {
                "errors": errors[:5],
                "guidanceMismatches": consistency["mismatches"],
                "duplicateLabels": duplicate_labels,
                "labelColorMismatches": color_mismatch,
            }
            browser.close()

    result = {"ok": all(checks.values()), "checks": checks, "diagnostics": diagnostics}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
