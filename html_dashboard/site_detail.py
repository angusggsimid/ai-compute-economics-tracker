"""Card and provider detail pages for the standalone static site.

The pages are generated after :func:`site_data.write_site_data` has written
``public/data``.  The HTML shell is rendered at build time from
``data/site-index.json``; the long tables and charts are filled by one small
inline script that fetches ``data/cards/<slug>.json`` or
``data/providers/<slug>.json`` with :mod:`site_shell`'s ``CC.get`` helper.

Nothing in this module hard-codes a price or a provider list.  Only slugs,
labels and source/licence URLs come from the generated index and data files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List

try:  # package import path (html_dashboard.site_detail)
    from .site_shell import page
except ImportError:  # script import path used by the test suite
    from site_shell import page  # type: ignore


# ---------------------------------------------------------------------------
# Small server-side formatters / HTML helpers
# ---------------------------------------------------------------------------

_HTTP_RE = re.compile(r"^https?://", re.IGNORECASE)


def _http_url(value: Any) -> str:
    """Return ``value`` only when it is a safe http(s) URL."""
    text = str(value or "").strip()
    return text if _HTTP_RE.match(text) else ""


def _http_link(value: Any, label: str = "来源") -> str:
    """Anchor for an http(s) URL, otherwise a muted dash."""
    href = _http_url(value)
    if not href:
        return '<span class="muted">—</span>'
    return (
        f'<a href="{_attr(href)}" target="_blank" rel="noopener">'
        f"{_text(label)}</a>"
    )


def _text(value: Any) -> str:
    from html import escape

    return escape("" if value is None else str(value))


def _attr(value: Any) -> str:
    from html import escape

    return escape("" if value is None else str(value), quote=True)


def _fmt_money(value: Any) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    digits = 3 if abs(number) < 1 else 2
    return f"${number:,.{digits}f}"


def _fmt_num(value: Any, digits: int = 0) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"{number:,.{digits}f}"


def _fmt_pct(value: Any, digits: int = 1) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "—"
    sign = "+" if number > 0 else ""
    return f"{sign}{number:.{digits}f}%"


def _badge(text: Any, tone: str = "") -> str:
    if text is None or text == "":
        return '<span class="muted">—</span>'
    class_attr = f" {_attr(tone)}" if tone else ""
    return f'<span class="badge{class_attr}">{_text(text)}</span>'


def _status_tone(value: Any) -> str:
    key = str(value or "").strip().lower()
    if key in {"live", "published", "withheld", "stopped", "no_data"}:
        return key
    if key in {"thin", "thin_market", "unconfirmed"}:
        return "thin"
    return ""


def _risk_tone(value: Any) -> str:
    key = str(value or "").strip().lower()
    return key if key in {"low", "medium", "high"} else ""


def _coverage_tone(value: Any) -> str:
    """Match the landscape page's coverage tones (ok green, none gray)."""
    key = str(value or "").strip().lower()
    if key == "ok":
        return "ok"
    if key in {"mixed", "thin", "none"}:
        return key
    if key == "sku_mismatch":
        return "high sku_mismatch"
    if key == "stale":
        return "thin"
    return "none"


def _kpi(label: str, value: str, hint: str = "", element_id: str = "") -> str:
    id_attr = f' id="{_attr(element_id)}"' if element_id else ""
    hint_html = f'<div class="hint">{hint}</div>' if hint else ""
    return (
        '<div class="kpi">'
        f'<div class="label">{_text(label)}</div>'
        f'<div class="value"{id_attr}>{value}</div>'
        f"{hint_html}</div>"
    )


def _js_json(payload: Any) -> str:
    """JSON safe to embed inside an inline ``<script>`` element."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _load_index(public_dir: Path) -> Dict[str, Any]:
    path = Path(public_dir) / "data" / "site-index.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"site-index.json not found at {path}; run write_site_data() before "
            "generating detail pages"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_provider_slice(public_dir: Path, slug: str) -> Dict[str, Any] | None:
    """Read one provider slice if it exists; pages still fetch it in the browser."""
    path = Path(public_dir) / "data" / "providers" / f"{slug}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _live_quote_stats(payload: Dict[str, Any] | None) -> Dict[str, int] | None:
    """Live external stats, matching the landscape page's definition.

    A live quote is ``status == "live"``, not a marketplace floor, and priced in
    USD.  ``live_cards`` counts distinct GPU ids, not the historical card list.
    Returns ``None`` when the provider slice is unavailable so the page can
    fall back to ``—`` instead of inventing zero live.
    """
    if payload is None:
        return None
    quotes = payload.get("quotes") or []
    live = [
        quote
        for quote in quotes
        if quote.get("status") == "live"
        and quote.get("price_scope") != "marketplace_floor"
        and quote.get("listed_currency") == "USD"
    ]
    gpu_ids = {
        str(quote.get("gpu_id"))
        for quote in live
        if quote.get("gpu_id")
    }
    return {"live_quotes": len(live), "live_cards": len(gpu_ids)}


def _index_lookups(index: Dict[str, Any]) -> Dict[str, Any]:
    cards = index.get("cards") or []
    own = (index.get("providers") or {}).get("own") or []
    external = (index.get("providers") or {}).get("external") or []
    return {
        "card_slug": {str(card.get("id")): card.get("slug") for card in cards},
        "own_slug": {str(provider.get("id")): provider.get("slug") for provider in own},
    }


# ---------------------------------------------------------------------------
# Shared browser helpers
# ---------------------------------------------------------------------------

_COMMON_JS = r"""
  var CC = window.CC;
  if (!CC) { return; }

  function price(value) {
    var number = Number(value);
    if (value === null || value === undefined || value === "" || !isFinite(number)) {
      return "—";
    }
    return CC.money(number, Math.abs(number) < 1 ? 3 : 2);
  }

  function safeUrl(value) {
    var text = String(value == null ? "" : value).trim();
    return /^https?:\/\//i.test(text) ? text : "";
  }

  function externalLink(value, label) {
    var href = safeUrl(value);
    if (!href) { return '<span class="muted">—</span>'; }
    return '<a href="' + CC.esc(href) + '" target="_blank" rel="noopener">' +
      CC.esc(label || href) + "</a>";
  }

  function badge(value, tone) {
    if (value === null || value === undefined || value === "") {
      return '<span class="muted">—</span>';
    }
    return CC.badge(value, tone || "");
  }

  function statusTone(value) {
    var key = String(value == null ? "" : value).toLowerCase();
    if (key === "live" || key === "published" || key === "withheld" ||
        key === "stopped" || key === "no_data") { return key; }
    if (key === "thin" || key === "thin_market" || key === "unconfirmed") {
      return "thin";
    }
    return "";
  }

  function statusBadge(value) { return badge(value, statusTone(value)); }

  function riskBadge(value) {
    var key = String(value == null ? "" : value).toLowerCase();
    var tone = (key === "low" || key === "medium" || key === "high") ? key : "";
    return badge(value, tone);
  }

  var COVERAGE = {
    ok: { label: "ok", tone: "ok" },
    mixed: { label: "mixed", tone: "mixed" },
    thin: { label: "thin", tone: "thin" },
    sku_mismatch: { label: "SKU mismatch", tone: "high sku_mismatch" },
    none: { label: "none", tone: "none" },
    stale: { label: "stale", tone: "thin" }
  };

  function coverageBadge(value) {
    var key = String(value == null ? "" : value).toLowerCase();
    var meta = COVERAGE[key] || { label: value || "—", tone: "none" };
    return badge(meta.label, meta.tone);
  }

  function providerCell(row, links) {
    var id = row.providerId || row.provider_id || "";
    var name = row.provider || id || "—";
    var slug = links && links[id];
    if (!slug) { return CC.esc(name); }
    return '<a href="../providers/' + CC.esc(slug) + '.html">' + CC.esc(name) + "</a>";
  }

  function factsTable(items) {
    var rows = (items || []).filter(function (item) {
      return item && item.value !== null && item.value !== undefined && item.value !== "";
    }).map(function (item) {
      return '<tr><th scope="row">' + CC.esc(item.label) + "</th><td>" +
        item.value + "</td></tr>";
    }).join("");
    if (!rows) { return CC.empty("暂无资料"); }
    return '<div class="table-wrap"><table class="data compact"><tbody>' +
      rows + "</tbody></table></div>";
  }

  function showFailure(error) {
    var message = "数据加载失败：" + (error && error.message ? error.message : "未知错误");
    document.querySelectorAll(".js-host").forEach(function (host) {
      host.innerHTML = CC.empty(message);
    });
  }
"""


# ---------------------------------------------------------------------------
# Card pages
# ---------------------------------------------------------------------------

_CARD_JS = r"""
  var buttons = document.querySelectorAll("[data-market-tab]");
  buttons.forEach(function (button) {
    button.addEventListener("click", function () {
      var id = button.getAttribute("data-market-tab");
      buttons.forEach(function (other) {
        var active = other === button;
        other.classList.toggle("active", active);
        other.setAttribute("aria-selected", active ? "true" : "false");
      });
      document.querySelectorAll("[data-market-panel]").forEach(function (panel) {
        panel.hidden = panel.getAttribute("data-market-panel") !== id;
      });
    });
  });

  function renderMarkets(markets) {
    Object.keys(markets || {}).forEach(function (id) {
      var market = markets[id] || {};
      var latest = market.latest || {};
      var series = market.series || [];
      var noData = market.status === "no_data" || !series.length;
      var chart = document.querySelector('[data-chart="' + id + '"]');
      if (chart) {
        if (noData) {
          chart.innerHTML = CC.empty("无自有报价");
        } else {
          CC.lineChart(chart, [
            {
              name: "Median", color: "#0071e3",
              points: series.map(function (point) {
                return { date: point.date, value: point.value };
              })
            },
            {
              name: "P25", color: "#00a6a6",
              points: series.map(function (point) {
                return { date: point.date, value: point.p25 };
              })
            },
            {
              name: "P75", color: "#8944ab",
              points: series.map(function (point) {
                return { date: point.date, value: point.p75 };
              })
            },
            {
              name: "Cheapest", color: "#d76b00",
              points: series.map(function (point) {
                return { date: point.date, value: point.cheapestValue };
              })
            }
          ], {
            kind: "price",
            yLabel: "USD / GPU-hour",
            ariaLabel: CARD.name + " · " + (market.label || id) + " 每日价格"
          });
        }
      }

      var offersHost = document.querySelector('[data-offers="' + id + '"]');
      if (!offersHost) { return; }
      var offers = noData ? [] : (latest.offers || []);
      offersHost.innerHTML = CC.table([
        {
          label: "Provider",
          render: function (_value, row) { return providerCell(row, CARD.own); }
        },
        {
          label: "Price", num: true,
          render: function (_value, row) { return price(row.value); }
        },
        {
          label: "Quotes", num: true,
          render: function (_value, row) { return CC.num(row.quotes, 0); }
        },
        {
          label: "Date",
          render: function () { return CC.esc(CC.date(latest.date)); }
        },
        {
          label: "Risk",
          render: function () { return riskBadge(market.risk); }
        },
        {
          label: "Source",
          render: function (_value, row) { return externalLink(row.sourceUrl, "来源"); }
        }
      ], offers, { compact: true, empty: "无自有报价" });
    });
  }

  function renderMonthly(monthly) {
    var host = document.getElementById("monthly-table");
    if (!host) { return; }
    host.innerHTML = CC.table([
      { label: "Month", key: "month" },
      { label: "Value", key: "value", num: true, title: "月度中位数", render: function (value) { return price(value); } },
      { label: "Panel", key: "panelCount", num: true, render: function (value) { return CC.num(value, 0); } },
      {
        label: "Coverage",
        render: function (_value, row) {
          if (row.coverageDays === null || row.coverageDays === undefined) {
            return "—";
          }
          var text = CC.num(row.coverageDays, 0) + "/" + CC.num(row.daysInMonth, 0) + " 天";
          if (row.coveragePct !== null && row.coveragePct !== undefined) {
            text += " · " + CC.num(row.coveragePct, 1) + "%";
          }
          return CC.esc(text);
        }
      },
      { label: "Status", key: "status", render: function (value) { return statusBadge(value); } },
      { label: "Vintage", key: "vintage", render: function (value) { return CC.esc(value || "—"); } }
    ], monthly, { compact: true, empty: "暂无月度数据" });
  }

  function renderWeekly(weeks, latest) {
    var host = document.getElementById("weekly-table");
    if (!host) { return; }
    var rows = (weeks || []).slice();
    if (!rows.length && latest) { rows = [latest]; }
    host.innerHTML = CC.table([
      { label: "ISO week", key: "isoWeek", render: function (value) { return CC.esc(value || "—"); } },
      { label: "Median", key: "median", num: true, render: function (value) { return price(value); } },
      { label: "Index", key: "index", num: true, render: function (value) { return CC.num(value, 1); } },
      { label: "Providers", key: "providerCount", num: true, render: function (value) { return CC.num(value, 0); } },
      { label: "Status", key: "status", render: function (value) { return statusBadge(value); } },
      { label: "Vintage", key: "vintage", render: function (value) { return CC.esc(value || "—"); } }
    ], rows, { compact: true, empty: "暂无周指数数据" });
  }

  function renderCrosscheck(doc) {
    var ext = doc.external || {};
    var attribution = document.getElementById("crosscheck-attribution");
    if (attribution) {
      var bits = ["<strong>GPU Economy · CC BY 4.0</strong>"];
      if (ext.attribution) { bits.push(CC.esc(ext.attribution)); }
      bits.push(externalLink(ext.prices_source_url || ext.source_url, "价格源"));
      bits.push(externalLink(ext.license_url, "许可"));
      if (ext.data_updated_at) {
        bits.push("抓取 " + CC.esc(CC.date(ext.data_updated_at)));
      }
      attribution.innerHTML = bits.join(" · ");
    }

    var host = document.getElementById("crosscheck-table");
    if (!host) { return; }
    host.innerHTML = CC.table([
      { label: "Market", key: "market", render: function (value) { return CC.esc(value || "—"); } },
      { label: "Own median", key: "own_median", num: true, render: function (value) { return price(value); } },
      { label: "Ext median", key: "ext_median", num: true, render: function (value) { return price(value); } },
      { label: "Diff", key: "diff_pct", num: true, render: function (value) { return CC.esc(CC.pct(value, 1)); } },
      { label: "Coverage", key: "coverage", render: function (value) { return coverageBadge(value); } },
      { label: "Own N", key: "own_providers", num: true, render: function (value) { return CC.num(value, 0); } },
      { label: "Ext N", key: "ext_providers", num: true, render: function (value) { return CC.num(value, 0); } },
      { label: "Note", key: "note", render: function (value) { return CC.esc(value || "—"); } }
    ], doc.crosscheck || [], { empty: "该卡暂无外部对照" });
  }

  CC.get(CARD.fetch).then(function (doc) {
    var card = doc.card || {};
    renderMarkets(card.markets || {});
    renderMonthly(card.monthly || []);
    renderWeekly(doc.weeks || [], card.weeklyIndex || null);
    renderCrosscheck(doc);
  }).catch(showFailure);
"""


def _card_body(card: Dict[str, Any], index: Dict[str, Any]) -> str:
    slug = str(card.get("slug") or "")
    name = card.get("name") or card.get("id") or slug
    family = card.get("family") or "—"
    vram = card.get("vram_gb")
    vram_text = f"{_fmt_num(vram, 0)} GB" if vram is not None else "—"
    as_of = card.get("as_of") or index.get("as_of") or "—"
    status = card.get("status")

    markets = card.get("markets") or {}
    market_meta = {
        str(item.get("id")): item for item in index.get("markets") or []
    }
    market_ids = [
        str(item.get("id"))
        for item in index.get("markets") or []
        if str(item.get("id")) in markets
    ]
    for market_id in markets:
        if market_id not in market_ids:
            market_ids.append(market_id)
    if not market_ids:
        market_ids = ["on_demand", "spot", "reserved", "community", "marketplace", "serverless"]
    default_market = "on_demand" if "on_demand" in market_ids else market_ids[0]

    weekly = card.get("weekly_index") or {}
    weekly_index = weekly.get("index")
    weekly_hint = weekly.get("isoWeek") or "未发布"
    card_no_data = (
        card.get("status") == "no_data"
        or int(card.get("provider_count") or 0) == 0
    )
    median_value = _text("无自有报价") if card_no_data else _fmt_money(card.get("median"))
    range_value = (
        "—"
        if card_no_data
        else f"{_fmt_money(card.get('p25'))} – {_fmt_money(card.get('p75'))}"
    )
    cheapest_value = "—" if card_no_data else _fmt_money(card.get("cheapest"))
    change_value = "—" if card_no_data else _fmt_pct(card.get("change_7d_pct"))
    index_value = (
        "—"
        if card_no_data or weekly_index is None
        else _fmt_num(weekly_index, 1)
    )

    kpis = "".join(
        [
            _kpi("Median", median_value, "自有面板挂牌价"),
            _kpi("P25 – P75", range_value, "四分位区间"),
            _kpi(
                "Cheapest",
                cheapest_value,
                _text(card.get("cheapest_provider") or "—"),
            ),
            _kpi("Providers", _fmt_num(card.get("provider_count")), "覆盖 provider 数"),
            _kpi("7d", change_value, "中位数周变化"),
            _kpi("Weekly index", index_value, _text(weekly_hint)),
        ]
    )

    tabs = []
    panels = []
    for market_id in market_ids:
        summary = markets.get(market_id) or {}
        meta = market_meta.get(market_id) or {}
        label = summary.get("label") or meta.get("label") or market_id
        short = meta.get("short") or label
        risk = summary.get("risk") or meta.get("risk")
        scope = summary.get("price_scope") or meta.get("scope") or "—"
        note = meta.get("note") or ""
        median = summary.get("median")
        market_as_of = summary.get("date") or as_of
        thin = summary.get("thin")
        provider_count = int(summary.get("provider_count") or 0)
        no_data = summary.get("status") == "no_data" or provider_count == 0
        hidden = "" if market_id == default_market else " hidden"
        selected = "true" if market_id == default_market else "false"
        active_class = " active" if market_id == default_market else ""

        tabs.append(
            f'<button type="button" role="tab" id="tab-{_attr(market_id)}" '
            f'data-market-tab="{_attr(market_id)}" '
            f'aria-controls="market-panel-{_attr(market_id)}" '
            f'aria-selected="{selected}" class="tab{active_class}">'
            f"{_text(short)}</button>"
        )

        if no_data:
            market_state = '<span class="badge none">无自有报价</span>'
            median_html = '<span class="muted">无自有报价</span>'
        else:
            market_state = _badge(risk, _risk_tone(risk))
            if thin:
                market_state += ' · <span class="badge thin">样本偏薄</span>'
            median_html = (
                f'<strong>{_fmt_money(median)}</strong> '
                '<span class="muted small">median</span>'
            )
        note_html = f'<p class="panel-note">{_text(note)}</p>' if note else ""
        panels.append(
            f'<div class="panel market-panel" id="market-panel-{_attr(market_id)}" '
            f'data-market-panel="{_attr(market_id)}" role="tabpanel" '
            f'aria-labelledby="tab-{_attr(market_id)}"{hidden}>'
            '<div class="panel-head"><div>'
            f"<h3>{_text(label)}</h3>"
            f"<p>{market_state} · scope {_text(scope)} · "
            f"as of {_text(market_as_of)}</p>"
            "</div>"
            f'<div class="num">{median_html}</div>'
            "</div>"
            f"{note_html}"
            f'<div class="js-host" data-chart="{_attr(market_id)}">'
            '<div class="empty">加载中…</div></div>'
            '<p class="kicker" style="margin-top:18px">Offers</p>'
            f'<div class="js-host" data-offers="{_attr(market_id)}">'
            '<div class="empty">加载中…</div></div>'
            "</div>"
        )

    external = index.get("external") or {}
    source_link = _http_link(external.get("source_url"), "GPU Economy")
    license_link = _http_link(external.get("license_url"), external.get("license") or "CC BY 4.0")
    methodology = card.get("methodology_version") or index.get("methodology_version") or "—"

    return f"""
<section class="hero compact">
  <p class="kicker">GPU card · {_text(family)}</p>
  <h1>{_text(name)}</h1>
  <p class="lede">{_text(vram_text)} · {_text(family)} · as of {_text(as_of)} · {_badge(status, _status_tone(status))}</p>
  <div class="row-actions">
    <a class="btn" href="../landscape.html">← Landscape</a>
    <a class="btn" href="../providers.html">Providers</a>
    <a class="btn" href="../compare.html">Compare</a>
  </div>
</section>

<section class="section">
  <div class="section-head">
    <h2>摘要</h2>
    <span class="muted small">as of {_text(as_of)} · 公开挂牌价，非成交价</span>
  </div>
  <div class="kpi-grid">{kpis}</div>
  <p class="panel-note">中位数来自自有 provider 面板；外部对照只作参考，不改写自有中位数与指数。</p>
</section>

<section class="section" aria-labelledby="market-title">
  <div class="section-head">
    <h2 id="market-title">市场对比</h2>
    <span class="muted small">6 个市场分开统计 · 默认 on-demand</span>
  </div>
  <div class="segmented" id="market-tabs" role="tablist" aria-label="市场" style="flex-wrap:wrap">
    {''.join(tabs)}
  </div>
  <div class="stack" id="market-panels" style="margin-top:16px">
    {''.join(panels)}
  </div>
</section>

<section class="section">
  <div class="section-head">
    <h2>月度中位数</h2>
    <span class="muted small">固定 provider panel · 未达覆盖门槛的月份 withheld，不补值</span>
  </div>
  <div class="js-host" id="monthly-table"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head">
    <h2>Weekly index</h2>
    <span class="muted small">链式 base-100 · 仅保留发布周</span>
  </div>
  <div class="js-host" id="weekly-table"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head">
    <h2>外部对照</h2>
    <span class="muted small">自有 vs GPU Economy · 不合并口径</span>
  </div>
  <p class="source" id="crosscheck-attribution">加载中…</p>
  <div class="js-host" id="crosscheck-table"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head">
    <h2>数据与来源</h2>
    <span class="muted small">methodology {_text(methodology)}</span>
  </div>
  <div class="row-actions">
    <a class="btn" href="../data/cards/{_attr(slug)}.json">卡片 JSON</a>
    <a class="btn" href="../data/price-index/{_attr(slug)}.json">周指数 JSON</a>
    <a class="btn" href="../data/receipts/index.json">Receipts</a>
    <a class="btn" href="../data/site-index.json">Site index</a>
  </div>
  <p class="source">自有面板 as of {_text(as_of)} · {source_link} · {license_link} · 外部参考层不改写自有中位数。</p>
</section>
"""


def _card_script(card: Dict[str, Any], own_slugs: Dict[str, Any]) -> str:
    payload = {
        "slug": card.get("slug"),
        "name": card.get("name") or card.get("id"),
        "fetch": f"cards/{card.get('slug')}.json",
        "own": own_slugs,
    }
    return (
        "(function () {\n"
        f"  var CARD = {_js_json(payload)};\n"
        f"{_COMMON_JS}{_CARD_JS}\n"
        "})();"
    )


def write_card_pages(public_dir: Path) -> List[str]:
    """Write ``public/gpu/<slug>.html`` for every card in ``site-index.json``.

    Returns paths relative to ``public_dir`` (``gpu/h100.html``, ...).
    """
    public_dir = Path(public_dir)
    index = _load_index(public_dir)
    lookups = _index_lookups(index)
    out_dir = public_dir / "gpu"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for card in index.get("cards") or []:
        slug = str(card.get("slug") or "")
        if not slug:
            raise ValueError(f"card without slug in site-index: {card!r}")
        title = f"{card.get('name') or card.get('id')} · GPU 价格与供给"
        description = (
            f"{card.get('name') or card.get('id')} 的 on-demand、spot、reserved、"
            "community、marketplace 与 serverless 挂牌价、月度中位数、周指数和外部对照。"
        )
        html = page(
            title,
            description,
            "..",
            "landscape",
            _card_body(card, index),
            _card_script(card, lookups["own_slug"]),
        )
        (out_dir / f"{slug}.html").write_text(html, encoding="utf-8")
        written.append(f"gpu/{slug}.html")
    return written


# ---------------------------------------------------------------------------
# Provider pages
# ---------------------------------------------------------------------------

_PROVIDER_JS = r"""
  function renderOwn(doc) {
    var quotes = doc.quotes || [];
    var host = document.getElementById("quotes-host");
    if (host) {
      host.innerHTML = CC.table([
        {
          label: "Card",
          render: function (_value, row) {
            var slug = PROVIDER.cards[row.card_id];
            var label = row.card || row.card_id || "—";
            if (!slug) { return CC.esc(label); }
            return '<a href="../gpu/' + CC.esc(slug) + '.html">' + CC.esc(label) + "</a>";
          }
        },
        {
          label: "Market",
          render: function (_value, row) { return CC.esc(row.market_label || row.market || "—"); }
        },
        {
          label: "Price", num: true,
          render: function (_value, row) { return price(row.usd_per_gpu_hour); }
        },
        {
          label: "Risk",
          render: function (_value, row) { return riskBadge(row.risk); }
        },
        {
          label: "Date",
          render: function (_value, row) { return CC.esc(CC.date(row.date)); }
        },
        {
          label: "Source",
          render: function (_value, row) { return externalLink(row.source_url, "来源"); }
        }
      ], quotes, { empty: "该 provider 暂无公开报价" });
    }
    var count = document.getElementById("quote-count");
    if (count) { count.textContent = CC.num(quotes.length, 0) + " 条"; }
  }

  function feeValue(row) {
    if (row.value !== null && row.value !== undefined && row.value !== "") {
      return CC.esc(row.value);
    }
    if (row.number === null || row.number === undefined) { return "—"; }
    var number = Number(row.number);
    var digits = isFinite(number) && number % 1 !== 0 ? 2 : 0;
    return CC.esc(CC.num(number, digits) + (row.unit ? " " + row.unit : ""));
  }

  function isEffectiveLiveQuote(quote) {
    return !!quote &&
      quote.status === "live" &&
      quote.price_scope !== "marketplace_floor" &&
      quote.listed_currency === "USD";
  }

  function liveQuoteStats(quotes) {
    var live = (quotes || []).filter(isEffectiveLiveQuote);
    var ids = {};
    live.forEach(function (quote) {
      if (quote.gpu_id) { ids[quote.gpu_id] = true; }
    });
    return { live_quotes: live.length, live_cards: Object.keys(ids).length };
  }

  function renderExternal(doc) {
    var provider = doc.provider || {};
    var ext = doc.external || {};
    var fees = Array.isArray(provider.fees) ? provider.fees : [];
    var quotes = doc.quotes || [];
    var live = liveQuoteStats(quotes);

    var liveQuotes = document.getElementById("ext-live-quotes");
    if (liveQuotes) { liveQuotes.textContent = CC.num(live.live_quotes, 0); }
    var liveCards = document.getElementById("ext-live-cards");
    if (liveCards) { liveCards.textContent = CC.num(live.live_cards, 0); }

    var models = document.getElementById("ext-models");
    if (models) { models.textContent = CC.num(provider.models_tracked, 0); }
    var feesKpi = document.getElementById("ext-fees");
    if (feesKpi) { feesKpi.textContent = fees.length ? "published" : "not published"; }

    var profile = document.getElementById("profile-host");
    if (profile) {
      profile.innerHTML = factsTable([
        { label: "Type", value: CC.esc(provider.type || "—") },
        { label: "Source kind", value: CC.esc(provider.source_kind || "—") },
        { label: "Website", value: externalLink(provider.website, "website") },
        { label: "Pricing page", value: externalLink(provider.pricing_page, "pricing") },
        {
          label: "Scraped",
          value: badge(provider.scraped ? "scraped" : "not scraped",
            provider.scraped ? "live" : "")
        },
        { label: "Live quotes", value: CC.num(live.live_quotes, 0) },
        { label: "Live cards", value: CC.num(live.live_cards, 0) },
        {
          label: "Raw records",
          value: CC.num(provider.current_quotes, 0) +
            ' <span class="muted">（含 stopped / 非 USD）</span>'
        },
        {
          label: "Historical cards",
          value: CC.num((provider.cards || []).length, 0) +
            ' <span class="muted">（含 stopped 覆盖）</span>'
        },
        { label: "Models tracked", value: CC.num(provider.models_tracked, 0) },
        {
          label: "Regions",
          value: CC.esc(Array.isArray(provider.regions) ? provider.regions.join(" · ") : (provider.regions || "—"))
        },
        { label: "Summary", value: CC.esc(provider.summary || "—") },
        { label: "Notes", value: CC.esc(provider.notes || "—") },
        { label: "GPU Economy page", value: externalLink(provider.page, "provider page") }
      ]);
    }

    var feesHost = document.getElementById("fees-host");
    if (feesHost) {
      if (!fees.length) {
        feesHost.innerHTML = CC.empty("not published") +
          '<p class="panel-note">GPU Economy 未收录该 provider 的费用结构；这不等于零费用。</p>';
      } else {
        feesHost.innerHTML = CC.table([
          { label: "Field", key: "field", render: function (value) { return CC.esc(value || "—"); } },
          { label: "What", key: "what", render: function (value) { return CC.esc(value || "—"); } },
          { label: "Value", render: function (_value, row) { return feeValue(row); } },
          { label: "Confidence", key: "confidence", render: function (value) { return CC.esc(value || "—"); } },
          { label: "Source", render: function (_value, row) { return externalLink(row.source_url, "来源"); } }
        ], fees, { compact: true, empty: "not published" });
      }
    }

    var quotesHost = document.getElementById("quotes-host");
    if (quotesHost) {
      quotesHost.innerHTML = CC.table([
        { label: "GPU", render: function (_value, row) { return CC.esc(row.gpu || row.gpu_id || "—"); } },
        { label: "Market", render: function (_value, row) { return CC.esc(row.market || "—"); } },
        { label: "Price", num: true, render: function (_value, row) { return price(row.usd_per_gpu_hour); } },
        { label: "Scope", render: function (_value, row) { return CC.esc(row.price_scope || "—"); } },
        { label: "Region", render: function (_value, row) { return CC.esc(row.region || "—"); } },
        { label: "Source", render: function (_value, row) { return externalLink(row.source_url, "来源"); } },
        { label: "Scraped", render: function (_value, row) { return CC.esc(CC.date(row.scraped_at)); } },
        { label: "Status", render: function (_value, row) { return statusBadge(row.status); } }
      ], quotes, { compact: true, empty: "该 provider 暂无报价记录" });
    }

    var attribution = document.getElementById("attribution-host");
    if (attribution) {
      var bits = ["<strong>GPU Economy · CC BY 4.0</strong>"];
      if (ext.attribution) { bits.push(CC.esc(ext.attribution)); }
      bits.push(externalLink(ext.source_url, "数据源"));
      bits.push(externalLink(ext.license_url, "许可"));
      if (ext.data_updated_at) {
        bits.push("数据更新 " + CC.esc(CC.date(ext.data_updated_at)));
      }
      if (ext.retrieved_at) {
        bits.push("抓取 " + CC.esc(CC.date(ext.retrieved_at)));
      }
      attribution.innerHTML = '<p class="source">' + bits.join(" · ") + "</p>";
    }
  }

  CC.get(PROVIDER.fetch).then(function (doc) {
    if (PROVIDER.layer === "own") {
      renderOwn(doc);
    } else {
      renderExternal(doc);
    }
  }).catch(showFailure);
"""


def _card_chips(card_ids: Iterable[Any], card_slugs: Dict[str, Any]) -> str:
    chips = []
    for card_id in card_ids or []:
        label = str(card_id)
        slug = card_slugs.get(label)
        if slug:
            chips.append(f'<a class="btn" href="../gpu/{_attr(slug)}.html">{_text(label)}</a>')
        else:
            chips.append(f'<span class="btn">{_text(label)}</span>')
    return "".join(chips)


def _market_chips(market_ids: Iterable[Any], index: Dict[str, Any]) -> str:
    labels = {
        str(item.get("id")): item.get("short") or item.get("label")
        for item in index.get("markets") or []
    }
    return "".join(
        f'<span class="badge">{_text(labels.get(str(market_id)) or market_id)}</span>'
        for market_id in market_ids or []
    )


def _external_attribution(index: Dict[str, Any]) -> str:
    external = index.get("external") or {}
    source_url = _http_url(external.get("source_url")) or "https://gpueconomy.com/data"
    license_url = (
        _http_url(external.get("license_url"))
        or "https://creativecommons.org/licenses/by/4.0/"
    )
    license_name = external.get("license") or "CC BY 4.0"
    return (
        '<p class="source"><strong>GPU Economy · '
        f"{_text(license_name)}</strong> · "
        f'<a href="{_attr(source_url)}" target="_blank" rel="noopener">数据源</a> · '
        f'<a href="{_attr(license_url)}" target="_blank" rel="noopener">许可</a> · '
        "外部参考层，仅作对照，不混入自有中位数。</p>"
    )


def _own_body(provider: Dict[str, Any], index: Dict[str, Any]) -> str:
    name = provider.get("name") or provider.get("id")
    cards = provider.get("cards") or []
    markets = provider.get("markets") or []
    as_of = index.get("as_of") or "—"
    cheapest = provider.get("cheapest") or {}
    cheapest_value = _fmt_money(cheapest.get("usd_per_gpu_hour"))
    cheapest_source = _http_url(cheapest.get("source_url"))
    if cheapest_source:
        cheapest_value = _http_link(cheapest_source, cheapest_value)
    cheapest_hint = " · ".join(
        part
        for part in [cheapest.get("card"), cheapest.get("market")]
        if part
    ) or "—"

    kpis = "".join(
        [
            _kpi("Quotes", _fmt_num(provider.get("quotes")), "条公开挂牌报价"),
            _kpi("Cards", _fmt_num(len(cards)), "覆盖卡数"),
            _kpi("Markets", _fmt_num(len(markets)), "覆盖市场数"),
            _kpi("Cheapest", cheapest_value, _text(cheapest_hint)),
        ]
    )

    return f"""
<section class="hero compact">
  <p class="kicker">自有供给 · Own panel</p>
  <h1>{_text(name)}</h1>
  <p class="lede">{_fmt_num(provider.get('quotes'))} 条挂牌报价 · {len(cards)} 张卡 · {len(markets)} 个市场 · as of {_text(as_of)}</p>
  <div class="row-actions">
    <a class="btn" href="../providers.html">← Providers</a>
    <a class="btn" href="../landscape.html">Landscape</a>
    {_card_chips(cards, _index_lookups(index)["card_slug"])}
  </div>
</section>

<section class="section">
  <div class="section-head">
    <h2>摘要</h2>
    <span class="muted small">as of {_text(as_of)} · 公开挂牌价，非成交价</span>
  </div>
  <div class="kpi-grid">{kpis}</div>
  <p class="panel-note">自有面板报价，按 card × market 汇总；报价可能包含多个配置。</p>
  <div class="row-actions">{_market_chips(markets, index)}</div>
  <p class="source">自有面板 · as of {_text(as_of)} · 公开挂牌价，非成交价。</p>
</section>

<section class="section">
  <div class="section-head">
    <h2>报价明细</h2>
    <span class="muted small" id="quote-count">加载中…</span>
  </div>
  <div class="js-host" id="quotes-host"><div class="empty">加载中…</div></div>
</section>
"""


def _ext_body(
    provider: Dict[str, Any],
    index: Dict[str, Any],
    live: Dict[str, int] | None = None,
) -> str:
    name = provider.get("name") or provider.get("id")
    cards = provider.get("cards") or []
    website = _http_url(provider.get("website"))
    pricing = _http_url(provider.get("pricing_page"))
    links = []
    if website:
        links.append(
            f'<a class="btn" href="{_attr(website)}" target="_blank" rel="noopener">Website</a>'
        )
    if pricing:
        links.append(
            f'<a class="btn" href="{_attr(pricing)}" target="_blank" rel="noopener">Pricing page</a>'
        )
    links.append('<a class="btn" href="../providers.html">← Providers</a>')

    scraped = provider.get("scraped")
    raw_quotes = int(provider.get("current_quotes") or 0)
    live_quotes = live.get("live_quotes") if live else None
    live_cards = live.get("live_cards") if live else None
    live_quotes_text = _fmt_num(live_quotes) if live_quotes is not None else "—"
    live_cards_text = _fmt_num(live_cards) if live_cards is not None else "—"
    raw_text = _fmt_num(raw_quotes)
    kpis = "".join(
        [
            _kpi("Type", _text(provider.get("type") or "—")),
            _kpi("Source kind", _text(provider.get("source_kind") or "—")),
            _kpi(
                "Live quotes",
                live_quotes_text,
                f"raw {raw_text} 条记录（含 stopped / 非 USD）",
                "ext-live-quotes",
            ),
            _kpi(
                "Live cards",
                live_cards_text,
                f"不同 GPU id 数；历史覆盖 {_fmt_num(len(cards))} 张关键卡（含 stopped）",
                "ext-live-cards",
            ),
            _kpi("Raw records", raw_text, "site-index current_quotes（含 stopped）"),
            _kpi("Scraped", _badge("scraped" if scraped else "not scraped", "live" if scraped else "")),
            _kpi("Models tracked", "—", "加载后更新", "ext-models"),
            _kpi("Fees", "—", "not published 表示未收录", "ext-fees"),
        ]
    )

    return f"""
<section class="hero compact">
  <p class="kicker">外部参考 · GPU Economy</p>
  <h1>{_text(name)}</h1>
  <p class="lede">{_text(provider.get('type') or '—')} · {_text(provider.get('source_kind') or '—')} · {live_quotes_text} live · Live cards {live_cards_text} · raw {raw_text} 条记录（含 stopped） · scraped {_text('yes' if scraped else 'no')}</p>
  <div class="row-actions">{''.join(links)}</div>
  {_external_attribution(index)}
</section>

<section class="section">
  <div class="section-head">
    <h2>概览</h2>
    <span class="muted small">外部层 · 不改写自有中位数</span>
  </div>
  <div class="kpi-grid">{kpis}</div>
  <p class="panel-note"><strong>Live quotes</strong> / <strong>Live cards</strong> 只统计 status=live、非 marketplace_floor、USD 的报价；raw 是 site-index 的 current_quotes 原始记录数，含 stopped。</p>
</section>

<section class="section">
  <div class="section-head"><h2>Provider profile</h2></div>
  <div class="js-host" id="profile-host"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head">
    <h2>Fees</h2>
    <span class="muted small">未收录时显示 not published</span>
  </div>
  <div class="js-host" id="fees-host"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head">
    <h2>报价明细</h2>
    <span class="muted small">含 stopped / 非 USD 原始记录</span>
  </div>
  <p class="panel-note">下表保留全部原始记录；当前可比较的 live 数见上方的 Live quotes / Live cards。</p>
  <div class="js-host" id="quotes-host"><div class="empty">加载中…</div></div>
</section>

<section class="section">
  <div class="section-head"><h2>来源与许可</h2></div>
  <div class="js-host" id="attribution-host">
    <p class="source"><strong>GPU Economy · CC BY 4.0</strong> · 外部参考层，仅作对照。</p>
  </div>
  {_external_attribution(index)}
</section>
"""


def _provider_body(
    provider: Dict[str, Any],
    layer: str,
    index: Dict[str, Any],
    live: Dict[str, int] | None = None,
) -> str:
    if layer == "own":
        return _own_body(provider, index)
    return _ext_body(provider, index, live)


def _provider_script(provider: Dict[str, Any], layer: str, index: Dict[str, Any]) -> str:
    lookups = _index_lookups(index)
    payload = {
        "slug": provider.get("slug"),
        "name": provider.get("name") or provider.get("id"),
        "fetch": f"providers/{provider.get('slug')}.json",
        "layer": layer,
        "cards": lookups["card_slug"],
    }
    return (
        "(function () {\n"
        f"  var PROVIDER = {_js_json(payload)};\n"
        f"{_COMMON_JS}{_PROVIDER_JS}\n"
        "})();"
    )


def write_provider_pages(public_dir: Path) -> List[str]:
    """Write one page per own provider and per external provider with quotes.

    Returns paths relative to ``public_dir`` (``providers/own-runpod.html``,
    ``providers/ext-runpod.html``, ...).  The slug list comes from
    ``site-index.json``; no provider pages are invented for providers without
    current quotes.
    """
    public_dir = Path(public_dir)
    index = _load_index(public_dir)
    providers = index.get("providers") or {}
    out_dir = public_dir / "providers"
    out_dir.mkdir(parents=True, exist_ok=True)

    written: List[str] = []
    for layer, key in (("own", "own"), ("gpueconomy", "external")):
        for provider in providers.get(key) or []:
            slug = str(provider.get("slug") or "")
            if not slug:
                raise ValueError(f"provider without slug in site-index: {provider!r}")
            name = provider.get("name") or provider.get("id")
            if layer == "own":
                title = f"{name} · 自有 provider 报价"
                description = f"{name} 的自有面板挂牌报价、覆盖卡与市场。"
                live = None
            else:
                title = f"{name} · GPU Economy 外部 provider"
                description = f"{name} 的 GPU Economy 外部报价、费用与来源。GPU Economy · CC BY 4.0。"
                live = _live_quote_stats(_load_provider_slice(public_dir, slug))
            html = page(
                title,
                description,
                "..",
                "providers",
                _provider_body(provider, layer, index, live),
                _provider_script(provider, layer, index),
            )
            (out_dir / f"{slug}.html").write_text(html, encoding="utf-8")
            written.append(f"providers/{slug}.html")
    return written
