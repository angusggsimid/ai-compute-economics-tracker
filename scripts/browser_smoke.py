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
        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            page.on("console", lambda msg: errors.append(f"console: {msg.text}") if msg.type == "error" else None)
            page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
            page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            page.wait_for_timeout(500)
            checks = {
                "console_zero_errors": len(errors) == 0,
                "capex_table_filled": page.locator("#capex-body tr").count() > 0,
                "four_clock_cards": page.locator(".clock-card").count() >= 4,
                "charts_have_svg": page.locator(".chart svg").count() >= 10,
            }
            browser.close()

    result = {"ok": all(checks.values()), "checks": checks, "errors": errors[:5]}
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
