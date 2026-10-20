/* 飞控 QMS · 分析与集成：SPC、质量分析、供应商质量、质量成本、报表、集成中心 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ------------------------------------------------------ SPC */
  F.register("spc", function () {
    F.api("GET", "/api/spc/processes").then(function (ps) {
      var p = F.state.params.p || ((ps.list[0] || {}).process || "");
      var c = F.state.params.c || ((ps.list[0] || {}).char_name || "");
      F.api("GET", "/api/spc/series?process=" + encodeURIComponent(p) +
        "&char=" + encodeURIComponent(c)).then(function (d) {
        var html = '<div class="panel"><div class="panel-title">SPC 控制图' +
          '<span class="panel-actions">' + ps.list.map(function (x) {
            return '<button class="chip' + (x.process === p && x.char_name === c ? " on" : "") +
              '" data-pc="' + F.esc(x.process + "|" + x.char_name) + '">' +
              F.esc(x.process + " · " + x.char_name) + "</button>";
          }).join("") + "</span></div>" +
          '<div class="panel-body">' + F.spcChart(d) + "</div></div>";
        var cp = d.cpk || {};
        html += '<div class="panel"><div class="panel-title">过程能力' +
          '<span class="panel-actions small muted">目标 Cpk ≥ ' +
          F.esc(F.state.boot ? "1.33" : "1.33") + "</span></div>" +
          '<div class="panel-body"><div class="kv-grid">' +
          F.kv("Cp", '<b style="font-size:18px">' + F.num(cp.cp, 3) + "</b>") +
          F.kv("Cpk", '<b style="font-size:18px;color:' + (cp.cpk >= 1.33 ? "#2f8f5b" :
            cp.cpk >= 1 ? "#c8963e" : "#b4463a") + '">' + F.num(cp.cpk, 3) + "</b>") +
          F.kv("能力等级", F.tag(cp.grade, cp.cpk >= 1.33 ? "green" : "gold")) +
          F.kv("均值 / 标准差", F.num(cp.mean, 4) + " / " + F.num(cp.std, 4)) +
          F.kv("USL / LSL", F.num(d.usl, 2) + " / " + F.num(d.lsl, 2)) +
          F.kv("超差点", cp.outSpec + " 个") +
          F.kv("判异点（控制限外）", ((d.limits || {}).outliers || []).length + " 个") +
          F.kv("样本数", (d.points || []).length) +
          "</div></div></div>";
        document.getElementById("view").innerHTML = html;
        document.querySelectorAll("[data-pc]").forEach(function (b) {
          b.addEventListener("click", function () {
            var pc = b.getAttribute("data-pc").split("|");
            F.go("spc", { p: pc[0], c: pc[1] });
          });
        });
        F.setSide('<div class="side-block"><div class="hd">判异说明</div><div class="bd small muted" ' +
          'style="line-height:1.9">· 红点：超出控制限 UCL/LCL<br>· 金线：规格限 USL/LSL<br>' +
          "· 控制限由 x̄-R 图（n=5）计算，规格限为设计要求</div></div>");
        F.setStatus("SPC · " + p + " · " + c);
      }).catch(function (e) { F.toast(e.message, "err"); });
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 质量分析 */
  F.register("analysis", function () {
    Promise.all([F.api("GET", "/api/analysis/pareto"), F.api("GET", "/api/analysis/fpy"),
      F.api("GET", "/api/analysis/trend")]).then(function (res) {
      var pt = res[0], fpy = res[1], tr = res[2];
      var html = '<div class="panel"><div class="panel-title">缺陷帕累托' +
        '<span class="panel-actions small muted">左轴不良数 · 橙线累计占比（80/20）</span></div>' +
        '<div class="panel-body">' + F.paretoChart(pt.list) + "</div></div>";
      html += '<div class="panel"><div class="panel-title">加权帕累托（致命×10 严重×5 轻微×1）</div>' +
        '<div class="panel-body flush">' +
        F.table([
          { label: "缺陷", key: "name" },
          { label: "加权值", num: true, key: "count" },
          { label: "占比", num: true, render: function (r) { return F.pct0(r.pct); } },
          { label: "累计", num: true, render: function (r) { return F.pct0(r.cumPct); } }
        ], pt.weighted.slice(0, 10)) + "</div></div>";
      html += '<div class="panel"><div class="panel-title">一次合格率 FPY（各类型直通率乘积口径）</div>' +
        '<div class="panel-body flush">' +
        F.table([
          { label: "阶段", key: "stage" },
          { label: "送检", num: true, key: "total" },
          { label: "合格", num: true, key: "ok" },
          { label: "直通率 RTY", num: true, render: function (r) { return F.pct0(r.rty); } }
        ], fpy.stages) +
        '<div class="form-foot">整机一次合格率 FPY：<b style="font-size:16px;color:#c8963e">' +
        F.pct0(fpy.fpy) + "</b></div></div></div>";
      html += '<div class="panel"><div class="panel-title">月度趋势（合格率与 NCR 开单）</div>' +
        '<div class="panel-body">' + F.lineChart([
          { name: "批次合格率%", data: tr.list.map(function (t) { return t.passRate; }) },
          { name: "NCR 数", data: tr.list.map(function (t) { return t.ncr; }) }
        ], { labels: tr.list.map(function (t) { return t.month; }),
          colors: ["#1f7a8c", "#b4463a"], zero: false }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setStatus("质量分析 · 帕累托/FPY/趋势");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 供应商质量 */
  F.register("supplier", function () {
    F.api("GET", "/api/supplier/quality").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">供应商月度评分（' + F.esc(d.month) + "）" +
        '<span class="panel-actions small muted">质量50% + 交付30% + 响应20%</span></div>' +
        '<div class="panel-body flush">' +
        F.table([
          { label: "供应商", key: "supplier" },
          { label: "批次（合格/总）", num: true, render: function (r) {
              return r.accepted + " / " + r.lots; } },
          { label: "IRR 批次合格率", render: function (r) {
              return '<div class="util-cell">' + F.progress(r.irr / 100) +
                '<span class="small">' + F.pct0(r.irr) + "</span></div>"; } },
          { label: "PPM", num: true, key: "ppm" },
          { label: "质量", num: true, key: "q" },
          { label: "交付", num: true, key: "d" },
          { label: "响应", num: true, key: "r" },
          { label: "总分", num: true, render: function (r) { return "<b>" + F.num(r.total, 1) + "</b>"; } },
          { label: "等级", render: function (r) { return F.tag(r.grade,
              r.grade === "A" ? "green" : (r.grade === "B" ? "blue" : (r.grade === "C" ? "gold" : "red"))); } }
        ], d.list, { empty: "暂无评分" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.api("GET", "/api/supplier/ppm").then(function (ppm) {
        F.setSide('<div class="side-block"><div class="hd">不良 PPM 排行</div><div class="bd">' +
          (ppm.list || []).slice(0, 6).map(function (r) {
            return F.kv(r.supplier, F.int(r.ppm));
          }).join("") + "</div></div>" +
          '<div class="side-block"><div class="hd">等级规则</div><div class="bd small muted" ' +
          'style="line-height:1.9">A ≥ 90 · B ≥ 80 · C ≥ 70 · D &lt; 70<br>' +
          "D 级触发供应商辅导与来料加严检验。</div></div>");
      }).catch(function () {});
      F.setStatus("供应商质量 · " + d.total + " 家");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 质量成本 */
  F.register("coq", function () {
    F.api("GET", "/api/coq").then(function (d) {
      var s = d.summary || { items: [], total: 0, failRate: 0 };
      var html = '<div class="panel"><div class="panel-title">质量成本 COQ（' + F.esc(d.month) + "）" +
        '<span class="panel-actions small muted">总额 ' + F.wan(s.total) + " 元 · 失败成本占比 " +
        F.pct0(s.failRate) + "</span></div>" +
        '<div class="panel-body">' +
        s.items.map(function (it) {
          return '<div class="fn-row"><div class="fn-name">' + F.tag(it.category) + "</div>" +
            '<div class="fn-bar"><i style="width:' + Math.max(3, it.pct) +
            '%;background:' + (F.TAGS[it.category] === "red" ? "#b4463a" :
              F.TAGS[it.category] === "gold" ? "#c8963e" :
              F.TAGS[it.category] === "blue" ? "#2b7fa8" : "#2f8f5b") + '"></i></div>' +
            '<div class="fn-val">' + F.wan(it.amount) + " <span class=\"muted small\">" +
            F.pct0(it.pct) + "</span></div><div class=\"fn-conv\"></div></div>";
        }).join("") + "</div>" +
        '<div class="panel-body flush">' +
        F.table([
          { label: "类别", render: function (r) { return F.tag(r.category); } },
          { label: "项目", key: "item" },
          { label: "金额（元）", num: true, render: function (r) { return F.num(r.amount, 0); } }
        ], d.list) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.api("GET", "/api/coq/trend").then(function (tr) {
        F.setSide('<div class="side-block"><div class="hd">月度对比</div><div class="bd small muted" ' +
          'style="line-height:1.9">' + (tr.list || []).map(function (m) {
            var total = ["预防成本", "鉴定成本", "内部损失", "外部损失"].reduce(function (a, k) {
              return a + Number(m[k] || 0); }, 0);
            return "● " + m.month + "：" + F.wan(total) + " 元";
          }).join("<br>") + "</div></div>" +
          '<div class="side-block"><div class="hd">口径</div><div class="bd small muted" ' +
          'style="line-height:1.9">PAF 分类：预防 + 鉴定为投入，' +
          "内部 + 外部损失为失败成本，失败占比越低质量体系越成熟。</div></div>");
      }).catch(function () {});
      F.setStatus("质量成本 COQ · " + F.wan(s.total) + " 元");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 报表中心 */
  F.register("reports", function () {
    F.api("GET", "/api/reports/kpi").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">质量 KPI 汇总' +
        '<span class="panel-actions">' +
        '<a class="btn sm" href="api/reports/inspections.csv" target="_blank">导出检验单</a>' +
        '<a class="btn sm" href="api/reports/ncrs.csv" target="_blank">导出 NCR</a>' +
        '<a class="btn sm" href="api/reports/defects.csv" target="_blank">导出缺陷</a>' +
        "</span></div>" +
        '<div class="panel-body flush">' +
        F.table([
          { label: "检验类型", render: function (r) { return F.tag(r.itype, "blue"); } },
          { label: "已判定", num: true, key: "total" },
          { label: "合格", num: true, render: function (r) { return r.ok || 0; } },
          { label: "批次合格率", num: true, render: function (r) { return F.pct0(r.passRate); } },
          { label: "累计不良", num: true, key: "bad" }
        ], d.byType) +
        '<div class="kv-grid" style="margin-top:12px">' +
        F.kv("NCR 总数 / 已闭环", d.ncr.total + " / " + d.ncr.closed) +
        F.kv("NCR 平均关闭天数", F.num(d.ncr.avgDays, 1) + " 天") +
        F.kv("CAPA 总数 / 已关闭", d.capa.total + " / " + d.capa.closed) +
        F.kv("CAPA 按期关闭率", F.pct0(d.capa.closeRate)) +
        "</div></div>" +
        '<div class="panel-body flush"><div class="sub-title">NCR 状态分布</div>' +
        F.stageBars(d.ncrByStatus.map(function (r) { return { status: r.status, count: r.c }; })) +
        "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setStatus("报表中心");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 集成中心 */
  F.register("integration", function () {
    var tab = F.state.params.tab || "keys";
    Promise.all([F.api("GET", "/api/integration/keys"),
      F.api("GET", "/api/integration/webhooks"),
      F.api("GET", "/api/integration/maps")]).then(function (res) {
      var keys = res[0], wh = res[1], maps = res[2];
      var html = '<div class="panel"><div class="panel-title">集成中心（三通道）' +
        F.chips([["keys", "API Key", keys.list.length],
          ["hooks", "Webhook", wh.list.length],
          ["maps", "字段映射", maps.list.length],
          ["sync", "增量同步"]], tab, "data-tab") + "</div>" +
        '<div class="panel-body" id="intBody"></div></div>';
      document.getElementById("view").innerHTML = html;
      var body = document.getElementById("intBody");
      function paint(t) {
        if (t === "keys") {
          body.innerHTML = (F.isAdmin() ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="ikNew">生成 API Key</button></div>' : "") +
            F.table([
              { label: "名称", key: "name" },
              { label: "前缀", render: function (r) { return '<span class="mono">' + F.esc(r.prefix) + "…</span>"; } },
              { label: "范围", render: function (r) { return F.tag(r.scope === "write" ? "读写" : "只读",
                  r.scope === "write" ? "blue" : "gray"); } },
              { label: "最近使用", render: function (r) { return F.esc(r.last_used || "—"); } },
              { label: "状态", render: function (r) { return F.tag(r.enabled ? "启用" : "停用"); } }
            ], keys.list);
          var nb = document.getElementById("ikNew");
          if (nb) nb.addEventListener("click", function () {
            F.dialog("生成 API Key", '<div class="form-grid">' +
              '<label>名称<input id="ikName" placeholder="如 ERP-推送"></label>' +
              '<label>权限<select id="ikScope"><option value="read">只读</option>' +
              '<option value="write">读写</option></select></label></div>',
              '<button class="btn" id="ikCancel">取消</button><button class="btn primary" id="ikOk">生成</button>');
            document.getElementById("ikCancel").addEventListener("click", F.closeDialog);
            document.getElementById("ikOk").addEventListener("click", function () {
              F.api("POST", "/api/integration/keys", {
                name: document.getElementById("ikName").value.trim(),
                scope: document.getElementById("ikScope").value
              }).then(function (r) {
                F.closeDialog();
                F.dialog("请立即保存 API Key（仅显示一次）",
                  '<div class="secret-box mono" id="ikRaw">' + F.esc(r.key) + "</div>" +
                  '<div class="muted small" style="margin-top:8px">以请求头 X-Qms-Key 携带；' +
                  "平台侧仅存 SHA-256 摘要，丢失只能重建。</div>",
                  '<button class="btn primary" id="ikCopied">已保存</button>');
                document.getElementById("ikCopied").addEventListener("click", function () {
                  F.closeDialog(); F.go("integration", { tab: "keys" });
                });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else if (t === "hooks") {
          body.innerHTML = (F.isAdmin() ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="whNew">新建 Webhook</button></div>' : "") +
            F.table([
              { label: "名称", key: "name" },
              { label: "URL", render: function (r) { return '<span class="mono small">' +
                F.esc(r.url) + "</span>"; } },
              { label: "事件", render: function (r) { return F.esc(r.events || "全部"); } },
              { label: "最近投递", render: function (r) { return F.tag(
                  r.last_status === "ok" ? "成功" : (r.last_status === "failed" ? "失败" : "待投递")); } }
            ], wh.list) +
            '<div class="sub-title">支持事件（' + wh.events.length + " 种）</div>" +
            '<div class="event-tags">' + wh.events.map(function (e) {
              return '<span class="tag gray mono">' + F.esc(e) + "</span>";
            }).join(" ") + "</div>" +
            '<div class="sub-title">最近投递日志</div>' +
            F.table([
              { label: "时间", render: function (r) { return '<span class="mono small">' + F.esc(r.ts) + "</span>"; } },
              { label: "事件", render: function (r) { return '<span class="mono">' + F.esc(r.event) + "</span>"; } },
              { label: "状态", render: function (r) { return F.tag(r.status === "ok" ? "成功" :
                  r.status === "failed" ? "失败" : "待投递"); } },
              { label: "响应", render: function (r) { return '<span class="small">' + F.esc(r.response) + "</span>"; } }
            ], wh.logs, { empty: "暂无投递记录" });
          var nb = document.getElementById("whNew");
          if (nb) nb.addEventListener("click", function () {
            F.dialog("新建 Webhook", '<div class="form-grid">' +
              '<label>名称<input id="whName"></label>' +
              '<label class="full">URL<input id="whUrl" placeholder="https://…"></label></div>',
              '<button class="btn" id="whCancel">取消</button><button class="btn primary" id="whOk">创建</button>');
            document.getElementById("whCancel").addEventListener("click", F.closeDialog);
            document.getElementById("whOk").addEventListener("click", function () {
              F.api("POST", "/api/integration/webhooks", {
                name: document.getElementById("whName").value.trim(),
                url: document.getElementById("whUrl").value.trim()
              }).then(function (r) {
                F.closeDialog();
                F.dialog("Webhook 已创建", '<div class="secret-box mono">' + F.esc(r.secret) +
                  "</div>" + '<div class="muted small" style="margin-top:8px">签名算法：' +
                  "HMAC-SHA256(secret, timestamp + \".\" + body)，请验签 X-Qms-Signature。</div>",
                  '<button class="btn primary" id="whSaved">已保存</button>');
                document.getElementById("whSaved").addEventListener("click", function () {
                  F.closeDialog(); F.go("integration", { tab: "hooks" });
                });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else if (t === "maps") {
          body.innerHTML = (F.isAdmin() ? '<div class="form-foot" style="justify-content:flex-start">' +
            '<button class="btn primary" id="mpNew">新增映射</button></div>' : "") +
            F.table([
              { label: "外部系统", key: "system" },
              { label: "实体", key: "entity" },
              { label: "外部主键", render: function (r) { return '<span class="mono">' + F.esc(r.ext_id) + "</span>"; } },
              { label: "内部单号", render: function (r) { return '<span class="mono">' + F.esc(r.int_id) + "</span>"; } },
              { label: "创建时间", render: function (r) { return '<span class="small">' + F.esc(r.created) + "</span>"; } }
            ], maps.list);
          var mb = document.getElementById("mpNew");
          if (mb) mb.addEventListener("click", function () {
            F.dialog("新增字段映射", '<div class="form-grid">' +
              '<label>系统<input id="mpSys" placeholder="ERP"></label>' +
              '<label>实体<input id="mpEnt" placeholder="inspection"></label>' +
              '<label>外部主键<input id="mpExt"></label>' +
              '<label>内部单号<input id="mpInt" placeholder="IQ2610-0001"></label></div>',
              '<button class="btn" id="mpOk">保存</button>');
            document.getElementById("mpOk").addEventListener("click", function () {
              F.api("POST", "/api/integration/maps", {
                system: document.getElementById("mpSys").value.trim(),
                entity: document.getElementById("mpEnt").value.trim(),
                extId: document.getElementById("mpExt").value.trim(),
                intId: document.getElementById("mpInt").value.trim()
              }).then(function () {
                F.closeDialog(); F.toast("映射已保存", "ok"); F.go("integration", { tab: "maps" });
              }).catch(function (e) { F.toast(e.message, "err"); });
            });
          });
        } else {
          F.api("GET", "/api/sync/changes?since=0").then(function (s) {
            body.innerHTML = '<div class="kv-grid">' +
              F.kv("同步端点", "GET /api/sync/changes?since={cursor}") +
              F.kv("当前游标", '<b class="mono">' + s.cursor + "</b>") +
              F.kv("单次上限", "500 条") + "</div>" +
              '<div class="sub-title">事件流（最近 20 条）</div>' +
              F.table([
                { label: "ID", num: true, key: "id" },
                { label: "时间", render: function (r) { return '<span class="mono small">' + F.esc(r.ts) + "</span>"; } },
                { label: "事件", render: function (r) { return '<span class="mono">' + F.esc(r.event) + "</span>"; } }
              ], s.changes.slice(-20).reverse()) +
              '<div class="muted small" style="margin-top:8px">对接方按游标增量拉取，' +
              "配合 Webhook 实时推送做兜底补偿。</div>";
          }).catch(function (e) { F.toast(e.message, "err"); });
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
      F.setStatus("集成中心 · API Key / Webhook / 增量同步");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);
