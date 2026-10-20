/* 飞控 QMS · 前端框架、质量驾驶舱、系统设置与操作日志（原生 JS，零依赖） */
(function (window, document) {
  "use strict";

  var F = window.F = {};
  var TOKEN_KEY = "qms_token";

  F.state = { boot: null, route: "dashboard", params: {}, timer: null };

  /* ---------------------------------------------------------- 基础工具 */
  F.esc = function (s) {
    return String(s === undefined || s === null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  };
  F.num = function (v, d) {
    var n = Number(v || 0);
    return n.toLocaleString("zh-CN", { minimumFractionDigits: d === undefined ? 2 : d,
      maximumFractionDigits: d === undefined ? 2 : d });
  };
  F.int = function (v) { return F.num(v, 0); };
  F.wan = function (v) {
    var n = Number(v || 0);
    return Math.abs(n) >= 10000 ? (n / 10000).toFixed(1) + " 万" : F.num(n, 0);
  };
  F.pct = function (v, d) {
    var n = Number(v || 0);
    return (v <= 1 && /rate|Rate|pct|util/i.test(String(arguments[2] || "")) ? n * 100 : n)
      .toFixed(d === undefined ? 1 : d) + "%";
  };
  F.pct0 = function (v, d) { return Number(v || 0).toFixed(d === undefined ? 1 : d) + "%"; };
  F.today = function () { return new Date().toISOString().slice(0, 10); };
  F.qs = function (o) {
    return Object.keys(o || {}).filter(function (k) { return o[k] !== undefined && o[k] !== null; })
      .map(function (k) { return encodeURIComponent(k) + "=" + encodeURIComponent(o[k]); }).join("&");
  };
  F.dash = function (v) { return v === null || v === undefined || v === "" ? "—" : v; };

  var TAGS = {
    // 检验单
    "待检验": "gray", "检验中": "gold", "待判定": "blue", "已判定": "blue",
    "已放行": "green", "已关闭": "gray", "已取消": "gray",
    "合格": "green", "不合格": "red",
    "OK": "green", "NG": "red",
    // NCR / CAPA
    "待评审": "gold", "已评审": "blue", "处置中": "gold", "待验证": "gold",
    "进行中": "gold", "已闭环": "green", "已关闭": "gray",
    // 缺陷等级 / 处置
    "A": "red", "B": "gold", "C": "blue",
    "致命": "red", "严重": "gold", "轻微": "blue",
    "返工": "gold", "返修": "gold", "让步接收": "blue", "报废": "red", "退货": "red", "挑选使用": "blue",
    "已逾期": "red", "今日到期": "gold", "正常": "green", "未设时限": "gray",
    // 供应商
    "优": "green", "良": "green", "中": "gold", "差": "red",
    "D1": "gray", "D2": "gray", "D3": "blue", "D4": "blue", "D5": "gold", "D6": "gold",
    "D7": "green", "D8": "green",
    // 通用
    "启用": "green", "停用": "gray", "吊销": "red", "禁用": "gray",
    "成功": "green", "失败": "red", "待投递": "gold", "pending": "gold", "ok": "green", "failed": "red",
    "编制中": "gold", "已发行": "green", "已作废": "gray",
    "高": "red", "中": "gold", "低": "gray",
    "预防成本": "green", "鉴定成本": "blue", "内部损失": "gold", "外部损失": "red"
  };
  F.TAGS = TAGS;
  F.tag = function (s, cls) {
    return '<span class="tag ' + (cls || TAGS[s] || "gray") + '">' + F.esc(s) + "</span>";
  };

  /* ---------------------------------------------------------- 请求 */
  F.raw = function (method, path, body, headers) {
    var h = { "Content-Type": "application/json" };
    var tk = localStorage.getItem(TOKEN_KEY);
    if (tk) { h.Authorization = "Bearer " + tk; h["X-Qms-Token"] = tk; }
    Object.keys(headers || {}).forEach(function (k) { h[k] = headers[k]; });
    var opt = { method: method, headers: h, credentials: "same-origin" };
    if (body !== undefined && body !== null) opt.body = JSON.stringify(body);
    return fetch(path.replace(/^\//, ""), opt).then(function (r) {
      return r.json().catch(function () { return { message: "响应解析失败" }; })
        .then(function (j) { return { status: r.status, body: j }; });
    });
  };

  F.api = function (method, path, body) {
    return F.raw(method, path, body).then(function (x) {
      if (x.status === 401) {
        localStorage.removeItem(TOKEN_KEY);
        location.href = "./login.html";
        return new Promise(function () {});
      }
      if (x.status >= 400) {
        var e = new Error((x.body && x.body.message) || ("请求失败 " + x.status));
        e.status = x.status;
        e.body = x.body;
        throw e;
      }
      return x.body;
    });
  };

  F.toast = function (msg, kind) {
    var el = document.getElementById("statusMsg");
    if (!el) return;
    el.textContent = msg;
    F._toastUntil = Date.now() + 6000;
    el.style.color = kind === "err" ? "#ffb3a7" : (kind === "ok" ? "#9ee6b8" : "");
    clearTimeout(F._t);
    F._t = setTimeout(function () { el.style.color = ""; }, 8000);
  };
  F.setStatus = function (t) {
    var el = document.getElementById("statusMsg");
    if (!el) return;
    if (F._toastUntil && Date.now() < F._toastUntil) return;
    el.textContent = t;
  };
  F.setSide = function (html) { var el = document.getElementById("side"); if (el) el.innerHTML = html; };

  F.can = function (perm) {
    var b = F.state.boot;
    return !!(b && b.user && (b.user.perms || []).indexOf(perm) >= 0);
  };
  F.isAdmin = function () { return F.state.boot && F.state.boot.user.role === "admin"; };
  F.me = function () { return (F.state.boot && F.state.boot.user) || {}; };

  /* ---------------------------------------------------------- 路由 */
  function parseHash() {
    var h = (location.hash || "#dashboard").replace(/^#\/?/, "");
    var i = h.indexOf("?");
    var route = i < 0 ? h : h.slice(0, i);
    var qs = i < 0 ? "" : h.slice(i + 1);
    var params = {};
    qs.split("&").forEach(function (kv) {
      if (!kv) return;
      var j = kv.indexOf("=");
      params[decodeURIComponent(j < 0 ? kv : kv.slice(0, j))] =
        decodeURIComponent(j < 0 ? "" : kv.slice(j + 1));
    });
    return { route: route || "dashboard", params: params };
  }

  F.go = function (route, params) {
    location.hash = "#" + route + (params && Object.keys(params).length ? "?" + F.qs(params) : "");
  };

  var PAGES = {};
  F.register = function (name, fn) { PAGES[name] = fn; };

  function render() {
    var r = parseHash();
    F.state.route = r.route;
    F.state.params = r.params;
    if (F.state.timer) { clearInterval(F.state.timer); F.state.timer = null; }
    var fn = PAGES[r.route] || PAGES.dashboard;
    var view = document.getElementById("view");
    view.innerHTML = "";
    paintNav(r.route);
    try {
      fn(r.params);
    } catch (e) {
      view.innerHTML = '<div class="panel"><div class="panel-body">页面渲染失败：' +
        F.esc(e.message) + "</div></div>";
    }
  }
  F.render = render;

  /* ---------------------------------------------------------- 导航 */
  var TREE = [
    { grp: "质量作业", items: [["dashboard", "质量驾驶舱"], ["iqc", "来料检验 IQC"],
      ["ipqc", "过程检验 IPQC"], ["fqc", "成品/出货检验"], ["ncr", "不合格品 NCR"],
      ["capa", "纠正预防 CAPA"]] },
    { grp: "质量工程", items: [["plans", "检验方案"], ["defects", "缺陷代码"],
      ["spc", "SPC 过程能力"], ["analysis", "质量分析"]] },
    { grp: "供应与成本", items: [["supplier", "供应商质量"], ["coq", "质量成本 COQ"]] },
    { grp: "基础", items: [["qdocs", "质量文件"], ["reports", "报表中心"]] },
    { grp: "系统", items: [["integration", "集成中心"], ["settings", "系统设置"],
      ["logs", "操作日志"]] }
  ];

  var MENU = TREE.map(function (g) { return [g.grp, g.items.map(function (i) { return i[0]; })]; });

  var TITLE = {
    dashboard: "质量驾驶舱", iqc: "来料检验 IQC", ipqc: "过程检验 IPQC", fqc: "成品/出货检验",
    ncr: "不合格品 NCR", capa: "纠正预防 CAPA", plans: "检验方案", defects: "缺陷代码",
    spc: "SPC 过程能力", analysis: "质量分析", supplier: "供应商质量", coq: "质量成本 COQ",
    qdocs: "质量文件", reports: "报表中心", integration: "集成中心", settings: "系统设置",
    logs: "操作日志"
  };
  F.TITLE = TITLE;

  function paintNav(route) {
    var tree = document.getElementById("tree");
    var boot = F.state.boot || {};
    var kpi = boot.kpi || {};
    var badgeFor = {
      iqc: kpi.iqcPending || 0, ncr: kpi.ncrOpen || 0, capa: kpi.capaOpen || 0,
      fqc: kpi.fqcPending || 0
    };
    tree.innerHTML = TREE.map(function (g) {
      return '<div class="grp">' + F.esc(g.grp) + "</div>" + g.items.map(function (it) {
        var n = badgeFor[it[0]] || 0;
        var badge = n ? '<b class="nav-badge">' + n + "</b>" : "";
        return '<a href="#' + it[0] + '" class="' + (it[0] === route ? "on" : "") + '">' +
          F.esc(it[1]) + badge + "</a>";
      }).join("");
    }).join("");

    var mb = document.getElementById("menubar");
    var groupOf = {};
    MENU.forEach(function (m) { m[1].forEach(function (r) { groupOf[r] = m[0]; }); });
    mb.innerHTML = MENU.map(function (m) {
      return '<button class="' + (groupOf[route] === m[0] ? "on" : "") + '" data-group="' +
        F.esc(m[0]) + '">' + F.esc(m[0]) + "</button>";
    }).join("");
    mb.querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        var g = b.getAttribute("data-group");
        var target = MENU.filter(function (m) { return m[0] === g; })[0];
        if (target) F.go(target[1][0]);
      });
    });

    var ts = document.getElementById("tabstrip");
    ts.innerHTML = '<span class="tab">' + F.esc(TITLE[route] || route) + "</span>" +
      '<span class="muted small">飞控 QMS / ' + F.esc(TITLE[route] || route) + "</span>";
  }

  /* ---------------------------------------------------------- 通用渲染 */
  F.table = function (headers, rows, opts) {
    opts = opts || {};
    var th = headers.map(function (h) {
      return "<th class='" + (h.num ? "num" : "") + "'" +
        (h.width ? " style='width:" + h.width + "'" : "") + ">" + F.esc(h.label) + "</th>";
    }).join("");
    var body = rows && rows.length ? rows.map(function (r, i) {
      return '<tr class="' + (opts.click ? "clickable" : "") + '"' +
        (opts.click ? " data-key='" + F.esc(opts.click(r, i)) + "'" : "") + ">" +
        headers.map(function (h) {
          var v = h.render ? h.render(r, i) : F.esc(r[h.key]);
          return "<td class='" + (h.num ? "num" : "") + "'>" + v + "</td>";
        }).join("") + "</tr>";
    }).join("") : '<tr class="empty-row"><td colspan="' + headers.length + '">' +
      F.esc(opts.empty || "暂无数据") + "</td></tr>";
    return "<table class='grid-table'><thead><tr>" + th + "</tr></thead><tbody>" + body + "</tbody></table>";
  };

  F.bindRows = function (root, fn) {
    (root || document).querySelectorAll("#view tbody tr[data-key]").forEach(function (tr) {
      tr.addEventListener("click", function () { fn(tr.getAttribute("data-key"), tr); });
    });
  };

  F.dialog = function (title, body, foot) {
    var mask = document.getElementById("mask");
    var dlg = document.getElementById("dialog");
    dlg.className = "dialog" + (F._wide ? " wide" : "");
    F._wide = false;
    dlg.innerHTML = '<div class="dh">' + F.esc(title) +
      '<span class="x" data-close="1">×</span></div><div class="db">' + body + "</div>" +
      (foot ? '<div class="df">' + foot + "</div>" : "");
    mask.className = "mask on";
    dlg.querySelector("[data-close]").addEventListener("click", F.closeDialog);
    return dlg;
  };
  F.dialogWide = function (title, body, foot) { F._wide = true; return F.dialog(title, body, foot); };
  F.closeDialog = function () { document.getElementById("mask").className = "mask"; };
  F.dialogOpen = function () {
    return document.getElementById("mask").className.indexOf("on") >= 0;
  };

  F.chips = function (items, active, attr) {
    return '<div class="chips">' + items.map(function (it) {
      var val = typeof it === "string" ? it : it[0];
      var label = typeof it === "string" ? it : it[1];
      var count = typeof it === "string" ? "" : (
        it[2] === undefined || it[2] === null ? "" : '<span class="chip-n">' + it[2] + "</span>");
      return '<button class="chip' + (val === active ? " on" : "") + '" ' + (attr || "data-st") +
        '="' + F.esc(val) + '">' + F.esc(label) + count + "</button>";
    }).join("") + "</div>";
  };

  F.lineChart = function (series, opts) {
    opts = opts || {};
    var W = opts.width || 640, H = opts.height || 190, P = 34;
    var labels = opts.labels || [];
    var all = [];
    series.forEach(function (s) { all = all.concat(s.data); });
    var max = Math.max.apply(null, all.concat([1]));
    var min = opts.zero === false ? Math.min.apply(null, all) : 0;
    var span = max - min || 1;
    var colors = opts.colors || ["#1f7a8c", "#c8963e", "#b4463a"];
    var w = (W - P * 2) / Math.max(1, labels.length - 1);
    var grid = [0, 0.25, 0.5, 0.75, 1].map(function (t) {
      var y = P + (H - P * 1.6) * t;
      var val = max - span * t;
      return '<line x1="' + P + '" y1="' + y + '" x2="' + (W - P) + '" y2="' + y +
        '" stroke="#eef2f5"/><text x="6" y="' + (y + 4) + '" font-size="10" fill="#8b9aa6">' +
        (val >= 10000 ? (val / 10000).toFixed(1) + "万" : Math.round(val)) + "</text>";
    }).join("");
    var paths = series.map(function (s, si) {
      var d = s.data.map(function (v, i) {
        var x = P + w * i;
        var y = P + (H - P * 1.6) * (1 - (v - min) / span);
        return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
      }).join(" ");
      return '<path d="' + d + '" fill="none" stroke="' + colors[si % colors.length] +
        '" stroke-width="2"/>' + s.data.map(function (v, i) {
          var x = P + w * i;
          var y = P + (H - P * 1.6) * (1 - (v - min) / span);
          return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.6" fill="' +
            colors[si % colors.length] + '"/>';
        }).join("");
    }).join("");
    var xlabels = labels.map(function (t, i) {
      return '<text x="' + (P + w * i) + '" y="' + (H - 6) +
        '" font-size="10" fill="#8b9aa6" text-anchor="middle">' + F.esc(t) + "</text>";
    }).join("");
    var legend = series.map(function (s, si) {
      return '<span class="lg-dot"><i style="background:' + colors[si % colors.length] + '"></i>' +
        F.esc(s.name) + "</span>";
    }).join("");
    return '<div class="chart-legend">' + legend + "</div>" +
      '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' +
      grid + paths + xlabels + "</svg>";
  };

  F.barChart = function (items, opts) {
    opts = opts || {};
    var W = opts.width || 640, H = opts.height || 180, P = 34;
    var max = Math.max.apply(null, items.map(function (i) { return i.value; }).concat([1]));
    var gap = (W - P * 2) / Math.max(1, items.length);
    var bw = gap * 0.56;
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' +
      items.map(function (it, i) {
        var h = (H - P * 1.8) * (it.value / max);
        var x = P + gap * i + (gap - bw) / 2;
        var y = H - P - h;
        return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
          '" height="' + Math.max(1, h).toFixed(1) + '" rx="2" fill="' + (it.color || "#2b9eb3") + '"/>' +
          '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (y - 5) +
          '" font-size="10" fill="#5d6f7c" text-anchor="middle">' + F.esc(it.label2 || "") +
          "</text>" + '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (H - 8) +
          '" font-size="10" fill="#8b9aa6" text-anchor="middle">' + F.esc(it.label) + "</text>";
      }).join("") + "</svg>";
  };

  F.stageBars = function (stages) {
    var max = Math.max.apply(null, stages.map(function (s) { return s.count; }).concat([1]));
    return '<div class="funnel">' + stages.map(function (s) {
      var w = Math.max(5, Math.round(s.count / max * 100));
      var color = TAGS[s.status] === "gold" ? "#c8963e" : (TAGS[s.status] === "green" ? "#2f8f5b" :
        (TAGS[s.status] === "red" ? "#b4463a" : "#2b7fa8"));
      return '<div class="fn-row"><div class="fn-name">' + F.esc(s.status) + "</div>" +
        '<div class="fn-bar"><i style="width:' + w + "%;background:" + color + '"></i></div>' +
        '<div class="fn-val">' + s.count + ' <span class="muted small">单</span></div>' +
        '<div class="fn-conv"></div></div>';
    }).join("") + "</div>";
  };

  F.ring = function (v, opts) {
    opts = opts || {};
    var p = Math.max(0, Math.min(1, Number(v || 0)));
    var color = opts.color || (p >= 0.85 ? "#2f8f5b" : (p >= 0.6 ? "#c8963e" : "#b4463a"));
    var deg = (p * 360).toFixed(1);
    return '<div class="ring" style="background:conic-gradient(' + color + " 0deg " + deg +
      "deg,#eef2f5 " + deg + 'deg 360deg)"><div class="ring-in"><b>' +
      (p <= 1 ? F.pct0(p * 100, opts.d === undefined ? 1 : opts.d) : F.pct0(p, 1)) +
      "</b><span>" + F.esc(opts.label || "") + "</span></div></div>";
  };

  F.empty = function (text) {
    return '<div class="empty-hint">' + F.esc(text || "暂无数据") + "</div>";
  };

  F.kv = function (label, value) {
    return '<div class="side-kv"><span>' + F.esc(label) + "</span><b>" + value + "</b></div>";
  };

  F.progress = function (v, cls) {
    var p = Math.max(0, Math.min(1, Number(v || 0)));
    return '<div class="pbar ' + (cls || "") + '"><i style="width:' + (p * 100).toFixed(1) + '%"></i></div>';
  };

  /* 帕累托图（柱 + 累计占比折线） */
  F.paretoChart = function (items) {
    if (!items.length) return F.empty("暂无缺陷数据");
    var W = 640, H = 200, P = 36;
    var max = Math.max.apply(null, items.map(function (i) { return i.count; }).concat([1]));
    var gap = (W - P * 2) / items.length;
    var bw = gap * 0.5;
    var bars = items.map(function (it, i) {
      var h = (H - P * 2) * (it.count / max);
      var x = P + gap * i + (gap - bw) / 2;
      var y = H - P - h;
      return '<rect x="' + x.toFixed(1) + '" y="' + y.toFixed(1) + '" width="' + bw.toFixed(1) +
        '" height="' + Math.max(1, h).toFixed(1) + '" rx="2" fill="#2b7fa8"/>' +
        '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (y - 5) +
        '" font-size="10" fill="#5d6f7c" text-anchor="middle">' + it.count + "</text>" +
        '<text x="' + (x + bw / 2).toFixed(1) + '" y="' + (H - 8) +
        '" font-size="9" fill="#8b9aa6" text-anchor="middle">' + F.esc(it.name.length > 5 ?
          it.name.slice(0, 5) + "…" : it.name) + "</text>";
    }).join("");
    var line = items.map(function (it, i) {
      var x = P + gap * i + gap / 2;
      var y = P + (H - P * 2) * (1 - it.cumPct / 100);
      return (i ? "L" : "M") + x.toFixed(1) + " " + y.toFixed(1);
    }).join(" ");
    var dots = items.map(function (it, i) {
      var x = P + gap * i + gap / 2;
      var y = P + (H - P * 2) * (1 - it.cumPct / 100);
      return '<circle cx="' + x.toFixed(1) + '" cy="' + y.toFixed(1) + '" r="2.5" fill="#c8963e"/>' +
        '<text x="' + (x + 4) + '" y="' + (y - 4) + '" font-size="9" fill="#c8963e">' +
        it.cumPct + "%</text>";
    }).join("");
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' +
      bars + '<path d="' + line + '" fill="none" stroke="#c8963e" stroke-width="1.6"/>' + dots + "</svg>";
  };

  /* SPC 控制图 */
  F.spcChart = function (d) {
    var values = (d.points || []).map(function (p) { return p.value; });
    if (!values.length) return F.empty("暂无测量数据");
    var W = 680, H = 220, P = 40;
    var lim = d.limits || {};
    var all = values.concat([lim.ucl || 0, lim.lcl || 0, d.usl || 0, d.lsl || 0]);
    var max = Math.max.apply(null, all), min = Math.min.apply(null, all);
    var span = (max - min) * 1.15 || 1;
    max += span * 0.08; min -= span * 0.08;
    var w = (W - P * 2) / Math.max(1, values.length - 1);
    function y(v) { return P + (H - P * 2) * (1 - (v - min) / (max - min)); }
    function hline(v, color, label) {
      return '<line x1="' + P + '" y1="' + y(v).toFixed(1) + '" x2="' + (W - P) + '" y2="' +
        y(v).toFixed(1) + '" stroke="' + color + '" stroke-dasharray="5 4"/>' +
        '<text x="4" y="' + (y(v) + 3).toFixed(1) + '" font-size="9" fill="' + color + '">' +
        label + "</text>";
    }
    var grid = [0, 0.25, 0.5, 0.75, 1].map(function (t) {
      var yy = P + (H - P * 2) * t;
      var val = max - (max - min) * t;
      return '<line x1="' + P + '" y1="' + yy + '" x2="' + (W - P) + '" y2="' + yy +
        '" stroke="#f0f4f7"/><text x="2" y="' + (yy + 4) + '" font-size="9" fill="#b3bec7">' +
        val.toFixed(2) + "</text>";
    }).join("");
    var path = values.map(function (v, i) {
      return (i ? "L" : "M") + (P + w * i).toFixed(1) + " " + y(v).toFixed(1);
    }).join(" ");
    var dots = values.map(function (v, i) {
      var out = v > (lim.ucl || Infinity) || v < (lim.lcl || -Infinity);
      return '<circle cx="' + (P + w * i).toFixed(1) + '" cy="' + y(v).toFixed(1) +
        '" r="2.8" fill="' + (out ? "#b4463a" : "#2b7fa8") + '"/>';
    }).join("");
    return '<svg viewBox="0 0 ' + W + " " + H + '" width="100%" height="' + H + '">' + grid +
      hline(lim.ucl || 0, "#b4463a", "UCL " + (lim.ucl || 0).toFixed(3)) +
      hline(lim.cl || 0, "#2f8f5b", "CL " + (lim.cl || 0).toFixed(3)) +
      hline(lim.lcl || 0, "#b4463a", "LCL " + (lim.lcl || 0).toFixed(3)) +
      (d.usl ? hline(d.usl, "#c8963e", "USL " + d.usl) : "") +
      (d.lsl ? hline(d.lsl, "#c8963e", "LSL " + d.lsl) : "") +
      '<path d="' + path + '" fill="none" stroke="#2b7fa8" stroke-width="1.8"/>' + dots + "</svg>";
  };

  /* ---------------------------------------------------------- 驾驶舱 */
  F.register("dashboard", function () {
    F.api("GET", "/api/board").then(function (d) {
      var k = d.kpi;
      var html = '<div class="kpi-grid six">' +
        '<div class="kpi"><div class="k-label">检验单总数</div><div class="k-value">' + F.int(k.inspections) +
        '</div><div class="k-sub">在途待处理 ' + k.pending + " 单</div></div>" +
        '<div class="kpi green"><div class="k-label">来料批次合格率</div><div class="k-value">' +
        F.pct0(k.iqcPassRate) + '</div><div class="k-sub">IQC 判定口径</div></div>' +
        '<div class="kpi gold"><div class="k-label">NCR 未闭环</div><div class="k-value">' + k.ncrOpen +
        '</div><div class="k-sub">让步/返工/报废处置</div></div>' +
        '<div class="kpi"><div class="k-label">CAPA 进行中</div><div class="k-value">' + k.capaOpen +
        '</div><div class="k-sub">逾期 ' + k.capaOverdue + " 项</div></div>" +
        '<div class="kpi gold"><div class="k-label">本月质量成本</div><div class="k-value">' +
        F.wan(k.coqMonth) + '</div><div class="k-sub">预防/鉴定/内外损</div></div>' +
        '<div class="kpi red"><div class="k-label">待办</div><div class="k-value">' +
        (d.todo["待检验"] + d.todo["待判定"]) +
        '</div><div class="k-sub">NCR 待验证 ' + d.todo["NCR待验证"] + " · CAPA 逾期 " +
        d.todo["CAPA逾期"] + "</div></div></div>";

      html += '<div class="panel"><div class="panel-title">缺陷帕累托（按不良数）' +
        '<span class="panel-actions"><a class="btn sm" href="#analysis">质量分析</a></span></div>' +
        '<div class="panel-body">' + F.paretoChart(d.pareto || []) + "</div></div>";

      html += '<div class="panel"><div class="panel-title">SPC 控制图 · 锁附扭矩（x̄-R）' +
        '<span class="panel-actions small muted">UCL ' + F.num((d.spc || {}).ucl, 3) +
        " / CL " + F.num((d.spc || {}).cl, 3) + " / LCL " + F.num((d.spc || {}).lcl, 3) +
        " · 判异 " + ((d.spc || {}).outliers || []).length + " 点</span></div>" +
        '<div class="panel-body">' + F.spcChart({ points: ((d.spc || {}).xbars || [])
          .map(function (v) { return { value: v }; }), limits: d.spc }) + "</div></div>";

      html += '<div class="panel"><div class="panel-title">各类型检验合格率' +
        '<span class="panel-actions"><a class="btn sm" href="#reports">报表中心</a></span></div>' +
        '<div class="panel-body flush">' +
        F.table([
          { label: "检验类型", render: function (r) {
              return "<b>" + F.esc(r.itype) + "</b> " + F.tag(r.itype, "blue"); } },
          { label: "已判定", num: true, render: function (r) { return r.total + " 单"; } },
          { label: "合格", num: true, render: function (r) { return (r.ok || 0) + " 单"; } },
          { label: "批次合格率", render: function (r) {
              return '<div class="util-cell">' + F.progress((r.passRate || 0) / 100) +
                '<span class="small">' + F.pct0(r.passRate) + "</span></div>"; } }
        ], d.byType) + "</div></div>";

      var st = Object.keys(d.byStatus || {}).map(function (s) {
        return { status: s, count: d.byStatus[s] };
      }).sort(function (a, b) { return b.count - a.count; });
      html += '<div class="panel"><div class="panel-title">检验单状态分布' +
        '<span class="panel-actions small muted">共 ' + k.inspections + " 单</span></div>" +
        '<div class="panel-body">' + F.stageBars(st) + "</div></div>";

      document.getElementById("view").innerHTML = html;

      F.setSide(
        '<div class="side-block"><div class="hd">质量快照</div><div class="bd">' +
        F.kv("待检验", d.todo["待检验"] + " 单") +
        F.kv("待判定", d.todo["待判定"] + " 单") +
        F.kv("NCR 待验证", d.todo["NCR待验证"] + " 单") +
        F.kv("CAPA 逾期", d.todo["CAPA逾期"] + " 项") +
        "</div></div>" +
        '<div class="side-block"><div class="hd">SPC 摘要</div><div class="bd">' +
        F.kv("控制限", F.num((d.spc || {}).lcl, 2) + " ~ " + F.num((d.spc || {}).ucl, 2)) +
        F.kv("中心线", F.num((d.spc || {}).cl, 3)) +
        F.kv("判异点", ((d.spc || {}).outliers || []).length + " 个") +
        "</div></div>" +
        '<div class="side-block"><div class="hd">工作准则</div><div class="bd small muted" style="line-height:1.9">' +
        "● 致命缺陷（A类）Ac=0，一票否决<br>● 让步接收须评审且不良率 ≤ 上限<br>" +
        "● 不合格判定自动开立 NCR<br>● CAPA 根因（5Why）不足 10 字不可推进<br>" +
        "● NCR / CAPA 逾期自动亮红</div></div>");
      F.setStatus("质量驾驶舱 · 数据截至 " + new Date().toLocaleTimeString("zh-CN"));
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 系统设置 */
  F.register("settings", function () {
    var tab = F.state.params.tab || "rules";
    Promise.all([F.api("GET", "/api/settings"), F.api("GET", "/api/users")]).then(function (res) {
      var d = res[0], du = res[1];
      var admin = F.isAdmin();
      var roleLabel = { admin: "系统管理员", quality_mgr: "质量经理", qa_engineer: "质量工程师",
        inspector: "检验员", process_engineer: "工艺工程师", purchaser: "采购员",
        supplier_qa: "SQE", viewer: "访客" };
      var html = '<div class="panel"><div class="panel-title">' +
        F.chips([["rules", "业务规则"], ["users", "账号与权限"], ["about", "系统信息"]], tab, "data-tab") +
        "</div><div class='panel-body' id='setBody'></div></div>";
      document.getElementById("view").innerHTML = html;

      var body = document.getElementById("setBody");
      function paint(t) {
        if (t === "rules") {
          body.innerHTML = F.table([
            { label: "规则", render: function (r) { return F.esc(r.remark) +
              ' <span class="muted small mono">' + F.esc(r.code) + "</span>"; } },
            { label: "当前值", num: true, render: function (r) {
                return '<input class="inp sm" data-rule="' + F.esc(r.code) + '" value="' +
                  F.esc(r.value) + '" style="width:110px">'; } }
          ], d.list) + (admin ? '<div class="form-foot"><button class="btn primary" id="ruleSave">' +
            "保存规则</button></div>" : '<div class="muted small">仅管理员可修改规则</div>');
          var sv = document.getElementById("ruleSave");
          if (sv) sv.addEventListener("click", function () {
            var items = [];
            body.querySelectorAll("[data-rule]").forEach(function (i) {
              items.push({ code: i.getAttribute("data-rule"), value: i.value });
            });
            F.api("PUT", "/api/settings", { items: items }).then(function () {
              F.toast("规则已保存", "ok");
            }).catch(function (e) { F.toast(e.message, "err"); });
          });
        } else if (t === "users") {
          body.innerHTML = (admin ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="uNew">新建账号</button></div>' : "") +
            F.table([
              { label: "账号", render: function (r) { return '<span class="mono">' + F.esc(r.username) + "</span>"; } },
              { label: "姓名", key: "name" },
              { label: "角色", render: function (r) { return F.tag(r.roleName, "blue"); } },
              { label: "部门", key: "dept" },
              { label: "状态", render: function (r) { return F.tag(r.enabled ? "启用" : "禁用"); } }
            ], du.list) +
            "<div class='sub-title'>角色权限矩阵（11 项权限 × 8 角色）</div>" +
            F.table([{ label: "角色", render: function (r) { return F.tag(roleLabel[r] || r, "blue"); } },
              { label: "权限", render: function (r) {
                return (du.matrix[r] || []).map(function (p) {
                  return '<span class="tag gray">' + F.esc(p) + "</span>";
                }).join(" ");
              } }], Object.keys(du.matrix));
          var nb = document.getElementById("uNew");
          if (nb) nb.addEventListener("click", function () {
            F.dialog("新建账号",
              '<div class="form-grid">' +
              '<label>账号<input id="nuName" placeholder="小写字母/数字"></label>' +
              '<label>姓名<input id="nuDisplay"></label>' +
              '<label>角色<select id="nuRole">' + Object.keys(roleLabel).map(function (r) {
                return '<option value="' + F.esc(r) + '">' + F.esc(roleLabel[r]) + "</option>";
              }).join("") + "</select></label>" +
              '<label>部门<input id="nuDept" placeholder="如 质量管理部"></label>' +
              '<label>初始密码<input id="nuPwd" value="qms@2026"></label></div>',
              '<button class="btn" id="nuOk">创建</button>');
            document.getElementById("nuOk").addEventListener("click", function () {
              F.api("POST", "/api/users", {
                username: document.getElementById("nuName").value.trim(),
                name: document.getElementById("nuDisplay").value.trim(),
                role: document.getElementById("nuRole").value,
                dept: document.getElementById("nuDept").value.trim(),
                password: document.getElementById("nuPwd").value
              }).then(function () {
                F.closeDialog(); F.toast("账号已创建", "ok"); F.go("settings", { tab: "users" });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else {
          body.innerHTML = '<div class="kv-grid">' +
            F.kv("系统名称", "飞控 QMS · 质量管理系统") +
            F.kv("版本", (F.state.boot && F.state.boot.version) || "1.0.0") +
            F.kv("接口契约", "GET /api/openapi.json") +
            F.kv("账号数", du.list.length) +
            "</div>" +
            '<div class="sub-title">部署与对接说明</div>' +
            '<div class="panel-body small muted" style="line-height:2">' +
            "· 零第三方依赖：Python 标准库 http.server + SQLite（WAL），单进程即可运行。<br>" +
            "· 前端为原生 HTML/CSS/JS，无构建步骤，hash 路由；同一份静态资源可由任意反向代理托管。<br>" +
            "· 与 ERP / MES / SRM 对接走「三通道」：API Key（fck_ 前缀）、Webhook（HMAC-SHA256 签名）、" +
            "增量同步 /api/sync/changes 游标拉取。<br>" +
            "· 令牌支持 Authorization / X-Qms-Token / Cookie / 查询串多通道携带，避免代理改写导致掉登录。</div>";
        }
      }
      paint(tab);
      document.querySelectorAll("[data-tab]").forEach(function (b) {
        b.addEventListener("click", function () {
          document.querySelectorAll("[data-tab]").forEach(function (x) { x.className = "chip"; });
          b.className = "chip on";
          paint(b.getAttribute("data-tab"));
        });
      });
      F.setStatus("系统设置 · " + (TITLE[F.state.route] || ""));
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 操作日志 */
  F.register("logs", function () {
    F.api("GET", "/api/logs").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">操作日志' +
        '<span class="panel-actions small muted">最近 ' + d.list.length + " 条</span></div>" +
        '<div class="panel-body flush">' +
        F.table([
          { label: "时间", render: function (r) { return '<span class="mono small">' +
            F.esc(r.ts) + "</span>"; } },
          { label: "操作人", render: function (r) { return F.esc(r.user); } },
          { label: "动作", render: function (r) { return F.tag(r.action, "blue"); } },
          { label: "详情", render: function (r) { return '<span class="small">' + F.esc(r.detail) + "</span>"; } }
        ], d.list, { empty: "暂无日志" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setStatus("操作日志 · 共 " + d.list.length + " 条");
      F.setSide('<div class="side-block"><div class="hd">说明</div><div class="bd small muted" ' +
        'style="line-height:1.9">所有写操作都会落审计日志：登录、检验单创建与推进、判定放行、' +
        'NCR 评审处置、CAPA 推进、评分调整、规则修改、集成配置变更等。</div></div>');
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ---------------------------------------------------------- 启动 */
  F.boot = function () {
    return F.api("GET", "/api/auth/me").then(function (me) {
      return F.api("GET", "/api/board").then(function (board) {
        F.state.boot = {
          user: me.user, version: me.version, brand: me.brand,
          kpi: { iqcPending: board.todo["待检验"], ncrOpen: board.kpi.ncrOpen,
                 capaOpen: board.kpi.capaOpen, fqcPending: board.todo["待判定"] },
          todo: board.todo
        };
        var u = me.user;
        var op = document.getElementById("opFoot");
        if (op) op.textContent = "操作员：" + u.name + "（" + u.roleName + "）";
        var pend = document.getElementById("pendLabel");
        if (pend) pend.textContent = "待检：" + board.kpi.pending;
        var nc = document.getElementById("ncrLabel");
        if (nc) nc.textContent = "NCR 未闭环：" + board.kpi.ncrOpen;
        var cp = document.getElementById("capaLabel");
        if (cp) cp.textContent = "CAPA 进行中：" + board.kpi.capaOpen;
        return F.state.boot;
      });
    });
  };

  function start() {
    if (!localStorage.getItem(TOKEN_KEY)) { location.href = "./login.html"; return; }
    F.boot().then(function () {
      render();
      window.addEventListener("hashchange", render);
      var lo = document.getElementById("btnLogout");
      if (lo) lo.addEventListener("click", function () {
        F.api("POST", "/api/auth/logout", {}).catch(function () {}).then(function () {
          localStorage.removeItem(TOKEN_KEY);
          document.cookie = "token=; path=/; max-age=0";
          location.href = "./login.html";
        });
      });
    }).catch(function (e) {
      if (e.status === 401) return;
      document.getElementById("view").innerHTML =
        '<div class="panel"><div class="panel-body">初始化失败：' + F.esc(e.message) + "</div></div>";
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})(window, document);
