#!/usr/bin/env python3
"""Browser-level publish gate: catch runtime JS errors that pytest cannot see.

起本地静态服务，用无头 Chromium 加载正式构建产物，断言：
console 零错误、CAPEX 表格已填充、四时钟卡片齐全、核心图表 SVG 数量达标。
任何一项失败即退出非零，阻止发布（2026-08-23 CAPEX 消失事故的永久防线）。
"""

from __future__ import annotations

import json
import socketserver
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = 8931


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
