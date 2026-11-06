"""Landscape and provider index pages for the standalone static site.

Both pages are thin, data-driven views over the committed static slices:

* ``landscape.html`` joins ``site-index.json`` (card/market summaries) with
  ``crosscheck.json`` (66 own-vs-external rows) in the browser.
* ``providers.html`` merges the own and GPU Economy provider summaries from
  ``site-index.json`` and computes the external cheapest live quote from
  ``external/prices.json``.

Hero numbers and filter options are rendered at build time from the same
files, so the pages are useful before JavaScript finishes loading.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

try:  # package import path (html_dashboard.site_landscape)
    from .site_shell import page
except ImportError:  # script import path used by the test suite
    from site_shell import page  # type: ignore


_COVERAGE_ORDER = ("ok", "mixed", "thin", "sku_mismatch", "none")
_COVERAGE_LABELS = {
    "ok": "ok（覆盖充足）",
    "mixed": "mixed（SKU 混合）",
    "thin": "thin（覆盖偏薄）",
    "sku_mismatch": "sku_mismatch（型号不一致）",
    "none": "none（无外部对照）",
    "stale": "stale（外部数据较旧）",
}


# ---------------------------------------------------------------------------
# Small helpers


def _load(public_dir: Path, relative: str) -> Dict[str, Any]:
    path = Path(public_dir) / relative
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; write the site data before generating pages"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value))


def _attr(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _number(value: Any) -> str:
    if isinstance(value, bool):
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _date(value: Any) -> str:
    text = str(value or "").strip()
    return text[:10] if text else "—"


def _options(items: Iterable[Tuple[str, str]], all_label: str = "全部") -> str:
    output = [f'<option value="">{escape(all_label)}</option>']
    for value, label in items:
        output.append(
            f'<option value="{_attr(value)}">{escape(str(label))}</option>'
        )
    return "".join(output)


def _card_label(card: Dict[str, Any]) -> str:
    card_id = str(card.get("id") or "")
    name = str(card.get("name") or card_id)
    if not card_id or name.startswith(card_id):
        return name or card_id
    return f"{card_id} · {name}"


def _external_meta(index: Dict[str, Any]) -> Dict[str, str]:
    external = index.get("external") or {}
    return {
        "source": str(external.get("source") or "gpueconomy"),
        "source_url": str(external.get("source_url") or "https://gpueconomy.com/data"),
        "license": str(external.get("license") or "CC BY 4.0"),
        "license_url": str(
            external.get("license_url")
            or "https://creativecommons.org/licenses/by/4.0/"
        ),
        "attribution": str(external.get("attribution") or "GPU Economy"),
        "data_date": _date(external.get("data_updated_at")),
    }


def _source_note(index: Dict[str, Any]) -> str:
    meta = _external_meta(index)
    return (
        '<p class="source">外部参考层：'
        f'<a href="{_attr(meta["source_url"])}" target="_blank" rel="noopener">'
        f'{escape(meta["attribution"])}</a> · '
        f'<a href="{_attr(meta["license_url"])}" target="_blank" rel="noopener">'
        f'{escape(meta["license"])}</a> · 外部数据 {escape(meta["data_date"])} · '
        "外部数字只作覆盖参考，不进入自有中位数、P25/P75 或周指数。</p>"
    )


# ---------------------------------------------------------------------------
# Landscape page


_LANDSCAPE_SCRIPT = r"""
(function () {
  "use strict";
  var tableHost = document.getElementById("landscape-table");
  var countEl = document.getElementById("landscape-count");
  var filtersRoot = document.getElementById("landscape-filters");
  if (!tableHost) { return; }

  var COVERAGE = {
    ok: { label: "ok", tone: "ok" },
    mixed: { label: "mixed", tone: "mixed" },
    thin: { label: "thin", tone: "thin" },
    sku_mismatch: { label: "SKU mismatch", tone: "high sku_mismatch" },
    none: { label: "none", tone: "none" },
    stale: { label: "stale", tone: "thin" }
  };

  var HEADERS = [
    { label: "GPU", key: "card_name", render: function (_value, row) {
        return CC.link(row.card_name, "gpu/" + row.card_slug + ".html");
      } },
    { label: "Market", key: "market_label", render: function (_value, row) {
        var hint = row.market;
        if (row.risk) { hint += " · risk " + row.risk; }
        return "<strong>" + CC.esc(row.market_label) + "</strong>" +
          '<br><span class="small muted">' + CC.esc(hint) + "</span>";
      } },
    { label: "Own median", key: "own_median", num: true, render: function (value) {
        return money(value);
      } },
    { label: "P25–P75", key: "p25", num: true, render: function (_value, row) {
        if (row.p25 == null || row.p75 == null) { return '<span class="muted">—</span>'; }
        return money(row.p25) + "–" + money(row.p75);
      } },
    { label: "Cheapest", key: "cheapest", num: true, title: "自有面板最低挂牌价；不是成交价", render: function (value, row) {
        if (value == null || !isFinite(Number(value))) { return '<span class="muted">—</span>'; }
        var html = money(value);
        if (row.cheapest_provider) {
          html += '<br><span class="small muted">' + CC.esc(row.cheapest_provider) + "</span>";
        }
        return html;
      } },
    { label: "Own N", key: "own_n", num: true, render: function (value) {
        return CC.num(value);
      } },
    { label: "7d", key: "change_7d", num: true, render: function (value) {
        return value == null ? '<span class="muted">—</span>' : CC.pct(value);
      } },
    { label: "Weekly idx (on-demand)", key: "weekly_index", num: true, title: "卡级 on-demand 周指数（起点=100）；非 on-demand 或 no_data 行显示 —", render: function (value, row) {
        if (row.market !== "on_demand" || row.status === "no_data" || row.own_n === 0 || value == null) {
          return '<span class="muted">—</span>';
        }
        var html = CC.num(value, 1);
        if (row.weekly_week) {
          html += '<br><span class="small muted">' + CC.esc(row.weekly_week) + "</span>";
        }
        return html;
      } },
    { label: "Ext median", key: "ext_median", num: true, render: function (value, row) {
        var html = value == null ? '<span class="muted">—</span>' : money(value);
        var hints = [];
        if (row.ext_n) { hints.push("n=" + CC.num(row.ext_n)); }
        if (row.diff_pct != null) { hints.push("Δ " + CC.pct(row.diff_pct)); }
        if (hints.length) {
          html += '<br><span class="small muted">' + CC.esc(hints.join(" · ")) + "</span>";
        }
        return html;
      } },
    { label: "Coverage", key: "coverage", render: function (value, row) {
        var meta = COVERAGE[value] || { label: value || "—", tone: "none" };
        if ((row.own_n === 0 || row.status === "no_data") && meta.tone === "thin") {
          return CC.badge(value === "thin" ? "thin（仅外部）" : meta.label, "none");
        }
        return CC.badge(meta.label, meta.tone);
      } },
    { label: "状态", key: "status", render: function (_value, row) {
        var parts = [];
        if (row.own_n === 0) {
          parts.push(CC.badge("无自有报价", "none"));
        } else if (row.status === "no_data") {
          parts.push(CC.badge("无可用报价", "none"));
        } else if (row.own_thin) {
          parts.push(CC.badge("样本偏薄", "thin"));
        }
        if (row.coverage === "none") {
          parts.push(CC.badge("无外部对照", "none"));
        } else if (row.comparable) {
          parts.push(CC.badge("可算差值", "ok"));
        } else {
          parts.push(CC.badge("仅参考", "none"));
        }
        if (row.status && row.status !== "live" && row.status !== "no_data") {
          parts.push(CC.badge(row.status, row.status));
        }
        var html = parts.join(" ");
        if (row.note) {
          html = '<span title="' + CC.esc(row.note) + '">' + html + "</span>";
        }
        return html;
      } }
  ];

  var rows = [];
  var ready = false;

  function money(value) {
    if (value == null || value === "" || !isFinite(Number(value))) {
      return '<span class="muted">—</span>';
    }
    return CC.money(value, 2);
  }

  function buildRows(index, crosscheck) {
    var cards = {};
    (index.cards || []).forEach(function (card) { cards[card.id] = card; });
    return (crosscheck.rows || []).map(function (row) {
      var card = cards[row.card_id] || {};
      var market = (card.markets || {})[row.market] || {};
      var weekly = card.weekly_index || null;
      var slug = card.slug || String(row.card_id || "").toLowerCase()
        .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
      return {
        card: row.card_id,
        card_id: row.card_id,
        card_name: card.name || row.card_id,
        card_slug: slug,
        market: row.market,
        market_label: market.label || row.market,
        risk: market.risk || "",
        status: market.status || (row.own_providers ? "live" : "no_data"),
        own_median: market.median != null ? market.median : row.own_median,
        p25: market.p25,
        p75: market.p75,
        cheapest: market.cheapest,
        cheapest_provider: market.cheapest_provider,
        own_n: market.provider_count != null ? market.provider_count : row.own_providers,
        change_7d: market.change_7d_pct,
        weekly_index: weekly ? weekly.index : null,
        weekly_week: weekly ? (weekly.isoWeek || weekly.weekStart) : null,
        ext_median: row.ext_median,
        ext_n: row.ext_providers,
        diff_pct: row.diff_pct,
        coverage: row.coverage || "none",
        comparable: !!row.comparable,
        own_thin: !!row.own_thin,
        note: row.note || "",
        search: [
          card.name, card.id, row.card_id, row.market, market.label, row.note
        ].join(" ").toLowerCase()
      };
    });
  }

  function render() {
    if (!ready) { return; }
    var filters = CC.readFilters(filtersRoot);
    var query = String(filters.search || "").trim().toLowerCase();
    var visible = CC.filterRows(rows, {
      card: filters.card,
      market: filters.market,
      coverage: filters.coverage,
      search: function (value) {
        return !query || String(value || "").toLowerCase().indexOf(query) >= 0;
      }
    }, { exact: ["card", "market", "coverage"] });

    tableHost.innerHTML = CC.table(HEADERS, visible, {
      empty: "没有匹配的 card × market 行，请调整筛选。",
      caption: "公开挂牌价，非成交价。P25/P75 仅在该市场至少 4 家时发布。"
    });
    tableHost.setAttribute("aria-busy", "false");
    if (countEl) { countEl.textContent = visible.length + " / " + rows.length + " 行"; }
  }

  function fail(error) {
    tableHost.setAttribute("aria-busy", "false");
    tableHost.innerHTML = CC.empty(
      "数据加载失败：" + (error && error.message ? error.message : error) +
      "。请通过本地静态服务器打开页面。"
    );
    if (countEl) { countEl.textContent = "加载失败"; }
  }

  CC.bindFilters(filtersRoot, render);
  Promise.all([CC.get("site-index.json"), CC.get("crosscheck.json")])
    .then(function (documents) {
      rows = buildRows(documents[0], documents[1]);
      ready = true;
      render();
    })
    .catch(fail);
})();
"""


def _landscape_filters(
    index: Dict[str, Any], crosscheck: Dict[str, Any]
) -> str:
    cards = '<option value="">全部卡</option>' + "".join(
        f'<option value="{_attr(card.get("id"))}">{escape(_card_label(card))}</option>'
        for card in index.get("cards") or []
    )
    markets = '<option value="">全部 market</option>' + "".join(
        f'<option value="{_attr(market.get("id"))}">'
        f'{escape(str(market.get("label") or market.get("short") or market.get("id")))}'
        "</option>"
        for market in index.get("markets") or []
    )
    present = {
        str(row.get("coverage") or "none") for row in crosscheck.get("rows") or []
    }
    coverage_values = list(_COVERAGE_ORDER)
    coverage_values += sorted(present.difference(coverage_values))
    coverage = '<option value="">全部 coverage</option>' + "".join(
        f'<option value="{_attr(value)}">{escape(_COVERAGE_LABELS.get(value, value))}</option>'
        for value in coverage_values
    )
    return (
        '<div class="filters" id="landscape-filters" role="group" '
        'aria-label="Landscape 筛选">'
        '<div class="field"><label for="landscape-card">卡</label>'
        f'<select id="landscape-card" data-filter="card">{cards}</select></div>'
        '<div class="field"><label for="landscape-market">Market</label>'
        f'<select id="landscape-market" data-filter="market">{markets}</select></div>'
        '<div class="field"><label for="landscape-coverage">Coverage</label>'
        f'<select id="landscape-coverage" data-filter="coverage">{coverage}</select></div>'
        '<div class="field"><label for="landscape-search">搜索卡名</label>'
        '<input id="landscape-search" type="search" data-filter="search" '
        'placeholder="例如 H100 或 RTX PRO" autocomplete="off"></div>'
        "</div>"
    )


def write_landscape_page(public_dir: Path) -> str:
    """Write ``landscape.html`` and return its absolute path."""
    public_dir = Path(public_dir)
    index = _load(public_dir, "data/site-index.json")
    crosscheck = _load(public_dir, "data/crosscheck.json")
    counts = index.get("counts") or {}
    cards_n = _number(counts.get("cards"))
    own_n = _number(counts.get("own_providers"))
    ext_n = _number(counts.get("external_providers"))
    ext_quotes = _number(counts.get("external_quotes"))
    own_quotes = _number(counts.get("own_quotes"))
    rows_n = _number(len(crosscheck.get("rows") or []))
    markets_n = _number(len(index.get("markets") or []))
    as_of = _text(index.get("as_of"))
    generated_at = _text(index.get("generated_at"))

    body = f"""
<section class="hero">
  <p class="kicker">Landscape · as of {as_of}</p>
  <h1>{cards_n} 张关键卡，自有与外部同屏对照</h1>
  <p class="lede">全表 {rows_n} 行（{cards_n} 卡 × {markets_n} 市场）。自有面板的 median、P25–P75、cheapest 与周指数来自 AI Compute Economics；外部 median 与 coverage 只作参考，不改写自有口径。</p>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">关键卡</div><div class="value">{cards_n}</div><div class="hint">{rows_n} 行 · {markets_n} 个市场</div></div>
    <div class="kpi"><div class="label">自有 provider</div><div class="value">{own_n}</div><div class="hint">{own_quotes} 条最新挂牌报价</div></div>
    <div class="kpi"><div class="label">外部 provider</div><div class="value">{ext_n}</div><div class="hint">有 current_quotes 记录（含 stopped）</div></div>
    <div class="kpi"><div class="label">外部报价</div><div class="value">{ext_quotes}</div><div class="hint">全量记录，含 stopped / 非 USD；仅覆盖参考</div></div>
  </div>
  <p class="source">自有面板 as-of <strong>{as_of}</strong> · 页面构建 {generated_at}。</p>
  {_source_note(index)}
</section>

<section class="section" id="landscape-detail">
  <div class="section-head">
    <div>
      <h2>Card × market 全表</h2>
      <p class="sub">coverage 是样本/口径覆盖提示，不是价格差；外部 median 不能当作成交价。</p>
    </div>
    <p class="small muted" id="landscape-count">加载中…</p>
  </div>
  {_landscape_filters(index, crosscheck)}
  <div id="landscape-table" aria-live="polite" aria-busy="true">
    <div class="empty" role="status">正在加载 card 与 crosscheck 数据…</div>
  </div>
  <p class="panel-note">Weekly idx (on-demand) 是卡级 on-demand 周指数（起点 = 100），不是市场指数；非 on_demand 或 no_data 行显示 —。7d 为市场级 7 日变化。Δ 是 own median / ext median − 1 的口径样本差，不是可执行价差。own_n = 0 的空市场标“无自有报价”；有少量自有报价才标“样本偏薄”。</p>
</section>
"""

    html = page(
        "Landscape",
        "11 张关键 GPU 的 card × market 全表：自有 median、P25–P75、cheapest、周指数与 GPU Economy 外部对照。",
        ".",
        "landscape",
        body,
        _LANDSCAPE_SCRIPT,
    )
    path = public_dir / "landscape.html"
    path.write_text(html, encoding="utf-8")
    return str(path)


# ---------------------------------------------------------------------------
# Providers page


_PROVIDERS_SCRIPT = r"""
(function () {
  "use strict";
  var tableHost = document.getElementById("providers-table");
  var countEl = document.getElementById("providers-count");
  var filtersRoot = document.getElementById("providers-filters");
  if (!tableHost) { return; }

  var HEADERS = [
    { label: "Provider", key: "name", render: function (_value, row) {
        var html = CC.link(row.name, "providers/" + row.slug + ".html");
        if (row.layer === "gpueconomy" && row.live_quotes === 0) {
          html += " " + CC.badge("0 live", "none");
        }
        html += '<br><span class="small muted">' + CC.esc(row.id) + "</span>";
        return html;
      } },
    { label: "Layer", key: "layer", render: function (value) {
        if (value === "own") { return CC.badge("own", "own"); }
        return CC.badge("gpueconomy", "ext");
      } },
    { label: "Type", key: "type", render: function (value, row) {
        var html = CC.esc(value || "—");
        if (row.source_kind) {
          html += '<br><span class="small muted">' + CC.esc(row.source_kind) + "</span>";
        }
        return html;
      } },
    { label: "Live coverage", key: "live_coverage_count", title: "自有 = 11 卡 key cards；外部 = live 报价的不同 GPU id 数；单位不同，不可直接比较", render: function (value, row) {
        var names = row.live_coverage_names || [];
        var html = value ? CC.num(value) : '<span class="muted">0</span>';
        html += ' <span class="small muted">' + CC.esc(row.live_coverage_unit || "") + "</span>";
        if (names.length) {
          var shown = names.slice(0, 2).join(", ");
          if (names.length > 2) { shown += " +" + (names.length - 2); }
          html += '<br><span class="small muted">' + CC.esc(shown) + "</span>";
        }
        var title = [];
        if (row.layer === "own") {
          title.push("自有：11 卡 key cards 覆盖数");
        } else {
          title.push("外部：live 报价的不同 GPU id 数，不是 11 卡覆盖");
        }
        if (names.length) { title.push("各型号: " + names.join(", ")); }
        if (row.layer === "gpueconomy" && (row.cards || []).length) {
          title.push("site-index 原始 key cards: " + (row.cards || []).join(", "));
        }
        if (title.length) {
          html = '<span title="' + CC.esc(title.join(" | ")) + '">' + html + "</span>";
        }
        return html;
      } },
    { label: "Live quotes", key: "live_quotes", num: true, title: "外部仅 live + 非 marketplace floor + USD；raw 为 site-index 原始记录数", render: function (value, row) {
        var html = CC.num(value);
        if (row.layer === "gpueconomy" && row.current_quotes != null) {
          html += '<br><span class="small muted">raw ' + CC.num(row.current_quotes) + "</span>";
        }
        return html;
      } },
    { label: "Cheapest", key: "cheapest", num: true, title: "外部仅 live + 非 marketplace floor + USD；自有取自有面板最低价", render: function (value, row) {
        if (!value || !isFinite(Number(value.value))) {
          return '<span class="muted">—</span>';
        }
        var html = CC.money(value.value, 2);
        var hints = [value.card, value.market].filter(Boolean);
        if (hints.length) {
          html += '<br><span class="small muted">' + CC.esc(hints.join(" · ")) + "</span>";
        }
        return html;
      } },
    { label: "Source", key: "source_url", render: function (value, row) {
        if (!value) { return '<span class="muted">—</span>'; }
        var label = row.source_label || "来源";
        return CC.link(label + " ↗", value, { target: "_blank", title: value });
      } }
  ];

  var rows = [];
  var ready = false;

  function isEffectiveExternalQuote(quote) {
    if (!quote) { return false; }
    if (quote.status !== "live") { return false; }
    if (quote.price_scope === "marketplace_floor") { return false; }
    if (quote.listed_currency !== "USD") { return false; }
    return true;
  }

  function buildRows(index, pricesDoc) {
    var stats = {};
    (pricesDoc.prices || []).forEach(function (quote) {
      if (quote.source_layer && quote.source_layer !== "gpueconomy") { return; }
      if (!isEffectiveExternalQuote(quote)) { return; }
      var providerId = quote.provider_id;
      if (!providerId) { return; }
      var item = stats[providerId];
      if (!item) {
        item = stats[providerId] = {
          live_quotes: 0,
          gpus: {},
          live_gpus: [],
          cheapest: null
        };
      }
      item.live_quotes += 1;
      var gpuKey = quote.gpu_id || quote.gpu || "";
      if (gpuKey && !item.gpus[gpuKey]) {
        item.gpus[gpuKey] = true;
        item.live_gpus.push(quote.gpu || quote.gpu_id || gpuKey);
      }
      var value = Number(quote.usd_per_gpu_hour);
      if (isFinite(value) && (!item.cheapest || value < item.cheapest.value)) {
        item.cheapest = {
          value: value,
          card: quote.gpu || quote.gpu_id,
          market: quote.market,
          scope: quote.price_scope,
          source_url: quote.source_url
        };
      }
    });

    var output = [];
    ((index.providers || {}).own || []).forEach(function (provider) {
      var own = provider.cheapest || null;
      output.push({
        id: provider.id,
        slug: provider.slug,
        name: provider.name || provider.id,
        layer: "own",
        type: "own",
        source_kind: "",
        cards: provider.cards || [],
        live_key_cards: (provider.cards || []).length,
        live_gpu_ids: null,
        live_coverage_count: (provider.cards || []).length,
        live_coverage_unit: "key cards",
        live_coverage_names: provider.cards || [],
        live_quotes: provider.quotes || 0,
        current_quotes: provider.quotes || 0,
        cheapest: own ? {
          value: own.usd_per_gpu_hour,
          card: own.card,
          market: own.market,
          scope: null,
          source_url: own.source_url
        } : null,
        source_url: own && own.source_url ? own.source_url : "",
        source_label: "挂牌页",
        search: [provider.name, provider.id, (provider.cards || []).join(" ")]
          .join(" ").toLowerCase()
      });
    });
    ((index.providers || {}).external || []).forEach(function (provider) {
      var live = stats[provider.id] || { live_quotes: 0, live_gpus: [], cheapest: null };
      output.push({
        id: provider.id,
        slug: provider.slug,
        name: provider.name || provider.id,
        layer: "gpueconomy",
        type: provider.type || "external",
        source_kind: provider.source_kind || "",
        cards: provider.cards || [],
        live_key_cards: null,
        live_gpu_ids: live.live_gpus.length,
        live_coverage_count: live.live_gpus.length,
        live_coverage_unit: "GPU ids",
        live_coverage_names: live.live_gpus,
        live_quotes: live.live_quotes,
        current_quotes: provider.current_quotes || 0,
        cheapest: live.cheapest,
        source_url: provider.pricing_page || provider.website || "",
        source_label: provider.pricing_page ? "pricing page" : "website",
        search: [
          provider.name, provider.id, provider.type, (provider.cards || []).join(" "),
          live.live_gpus.join(" ")
        ].join(" ").toLowerCase()
      });
    });
    return output;
  }

  function render() {
    if (!ready) { return; }
    var filters = CC.readFilters(filtersRoot);
    var query = String(filters.search || "").trim().toLowerCase();
    var visible = CC.filterRows(rows, {
      layer: filters.layer,
      type: filters.type,
      search: function (value) {
        return !query || String(value || "").toLowerCase().indexOf(query) >= 0;
      }
    }, { exact: ["layer", "type"] });

    tableHost.innerHTML = CC.table(HEADERS, visible, {
      empty: "没有匹配的 provider，请调整筛选。",
      caption: "外部 provider 的报价来自 GPU Economy，仅作参考；自有与外部不会合并成同一家中位数。"
    });
    tableHost.setAttribute("aria-busy", "false");
    if (countEl) { countEl.textContent = visible.length + " / " + rows.length + " 家"; }
  }

  function fail(error) {
    tableHost.setAttribute("aria-busy", "false");
    tableHost.innerHTML = CC.empty(
      "数据加载失败：" + (error && error.message ? error.message : error) +
      "。请通过本地静态服务器打开页面。"
    );
    if (countEl) { countEl.textContent = "加载失败"; }
  }

  CC.bindFilters(filtersRoot, render);
  Promise.all([CC.get("site-index.json"), CC.get("external/prices.json")])
    .then(function (documents) {
      rows = buildRows(documents[0], documents[1]);
      ready = true;
      render();
    })
    .catch(fail);
})();
"""


def _providers_filters(index: Dict[str, Any]) -> str:
    external = (index.get("providers") or {}).get("external") or []
    types = sorted({
        str(provider.get("type") or "external") for provider in external
    })
    type_items: List[Tuple[str, str]] = [("own", "own（自有）")]
    type_items += [(value, value) for value in types if value != "own"]
    layers = [("own", "own"), ("gpueconomy", "gpueconomy")]
    return (
        '<div class="filters" id="providers-filters" role="group" '
        'aria-label="Provider 筛选">'
        '<div class="field"><label for="providers-layer">Layer</label>'
        f'<select id="providers-layer" data-filter="layer">'
        f'{_options(layers)}</select></div>'
        '<div class="field"><label for="providers-type">Type</label>'
        f'<select id="providers-type" data-filter="type">'
        f'{_options(type_items)}</select></div>'
        '<div class="field"><label for="providers-search">搜索 provider</label>'
        '<input id="providers-search" type="search" data-filter="search" '
        'placeholder="名称或 ID，例如 RunPod" autocomplete="off"></div>'
        "</div>"
    )


def write_providers_page(public_dir: Path) -> str:
    """Write ``providers.html`` and return its absolute path."""
    public_dir = Path(public_dir)
    index = _load(public_dir, "data/site-index.json")
    counts = index.get("counts") or {}
    providers = index.get("providers") or {}
    own_n = _number(counts.get("own_providers"))
    ext_n = _number(counts.get("external_providers"))
    ext_quotes = _number(counts.get("external_quotes"))
    own_quotes = _number(counts.get("own_quotes"))
    total = _number(
        len(providers.get("own") or []) + len(providers.get("external") or [])
    )
    as_of = _text(index.get("as_of"))
    generated_at = _text(index.get("generated_at"))
    meta = _external_meta(index)

    body = f"""
<section class="hero">
  <p class="kicker">Providers · as of {as_of}</p>
  <h1>{total} 家 provider：自有 {own_n} 家 + 外部 {ext_n} 家</h1>
  <p class="lede">自有 provider 来自 AI Compute Economics 的最新挂牌面板；外部 provider 来自 GPU Economy 的当前报价快照。两层分开展示，外部数字不会并入自有中位数或周指数。</p>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">Provider 总数</div><div class="value">{total}</div><div class="hint">{own_n} 自有 · {ext_n} 外部</div></div>
    <div class="kpi"><div class="label">自有报价</div><div class="value">{own_quotes}</div><div class="hint">最新挂牌价，非成交价</div></div>
    <div class="kpi"><div class="label">外部报价记录</div><div class="value">{ext_quotes}</div><div class="hint">全量快照，含 stopped / 非 USD；live 见表格</div></div>
    <div class="kpi"><div class="label">外部数据</div><div class="value">{escape(meta["data_date"])}</div><div class="hint">{escape(meta["license"])} · 仅参考</div></div>
  </div>
  <p class="source">自有面板 as-of <strong>{as_of}</strong> · 页面构建 {generated_at}。</p>
  {_source_note(index)}
</section>

<section class="section" id="providers-detail">
  <div class="section-head">
    <div>
      <h2>Provider 全表</h2>
      <p class="sub">Live coverage 的单位随 layer 不同：自有是 <strong>key cards</strong>（11 卡覆盖数），外部是 <strong>GPU ids</strong>（live 报价的不同 GPU 型号数），两者不可直接比较。Live quotes 与 Cheapest：自有行取自有面板；外部行只统计 live + 非 marketplace floor + USD 的报价。Live quotes 下方的 raw 是 site-index 的 current_quotes 原始记录数。</p>
    </div>
    <p class="small muted" id="providers-count">加载中…</p>
  </div>
  {_providers_filters(index)}
  <div id="providers-table" aria-live="polite" aria-busy="true">
    <div class="empty" role="status">正在加载 provider 数据…</div>
  </div>
  <p class="panel-note">外部 provider 统一标为 <span class="badge ext">gpueconomy</span>，来源为 <a href="{_attr(meta["source_url"])}" target="_blank" rel="noopener">GPU Economy</a> · {escape(meta["license"])}；每行的 Source 链接指向 provider 自己的定价页。site-index 的 cards/current_quotes 可能包含 stopped 或历史覆盖，表格不把它们当作 live；外部 Live coverage 是 GPU id 数，不是 11 卡覆盖。有记录但 0 live 的行会标 <span class="badge none">0 live</span>。没有 current_quotes 记录的外部 provider 不会出现在这里。</p>
</section>
"""

    html = page(
        "Providers",
        f"自有 {own_n} 家与 GPU Economy 外部 {ext_n} 家 provider 的合并索引：layer、type、live 覆盖的卡、live 报价数与最低挂牌价。",
        ".",
        "providers",
        body,
        _PROVIDERS_SCRIPT,
    )
    path = public_dir / "providers.html"
    path.write_text(html, encoding="utf-8")
    return str(path)
