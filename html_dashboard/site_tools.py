"""Compare, spread and cheapest tool pages for the standalone static site.

All three pages are thin views over the committed slices written by
``site_data.write_site_data``:

* ``compare.html`` reads ``site-index.json`` and the selected
  ``cards/<slug>.json`` files.
* ``spread.html`` and ``cheapest.html`` read the own ``prices.json`` and the
  GPU Economy ``external/prices.json``.

The build step only renders the shell, filter options and page copy.  Prices,
grouping and ranking are computed in the browser from the data files, so the
pages stay in sync with the daily refresh without a rebuild of hard-coded
numbers.
"""

from __future__ import annotations

import json
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:  # package import path (html_dashboard.site_tools)
    from .gpu_external import MARKET_VIEWS
    from .site_shell import page
except ImportError:  # script import path used by the test suite / build
    from gpu_external import MARKET_VIEWS  # type: ignore
    from site_shell import page  # type: ignore


_EXTRA_MARKET_LABELS = {
    "reserved_1y": "Reserved 1y",
    "reserved_3y": "Reserved 3y",
    "shared": "Shared",
}


# ---------------------------------------------------------------------------
# Small helpers


def _load(public_dir: Path, relative: str) -> Dict[str, Any]:
    path = Path(public_dir) / relative
    if not path.is_file():
        raise FileNotFoundError(
            f"{path} is missing; write the site data before generating toolbar pages"
        )
    return json.loads(path.read_text(encoding="utf-8"))


def _load_optional(public_dir: Path, relative: str) -> Dict[str, Any]:
    path = Path(public_dir) / relative
    if not path.is_file():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _text(value: Any, fallback: str = "—") -> str:
    if value is None or value == "":
        return fallback
    return escape(str(value))


def _attr(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def _num(value: Any) -> str:
    if isinstance(value, bool):
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "—"


def _js_json(payload: Any) -> str:
    """JSON safe to embed inside an inline ``<script>`` element."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _card_label(card: Dict[str, Any]) -> str:
    card_id = str(card.get("id") or "")
    name = str(card.get("name") or card_id)
    if not card_id or name.startswith(card_id):
        return name or card_id
    return f"{card_id} · {name}"


def _pretty_market(market_id: str) -> str:
    if market_id in _EXTRA_MARKET_LABELS:
        return _EXTRA_MARKET_LABELS[market_id]
    return str(market_id or "").replace("_", " ").title()


def _market_catalog(index: Dict[str, Any]) -> Tuple[Dict[str, str], List[str]]:
    labels: Dict[str, str] = {}
    order: List[str] = []
    for market in index.get("markets") or []:
        market_id = str(market.get("id") or "")
        if not market_id:
            continue
        labels[market_id] = str(
            market.get("label") or market.get("short") or market_id
        )
        order.append(market_id)
    for market_id, view in MARKET_VIEWS.items():
        if market_id in labels:
            continue
        labels[market_id] = _pretty_market(market_id)
        order.append(market_id)
    return labels, order


def _external_view_market(row: Dict[str, Any]) -> str:
    """Map an external row to our market view, mirroring build_crosscheck."""
    external_market = str(row.get("market") or "")
    scope = str(row.get("price_scope") or "")
    for market_id, view in MARKET_VIEWS.items():
        if external_market not in (view.get("ext_markets") or []):
            continue
        wanted_scope = view.get("scope")
        if wanted_scope:
            if scope != wanted_scope:
                continue
        elif scope == "marketplace_floor":
            continue
        return market_id
    return ""


def _ext_card_map(crosscheck: Dict[str, Any]) -> Dict[str, str]:
    """Map a GPU Economy ``gpu_id`` to the matching key card id."""
    mapping: Dict[str, str] = {}
    for row in crosscheck.get("rows") or []:
        gpu_id = str(row.get("match_id") or "")
        card_id = str(row.get("card_id") or "")
        if gpu_id and card_id:
            mapping[gpu_id] = card_id
    return mapping


def _provider_slugs(index: Dict[str, Any]) -> Dict[str, str]:
    providers = index.get("providers") or {}
    output: Dict[str, str] = {}
    for provider in providers.get("own") or []:
        provider_id = str(provider.get("id") or "")
        slug = str(provider.get("slug") or "")
        if provider_id and slug:
            output[f"own|{provider_id}"] = slug
    for provider in providers.get("external") or []:
        provider_id = str(provider.get("id") or "")
        slug = str(provider.get("slug") or "")
        if provider_id and slug:
            output[f"gpueconomy|{provider_id}"] = slug
    return output


def _effective_external_count(external_prices: Dict[str, Any]) -> int:
    count = 0
    for row in external_prices.get("prices") or []:
        if row.get("status") != "live":
            continue
        if row.get("listed_currency") != "USD":
            continue
        if not _external_view_market(row):
            continue
        try:
            float(row.get("usd_per_gpu_hour"))
        except (TypeError, ValueError):
            continue
        count += 1
    return count


def _nonfloor_external_count(external_prices: Dict[str, Any]) -> int:
    """Live + USD + non-floor rows, regardless of market-view mapping."""
    count = 0
    for row in external_prices.get("prices") or []:
        if row.get("status") != "live":
            continue
        if row.get("listed_currency") != "USD":
            continue
        if row.get("price_scope") == "marketplace_floor":
            continue
        try:
            float(row.get("usd_per_gpu_hour"))
        except (TypeError, ValueError):
            continue
        count += 1
    return count


def _options(items: Iterable[Tuple[str, str]], all_label: str) -> str:
    output = [f'<option value="">{escape(all_label)}</option>']
    for value, label in items:
        output.append(
            f'<option value="{_attr(value)}">{escape(str(label))}</option>'
        )
    return "".join(output)


def _filters(
    root_id: str,
    index: Dict[str, Any],
    market_labels: Dict[str, str],
    market_order: List[str],
    include_layer: bool = True,
) -> str:
    root = root_id
    cards = [(str(card.get("id") or ""), _card_label(card)) for card in index.get("cards") or []]
    markets = [(market_id, market_labels.get(market_id, market_id)) for market_id in market_order]
    layer_field = ""
    if include_layer:
        layer_field = (
            f'<div class="field"><label for="{root}-layer">Layer</label>'
            '<select id="' + root + '-layer" data-filter="layer">'
            + _options(
                [("own", "own（自有）"), ("gpueconomy", "gpueconomy（外部）")],
                "全部 layer",
            )
            + "</select></div>"
        )
    return (
        f'<div class="filters" id="{root}-filters" role="group" '
        f'aria-label="{escape(root.title())} 筛选">'
        f'<div class="field"><label for="{root}-card">卡</label>'
        f'<select id="{root}-card" data-filter="card">'
        f'{_options(cards, "全部卡")}</select></div>'
        f'<div class="field"><label for="{root}-market">Market</label>'
        f'<select id="{root}-market" data-filter="market">'
        f'{_options(markets, "全部 market")}</select></div>'
        f"{layer_field}"
        "</div>"
    )


# ---------------------------------------------------------------------------
# Compare


_COMPARE_SCRIPT = r"""
(function () {
  "use strict";
  var CC = window.CC;
  if (!CC) { return; }
  var CONTEXT = __CONTEXT__;
  var CARDS = CONTEXT.cards || [];
  var cardLookup = {};
  CARDS.forEach(function (card) { cardLookup[card.id] = card; });

  var options = document.getElementById("compare-card-options");
  var chartHost = document.getElementById("compare-chart");
  var tableHost = document.getElementById("compare-table");
  var hint = document.getElementById("compare-hint");
  var countEl = document.getElementById("compare-count");
  if (!options || !chartHost || !tableHost) { return; }

  var checks = Array.prototype.slice.call(
    options.querySelectorAll("[data-card-toggle]")
  );
  var requestId = 0;

  function selected() {
    return checks.filter(function (input) { return input.checked; }).map(function (input) {
      return cardLookup[input.value] || { id: input.value, slug: input.value.toLowerCase(), name: input.value };
    });
  }

  function setCount(text) {
    if (countEl) { countEl.textContent = text; }
  }

  function syncChecks() {
    var picked = selected().length;
    checks.forEach(function (input) {
      input.disabled = !input.checked && picked >= 4;
      var label = input.closest ? input.closest("label") : null;
      if (label) { label.classList.toggle("primary", input.checked); }
    });
  }

  function reset(message, status) {
    requestId += 1;
    chartHost.innerHTML = CC.empty(message);
    tableHost.innerHTML = "";
    if (hint) { hint.textContent = message; }
    setCount(status || "未选择");
  }

  function fail(error) {
    var message = "数据加载失败：" + (error && error.message ? error.message : error) +
      "。请通过本地静态服务器打开页面。";
    chartHost.innerHTML = CC.empty(message);
    tableHost.innerHTML = "";
    if (hint) { hint.textContent = message; }
    setCount("加载失败");
  }

  function load() {
    var picked = selected();
    syncChecks();
    if (!CARDS.length) {
      reset("site-index 中没有可比较的卡片。", "0 / 4 张");
      return;
    }
    if (picked.length === 0) {
      reset("请选择 2–4 张卡，比较它们的周指数；共同起点统一重定基为 100。", "0 / 4 张");
      return;
    }
    if (picked.length < 2) {
      reset("再选至少 1 张卡。Compare 需要 2–4 张卡才能放在同一张图上。", picked.length + " / 4 张");
      return;
    }
    if (picked.length > 4) {
      reset("最多选择 4 张卡。", picked.length + " / 4 张");
      return;
    }

    var token = ++requestId;
    setCount(picked.length + " / 4 张");
    if (hint) { hint.textContent = "正在加载所选卡片的周指数…"; }
    chartHost.innerHTML = '<div class="empty" role="status">正在加载周指数…</div>';
    tableHost.innerHTML = "";

    Promise.all(picked.map(function (card) {
      return CC.get("cards/" + encodeURIComponent(card.slug) + ".json");
    })).then(function (docs) {
      if (token !== requestId) { return; }
      render(picked, docs);
    }).catch(function (error) {
      if (token !== requestId) { return; }
      fail(error);
    });
  }

  function render(cards, docs) {
    var prepared = [];
    var missing = [];
    cards.forEach(function (card, index) {
      var doc = docs[index] || {};
      var weeks = (doc.weeks || []).filter(function (week) {
        return week && week.weekStart &&
          week.index !== null && week.index !== undefined &&
          isFinite(Number(week.index));
      }).sort(function (left, right) {
        return String(left.weekStart).localeCompare(String(right.weekStart));
      });
      if (!weeks.length) {
        missing.push(card.name || card.id);
        return;
      }
      prepared.push({ card: card, weeks: weeks });
    });

    if (missing.length) {
      reset("这些卡没有可用的周指数：" + missing.join("、") + "。换一张卡或稍后再试。", "不可比较");
      return;
    }
    if (prepared.length < 2) {
      reset("至少需要 2 张有周指数的卡。", "不可比较");
      return;
    }

    var commonDates = prepared[0].weeks.filter(function (week) {
      var date = String(week.weekStart);
      return prepared.every(function (item) {
        return item.weeks.some(function (other) {
          return String(other.weekStart) === date;
        });
      });
    }).map(function (week) { return String(week.weekStart); });

    if (!commonDates.length) {
      reset("所选卡片没有共同的有效周指数，无法在统一起点比较。", "不可比较");
      return;
    }
    var commonStart = commonDates.sort()[0];

    var series = [];
    var rows = [];
    var incomplete = [];
    prepared.forEach(function (item) {
      var windowWeeks = item.weeks.filter(function (week) {
        return String(week.weekStart) >= commonStart;
      });
      if (!windowWeeks.length) {
        incomplete.push(item.card.name || item.card.id);
        return;
      }
      var base = Number(windowWeeks[0].index);
      if (!isFinite(base) || base === 0) {
        incomplete.push(item.card.name || item.card.id);
        return;
      }
      var last = windowWeeks[windowWeeks.length - 1];
      var end = Number(last.index) / base * 100;
      series.push({
        name: item.card.name || item.card.id,
        points: windowWeeks.map(function (week) {
          return {
            date: week.weekStart,
            value: Number(week.index) / base * 100
          };
        })
      });
      rows.push({
        name: item.card.name || item.card.id,
        slug: item.card.slug,
        start_date: commonStart,
        start_index: 100,
        end_date: last.weekStart,
        end_index: end,
        change: end - 100,
        median: item.card.median,
        providers: item.card.provider_count,
        weeks: windowWeeks.length,
        last_status: last.status || ""
      });
    });

    if (incomplete.length) {
      reset("这些卡在共同起点之后没有周指数：" + incomplete.join("、") + "。", "不可比较");
      return;
    }

    var maxEndDate = rows.map(function (row) {
      return String(row.end_date || "");
    }).sort().pop();

    rows.forEach(function (row) {
      var endStamp = Date.parse(String(row.end_date) + "T00:00:00Z");
      var maxStamp = Date.parse(String(maxEndDate) + "T00:00:00Z");
      var lagDays = isFinite(endStamp) && isFinite(maxStamp)
        ? Math.round((maxStamp - endStamp) / 86400000) : 0;
      row.lag_days = lagDays;
      row.comparable = row.weeks >= 2 && lagDays < 14;
      row.coverage_status = row.comparable ? "" : "覆盖不足";
      row.coverage_reason = row.weeks < 2
        ? "weeks=" + row.weeks
        : "末期滞后 " + lagDays + " 天";
    });

    CC.lineChart(chartHost, series, {
      kind: "index",
      yLabel: "Index · 共同起点 = 100",
      ariaLabel: "所选 GPU 的周指数，共同起点 100"
    });

    tableHost.innerHTML = CC.table([
      {
        label: "GPU", key: "name",
        render: function (value, row) {
          if (!row.slug) { return CC.esc(value); }
          return CC.link(value, "gpu/" + encodeURIComponent(row.slug) + ".html");
        }
      },
      { label: "起点周", key: "start_date", className: "nowrap" },
      {
        label: "起点 index", key: "start_index", num: true,
        render: function (value) { return CC.num(value, 1); }
      },
      { label: "末期周", key: "end_date", className: "nowrap" },
      {
        label: "末期 index", key: "end_index", num: true,
        render: function (value) { return CC.num(value, 1); }
      },
      {
        label: "Weeks", key: "weeks", num: true,
        render: function (value) { return CC.num(value, 0); }
      },
      {
        label: "变化", key: "change", num: true,
        render: function (value, row) {
          if (!row.comparable) { return '<span class="muted">—</span>'; }
          return CC.pct(value, 1);
        }
      },
      {
        label: "最新 median", key: "median", num: true,
        render: function (value) { return CC.money(value, 2); }
      },
      {
        label: "Providers", key: "providers", num: true,
        render: function (value) { return CC.num(value, 0); }
      },
      {
        label: "Status", key: "coverage_status",
        render: function (value, row) {
          if (!row.comparable) {
            return '<span class="badge thin" title="' +
              CC.esc(row.coverage_reason || "") +
              '">' + CC.esc(value || "覆盖不足") + "，不可比较</span>";
          }
          return row.last_status
            ? CC.badge(row.last_status, row.last_status === "published" ? "ok" : "thin")
            : '<span class="badge ok">ok</span>';
        }
      }
    ], rows, {
      caption: "共同起点 " + commonStart + "；每张卡在该周重定基为 100。Weeks < 2 或末期滞后 ≥ 14 天标“覆盖不足，不可比较”，变化留空。"
    });

    if (hint) {
      var limited = rows.filter(function (row) { return !row.comparable; })
        .map(function (row) { return row.name; });
      hint.textContent = "共同起点 " + commonStart + "；折线与表格均按该周 = 100 重定基。";
      if (limited.length) {
        hint.textContent += "覆盖不足，不可比较：" + limited.join("、") + "。";
      }
    }
    setCount(rows.length + " / 4 张");
  }

  checks.forEach(function (input) {
    input.addEventListener("change", load);
  });
  load();
})();
"""


def _compare_body(index: Dict[str, Any]) -> str:
    counts = index.get("counts") or {}
    cards = index.get("cards") or []
    as_of = _text(index.get("as_of"))
    card_inputs = "".join(
        '<label class="btn"><input type="checkbox" data-card-toggle '
        f'value="{_attr(card.get("id"))}"> '
        f'{_text(_card_label(card))}'
        '<span class="small muted" style="margin-left:6px">'
        f'{_num(card.get("provider_count"))} 家</span></label>'
        for card in cards
    )
    return f"""
<section class="hero compact">
  <p class="kicker">Compare · 周指数 · as of {as_of}</p>
  <h1>把 2–4 张卡放在共同起点</h1>
  <p class="lede">选择 2–4 张卡，用各自的周指数在共同起点重定基为 100，再看相对变化。周指数本身来自自有 provider 面板；外部数据不参与。</p>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">可选卡</div><div class="value">{_num(counts.get("cards"))}</div><div class="hint">{_num(len(index.get("markets") or []))} 个市场</div></div>
    <div class="kpi"><div class="label">自有报价</div><div class="value">{_num(counts.get("own_quotes"))}</div><div class="hint">最新挂牌价，非成交价</div></div>
    <div class="kpi"><div class="label">比较方式</div><div class="value">2–4</div><div class="hint">共同起点 = 100</div></div>
  </div>
  <p class="source">周指数来自 <a href="data/site-index.json">site-index.json</a> 对应的 <a href="data/cards/h100.json">cards/&lt;slug&gt;.json</a> 切片。指数是链式 base-100，不是价格水平；不同卡的价格不可直接相减。</p>
</section>

<section class="section">
  <div class="section-head">
    <div>
      <h2>选择卡片</h2>
      <p class="sub">选中 2–4 张卡后，图表和表格会自动更新。</p>
    </div>
    <p class="small muted" id="compare-count">未选择</p>
  </div>
  <div class="filters" id="compare-card-options" role="group" aria-label="选择卡片">
    {card_inputs}
  </div>
  <p class="panel-note" id="compare-hint" role="status">请选择 2–4 张卡。</p>
  <div class="chart" id="compare-chart" aria-live="polite">
    <div class="empty" role="status">请选择 2–4 张卡，查看共同起点后的周指数。</div>
  </div>
  <div id="compare-table" style="margin-top:16px" aria-live="polite"></div>
  <p class="panel-note">共同起点取所有选中卡都有非空周指数的最早周；Weeks &lt; 2 或末期比其他卡滞后 ≥ 14 天时标“覆盖不足，不可比较”，变化留空，不补零。周指数遇到样本不足会 withheld，这是数据质量信号。</p>
</section>
"""


# ---------------------------------------------------------------------------
# Spread


_SHARED_PRICE_JS = r"""
  function safeUrl(value) {
    var text = String(value == null ? "" : value).trim();
    return /^https?:\/\//i.test(text) ? text : "";
  }

  function sourceCell(value, label) {
    var href = safeUrl(value);
    if (!href) { return '<span class="muted">—</span>'; }
    return '<a href="' + CC.esc(href) + '" target="_blank" rel="noopener">' +
      CC.esc(label || "来源") + "</a>";
  }

  function marketLabel(id) {
    return MARKET_LABELS[id] || String(id || "").replace(/_/g, " ").replace(/\b\w/g, function (ch) {
      return ch.toUpperCase();
    });
  }

  function cardLink(row) {
    var label = row.card_label || row.card_id || "—";
    if (row.card_slug) {
      return CC.link(label, "gpu/" + encodeURIComponent(row.card_slug) + ".html");
    }
    return CC.esc(label);
  }

  function cardLabel(card) {
    var id = String(card && card.id != null ? card.id : "");
    var name = String(card && card.name != null ? card.name : id);
    if (!id || name.indexOf(id) === 0) { return name || id; }
    return id + " · " + name;
  }

  function populateCardOptions(root, rows, cards) {
    var select = root ? root.querySelector('[data-filter="card"]') : null;
    if (!select) { return; }
    var seen = {};
    var options = ['<option value="">全部卡</option>'];
    (cards || []).forEach(function (card) {
      var id = String(card && card.id != null ? card.id : "");
      if (!id || seen[id]) { return; }
      seen[id] = true;
      options.push('<option value="' + CC.esc(id) + '">' +
        CC.esc(cardLabel(card)) + "</option>");
    });
    var extras = [];
    (rows || []).forEach(function (row) {
      var key = String(row.card_key || "");
      if (!key || seen[key]) { return; }
      seen[key] = true;
      if (row.card_id) { return; }
      extras.push({
        value: key,
        label: String(row.card_label || key).replace(/\s+$/, "") + "（外部）"
      });
    });
    extras.sort(function (left, right) {
      return left.label.localeCompare(right.label);
    });
    extras.forEach(function (item) {
      options.push('<option value="' + CC.esc(item.value) + '">' +
        CC.esc(item.label) + "</option>");
    });
    var current = select.value;
    select.innerHTML = options.join("");
    if (current) {
      var exists = Array.prototype.some.call(select.options, function (option) {
        return option.value === current;
      });
      select.value = exists ? current : "";
    }
  }

  function riskBadge(value) {
    var key = String(value == null ? "" : value).toLowerCase();
    var tone = (key === "low" || key === "medium" || key === "high") ? key : "";
    return value ? CC.badge(value, tone) : '<span class="muted">—</span>';
  }

  function statusBadge(value) {
    var key = String(value == null ? "" : value).toLowerCase();
    var tone = key === "live" ? "live" : (key === "unconfirmed" || key === "thin_market" ? "thin" : (key === "stopped" ? "stopped" : ""));
    return value ? CC.badge(value, tone) : '<span class="muted">—</span>';
  }

  function providerSlug(layer, providerId) {
    var key = String(layer) + "|" + String(providerId);
    if (PROVIDER_SLUGS[key]) { return PROVIDER_SLUGS[key]; }
    var slug = String(providerId == null ? "" : providerId).toLowerCase()
      .replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "");
    if (!slug) { return ""; }
    return (layer === "own" ? "own-" : "ext-") + slug;
  }

  function providerCell(row) {
    var label = row.provider || row.provider_id || "—";
    var slug = row.provider_id ? providerSlug(row.layer, row.provider_id) : "";
    if (!slug) { return CC.esc(label); }
    return CC.link(label, "providers/" + encodeURIComponent(slug) + ".html");
  }

  function round6(value) {
    if (value == null || !isFinite(Number(value))) { return value; }
    return Math.round(Number(value) * 1000000) / 1000000;
  }

  function median(values) {
    if (!values.length) { return null; }
    var sorted = values.slice().sort(function (a, b) { return a - b; });
    var middle = Math.floor(sorted.length / 2);
    if (sorted.length % 2) { return sorted[middle]; }
    return (sorted[middle - 1] + sorted[middle]) / 2;
  }

  function quantile(values, q) {
    if (!values.length) { return null; }
    var position = (values.length - 1) * q;
    var base = Math.floor(position);
    var rest = position - base;
    var lower = values[base];
    var upper = values[Math.min(base + 1, values.length - 1)];
    return lower + (upper - lower) * rest;
  }

  function fromOwn(row) {
    var price = Number(row.usd_per_gpu_hour);
    if (!isFinite(price)) { return null; }
    return {
      layer: "own",
      card_id: row.card_id || "",
      card_key: row.card_id || row.card || "",
      card_label: row.card || row.card_id || "",
      market: row.market || "",
      provider_id: row.provider_id || "",
      provider: row.provider || row.provider_id || "",
      price: price,
      date: row.date,
      risk: row.risk,
      status: row.status,
      scope: row.price_scope,
      source_url: row.source_url
    };
  }

  function externalMarketView(row) {
    var views = CONTEXT.marketViews || {};
    var externalMarket = String(row.market || "");
    var scope = String(row.price_scope || "");
    var ids = Object.keys(views);
    for (var i = 0; i < ids.length; i += 1) {
      var marketId = ids[i];
      var view = views[marketId] || {};
      if ((view.ext_markets || []).indexOf(externalMarket) < 0) {
        continue;
      }
      if (view.scope) {
        if (scope !== view.scope) { continue; }
      } else if (scope === "marketplace_floor") {
        continue;
      }
      return marketId;
    }
    return "";
  }

  function fromExternal(row) {
    if (row.status !== "live") { return null; }
    if (row.listed_currency !== "USD") { return null; }
    var market = externalMarketView(row);
    if (!market) { return null; }
    var price = Number(row.usd_per_gpu_hour);
    if (!isFinite(price)) { return null; }
    var cardId = EXT_CARD[row.gpu_id] || "";
    return {
      layer: "gpueconomy",
      card_id: cardId,
      card_key: cardId || ("gpu:" + String(row.gpu_id || row.gpu || "")),
      card_label: row.gpu || row.gpu_id || "",
      market: market,
      external_market: row.market || "",
      provider_id: row.provider_id || "",
      provider: row.provider || row.provider_id || "",
      price: price,
      date: row.scraped_at,
      risk: row.risk,
      status: row.status,
      scope: row.price_scope,
      source_url: row.source_url
    };
  }

  function effectiveExternalRows(externalDoc) {
    var byProvider = {};
    (externalDoc.prices || []).forEach(function (row) {
      var item = fromExternal(row);
      if (!item) { return; }
      var key = [item.market, item.card_key, item.provider_id].join("|");
      var current = byProvider[key];
      if (!current || item.price < current.price) {
        byProvider[key] = item;
      }
    });
    return Object.keys(byProvider).map(function (key) {
      return byProvider[key];
    });
  }

  function cardSortValue(row) {
    var index = CARD_ORDER[row.card_id];
    return index === undefined ? 999 : index;
  }

  function marketSortValue(row) {
    var index = MARKET_ORDER.indexOf(row.market);
    return index < 0 ? 999 : index;
  }

  function layerSortValue(row) {
    return row.layer === "own" ? 0 : 1;
  }

  function sortGroups(rows) {
    return rows.sort(function (left, right) {
      return layerSortValue(left) - layerSortValue(right) ||
        cardSortValue(left) - cardSortValue(right) ||
        String(left.card_label).localeCompare(String(right.card_label)) ||
        marketSortValue(left) - marketSortValue(right) ||
        String(left.market).localeCompare(String(right.market));
    });
  }

  function normalizePrices(ownDoc, externalDoc) {
    var rows = [];
    (ownDoc.quotes || []).forEach(function (row) {
      var item = fromOwn(row);
      if (item) { rows.push(item); }
    });
    effectiveExternalRows(externalDoc).forEach(function (row) {
      rows.push(row);
    });
    return rows;
  }
"""


_SPREAD_SCRIPT = r"""
(function () {
  "use strict";
  var CC = window.CC;
  if (!CC) { return; }
  var CONTEXT = __CONTEXT__;
  var CARD_ORDER = CONTEXT.cardOrder || {};
  var CARD_SLUGS = CONTEXT.cardSlugs || {};
  var MARKET_LABELS = CONTEXT.marketLabels || {};
  var MARKET_ORDER = CONTEXT.marketOrder || [];
  var EXT_CARD = CONTEXT.extCard || {};
  var PROVIDER_SLUGS = CONTEXT.providerSlugs || {};
__SHARED__
  var tableHost = document.getElementById("spread-table");
  var countEl = document.getElementById("spread-count");
  var filtersRoot = document.getElementById("spread-filters");
  if (!tableHost) { return; }

  var HEADERS = [
    { label: "Layer", key: "layer", render: function (value) {
        return value === "own" ? CC.badge("own", "own") : CC.badge("gpueconomy", "ext");
      } },
    { label: "Card", key: "card_label", render: function (_value, row) {
        var html = cardLink(row);
        if (row.card_id) {
          html += '<br><span class="small muted">' + CC.esc(row.card_id) + "</span>";
        } else {
          html += '<br><span class="small muted">外部参考 · 无单卡页</span>';
        }
        return html;
      } },
    { label: "Market", key: "market", render: function (value) {
        var html = "<strong>" + CC.esc(marketLabel(value)) + "</strong>" +
          '<br><span class="small muted">' + CC.esc(value || "—") + "</span>";
        if (value === "marketplace") {
          html += '<br><span class="badge thin">floor，不是 rate card</span>';
        }
        return html;
      } },
    { label: "Cheapest", key: "cheapest", num: true, render: function (value) {
        if (!value || !isFinite(Number(value.price))) { return '<span class="muted">—</span>'; }
        return CC.money(value.price, 2) +
          '<br><span class="small muted">' + CC.esc(value.provider || "—") + "</span>";
      } },
    { label: "Median", key: "median", num: true, render: function (value) {
        return value == null ? '<span class="muted">—</span>' : CC.money(value, 2);
      } },
    { label: "Dearest", key: "dearest", num: true, render: function (value) {
        if (!value || !isFinite(Number(value.price))) { return '<span class="muted">—</span>'; }
        return CC.money(value.price, 2) +
          '<br><span class="small muted">' + CC.esc(value.provider || "—") + "</span>";
      } },
    { label: "Spread", key: "spread", num: true, render: function (value) {
        return value == null ? '<span class="muted">—</span>' : CC.num(value, 2) + "×";
      } },
    { label: "P25–P75", key: "p25", num: true, render: function (_value, row) {
        if (row.p25 == null || row.p75 == null) {
          return '<span class="badge thin">样本偏薄</span>';
        }
        return CC.money(row.p25, 2) + "–" + CC.money(row.p75, 2);
      } },
    { label: "Providers", key: "providers", num: true, render: function (value) {
        return CC.num(value, 0);
      } }
  ];

  var rows = [];
  var ready = false;

  function buildGroups(prices) {
    var groups = {};
    prices.forEach(function (row) {
      var key = row.layer + "|" + row.card_key + "|" + row.market;
      var group = groups[key];
      if (!group) {
        group = groups[key] = {
          card: row.card_key,
          layer: row.layer,
          card_id: row.card_id,
          card_key: row.card_key,
          card_label: row.card_label,
          card_slug: CARD_SLUGS[row.card_id] || "",
          market: row.market,
          providerRows: {}
        };
      }
      var providerKey = row.provider_id || row.provider;
      var current = group.providerRows[providerKey];
      if (!current || row.price < current.price) {
        group.providerRows[providerKey] = row;
      }
    });
    return sortGroups(Object.keys(groups).map(function (key) {
      var group = groups[key];
      var providerRows = Object.keys(group.providerRows).map(function (providerKey) {
        return group.providerRows[providerKey];
      });
      var values = providerRows.map(function (row) {
        return row.price;
      }).sort(function (a, b) { return a - b; });
      var cheapest = null;
      var dearest = null;
      providerRows.forEach(function (row) {
        if (!cheapest || row.price < cheapest.price) { cheapest = row; }
        if (!dearest || row.price > dearest.price) { dearest = row; }
      });
      var n = providerRows.length;
      return {
        card: group.card,
        layer: group.layer,
        card_id: group.card_id,
        card_key: group.card_key,
        card_label: group.card_label,
        card_slug: group.card_slug,
        market: group.market,
        cheapest: cheapest,
        median: round6(median(values)),
        dearest: dearest,
        spread: cheapest && dearest && cheapest.price > 0
          ? dearest.price / cheapest.price : null,
        p25: n >= 4 ? round6(quantile(values, 0.25)) : null,
        p75: n >= 4 ? round6(quantile(values, 0.75)) : null,
        providers: n,
        quotes: values.length
      };
    }));
  }

  function render() {
    if (!ready) { return; }
    var filters = CC.readFilters(filtersRoot);
    var visible = CC.filterRows(rows, {
      card: filters.card,
      market: filters.market,
      layer: filters.layer
    }, { exact: ["card", "market", "layer"] });
    tableHost.innerHTML = CC.table(HEADERS, visible, {
      empty: "没有匹配的 card × market 组，请调整筛选。",
      caption: "同一 card × market 内按 provider 挂牌价计算；cheapest 与 dearest 是挂牌报价端点，不是成交价。"
    });
    tableHost.setAttribute("aria-busy", "false");
    if (countEl) { countEl.textContent = visible.length + " / " + rows.length + " 组"; }
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
  Promise.all([CC.get("prices.json"), CC.get("external/prices.json")])
    .then(function (documents) {
      rows = buildGroups(normalizePrices(documents[0], documents[1]));
      populateCardOptions(filtersRoot, rows, CONTEXT.cards || []);
      ready = true;
      render();
    })
    .catch(fail);
})();
"""


def _spread_body(
    index: Dict[str, Any],
    market_labels: Dict[str, str],
    market_order: List[str],
    external_mappable: int,
    external_nonfloor: int,
) -> str:
    counts = index.get("counts") or {}
    as_of = _text(index.get("as_of"))
    return f"""
<section class="hero compact">
  <p class="kicker">Spread · 挂牌价离散度 · as of {as_of}</p>
  <h1>同一张卡、同一个市场，报价差多少</h1>
  <p class="lede">按 card × market 把自有与 GPU Economy 的挂牌报价分开聚合，计算 cheapest、median、dearest、spread ratio 和 P25–P75。own 与 external 不合并。外部先按 market view 对齐 crosscheck，再对每个 provider 取最低价。</p>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">自有报价</div><div class="value">{_num(counts.get("own_quotes"))}</div><div class="hint">最新挂牌价，非成交价</div></div>
    <div class="kpi"><div class="label">外部 live+USD 可映射</div><div class="value">{_num(external_mappable)}</div><div class="hint">可按 MARKET_VIEWS 映射；含 marketplace floor</div></div>
    <div class="kpi"><div class="label">非 floor 可比</div><div class="value">{_num(external_nonfloor)}</div><div class="hint">全量 live+USD 非 floor 口径；表格再按 market view 筛选</div></div>
    <div class="kpi"><div class="label">外部原始报价</div><div class="value">{_num(counts.get("external_quotes"))}</div><div class="hint">含 stopped / 非 USD / 不可映射 market</div></div>
  </div>
  <p class="source">外部数据：GPU Economy · CC BY 4.0 · 仅作参考；自有中位数与周指数不受外部数据改写。</p>
</section>

<section class="section">
  <div class="section-head">
    <div>
      <h2>Card × market 分布</h2>
      <p class="sub">Spread = dearest ÷ cheapest；P25–P75 在 provider 少于 4 家时显示“样本偏薄”。</p>
    </div>
    <p class="small muted" id="spread-count">加载中…</p>
  </div>
  {_filters("spread", index, market_labels, market_order)}
  <div id="spread-table" aria-live="polite" aria-busy="true">
    <div class="empty" role="status">正在加载自有与外部报价…</div>
  </div>
  <p class="panel-note">表格里的 cheapest/dearest 是同一 card × market 下的挂牌报价端点，不是成交价，也不是可执行价差。外部按 <span class="mono">MARKET_VIEWS</span> 对齐 crosscheck：<span class="mono">status=live</span>、<span class="mono">listed_currency=USD</span>、符合该市场 scope，每个 provider 取最低价后计入 median/P25–P75；community 只用 instance，marketplace 只用 community 里的 floor（标 “floor，不是 rate card”）。own 与 external 分组独立。</p>
</section>
"""


# ---------------------------------------------------------------------------
# Cheapest


_CHEAPEST_SCRIPT = r"""
(function () {
  "use strict";
  var CC = window.CC;
  if (!CC) { return; }
  var CONTEXT = __CONTEXT__;
  var CARD_ORDER = CONTEXT.cardOrder || {};
  var CARD_SLUGS = CONTEXT.cardSlugs || {};
  var MARKET_LABELS = CONTEXT.marketLabels || {};
  var MARKET_ORDER = CONTEXT.marketOrder || [];
  var EXT_CARD = CONTEXT.extCard || {};
  var PROVIDER_SLUGS = CONTEXT.providerSlugs || {};
__SHARED__
  var tableHost = document.getElementById("cheapest-table");
  var countEl = document.getElementById("cheapest-count");
  var filtersRoot = document.getElementById("cheapest-filters");
  if (!tableHost) { return; }

  var HEADERS = [
    { label: "Layer", key: "layer", render: function (value) {
        return value === "own" ? CC.badge("own", "own") : CC.badge("gpueconomy", "ext");
      } },
    { label: "Card", key: "card_label", render: function (_value, row) {
        var html = cardLink(row);
        if (row.card_id) {
          html += '<br><span class="small muted">' + CC.esc(row.card_id) + "</span>";
        } else {
          html += '<br><span class="small muted">外部参考 · 无单卡页</span>';
        }
        return html;
      } },
    { label: "Market", key: "market", render: function (value) {
        var html = "<strong>" + CC.esc(marketLabel(value)) + "</strong>" +
          '<br><span class="small muted">' + CC.esc(value || "—") + "</span>";
        if (value === "marketplace") {
          html += '<br><span class="badge thin">floor，不是 rate card</span>';
        }
        return html;
      } },
    { label: "Cheapest provider", key: "provider", render: function (value, row) {
        var html = providerCell(row);
        if (row.provider_id) {
          html += '<br><span class="small muted">' + CC.esc(row.provider_id) + "</span>";
        }
        return html;
      } },
    { label: "Price", key: "price", num: true, render: function (value) {
        return CC.money(value, 2);
      } },
    { label: "Source", key: "source_url", render: function (value) {
        return sourceCell(value, "来源");
      } },
    { label: "Date", key: "date", className: "nowrap", render: function (value) {
        return CC.date(value);
      } },
    { label: "Risk", key: "risk", render: function (value) {
        return riskBadge(value);
      } },
    { label: "Status", key: "status", render: function (value) {
        return statusBadge(value);
      } },
    { label: "Scope", key: "scope", render: function (value) {
        return value ? '<span class="small mono">' + CC.esc(value) + "</span>" : '<span class="muted">—</span>';
      } }
  ];

  var rows = [];
  var ready = false;

  function buildCheapest(prices) {
    var groups = {};
    prices.forEach(function (row) {
      var key = row.layer + "|" + row.card_key + "|" + row.market;
      var group = groups[key];
      if (!group) {
        group = groups[key] = {
          card: row.card_key,
          layer: row.layer,
          card_id: row.card_id,
          card_key: row.card_key,
          card_label: row.card_label,
          card_slug: CARD_SLUGS[row.card_id] || "",
          market: row.market,
          providerRows: {}
        };
      }
      var providerKey = row.provider_id || row.provider;
      var current = group.providerRows[providerKey];
      if (!current || row.price < current.price) {
        group.providerRows[providerKey] = row;
      }
    });
    return Object.keys(groups).map(function (key) {
      var group = groups[key];
      var cheapest = null;
      Object.keys(group.providerRows).forEach(function (providerKey) {
        var row = group.providerRows[providerKey];
        if (!cheapest || row.price < cheapest.price) {
          cheapest = row;
        }
      });
      return {
        card: group.card,
        layer: group.layer,
        card_id: group.card_id,
        card_key: group.card_key,
        card_label: group.card_label,
        card_slug: group.card_slug,
        market: group.market,
        provider_id: cheapest.provider_id,
        provider: cheapest.provider,
        price: cheapest.price,
        source_url: cheapest.source_url,
        date: cheapest.date,
        risk: cheapest.risk,
        status: cheapest.status,
        scope: cheapest.scope
      };
    }).sort(function (left, right) {
      return layerSortValue(left) - layerSortValue(right) ||
        cardSortValue(left) - cardSortValue(right) ||
        String(left.card_label).localeCompare(String(right.card_label)) ||
        marketSortValue(left) - marketSortValue(right) ||
        String(left.market).localeCompare(String(right.market)) ||
        left.price - right.price;
    });
  }

  function render() {
    if (!ready) { return; }
    var filters = CC.readFilters(filtersRoot);
    var visible = CC.filterRows(rows, {
      card: filters.card,
      market: filters.market,
      layer: filters.layer
    }, { exact: ["card", "market", "layer"] });
    tableHost.innerHTML = CC.table(HEADERS, visible, {
      empty: "没有匹配的 cheapest 行，请调整筛选。",
      caption: "每个 card × market 只列最低挂牌报价；价格是 listed rate，不是成交价。"
    });
    tableHost.setAttribute("aria-busy", "false");
    if (countEl) { countEl.textContent = visible.length + " / " + rows.length + " 组"; }
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
  Promise.all([CC.get("prices.json"), CC.get("external/prices.json")])
    .then(function (documents) {
      rows = buildCheapest(normalizePrices(documents[0], documents[1]));
      populateCardOptions(filtersRoot, rows, CONTEXT.cards || []);
      ready = true;
      render();
    })
    .catch(fail);
})();
"""


def _cheapest_body(
    index: Dict[str, Any],
    market_labels: Dict[str, str],
    market_order: List[str],
    external_mappable: int,
    external_nonfloor: int,
) -> str:
    counts = index.get("counts") or {}
    as_of = _text(index.get("as_of"))
    return f"""
<section class="hero compact">
  <p class="kicker">Cheapest · 最低挂牌价 · as of {as_of}</p>
  <h1>每个 card × market 的最低报价</h1>
  <p class="lede">按卡、市场和 layer 过滤，列出每个组合的最低挂牌 provider、价格、来源、日期与风险。自有与 GPU Economy 分开；外部按 market view 对齐 crosscheck，先对每个 provider 取最低价。</p>
  <div class="kpi-grid">
    <div class="kpi"><div class="label">自有报价</div><div class="value">{_num(counts.get("own_quotes"))}</div><div class="hint">最新挂牌价，非成交价</div></div>
    <div class="kpi"><div class="label">外部 live+USD 可映射</div><div class="value">{_num(external_mappable)}</div><div class="hint">可按 MARKET_VIEWS 映射；含 marketplace floor</div></div>
    <div class="kpi"><div class="label">非 floor 可比</div><div class="value">{_num(external_nonfloor)}</div><div class="hint">全量 live+USD 非 floor 口径；表格再按 market view 筛选</div></div>
    <div class="kpi"><div class="label">外部原始报价</div><div class="value">{_num(counts.get("external_quotes"))}</div><div class="hint">含 stopped / 非 USD / 不可映射 market</div></div>
  </div>
  <p class="source">最低价是公开挂牌价，不等于可成交价或可用容量；外部报价不改写自有中位数、周指数或 provider 计数。</p>
</section>

<section class="section">
  <div class="section-head">
    <div>
      <h2>Cheapest 明细</h2>
      <p class="sub">每一行是该 card × market × layer 的最低挂牌报价。</p>
    </div>
    <p class="small muted" id="cheapest-count">加载中…</p>
  </div>
  {_filters("cheapest", index, market_labels, market_order)}
  <div id="cheapest-table" aria-live="polite" aria-busy="true">
    <div class="empty" role="status">正在加载自有与外部报价…</div>
  </div>
  <p class="panel-note">价格与来源仅代表公开挂牌信息；<strong>不是成交价</strong>。外部按 <span class="mono">MARKET_VIEWS</span> 对齐 crosscheck（live、USD、market scope、每个 provider 最低价），marketplace 使用 community 里的 floor 并标 “floor，不是 rate card”。stopped、非 USD、无法映射 market 的原始行会在浏览器端剔除，因此页面计数可能小于 <span class="mono">external/prices.json</span> 的 {_num(counts.get("external_quotes"))} 条。</p>
</section>
"""


# ---------------------------------------------------------------------------
# Public entry point


def _context(
    index: Dict[str, Any],
    crosscheck: Dict[str, Any],
    market_labels: Dict[str, str],
    market_order: List[str],
    include_providers: bool,
) -> Dict[str, Any]:
    cards = index.get("cards") or []
    context: Dict[str, Any] = {
        "cards": [
            {
                "id": card.get("id"),
                "slug": card.get("slug"),
                "name": card.get("name") or card.get("id"),
                "median": card.get("median"),
                "provider_count": card.get("provider_count"),
            }
            for card in cards
        ],
        "cardOrder": {
            str(card.get("id")): position for position, card in enumerate(cards)
        },
        "cardSlugs": {
            str(card.get("id")): card.get("slug") for card in cards if card.get("slug")
        },
        "marketLabels": market_labels,
        "marketOrder": market_order,
        "marketViews": MARKET_VIEWS,
        "extCard": _ext_card_map(crosscheck),
    }
    if include_providers:
        context["providerSlugs"] = _provider_slugs(index)
    return context


def write_tool_pages(public_dir: Path) -> List[str]:
    """Write ``compare.html``, ``spread.html`` and ``cheapest.html``.

    Returns absolute paths in that order.  The caller must write the site data
    slices first (``site_data.write_site_data``) and the ``crosscheck.json``
    file for external card links.
    """
    public_dir = Path(public_dir).resolve()
    index = _load(public_dir, "data/site-index.json")
    external_prices = _load(public_dir, "data/external/prices.json")
    crosscheck = _load_optional(public_dir, "data/crosscheck.json")
    market_labels, market_order = _market_catalog(index)
    external_effective = _effective_external_count(external_prices)
    external_nonfloor = _nonfloor_external_count(external_prices)

    written: List[str] = []

    compare_context = _context(
        index, crosscheck, market_labels, market_order, include_providers=False
    )
    compare_script = _COMPARE_SCRIPT.replace("__CONTEXT__", _js_json(compare_context))
    compare_html = page(
        "Compare",
        "选择 2–4 张 GPU，把各自周指数在共同起点重定基为 100，比较相对变化。",
        ".",
        "compare.html",
        _compare_body(index),
        compare_script,
    )
    compare_path = public_dir / "compare.html"
    compare_path.write_text(compare_html, encoding="utf-8")
    written.append(str(compare_path))

    price_context = _context(
        index, crosscheck, market_labels, market_order, include_providers=True
    )
    price_context_json = _js_json(price_context)
    shared_js = _SHARED_PRICE_JS

    spread_script = (
        _SPREAD_SCRIPT.replace("__CONTEXT__", price_context_json)
        .replace("__SHARED__", shared_js)
    )
    spread_html = page(
        "Spread",
        "按 card × market 比较自有与 GPU Economy 挂牌价的 cheapest、median、dearest、spread ratio 和 P25–P75。",
        ".",
        "spread.html",
        _spread_body(
            index,
            market_labels,
            market_order,
            external_effective,
            external_nonfloor,
        ),
        spread_script,
    )
    spread_path = public_dir / "spread.html"
    spread_path.write_text(spread_html, encoding="utf-8")
    written.append(str(spread_path))

    cheapest_script = (
        _CHEAPEST_SCRIPT.replace("__CONTEXT__", price_context_json)
        .replace("__SHARED__", shared_js)
    )
    cheapest_html = page(
        "Cheapest",
        "按 card、market、layer 过滤，列出每个组合的最低挂牌 provider、价格、来源、日期与风险。",
        ".",
        "cheapest.html",
        _cheapest_body(
            index,
            market_labels,
            market_order,
            external_effective,
            external_nonfloor,
        ),
        cheapest_script,
    )
    cheapest_path = public_dir / "cheapest.html"
    cheapest_path.write_text(cheapest_html, encoding="utf-8")
    written.append(str(cheapest_path))

    return written
