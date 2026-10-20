/* 飞控 QMS · 主数据：检验方案、缺陷代码、质量文件 */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ------------------------------------------------------ 检验方案 */
  F.register("plans", function () {
    F.api("GET", "/api/plans").then(function (d) {
      var typeLabel = { IQC: "来料", IPQC: "过程", FQC: "成品", OQC: "出货" };
      var html = '<div class="panel"><div class="panel-title">检验方案库' +
        '<span class="panel-actions small muted">共 ' + d.total + " 套 · AQL 按 ISO 2859-1</span></div>" +
        '<div class="panel-body flush">' +
        F.table([
          { label: "方案", render: function (r) { return '<span class="mono">' + F.esc(r.code) +
              "</span> <b>" + F.esc(r.name) + "</b>"; } },
          { label: "类型", render: function (r) { return F.tag(r.itype, "blue"); } },
          { label: "适用物料", render: function (r) { return F.esc(r.mat_code || "通用"); } },
          { label: "AQL / 水平", render: function (r) {
              return r.aql === "-" ? "—" : "AQL " + r.aql + " · IL " + r.il; } },
          { label: "项目数", num: true, render: function (r) { return (r.items || []).length; } },
          { label: "检验项目", render: function (r) {
              return (r.items || []).map(function (it) {
                return '<span class="tag ' + (it.severity === "A" ? "red" :
                  it.severity === "B" ? "gold" : "gray") + '">' + F.esc(it.item) + "</span>";
              }).join(" ") || "—"; } }
        ], d.list, { empty: "暂无方案" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setSide('<div class="side-block"><div class="hd">方案说明</div><div class="bd small muted" ' +
        'style="line-height:1.9">· 新建检验单时自动按类型与物料匹配方案并载入项目<br>' +
        "· A 级项目为致命特性，Ac=0 一票否决<br>· 抽样量按批量与 AQL 自动查表</div></div>");
      F.setStatus("检验方案 · 共 " + d.total + " 套");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 缺陷代码 */
  F.register("defects", function () {
    F.api("GET", "/api/defects").then(function (d) {
      var sev = { A: "致命", B: "严重", C: "轻微" };
      var by = {};
      (d.list || []).forEach(function (r) { (by[r.category] = by[r.category] || []).push(r); });
      var html = '<div class="panel"><div class="panel-title">缺陷代码库' +
        '<span class="panel-actions small muted">共 ' + d.total + " 项 · " + Object.keys(by).length +
        " 个分类</span></div>";
      Object.keys(by).forEach(function (cat) {
        html += '<div class="panel-body flush" style="padding-top:0">' +
          '<div class="sub-title">' + F.esc(cat) + "</div>" +
          F.table([
            { label: "代码", render: function (r) { return '<span class="mono">' + F.esc(r.code) + "</span>"; } },
            { label: "名称", key: "name" },
            { label: "等级", render: function (r) { return F.tag(sev[r.severity] || r.severity,
                r.severity === "A" ? "red" : (r.severity === "B" ? "gold" : "blue")); } },
            { label: "关联物料", render: function (r) { return F.esc(r.mat_code || "通用"); } },
            { label: "工序", render: function (r) { return F.esc(r.process || "—"); } }
          ], by[cat]) + "</div>";
      });
      document.getElementById("view").innerHTML = html + "</div>";
      F.setStatus("缺陷代码 · 共 " + d.total + " 项");
      F.setSide('<div class="side-block"><div class="hd">加权规则</div><div class="bd small muted" ' +
        'style="line-height:1.9">缺陷加权指数 = 致命×10 + 严重×5 + 轻微×1，' +
        "用于供应商质量评分与帕累托加权口径。</div></div>");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  /* ------------------------------------------------------ 质量文件 */
  F.register("qdocs", function () {
    F.api("GET", "/api/qdocs").then(function (d) {
      var html = '<div class="panel"><div class="panel-title">质量文件中心' +
        '<span class="panel-actions small muted">SOP / SIP 版本受控</span></div><div class="panel-body flush">' +
        F.table([
          { label: "编号", render: function (r) { return '<span class="mono">' + F.esc(r.code) + "</span>"; } },
          { label: "名称", key: "name" },
          { label: "类别", render: function (r) { return F.tag(r.category, r.category === "SIP" ? "blue" : "gray"); } },
          { label: "版本", render: function (r) { return '<span class="mono">' + F.esc(r.version) + "</span>"; } },
          { label: "负责人", render: function (r) { return F.esc(r.owner || "—"); } },
          { label: "状态", render: function (r) { return F.tag(r.status); } },
          { label: "发行时间", render: function (r) { return F.esc(r.released || "—"); } }
        ], d.list, { empty: "暂无文件" }) + "</div></div>";
      document.getElementById("view").innerHTML = html;
      F.setStatus("质量文件 · 共 " + d.total + " 份");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });
})(window, document);
