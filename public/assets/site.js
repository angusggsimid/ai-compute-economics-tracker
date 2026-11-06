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
