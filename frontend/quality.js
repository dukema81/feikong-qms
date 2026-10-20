/* 飞控 QMS · 不合格品 NCR 与纠正预防 CAPA */
(function (window, document) {
  "use strict";
  var F = window.F;

  /* ------------------------------------------------------ NCR */
  F.register("ncr", function () {
    var stFilter = F.state.params.st || "";
    F.api("GET", "/api/ncrs" + (stFilter ? "?status=" + encodeURIComponent(stFilter) : ""))
      .then(function (d) {
      var cnt = {};
      (d.list || []).forEach(function (r) { cnt[r.status] = (cnt[r.status] || 0) + 1; });
      var html = '<div class="panel"><div class="panel-title">不合格品报告 NCR' +
        '<span class="panel-actions">' +
        (F.can("ncr.manage") ? '<button class="btn primary sm" id="nNew">手工开立</button>' : "") +
        "</span></div><div class='panel-body'>" +
        F.chips([["", "全部", d.total], ["待评审", "待评审", cnt["待评审"]],
          ["已评审", "已评审", cnt["已评审"]], ["处置中", "处置中", cnt["处置中"]],
          ["待验证", "待验证", cnt["待验证"]], ["已关闭", "已关闭", cnt["已关闭"]]],
          stFilter, "data-st") + "</div><div class='panel-body flush'>" +
        F.table([
          { label: "NCR 单号", render: function (r) {
              return '<span class="mono">' + F.esc(r.no) + "</span>" +
                '<br><span class="muted small">来源 ' + F.esc(r.insNo || "手工") + "</span>"; } },
          { label: "物料 / 批次", render: function (r) {
              return F.esc(r.matCode) + '<br><span class="muted small mono">' +
                F.esc(r.batchNo || "—") + "</span>"; } },
          { label: "不良 / 批量", num: true, render: function (r) {
              return r.badQty + " / " + F.int(r.qty); } },
          { label: "等级", render: function (r) { return F.tag(r.severityName); } },
          { label: "状态", render: function (r) { return F.tag(r.status) +
              (r.dueState === "已逾期" ? ' <span class="tag red">逾期</span>' : ""); } },
          { label: "处置", render: function (r) {
              return r.disposition ? F.tag(r.disposition) : "—"; } },
          { label: "责任人", render: function (r) { return F.esc(r.owner || "—"); } },
          { label: "时限", render: function (r) { return F.esc(r.due || "—") +
              '<br><span class="small muted">' + F.esc(r.dueState) + "</span>"; } }
        ], d.list, { click: function (r) { return r.no; }, empty: "暂无 NCR" }) +
        "</div></div>";
      document.getElementById("view").innerHTML = html;
      document.querySelectorAll("[data-st]").forEach(function (b) {
        b.addEventListener("click", function () { F.go("ncr", { st: b.getAttribute("data-st") }); });
      });
      var nb = document.getElementById("nNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("手工开立 NCR",
          '<div class="form-grid">' +
          '<label>物料编码<input id="nnMat" placeholder="MAT001"></label>' +
          '<label>批次号<input id="nnBatch"></label>' +
          '<label>批量<input id="nnQty" type="number" value="100"></label>' +
          '<label>不良数<input id="nnBad" type="number" value="1"></label>' +
          '<label>等级<select id="nnSev"><option value="A">致命 A</option>' +
          '<option value="B" selected>严重 B</option><option value="C">轻微 C</option></select></label>' +
          '<label>描述<input id="nnDesc" placeholder="不良现象描述"></label></div>',
          '<button class="btn" id="nnCancel">取消</button><button class="btn primary" id="nnOk">开立</button>');
        document.getElementById("nnCancel").addEventListener("click", F.closeDialog);
        document.getElementById("nnOk").addEventListener("click", function () {
          F.api("POST", "/api/ncrs", {
            matCode: document.getElementById("nnMat").value.trim(),
            batchNo: document.getElementById("nnBatch").value.trim(),
            qty: Number(document.getElementById("nnQty").value || 0),
            badQty: Number(document.getElementById("nnBad").value || 0),
            severity: document.getElementById("nnSev").value,
            description: document.getElementById("nnDesc").value.trim()
          }).then(function (r) {
            F.closeDialog(); F.toast("NCR 已开立：" + r.no, "ok"); F.go("ncr");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.bindRows(document, openNcr);
      F.setSide('<div class="side-block"><div class="hd">NCR 五态</div><div class="bd small muted" ' +
        'style="line-height:1.9">待评审 → 已评审 → 处置中 → 待验证 → 已关闭<br>' +
        "· 让步接收须过不良率上限闸口<br>· 关闭前须完成效果验证</div></div>");
      F.setStatus("不合格品 NCR · 共 " + d.total + " 单");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  var NCR_BTN = {
    "待评审": [["已评审", "评审"]],
    "已评审": [["处置中", "下达处置"]],
    "处置中": [["待验证", "处置完成"]],
    "待验证": [["已关闭", "验证关闭"]]
  };

  function openNcr(no) {
    F.api("GET", "/api/ncrs/" + no).then(function (d) {
      var fields = "";
      if (d.status === "待评审") {
        fields = '<div class="form-grid"><label class="full">评审意见<textarea id="nsReview" rows="2">' +
          F.esc(d.review || "") + "</textarea></label>" +
          '<label>处置方式<select id="nsDisp"><option value=""></option>' +
          (d.dispositions || ["返工", "返修", "让步接收", "报废", "退货", "挑选使用"]).map(function (x) {
            return '<option value="' + F.esc(x) + '">' + F.esc(x) + "</option>";
          }).join("") + "</select></label></div>";
      } else if (d.status === "已评审") {
        fields = '<div class="form-grid"><label>处置责任人<input id="nsOwner" value="' +
          F.esc(d.owner || "") + '"></label><label>处置时限<input id="nsDue" type="date" value="' +
          F.esc(d.due || F.today()) + '"></label></div>';
      } else if (d.status === "处置中") {
        fields = '<div class="form-grid"><label class="full">处置结果<textarea id="nsDone" rows="2">' +
          "</textarea></label></div>";
      } else if (d.status === "待验证") {
        fields = '<div class="form-grid"><label class="full">效果验证<textarea id="nsVerified" rows="2">' +
          "</textarea></label><label>验证人<input id='nsVerifier' value='" +
          F.esc(F.me().username || "") + "'></label></div>";
      }
      var btns = (NCR_BTN[d.status] || []).map(function (b) {
        return '<button class="btn primary" data-stage="' + b[0] + '">' + b[1] + "</button>";
      }).join(" ");
      F.dialogWide("NCR " + d.no + "（" + d.status + "）",
        '<div class="kv-grid">' +
        F.kv("物料 / 批次", F.esc(d.matCode) + " / " + F.esc(d.batchNo || "—")) +
        F.kv("来源检验单", d.insNo ? '<span class="mono">' + F.esc(d.insNo) + "</span>" : "手工") +
        F.kv("不良 / 批量", d.badQty + " / " + F.int(d.qty)) +
        F.kv("等级", F.tag(d.severityName)) +
        F.kv("状态", F.tag(d.status)) +
        F.kv("时限", F.esc(d.due || "—") + "（" + d.dueState + "）") +
        F.kv("责任人", F.esc(d.owner || "—")) +
        F.kv("处置方式", d.disposition ? F.tag(d.disposition) : "—") +
        "</div>" +
        '<div class="sub-title">不良描述</div><div class="small" style="line-height:1.8">' +
        F.esc(d.description) + "</div>" +
        (d.review ? '<div class="sub-title">评审意见</div><div class="small">' + F.esc(d.review) + "</div>" : "") +
        (d.verified ? '<div class="sub-title">验证记录</div><div class="small">' +
          F.esc(d.verified) + "（" + F.esc(d.verifier) + "）</div>" : "") +
        (fields ? '<div class="sub-title">本次动作</div>' + fields : ""),
        (btns ? btns + " " : "") + '<button class="btn" data-close-x="1">关闭</button>');
      var dlg = document.getElementById("dialog");
      dlg.querySelector("[data-close-x]").addEventListener("click", F.closeDialog);
      dlg.querySelectorAll("[data-stage]").forEach(function (b) {
        b.addEventListener("click", function () {
          var target = b.getAttribute("data-stage");
          var body = { target: target };
          var g = function (id) { var el = document.getElementById(id);
            return el ? el.value.trim() : ""; };
          if (target === "已评审") { body.review = g("nsReview"); body.disposition = g("nsDisp"); }
          if (target === "处置中") { body.owner = g("nsOwner"); body.due = g("nsDue"); }
          if (target === "待验证") { body.doneDesc = g("nsDone"); }
          if (target === "已关闭") { body.verified = g("nsVerified"); body.verifier = g("nsVerifier"); }
          F.api("POST", "/api/ncrs/" + d.no + "/stage", body).then(function (r) {
            F.toast("NCR 已推进至「" + r.status + "」", "ok"); openNcr(d.no);
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
    }).catch(function (e) { F.toast(e.message, "err"); });
  }

  /* ------------------------------------------------------ CAPA */
  F.register("capa", function () {
    F.api("GET", "/api/capas").then(function (d) {
      var open = d.list.filter(function (r) { return r.status !== "已关闭"; });
      var html = '<div class="panel"><div class="panel-title">纠正预防措施 CAPA（8D）' +
        '<span class="panel-actions">' +
        (F.can("capa.manage") ? '<button class="btn primary sm" id="cNew">发起 CAPA</button>' : "") +
        "</span></div><div class='panel-body flush'>" +
        F.table([
          { label: "单号", render: function (r) { return '<span class="mono">' + F.esc(r.no) + "</span>" +
              '<br><span class="muted small">' + F.esc(r.source) +
              (r.ncrNo ? " · " + F.esc(r.ncrNo) : "") + "</span>"; } },
          { label: "问题", render: function (r) { return '<span class="small"><b>' +
              F.esc(r.problem.length > 24 ? r.problem.slice(0, 24) + "…" : r.problem) +
              "</b></span>"; } },
          { label: "步骤", render: function (r) {
              return F.tag(r.step) + " " + F.esc(r.stepName) +
                '<div class="pbar" style="margin-top:4px"><i style="width:' + r.progress + '%"></i></div>'; } },
          { label: "组长", render: function (r) { return F.esc(r.leader || "—"); } },
          { label: "状态", render: function (r) { return F.tag(r.status) +
              (r.dueState === "已逾期" ? ' <span class="tag red">逾期</span>' : ""); } },
          { label: "时限", render: function (r) { return F.esc(r.due || "—"); } }
        ], d.list, { click: function (r) { return r.no; }, empty: "暂无 CAPA" }) +
        "</div></div>";
      document.getElementById("view").innerHTML = html;
      var nb = document.getElementById("cNew");
      if (nb) nb.addEventListener("click", function () {
        F.dialog("发起 CAPA",
          '<div class="form-grid">' +
          '<label>来源<select id="ncSrc"><option>客户投诉</option><option>NCR</option>' +
          "<option>内审</option><option>数据分析</option><option>内部</option></select></label>" +
          '<label>关联 NCR（可选）<input id="ncNcr" placeholder="NCR2601-0001"></label>' +
          '<label class="full">问题描述（≥8 字）<textarea id="ncProblem" rows="2"></textarea></label>' +
          '<label>组长<input id="ncLeader"></label>' +
          '<label>成员（逗号分隔）<input id="ncMembers"></label></div>',
          '<button class="btn" id="ncCancel">取消</button><button class="btn primary" id="ncOk">创建</button>');
        document.getElementById("ncCancel").addEventListener("click", F.closeDialog);
        document.getElementById("ncOk").addEventListener("click", function () {
          F.api("POST", "/api/capas", {
            source: document.getElementById("ncSrc").value,
            ncrNo: document.getElementById("ncNcr").value.trim(),
            problem: document.getElementById("ncProblem").value.trim(),
            leader: document.getElementById("ncLeader").value.trim(),
            members: document.getElementById("ncMembers").value.trim()
          }).then(function (r) {
            F.closeDialog(); F.toast("CAPA 已发起：" + r.no, "ok"); F.go("capa");
          }).catch(function (e) { F.toast(e.message, "err"); });
        });
      });
      F.bindRows(document, openCapa);
      F.setSide('<div class="side-block"><div class="hd">8D 步骤</div><div class="bd small muted" ' +
        'style="line-height:1.9">' + Object.keys(d.stepNames).map(function (s) {
          return "● " + s + " " + d.stepNames[s];
        }).join("<br>") + "</div></div>" +
        '<div class="side-block"><div class="hd">进行中</div><div class="bd">' +
        F.kv("未关闭", open.length + " 项") +
        F.kv("逾期", open.filter(function (r) { return r.dueState === "已逾期"; }).length + " 项") +
        "</div></div>");
      F.setStatus("纠正预防 CAPA · 共 " + d.total + " 项");
    }).catch(function (e) { F.toast(e.message, "err"); });
  });

  function openCapa(no) {
    F.api("GET", "/api/capas/" + no).then(function (d) {
      var need = { D2: ["description", "问题描述（≥20 字，5W2H）"],
        D4: ["rootCause", "根因分析（≥10 字，5Why）"],
        D6: ["effect", "实施效果验证"],
        D7: ["prevention", "预防再发措施"] }[d.nextStep];
      var fields = "";
      if (d.status !== "已关闭") {
        if (d.step === "D1") {
          fields = '<div class="form-grid"><label>组长<input id="cpLeader" value="' +
            F.esc(d.leader || "") + '"></label><label>成员<input id="cpMembers" value="' +
            F.esc(d.members || "") + '"></label></div>';
        }
        if (need) {
          fields += '<div class="form-grid"><label class="full">' + need[1] +
            '<textarea id="cp_' + need[0] + '" rows="2">' +
            F.esc(d[need[0]] || "") + "</textarea></label></div>";
        }
        if (d.step === "D3") {
          fields += '<div class="form-grid"><label class="full">纠正措施<textarea id="cp_actions" rows="2">' +
            F.esc(d.actions || "") + "</textarea></label></div>";
        }
      }
      var tasks = (d.tasks || []).map(function (t) {
        return '<tr><td>' + F.tag(t.phase) + "</td><td>" + F.esc(t.action) + "</td><td>" +
          F.esc(t.owner) + "</td><td>" + F.esc(t.due) + "</td><td>" + F.tag(t.status) + "</td></tr>";
      }).join("");
      var steps = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"].map(function (s) {
        var done = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"].indexOf(s) <=
          ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"].indexOf(d.step);
        return '<span class="tag ' + (done ? "green" : "gray") + '">' + s + "</span>";
      }).join(" → ");
      F.dialogWide("CAPA " + d.no + " · " + d.status,
        '<div class="kv-grid">' +
        F.kv("来源", F.esc(d.source) + (d.ncrNo ? " · " + F.esc(d.ncrNo) : "")) +
        F.kv("状态", F.tag(d.status)) +
        F.kv("当前步骤", F.tag(d.step) + " " + F.esc(d.stepName)) +
        F.kv("组长 / 成员", F.esc(d.leader || "—") + " / " + F.esc(d.members || "—")) +
        F.kv("时限", F.esc(d.due || "—") + "（" + d.dueState + "）") +
        F.kv("目标", F.esc(d.target || "—")) +
        "</div>" +
        '<div class="sub-title">8D 进度</div><div style="margin:6px 0">' + steps + "</div>" +
        '<div class="sub-title">问题描述</div><div class="small" style="line-height:1.8">' +
        F.esc(d.description || d.problem) + "</div>" +
        (d.rootCause ? '<div class="sub-title">根因</div><div class="small">' + F.esc(d.rootCause) + "</div>" : "") +
        (d.actions ? '<div class="sub-title">纠正措施</div><div class="small">' + F.esc(d.actions) + "</div>" : "") +
        (d.effect ? '<div class="sub-title">效果验证</div><div class="small">' + F.esc(d.effect) + "</div>" : "") +
        (tasks ? '<div class="sub-title">任务清单</div><table class="grid-table"><thead><tr>' +
          "<th>阶段</th><th>任务</th><th>负责人</th><th>时限</th><th>状态</th></tr></thead><tbody>" +
          tasks + "</tbody></table>" : "") +
        (fields ? '<div class="sub-title">推进至 ' + d.nextStep + "（" +
          F.esc(d.stepName) + "→）</div>" + fields : ""),
        (d.status !== "已关闭" ? '<button class="btn primary" id="cpStep">推进到 ' +
          d.nextStep + "</button> " : "") + '<button class="btn" data-close-x="1">关闭</button>');
      var dlg = document.getElementById("dialog");
      dlg.querySelector("[data-close-x]").addEventListener("click", F.closeDialog);
      var sb = document.getElementById("cpStep");
      if (sb) sb.addEventListener("click", function () {
        var g = function (id) { var el = document.getElementById(id);
          return el ? el.value.trim() : ""; };
        var body = { leader: g("cpLeader") || d.leader, members: g("cpMembers") || d.members,
          description: g("cp_description") || d.description,
          rootCause: g("cp_rootCause") || d.rootCause,
          actions: g("cp_actions") || d.actions, effect: g("cp_effect") || d.effect,
          prevention: g("cp_prevention") };
        F.api("POST", "/api/capas/" + d.no + "/step", body).then(function (r) {
          F.toast("已推进至 " + r.step + "（" + r.stepName + "）", "ok"); openCapa(d.no);
        }).catch(function (e) { F.toast(e.message, "err"); });
      });
    }).catch(function (e) { F.toast(e.message, "err"); });
  }
})(window, document);
