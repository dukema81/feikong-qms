/* 飞控 QMS · 检验作业：IQC / IPQC / FQC(含OQC) 列表、详情推进、新建检验单 */
(function (window, document) {
  "use strict";
  var F = window.F;

  var TYPE_CONF = {
    iqc: { itype: "IQC", label: "来料检验", perm: "iqc.do" },
    ipqc: { itype: "IPQC", label: "过程检验", perm: "ipqc.do" },
    fqc: { itype: "FQC", label: "成品/出货检验", perm: "fqc.do" }
  };

  function listPage(kind) {
    var conf = TYPE_CONF[kind];
    var stFilter = F.state.params.st || "";
    var q = F.state.params.q || "";
    F.api("GET", "/api/inspections?itype=" + conf.itype +
      (stFilter ? "&status=" + encodeURIComponent(stFilter) : "") +
      (q ? "&q=" + encodeURIComponent(q) : "")).then(function (d) {
      var cnt = {};
      (d.list || []).forEach(function (r) { cnt[r.status] = (cnt[r.status] || 0) + 1; });
      var html = '<div class="panel"><div class="panel-title">' + conf.label + "检验单" +
        '<span class="panel-actions">' +
        '<input class="inp sm" id="q" placeholder="单号/物料/批次/工单" value="' + F.esc(q) + '">' +
        '<button class="btn sm" id="go">查询</button>' +
        (F.can(conf.perm) ? '<button class="btn primary sm" id="newIns">新建检验单</button>' : "") +
        "</span></div><div class='panel-body'>" +
        F.chips([["", "全部", d.total], ["待检验", "待检验", cnt["待检验"]],
          ["检验中", "检验中", cnt["检验中"]], ["待判定", "待判定", cnt["待判定"]],
          ["已判定", "已判定", cnt["已判定"]], ["已放行", "已放行", cnt["已放行"]],
          ["已关闭", "已关闭", cnt["已关闭"]]], stFilter, "data-st") +
        "</div><div class='panel-body flush'>" +
        F.table([
          { label: "单号", render: function (r) {
              return '<span class="mono">' + F.esc(r.no) + "</span>" +
                (r.ncrNo ? '<br><span class="tag red small">NCR ' + F.esc(r.ncrNo) + "</span>" : ""); } },
          { label: "物料", render: function (r) { return "<b>" + F.esc(r.matName) + "</b>" +
              '<br><span class="muted small mono">' + F.esc(r.matCode) + "</span>"; } },
          { label: kind === "iqc" ? "供应商" : (kind === "ipqc" ? "工序" : "工单/批次"),
            render: function (r) {
              if (kind === "iqc") return F.esc(r.supplier || "—");
              if (kind === "ipqc") return F.esc(r.process || "—");
              return F.esc(r.orderNo || "—") + " / " + F.esc(r.batchNo || "—"); } },
          { label: "批量", num: true, render: function (r) { return F.int(r.lotSize); } },
          { label: "抽样", num: true, render: function (r) {
              return r.plan ? r.plan.sampleSize + ' <span class="muted small">Ac=' + r.plan.ac + "</span>" : "—"; } },
          { label: "状态", render: function (r) { return F.tag(r.status); } },
          { label: "判定", render: function (r) {
              return r.verdict ? F.tag(r.verdict) + (r.criticalBad > 0 ?
                ' <span class="tag red">致命 ' + r.criticalBad + "</span>" : "") : "—"; } },
          { label: "检验员", render: function (r) { return F.esc(r.inspector || "—"); } },
          { label: "创建", render: function (r) {
              return '<span class="small muted">' + F.esc((r.created || "").slice(0, 10)) + "</span>"; } }
        ], d.list, { click: function (r) { return r.no; },
          empty: "暂无" + conf.label + "检验单" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;

      document.getElementById("go").addEventListener("click", function () {
        F.go(kind, { q: document.getElementById("q").value.trim(), st: stFilter });
      });
      document.querySelectorAll("[data-st]").forEach(function (b) {
        b.addEventListener("click", function () {
          F.go(kind, { q: q, st: b.getAttribute("data-st") });
        });
      });
      var nb = document.getElementById("newIns");
      if (nb) nb.addEventListener("click", function () { newDialog(kind); });
      F.bindRows(document, openDetail);
      F.setSide('<div class="side-block"><div class="hd">' + conf.label + "口径</div>" +
        '<div class="bd small muted" style="line-height:1.9">· 抽样按 ISO 2859-1 一般水平 II 查表<br>' +
        "· 致命缺陷（A类）Ac=0 一票否决<br>· 不合格判定自动开立 NCR<br>" +
        "· 项目全部录入后才可提交判定</div></div>");
      F.setStatus(conf.label + " · 共 " + d.total + " 单");
    }).catch(function (e) { F.toast(e.message, "err"); });
  }

  F.register("iqc", function () { listPage("iqc"); });
  F.register("ipqc", function () { listPage("ipqc"); });
  F.register("fqc", function () { listPage("fqc"); });

  /* ------------------------------------------------------ 新建检验单 */
  function newDialog(kind) {
    var conf = TYPE_CONF[kind];
    Promise.all([F.api("GET", "/api/materials"), F.api("GET", "/api/suppliers")])
      .then(function (res) {
        F.dialog("新建" + conf.label + "检验单",
          '<div class="form-grid">' +
          '<label>物料<select id="niMat">' + (res[0].list || []).map(function (x) {
            return '<option value="' + F.esc(x.code) + '">' + F.esc(x.code + " " + x.name) + "</option>";
          }).join("") + "</select></label>" +
          (kind === "iqc" ? '<label>供应商<select id="niSup"><option value=""></option>' +
            (res[1].list || []).map(function (x) {
              return '<option value="' + F.esc(x.code) + '">' + F.esc(x.code + " " + x.name) + "</option>";
            }).join("") + "</select></label>" : "") +
          (kind === "ipqc" ? '<label>工序<input id="niProc" placeholder="如 SMT / 组装"></label>' : "") +
          '<label>' + (kind === "iqc" ? "采购单号" : (kind === "ipqc" ? "工单号" : "生产工单")) +
          '<input id="niOrder" placeholder="如 PO-2601-0001"></label>' +
          '<label>批次号<input id="niBatch" placeholder="如 LOT-26010101"></label>' +
          '<label>批量<input id="niLot" type="number" value="1000" min="1"></label>' +
          '<label>AQL（留空自动取方案）<input id="niAql" placeholder="1.0"></label></div>',
          '<button class="btn" id="niCancel">取消</button>' +
          '<button class="btn primary" id="niOk">创建</button>');
        document.getElementById("niCancel").addEventListener("click", F.closeDialog);
        document.getElementById("niOk").addEventListener("click", function () {
          var body = { itype: conf.itype,
            matCode: document.getElementById("niMat").value,
            orderNo: document.getElementById("niOrder").value.trim(),
            batchNo: document.getElementById("niBatch").value.trim(),
            lotSize: Number(document.getElementById("niLot").value || 0) };
          if (kind === "iqc") body.supplier = document.getElementById("niSup").value;
          if (kind === "ipqc") body.process = document.getElementById("niProc").value.trim();
          var aql = document.getElementById("niAql").value.trim();
          if (aql) body.aql = aql;
          F.api("POST", "/api/inspections", body).then(function (r) {
            F.closeDialog();
            F.toast("检验单已创建：" + r.no + "（抽样 " + r.sampleSize + "）", "ok");
            F.go(kind);
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      }).catch(function (e) { F.toast(e.message, "err"); });
  }

  /* ------------------------------------------------------ 详情与推进 */
  var STAGE_BTN = {
    "待检验": [["检验中", "开始检验", "primary"]],
    "检验中": [["待判定", "提交判定", "primary"]],
    "待判定": [["已判定", "判定", "primary"]],
    "已判定": [["已放行", "放行", "primary"], ["已关闭", "关闭", ""]],
    "已放行": [["已关闭", "关闭", ""]]
  };

  function openDetail(no) {
    F.api("GET", "/api/inspections/" + no).then(function (d) {
      var canDo = F.can("iqc.do") || F.can("ipqc.do") || F.can("fqc.do");
      var items = (d.items || []).map(function (it) {
        return '<tr><td>' + it.seq + "</td><td><b>" + F.esc(it.item) + "</b></td><td class='small'>" +
          F.esc(it.standard) + "</td><td>" + F.esc(it.tool) + "</td><td>" +
          F.tag(it.severity, it.severity === "A" ? "red" : (it.severity === "B" ? "gold" : "blue")) +
          "</td><td>" + (it.result ? F.tag(it.result) : '<input class="inp sm" style="width:64px" ' +
            'data-rec-seq="' + it.seq + '" data-rec-ok="1" placeholder="OK/NG">') + "</td><td>" +
          (it.result === "NG" ? it.bad_qty : "") + "</td><td>" + F.esc(it.defect_code || "") + "</td></tr>";
      }).join("");
      var gates = (d.gates || []).map(function (g) {
        return '<div class="side-kv"><span>' + F.esc(g.name) + "</span><b>" +
          (g.ok ? '<span class="tag green">通过</span>' : '<span class="tag gold">未满足</span>') +
          "</b></div>";
      }).join("");
      var planBox = d.plan ? '<div class="sub-title">抽样方案（AQL ' + F.esc(d.aql) + "）</div>" +
        '<div class="kv-grid">' + F.kv("样本字码", d.plan.code) +
        F.kv("样本量", d.plan.sampleSize) + F.kv("Ac / Re", d.plan.ac + " / " + d.plan.re) +
        F.kv("致命 Ac", d.plan.criticalAc + "（一票否决）") + "</div>" : "";
      var btns = "";
      (STAGE_BTN[d.status] || []).forEach(function (b) {
        btns += '<button class="btn ' + b[2] + '" data-stage="' + b[0] + '">' + b[1] + "</button> ";
      });
      if (d.status === "待判定") {
        btns = '<select id="jdVerdict" class="inp sm" style="width:90px">' +
          '<option value="合格">合格</option><option value="不合格">不合格</option></select> ' + btns;
      }
      var recBtn = canDo && d.status === "检验中" ?
        '<button class="btn" id="recSave">保存录入</button> ' : "";

      F.dialogWide("检验单 " + d.no + " · " + d.typeName,
        '<div class="kv-grid">' +
        F.kv("物料", F.esc(d.matCode + " " + d.matName)) +
        F.kv("状态", F.tag(d.status)) +
        F.kv("判定", d.verdict ? F.tag(d.verdict) : "—") +
        F.kv("批量 / 抽样", F.int(d.lotSize) + " / " + F.int(d.sampleSize)) +
        F.kv("供应商", F.esc(d.supplier || "—")) +
        F.kv("工单/采购单", F.esc(d.orderNo || "—")) +
        F.kv("批次", F.esc(d.batchNo || "—")) +
        F.kv("工序", F.esc(d.process || "—")) +
        F.kv("不良（致命/严重/轻微）", d.criticalBad + " / " + d.majorBad + " / " + d.minorBad) +
        F.kv("NCR", d.ncrNo ? '<span class="mono">' + F.esc(d.ncrNo) + "</span>" : "—") +
        "</div>" + planBox +
        '<div class="sub-title">检验项目（' + d.count + ' 项）</div>' +
        '<table class="grid-table"><thead><tr><th>#</th><th>项目</th><th>标准</th><th>量具</th>' +
        "<th>等级</th><th>结果</th><th>不良</th><th>缺陷码</th></tr></thead><tbody>" + items +
        "</tbody></table>" + recBtn,
        btns + '<button class="btn" data-close-x="1">关闭</button>');

      var dlg = document.getElementById("dialog");
      dlg.querySelector("[data-close-x]").addEventListener("click", F.closeDialog);

      var rs = document.getElementById("recSave");
      if (rs) rs.addEventListener("click", function () {
        var records = [];
        dlg.querySelectorAll("[data-rec-seq]").forEach(function (i) {
          var v = (i.value || "").trim().toUpperCase();
          if (v) records.push({ seq: Number(i.getAttribute("data-rec-seq")),
            result: v === "OK" ? "OK" : "NG",
            badQty: v === "NG" ? Number(i.getAttribute("data-rec-bad") || 1) : 0 });
        });
        if (!records.length) { F.toast("请至少录入一项结果（OK/NG）", "err"); return; }
        F.api("POST", "/api/inspections/" + d.no + "/record", { records: records })
          .then(function () { F.toast("录入已保存", "ok"); openDetail(d.no); })
          .catch(function (e) { F.toast(e.message, "err"); });
      });

      dlg.querySelectorAll("[data-stage]").forEach(function (b) {
        b.addEventListener("click", function () {
          var target = b.getAttribute("data-stage");
          var body = { target: target };
          if (target === "已判定") body.verdict = document.getElementById("jdVerdict").value;
          F.api("POST", "/api/inspections/" + d.no + "/stage", body).then(function (r) {
            F.toast("已推进至「" + r.status + "」" + (r.ncrNo ? "，自动生成 NCR：" + r.ncrNo : ""), "ok");
            openDetail(d.no);
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });

      F.setSide('<div class="side-block"><div class="hd">推进闸口</div><div class="bd">' +
        (gates || '<div class="muted small">当前状态无闸口</div>') + "</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  }
  F.openInsDetail = openDetail;
})(window, document);
