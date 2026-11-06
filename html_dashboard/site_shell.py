"""Shared HTML shell, CSS and JavaScript for the standalone static pages.

The pages are plain files: no framework, no CDN, no build step.  All links are
relative to ``base`` (``"."`` at the public root, ``".."`` inside ``gpu/`` and
``providers/``) so the site works from a GitHub Pages project sub-path.
"""

from __future__ import annotations

from html import escape
from pathlib import Path


NAV = [
    ("index.html", "总览"),
    ("landscape.html", "Landscape"),
    ("providers.html", "Providers"),
    ("compare.html", "Compare"),
    ("spread.html", "Spread"),
    ("cheapest.html", "Cheapest"),
]

_NAV_ALIASES = {
    "gpu": "landscape.html",
    "card": "landscape.html",
    "cards": "landscape.html",
    "landscape": "landscape.html",
    "providers": "providers.html",
    "provider": "providers.html",
    "own": "providers.html",
    "ext": "providers.html",
    "external": "providers.html",
    "index": "index.html",
}

SITE_CSS = r"""
:root{--bg:#f5f5f7;--paper:#fff;--ink:#1d1d1f;--muted:#6e6e73;--line:#d2d2d7;--blue:#0071e3;--cyan:#00a6a6;--green:#248a3d;--orange:#d76b00;--red:#d70015;--purple:#8944ab;--radius:8px;--max:1440px}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%;scroll-behavior:smooth}
html,body{max-width:100%;overflow-x:hidden}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI","Noto Sans SC",sans-serif;font-size:15px;line-height:1.5;letter-spacing:0}
a{color:var(--blue);text-decoration:none}
a:hover{text-decoration:underline}
img,svg{max-width:100%}
.skip{position:absolute;left:-9999px;top:0;z-index:100;padding:10px 14px;border-radius:0 0 8px 0;background:var(--ink);color:#fff}
.skip:focus{left:0}
.topbar{position:sticky;top:0;z-index:30;border-bottom:1px solid rgba(0,0,0,.08);background:rgba(245,245,247,.88);backdrop-filter:saturate(180%) blur(14px);-webkit-backdrop-filter:saturate(180%) blur(14px)}
.topbar-inner{max-width:var(--max);margin:0 auto;min-height:52px;padding:0 28px;display:flex;align-items:center;justify-content:space-between;gap:18px}
.brand{flex:none;color:var(--ink);font-size:15px;font-weight:650;white-space:nowrap;letter-spacing:-.01em}
.brand:hover{text-decoration:none;color:var(--blue)}
.nav{display:flex;align-items:center;gap:3px;min-width:0;overflow-x:auto;scrollbar-width:none;-webkit-overflow-scrolling:touch}
.nav::-webkit-scrollbar{display:none}
.nav a{flex:none;padding:7px 10px;border-radius:6px;color:var(--muted);font-size:13px;line-height:1.2;text-decoration:none;white-space:nowrap}
.nav a:hover{background:#fff;color:var(--ink);text-decoration:none}
.nav a.active{background:var(--ink);color:#fff}
.shell{max-width:var(--max);margin:0 auto;padding:0 28px 64px}
.hero{padding:42px 0 26px;border-bottom:1px solid var(--line)}
.hero.compact{padding:30px 0 22px}
.kicker{margin:0 0 8px;color:var(--muted);font-size:11px;font-weight:650;letter-spacing:.08em;text-transform:uppercase}
h1{margin:0;font-size:42px;line-height:1.12;font-weight:700;letter-spacing:-.02em;overflow-wrap:anywhere}
h2{margin:0;font-size:25px;line-height:1.2;letter-spacing:-.01em}
h3{margin:0;font-size:17px;line-height:1.35}
.lede,.sub{margin:10px 0 0;color:var(--muted);font-size:16px;max-width:860px}
.section{padding:32px 0 8px;border-bottom:1px solid var(--line);scroll-margin-top:64px}
.section:last-child{border-bottom:0}
.section-head{display:flex;align-items:baseline;justify-content:space-between;gap:18px;flex-wrap:wrap;margin-bottom:16px}
.panel{min-width:0;padding:20px;border:1px solid rgba(0,0,0,.09);border-radius:var(--radius);background:var(--paper);box-shadow:0 1px 2px rgba(0,0,0,.03)}
.panel.full{grid-column:1/-1}
.panel-head{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:14px}
.panel-head p{margin:4px 0 0;color:var(--muted);font-size:13px}
.panel-note{margin:8px 0 0;color:var(--muted);font-size:12px;line-height:1.45}
.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;min-width:0}
.grid>*{min-width:0}
.stack{display:flex;flex-direction:column;gap:16px;min-width:0}
.stack>*{min-width:0}
.toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px;flex-wrap:wrap;margin-bottom:16px}
.muted{color:var(--muted)}
.small{font-size:12px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace}
.num{font-variant-numeric:tabular-nums}
.kpi-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;min-width:0}
.kpi{min-width:0;padding:14px 16px;border:1px solid rgba(0,0,0,.08);border-radius:var(--radius);background:var(--paper)}
.kpi .label{color:var(--muted);font-size:11px;font-weight:650;letter-spacing:.05em;text-transform:uppercase}
.kpi .value{margin-top:5px;font-size:22px;font-weight:650;line-height:1.2;letter-spacing:-.01em;overflow-wrap:anywhere}
.kpi .hint{margin-top:3px;color:var(--muted);font-size:11px}
.filters{display:flex;align-items:end;flex-wrap:wrap;gap:10px;min-width:0;margin:0 0 16px}
.field{display:flex;flex-direction:column;gap:5px;flex:1 1 160px;min-width:0;max-width:280px}
.field label{color:var(--muted);font-size:11px;font-weight:650;letter-spacing:.05em;text-transform:uppercase}
.field input,.field select{width:100%;height:36px;padding:0 10px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit;font-size:13px}
.field input:focus,.field select:focus{outline:2px solid rgba(0,113,227,.28);outline-offset:1px;border-color:var(--blue)}
.segmented{display:inline-flex;padding:3px;border:1px solid var(--line);border-radius:7px;background:#fff}
.segmented button{height:28px;padding:0 11px;border:0;border-radius:5px;background:transparent;color:var(--muted);font:inherit;font-size:12px;cursor:pointer}
.segmented button.active{background:var(--ink);color:#fff}
.badge{display:inline-flex;align-items:center;gap:4px;max-width:100%;padding:2px 7px;border:1px solid transparent;border-radius:99px;background:#eef0f2;color:var(--muted);font-size:11px;font-weight:600;line-height:1.5;white-space:nowrap;vertical-align:middle}
.badge.low,.badge.ok,.badge.live,.badge.published{background:#e8f5ec;color:#1d6b32}
.badge.medium,.badge.thin,.badge.mixed,.badge.sku_mismatch,.badge.sku-mismatch,.badge.unconfirmed{background:#fff4e5;color:#8f4a00}
.badge.high,.badge.warn,.badge.stopped,.badge.withheld,.badge.no_data{background:#fdecec;color:#a30012}
.badge.own{background:#e8f1fd;color:#0059b3}
.badge.ext{background:#f1ecf9;color:#6b3d91}
.table-wrap{width:100%;max-width:100%;overflow-x:auto;border:1px solid rgba(0,0,0,.08);border-radius:var(--radius);background:var(--paper);-webkit-overflow-scrolling:touch}
table.data{width:100%;min-width:680px;border-collapse:collapse;font-size:13px}
table.data.compact{min-width:520px}
table.data caption{caption-side:top;padding:12px 14px 0;color:var(--muted);font-size:12px;text-align:left}
table.data th,table.data td{padding:10px 12px;border-bottom:1px solid #ececf0;text-align:left;vertical-align:top}
table.data th{background:#fafafc;color:var(--muted);font-size:11px;font-weight:650;letter-spacing:.04em;text-transform:uppercase;white-space:nowrap}
table.data tr:last-child td{border-bottom:0}
table.data tbody tr:hover td{background:#fbfbfd}
table.data td{overflow-wrap:anywhere}
table.data td.nowrap,table.data th.nowrap{white-space:nowrap}
table.data td.num,table.data th.num{text-align:right;white-space:nowrap;font-variant-numeric:tabular-nums}
table.data a{font-weight:500}
.empty{padding:30px 20px;border:1px dashed var(--line);border-radius:var(--radius);background:rgba(255,255,255,.65);color:var(--muted);font-size:13px;text-align:center}
.chart{position:relative;width:100%;min-width:0}
.chart-plot{position:relative;width:100%;min-width:0}
.chart svg{display:block;width:100%;height:auto;overflow:visible}
.chart-grid line{stroke:#e6e6eb;stroke-width:1}
.chart-grid text,.chart-axis text{fill:var(--muted);font-size:11px;font-family:-apple-system,BlinkMacSystemFont,"SF Pro Text","Segoe UI",sans-serif}
.chart-ylabel{fill:var(--muted);font-size:10px;letter-spacing:.04em;text-transform:uppercase}
.chart-lines path{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.chart-legend{display:flex;flex-wrap:wrap;gap:10px 14px;margin:0 0 8px;color:var(--muted);font-size:12px}
.legend-item{display:inline-flex;align-items:center;gap:6px;min-width:0}
.legend-swatch{flex:none;width:10px;height:10px;border-radius:50%}
.chart-tooltip{position:absolute;z-index:3;display:none;max-width:240px;padding:7px 9px;border-radius:6px;background:rgba(29,29,31,.94);color:#fff;font-size:11px;line-height:1.45;pointer-events:none;box-shadow:0 4px 16px rgba(0,0,0,.18)}
.chart-tooltip.visible{display:block}
.chart-tooltip .muted{color:#c7c7cc}
.note{margin:0;padding:12px 14px;border-left:3px solid var(--line);background:rgba(255,255,255,.6);color:var(--muted);font-size:12px;line-height:1.55}
.source{margin:10px 0 0;color:var(--muted);font-size:11px;line-height:1.55;overflow-wrap:anywhere}
.footer{margin-top:48px;border-top:1px solid var(--line);background:rgba(255,255,255,.45)}
.footer-inner{max-width:var(--max);margin:0 auto;padding:22px 28px;color:var(--muted);font-size:11px;line-height:1.6}
.footer p{margin:0 0 3px}
.footer a{color:var(--muted);text-decoration:underline}
.row-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:12px}
.btn{display:inline-flex;align-items:center;justify-content:center;min-height:34px;padding:0 12px;border:1px solid var(--line);border-radius:6px;background:#fff;color:var(--ink);font:inherit;font-size:12px;cursor:pointer;text-decoration:none}
.btn:hover{border-color:var(--muted);text-decoration:none}
.btn.primary{background:var(--ink);border-color:var(--ink);color:#fff}
@media(max-width:820px){
 .topbar-inner{min-height:0;padding:8px 16px 6px;flex-wrap:wrap;gap:4px}
 .brand{font-size:14px}
 .nav{width:100%;padding-bottom:2px}
 .shell{padding:0 16px 48px}
 h1{font-size:32px}
 h2{font-size:22px}
 .lede,.sub{font-size:15px}
 .hero{padding:30px 0 22px}
 .grid{grid-template-columns:minmax(0,1fr)}
 .section{padding:26px 0 6px}
 .panel{padding:16px}
 .footer-inner{padding:18px 16px}
}
@media(max-width:560px){
 h1{font-size:28px}
 .kicker{font-size:10px}
 .kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
 .kpi{padding:12px}
 .kpi .value{font-size:19px}
 .field{flex:1 1 100%;max-width:none}
 .hero{padding:26px 0 18px}
 .panel{padding:14px}
 table.data{font-size:12px}
 table.data th,table.data td{padding:8px 10px}
 .footer{margin-top:36px}
}
@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
"""


SITE_JS = r"""
(function () {
  "use strict";
  var body = document.body;
  var base = (body && body.getAttribute("data-base")) || ".";
  var CC = (window.CC = window.CC || {});
  CC.base = base;

  function strip(path) {
    return String(path == null ? "" : path).replace(/^\/+/, "");
  }

  CC.asset = function (path) {
    return base + "/" + strip(path);
  };

  CC.get = function (path) {
    var url = base + "/data/" + strip(path);
    return fetch(url, { cache: "no-store" }).then(function (response) {
      if (!response.ok) {
        throw new Error("HTTP " + response.status + " · " + url);
      }
      return response.json();
    });
  };
  CC.fetchJSON = CC.get;

  var ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  CC.esc = function (value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (ch) {
      return ESC[ch];
    });
  };

  CC.num = function (value, digits) {
    var number = Number(value);
    if (value === null || value === undefined || value === "" || !isFinite(number)) {
      return "—";
    }
    var places = digits == null ? 0 : digits;
    return number.toLocaleString("en-US", {
      minimumFractionDigits: places,
      maximumFractionDigits: places
    });
  };

  CC.money = function (value, digits) {
    var number = Number(value);
    if (value === null || value === undefined || value === "" || !isFinite(number)) {
      return "—";
    }
    var places = digits == null ? 2 : digits;
    return "$" + number.toFixed(places);
  };

  CC.pct = function (value, digits) {
    var number = Number(value);
    if (value === null || value === undefined || value === "" || !isFinite(number)) {
      return "—";
    }
    var places = digits == null ? 1 : digits;
    return (number > 0 ? "+" : "") + number.toFixed(places) + "%";
  };

  CC.date = function (value) {
    if (value === null || value === undefined || value === "") {
      return "—";
    }
    return String(value).slice(0, 10);
  };

  CC.weekLabel = function (week) {
    if (!week) {
      return "—";
    }
    if (typeof week === "string") {
      return week;
    }
    if (week.isoWeek) {
      return week.weekStart ? week.isoWeek + " · " + week.weekStart : week.isoWeek;
    }
    return week.weekStart || week.date || "—";
  };

  CC.link = function (text, href, opts) {
    opts = opts || {};
    var attrs = ' href="' + CC.esc(href || "#") + '"';
    if (opts.className) {
      attrs += ' class="' + CC.esc(opts.className) + '"';
    }
    if (opts.title) {
      attrs += ' title="' + CC.esc(opts.title) + '"';
    }
    if (opts.target) {
      attrs += ' target="' + CC.esc(opts.target) + '" rel="noopener"';
    }
    return "<a" + attrs + ">" + CC.esc(text) + "</a>";
  };

  CC.badge = function (text, tone) {
    return '<span class="badge ' + CC.esc(tone || "") + '">' + CC.esc(text) + "</span>";
  };

  CC.empty = function (message) {
    return '<div class="empty" role="status">' + CC.esc(message || "暂无数据") + "</div>";
  };

  CC.table = function (headers, rows, opts) {
    opts = opts || {};
    var normalized = (headers || []).map(function (header) {
      return typeof header === "string" ? { label: header } : Object.assign({}, header);
    });
    rows = rows || [];
    if (!rows.length) {
      return CC.empty(opts.empty || "暂无数据");
    }
    var keys = opts.keys || normalized.map(function (header) { return header.key; });
    var head = normalized.map(function (header) {
      var classes = [];
      if (header.align === "right" || header.num) { classes.push("num"); }
      if (header.className) { classes.push(header.className); }
      var attrs = classes.length ? ' class="' + CC.esc(classes.join(" ")) + '"' : "";
      if (header.title) { attrs += ' title="' + CC.esc(header.title) + '"'; }
      return "<th" + attrs + ">" + CC.esc(header.label) + "</th>";
    }).join("");
    var bodyRows = rows.map(function (row, rowIndex) {
      var cells = normalized.map(function (header, index) {
        var value;
        if (Array.isArray(row)) {
          value = row[index];
        } else if (header.key) {
          value = row[header.key];
        } else if (keys[index]) {
          value = row[keys[index]];
        } else {
          value = row[header.label];
        }
        var content;
        if (typeof header.render === "function") {
          content = header.render(value, row, index);
        } else if (opts.render && header.key && typeof opts.render[header.key] === "function") {
          content = opts.render[header.key](value, row, index);
        } else {
          content = CC.esc(value == null || value === "" ? "—" : value);
        }
        var classes = [];
        if (header.align === "right" || header.num) { classes.push("num"); }
        if (header.cellClass) { classes.push(header.cellClass); }
        var attrs = classes.length ? ' class="' + CC.esc(classes.join(" ")) + '"' : "";
        return "<td" + attrs + ">" + content + "</td>";
      }).join("");
      var rowClass = typeof opts.rowClass === "function" ? opts.rowClass(row, rowIndex) : "";
      return "<tr" + (rowClass ? ' class="' + CC.esc(rowClass) + '"' : "") + ">" + cells + "</tr>";
    }).join("");
    var caption = opts.caption ? "<caption>" + CC.esc(opts.caption) + "</caption>" : "";
    var className = "data";
    if (opts.compact) { className += " compact"; }
    if (opts.className) { className += " " + opts.className; }
    return '<div class="table-wrap"><table class="' + CC.esc(className) + '">' + caption +
      "<thead><tr>" + head + "</tr></thead><tbody>" + bodyRows + "</tbody></table></div>";
  };

  CC.filterRows = function (rows, filters, opts) {
    opts = opts || {};
    var exact = opts.exact || [];
    var entries = Object.keys(filters || {});
    return (rows || []).filter(function (row) {
      return entries.every(function (key) {
        var wanted = filters[key];
        if (wanted === null || wanted === undefined || wanted === "") {
          return true;
        }
        var actual = row ? row[key] : undefined;
        if (Array.isArray(actual)) { actual = actual.join(" "); }
        if (typeof wanted === "function") {
          return !!wanted(actual, row);
        }
        if (exact.indexOf(key) >= 0) {
          return String(actual) === String(wanted);
        }
        return String(actual == null ? "" : actual).toLowerCase().indexOf(String(wanted).toLowerCase()) >= 0;
      });
    });
  };

  CC.readFilters = function (root) {
    root = typeof root === "string" ? document.querySelector(root) : root;
    var values = {};
    if (!root) { return values; }
    root.querySelectorAll("[data-filter]").forEach(function (element) {
      values[element.getAttribute("data-filter")] = element.value;
    });
    return values;
  };

  CC.bindFilters = function (root, handler) {
    root = typeof root === "string" ? document.querySelector(root) : root;
    if (!root) { return function () {}; }
    var run = function () {
      if (typeof handler === "function") {
        handler(CC.readFilters(root));
      }
    };
    root.addEventListener("input", run);
    root.addEventListener("change", run);
    run();
    return run;
  };

  function parseDay(value) {
    var text = CC.date(value);
    var stamp = Date.parse(text + "T00:00:00Z");
    return isFinite(stamp) ? stamp : NaN;
  }

  function finiteValue(value) {
    if (value === null || value === undefined) {
      return null;
    }
    if (typeof value === "string" && value.trim() === "") {
      return null;
    }
    var number = Number(value);
    return isFinite(number) ? number : null;
  }

  function niceStep(span, count) {
    var rough = span / Math.max(1, count);
    var power = Math.pow(10, Math.floor(Math.log(rough) / Math.LN10));
    var norm = rough / power;
    var step;
    if (norm <= 1) { step = 1; }
    else if (norm <= 2) { step = 2; }
    else if (norm <= 2.5) { step = 2.5; }
    else if (norm <= 5) { step = 5; }
    else { step = 10; }
    return step * power;
  }

  var chartRegistry = [];
  var chartResizeTimer = null;
  var chartObserver = null;

  function redrawChartIfNeeded(host, width) {
    for (var index = 0; index < chartRegistry.length; index += 1) {
      var entry = chartRegistry[index];
      if (entry.host !== host) { continue; }
      if (Math.abs(width - entry.width) > 1) {
        entry.width = width;
        CC.lineChart(host, entry.series, entry.opts);
      }
      return;
    }
  }

  function observeChart(host) {
    if (typeof window.ResizeObserver !== "function") { return; }
    if (!chartObserver) {
      chartObserver = new window.ResizeObserver(function (entries) {
        entries.forEach(function (entry) {
          var width = entry.contentRect ? entry.contentRect.width : entry.target.clientWidth;
          redrawChartIfNeeded(entry.target, Number(width) || 0);
        });
      });
    }
    chartObserver.observe(host);
  }

  function rememberChart(host, series, opts) {
    var existing = null;
    for (var index = 0; index < chartRegistry.length; index += 1) {
      if (chartRegistry[index].host === host) {
        existing = chartRegistry[index];
        break;
      }
    }
    var width = Number(host.clientWidth) || 0;
    if (existing) {
      existing.series = series;
      existing.opts = opts;
      existing.width = width;
    } else {
      chartRegistry.push({ host: host, series: series, opts: opts, width: width });
    }
    observeChart(host);
  }

  function redrawCharts() {
    chartResizeTimer = null;
    chartRegistry = chartRegistry.filter(function (entry) {
      var keep = !!entry.host;
      if (keep && typeof document.body.contains === "function") {
        keep = document.body.contains(entry.host);
      }
      if (!keep && chartObserver && entry.host) {
        chartObserver.unobserve(entry.host);
      }
      return keep;
    });
    chartRegistry.forEach(function (entry) {
      redrawChartIfNeeded(entry.host, Number(entry.host.clientWidth) || 0);
    });
  }

  if (typeof window.addEventListener === "function") {
    window.addEventListener("resize", function () {
      if (chartResizeTimer !== null) {
        clearTimeout(chartResizeTimer);
      }
      chartResizeTimer = setTimeout(redrawCharts, 150);
    });
  }

  CC.lineChart = function (host, series, opts) {
    host = typeof host === "string" ? document.querySelector(host) : host;
    if (!host) { return null; }
    opts = opts || {};
    rememberChart(host, series, opts);

    var normalize = !!opts.normalize;
    var zero = !!opts.zero;
    var kind = opts.kind || (normalize ? "index" : "price");
    var palette = ["#0071e3", "#d76b00", "#248a3d", "#8944ab", "#00a6a6", "#d70015"];
    var lines = (series || []).map(function (item, index) {
      var points = (item.points || []).map(function (point) {
        var stamp = parseDay(point.date);
        var value = finiteValue(point.value);
        return {
          date: CC.date(point.date),
          stamp: stamp,
          value: value,
          raw: value
        };
      }).filter(function (point) {
        return isFinite(point.stamp);
      }).sort(function (left, right) {
        return left.stamp - right.stamp;
      });
      if (normalize && points.length) {
        var start = null;
        for (var index = 0; index < points.length; index += 1) {
          if (points[index].value !== null) {
            start = points[index].value;
            break;
          }
        }
        if (start) {
          points = points.map(function (point) {
            if (point.value === null) { return point; }
            return {
              date: point.date,
              stamp: point.stamp,
              value: point.value / start * 100,
              raw: point.raw
            };
          });
        }
      }
      return {
        name: item.name || "Series " + (index + 1),
        color: item.color || palette[index % palette.length],
        points: points
      };
    }).filter(function (line) {
      return line.points.some(function (point) { return point.value !== null; });
    });

    if (!lines.length) {
      host.innerHTML = CC.empty(opts.empty || "暂无可绘制的数据");
      return null;
    }

    var measuredWidth = Number(host.clientWidth) || 0;
    var width = Math.max(320, Math.min(1000, measuredWidth || 760));
    var height = Math.max(180, Number(opts.height) || 260);
    var narrow = width < 480;
    var margin = {
      top: 14,
      right: narrow ? 12 : 18,
      bottom: narrow ? 30 : 34,
      left: narrow ? 52 : 58
    };
    var plotWidth = width - margin.left - margin.right;
    var plotHeight = height - margin.top - margin.bottom;
    var minTime = Infinity;
    var maxTime = -Infinity;
    var values = [];
    var dateMap = {};
    lines.forEach(function (line) {
      line.points.forEach(function (point) {
        if (point.value === null) { return; }
        if (point.stamp < minTime) { minTime = point.stamp; }
        if (point.stamp > maxTime) { maxTime = point.stamp; }
        values.push(point.value);
        dateMap[point.date] = point.stamp;
      });
    });
    if (minTime === maxTime) {
      minTime -= 86400000;
      maxTime += 86400000;
    }
    var minValue = Math.min.apply(null, values);
    var maxValue = Math.max.apply(null, values);
    if (zero) { minValue = Math.min(0, minValue); }
    if (minValue === maxValue) {
      var pad = Math.abs(minValue) * 0.05 || 1;
      minValue -= pad;
      maxValue += pad;
    } else {
      var padding = (maxValue - minValue) * 0.06;
      minValue -= padding;
      maxValue += padding;
      if (zero && minValue > 0) { minValue = 0; }
    }

    var step = niceStep(maxValue - minValue, narrow ? 3 : 4);
    var tickStart = Math.ceil(minValue / step) * step;
    var ticks = [];
    for (var tick = tickStart; tick <= maxValue + step * 0.001; tick += step) {
      ticks.push(tick);
    }
    if (!ticks.length) { ticks = [minValue, maxValue]; }

    function xScale(stamp) {
      return margin.left + (stamp - minTime) / (maxTime - minTime) * plotWidth;
    }
    function yScale(value) {
      return margin.top + (maxValue - value) / (maxValue - minValue) * plotHeight;
    }
    function formatValue(value) {
      if (typeof opts.format === "function") { return opts.format(value); }
      if (kind === "index") { return CC.num(value, 1); }
      if (kind === "pct") { return CC.num(value, 1) + "%"; }
      return CC.money(value, Math.abs(value) < 1 ? 3 : 2);
    }

    var gapDays = Number(opts.maxGapDays);
    if (!isFinite(gapDays) || gapDays <= 0) { gapDays = 14; }
    var gapMs = gapDays * 86400000;
    function segmentsFor(points) {
      var segments = [];
      var current = [];
      var lastStamp = null;
      points.forEach(function (point) {
        if (point.value === null) {
          if (current.length) {
            segments.push(current);
            current = [];
          }
          lastStamp = null;
          return;
        }
        if (lastStamp !== null && point.stamp - lastStamp > gapMs) {
          if (current.length) {
            segments.push(current);
            current = [];
          }
        }
        current.push(point);
        lastStamp = point.stamp;
      });
      if (current.length) { segments.push(current); }
      return segments;
    }

    var svg = ['<svg viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="' +
      CC.esc(opts.ariaLabel || "折线图") + '">'];
    svg.push('<g class="chart-grid">');
    ticks.forEach(function (tick) {
      var y = yScale(tick);
      svg.push('<line x1="' + margin.left + '" y1="' + y.toFixed(2) + '" x2="' +
        (width - margin.right) + '" y2="' + y.toFixed(2) + '"></line>');
      svg.push('<text x="' + (margin.left - 8) + '" y="' + y.toFixed(2) +
        '" text-anchor="end" dominant-baseline="middle">' + CC.esc(formatValue(tick)) + "</text>");
    });
    if (opts.yLabel) {
      svg.push('<text class="chart-ylabel" x="14" y="' + (height / 2).toFixed(2) +
        '" text-anchor="middle" transform="rotate(-90 14 ' + (height / 2).toFixed(2) + ')">' +
        CC.esc(opts.yLabel) + "</text>");
    }
    svg.push("</g>");

    var dateList = Object.keys(dateMap).sort(function (left, right) {
      return dateMap[left] - dateMap[right];
    });
    var labelLimit = width < 480 ? 4 : width < 760 ? 5 : 6;
    var labelCount = Math.min(labelLimit, Math.max(2, dateList.length));
    var labelIndexes = [];
    for (var index = 0; index < labelCount; index += 1) {
      labelIndexes.push(Math.round(index * (dateList.length - 1) / (labelCount - 1)));
    }
    labelIndexes = labelIndexes.filter(function (value, position, list) {
      return list.indexOf(value) === position;
    });
    svg.push('<g class="chart-axis">');
    labelIndexes.forEach(function (index) {
      var date = dateList[index];
      var x = xScale(dateMap[date]);
      svg.push('<text x="' + x.toFixed(2) + '" y="' + (height - (narrow ? 8 : 10)) +
        '" text-anchor="middle"><title>' + CC.esc(date) + "</title>" + CC.esc(date.slice(5)) + "</text>");
    });
    svg.push("</g>");

    svg.push('<g class="chart-lines">');
    lines.forEach(function (line) {
      segmentsFor(line.points).forEach(function (segment) {
        var path = segment.map(function (point, position) {
          return (position ? "L" : "M") + xScale(point.stamp).toFixed(2) + " " + yScale(point.value).toFixed(2);
        }).join(" ");
        svg.push('<path d="' + path + '" stroke="' + CC.esc(line.color) +
          '" vector-effect="non-scaling-stroke"></path>');
      });
    });
    svg.push("</g>");

    svg.push('<g class="chart-points">');
    lines.forEach(function (line) {
      line.points.forEach(function (point) {
        if (point.value === null) { return; }
        svg.push('<circle cx="' + xScale(point.stamp).toFixed(2) + '" cy="' +
          yScale(point.value).toFixed(2) + '" r="2.8" fill="' + CC.esc(line.color) +
          '" stroke="#fff" stroke-width="1.3" pointer-events="none"></circle>');
      });
    });
    lines.forEach(function (line) {
      line.points.forEach(function (point) {
        if (point.value === null) { return; }
        svg.push('<circle class="chart-hit" cx="' + xScale(point.stamp).toFixed(2) + '" cy="' +
          yScale(point.value).toFixed(2) + '" r="9" fill="transparent" stroke="none" data-date="' +
          CC.esc(point.date) + '" data-name="' + CC.esc(line.name) + '" data-color="' +
          CC.esc(line.color) + '" data-value="' + CC.esc(point.value) + '" data-raw="' +
          CC.esc(point.raw) + '"></circle>');
      });
    });
    svg.push("</g></svg>");

    var legend = '<div class="chart-legend">' + lines.map(function (line) {
      return '<span class="legend-item"><i class="legend-swatch" style="background:' +
        CC.esc(line.color) + '"></i>' + CC.esc(line.name) + "</span>";
    }).join("") + "</div>";
    host.classList.add("chart");
    host.innerHTML = legend + '<div class="chart-plot">' + svg.join("") +
      '<div class="chart-tooltip" role="status"></div></div>';

    var plot = host.querySelector(".chart-plot");
    var tooltip = host.querySelector(".chart-tooltip");
    host.querySelectorAll(".chart-hit").forEach(function (circle) {
      var show = function () {
        var circleRect = circle.getBoundingClientRect();
        var plotRect = plot.getBoundingClientRect();
        if (!plotRect.width) { return; }
        var value = Number(circle.getAttribute("data-value"));
        var raw = Number(circle.getAttribute("data-raw"));
        var html = "<strong>" + CC.esc(circle.getAttribute("data-date")) + "</strong><br>" +
          '<span class="legend-swatch" style="display:inline-block;background:' +
          CC.esc(circle.getAttribute("data-color")) + '"></span> ' +
          CC.esc(circle.getAttribute("data-name")) + " · " + CC.esc(formatValue(value));
        if (normalize && isFinite(raw)) {
          html += ' <span class="muted">(' + CC.esc(CC.money(raw, Math.abs(raw) < 1 ? 3 : 2)) + ")</span>";
        }
        tooltip.innerHTML = html;
        tooltip.classList.add("visible");
        var left = circleRect.left - plotRect.left + circleRect.width / 2;
        var top = circleRect.top - plotRect.top;
        var maxLeft = Math.max(4, plotRect.width - tooltip.offsetWidth - 4);
        tooltip.style.left = Math.max(4, Math.min(left - tooltip.offsetWidth / 2, maxLeft)) + "px";
        tooltip.style.top = Math.max(4, top - tooltip.offsetHeight - 10) + "px";
      };
      var hide = function () {
        tooltip.classList.remove("visible");
      };
      circle.addEventListener("mouseenter", show);
      circle.addEventListener("mousemove", show);
      circle.addEventListener("mouseleave", hide);
    });
    return host;
  };
})();
"""


def _active_href(active: str) -> str:
    key = str(active or "").strip()
    if not key:
        return ""
    if key in _NAV_ALIASES:
        return _NAV_ALIASES[key]
    if not key.endswith(".html"):
        return key + ".html"
    return key


def page(
    title: str,
    description: str,
    base: str,
    active: str,
    body: str,
    script: str = "",
) -> str:
    """Render a complete static page with the shared topbar, nav and footer."""
    title_text = escape(title)
    description_text = escape(description)
    base = str(base or ".")
    active_href = _active_href(active)
    nav = "".join(
        '<a href="{base}/{href}"{active}>{label}</a>'.format(
            base=base,
            href=href,
            active=' class="active" aria-current="page"' if href == active_href else "",
            label=escape(label),
        )
        for href, label in NAV
    )
    script_block = "<script>" + script + "</script>" if script else ""
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width,initial-scale=1">\n'
        '<meta name="color-scheme" content="light">\n'
        '<meta name="theme-color" content="#f5f5f7">\n'
        f"<title>{title_text} · AI Compute Economics</title>\n"
        f'<meta name="description" content="{description_text}">\n'
        f'<link rel="icon" type="image/svg+xml" href="{base}/favicon.svg">\n'
        f'<link rel="stylesheet" href="{base}/assets/site.css">\n'
        "</head>\n"
        f'<body data-base="{escape(base)}">\n'
        f'<a class="skip" href="#main">跳到正文</a>\n'
        '<header class="topbar"><div class="topbar-inner">'
        f'<a class="brand" href="{base}/index.html">AI Compute Economics</a>'
        f'<nav class="nav" aria-label="主导航">{nav}</nav>'
        "</div></header>\n"
        f'<main class="shell" id="main">\n{body}\n</main>\n'
        '<footer class="footer"><div class="footer-inner">'
        "<p>AI Compute Economics · 公开挂牌价，非成交价。</p>"
        '<p>外部参考层：<a href="https://gpueconomy.com/data" target="_blank" rel="noopener">GPU Economy</a> · CC BY 4.0。'
        f'自有中位数与指数不受外部数据改写 · <a href="{base}/data/manifest.json">数据说明</a></p>'
        "</div></footer>\n"
        f'<script src="{base}/assets/site.js"></script>\n'
        f"{script_block}\n"
        "</body>\n"
        "</html>\n"
    )


def write_assets(public_dir: Path) -> None:
    """Write ``assets/site.css`` and ``assets/site.js`` under ``public_dir``."""
    assets = Path(public_dir) / "assets"
    assets.mkdir(parents=True, exist_ok=True)
    (assets / "site.css").write_text(SITE_CSS.strip() + "\n", encoding="utf-8")
    (assets / "site.js").write_text(SITE_JS.strip() + "\n", encoding="utf-8")
