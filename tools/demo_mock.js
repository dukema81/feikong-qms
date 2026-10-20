/* 飞控QMS · 离线 DEMO 内存后端：拦截 fetch，按快照同口径读写（sessionStorage 持久化） */
(function () {
  "use strict";
  var SNAP = window.__QMS_SNAPSHOT__ || {};
  var KEY = "fk_qms_demo";
  var DB = null;

  function clone(o) { return JSON.parse(JSON.stringify(o)); }
  function esc(s) { return String(s === null || s === undefined ? "" : s); }
  function lst(x) { return (x && x.list) ? x.list : (x || []); }

  function load() {
    try {
      var raw = sessionStorage.getItem(KEY);
      if (raw) { DB = JSON.parse(raw); return; }
    } catch (e) { /* ignore */ }
    DB = {
      user: { username: "admin", name: "系统管理员", role: "admin", roleName: "系统管理员",
        dept: "质量管理部", enabled: true, perms: ["board.view", "iqc.do", "ipqc.do", "fqc.do",
          "ncr.manage", "capa.manage", "mdm.edit", "supplier.edit", "coq.edit",
          "integration.admin", "settings.admin"] },
      version: "1.0.0", brand: "飞控QMS系统",
      board: SNAP.board || {}, materials: lst(SNAP.materials), suppliers: lst(SNAP.suppliers),
      plans: lst(SNAP.plans), defects: lst(SNAP.defects),
      inspections: lst(SNAP.inspections), ncrs: lst(SNAP.ncrs), capas: lst(SNAP.capas),
      spcProc: lst(SNAP.spcProcesses), spc: SNAP.spc || {},
      pareto: SNAP.pareto || {}, fpy: SNAP.fpy || {}, trend: lst(SNAP.trend),
      supplierQuality: SNAP.supplierQuality || {}, supplierPpm: lst(SNAP.supplierPpm),
      coq: SNAP.coq || {}, coqTrend: lst(SNAP.coqTrend),
      reports: SNAP.reports || {}, qdocs: lst(SNAP.qdocs),
      users: lst(SNAP.users), settings: lst(SNAP.settings), logs: lst(SNAP.logs),
      keys: [], hooks: { list: [], logs: [], events: SNAP.events || [] },
      maps: [], sync: SNAP.sync || { cursor: 0, changes: [] },
      seq: 900
    };
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(DB)); } catch (e) { /* 超限忽略 */ }
  }
  function log(action, detail) {
    DB.logs.unshift({ user: DB.user.username, action: action, detail: detail || "",
      ts: new Date().toLocaleString("zh-CN", { hour12: false }) });
  }
  function no(prefix) {
    DB.seq += 1;
    return prefix + "2610-" + String(DB.seq).slice(-4);
  }
  function err(status, msg) {
    return new Response(JSON.stringify({ code: status, message: msg }),
      { status: status, headers: { "Content-Type": "application/json" } });
  }
  function ok(data) {
    return new Response(JSON.stringify(data === undefined ? { ok: true } : data),
      { status: 200, headers: { "Content-Type": "application/json" } });
  }

  /* ------------------------------------------------------ 业务闸口（与后端同口径） */
  function insGate(target, r) {
    if (target === "已判定") {
      if (r.verdict !== "合格" && r.verdict !== "不合格") return "判定结论必须为「合格」或「不合格」";
      if (r.verdict === "合格" && (r.criticalBad || 0) > 0) return "存在致命缺陷（A类），不允许判定合格";
      if (r.verdict === "不合格" && (r.criticalBad + r.majorBad + r.minorBad) <= 0)
        return "判定不合格但未录入不良数";
    }
    if (target === "已放行" && r.verdict !== "合格") return "仅合格单可放行";
    if (target === "已关闭" && r.verdict === "不合格" && !r.ncrNo)
      return "不合格单须已生成 NCR 方可关闭";
    return "";
  }
  function ncrGate(target, r) {
    if (target === "已评审" && !r._review) return "评审意见必填";
    if (target === "处置中" && !r._owner) return "须指定处置责任人";
    if (target === "待验证" && !r._done) return "处置完成须填写处置结果";
    if (target === "已关闭" && !r._verified) return "关闭前须完成效果验证";
    return "";
  }
  function capaGate(next, d) {
    if (next === "D2" && !(d.leader && d.members)) return "D1：须指定组长与成员";
    if (next === "D3" && (d.description || "").length < 20) return "D2：问题描述不少于 20 字（5W2H）";
    if (next === "D5" && (d.rootCause || "").length < 10) return "D4：根因分析不少于 10 字（5Why）";
    if (next === "D7" && !d.effect) return "D6：实施效果验证必填";
    if (next === "D8" && !d.prevention) return "D7：预防再发措施必填";
    return "";
  }
  var CAPA_STEPS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"];
  var STEP_NAMES = { D1: "组建小组", D2: "问题描述", D3: "围堵措施", D4: "根因分析",
    D5: "纠正措施", D6: "实施验证", D7: "预防再发", D8: "总结关闭" };

  function insView(r) { return r; }
  function ncrView(r) {
    var v = clone(r);
    v.severityName = { A: "致命", B: "严重", C: "轻微" }[r.severity] || r.severity;
    v.dispositions = ["返工", "返修", "让步接收", "报废", "退货", "挑选使用"];
    var today = new Date().toISOString().slice(0, 10);
    v.dueState = !r.due ? "未设时限" : (r.due < today ? "已逾期" : (r.due === today ? "今日到期" : "正常"));
    return v;
  }
  function capaView(r) {
    var v = clone(r);
    v.stepName = STEP_NAMES[r.step] || r.step;
    v.nextStep = CAPA_STEPS[Math.min(CAPA_STEPS.indexOf(r.step) + 1, 7)];
    var today = new Date().toISOString().slice(0, 10);
    v.dueState = !r.due ? "未设时限" : (r.due < today ? "已逾期" : "正常");
    v.progress = Math.round(CAPA_STEPS.indexOf(r.step) / 7 * 100);
    v.tasks = r.tasks || [];
    return v;
  }

  /* ------------------------------------------------------ 路由 */
  var ROUTES = [
    ["POST", /^api\/auth\/login$/, function () {
      return { token: "demo-token", user: DB.user };
    }],
    ["POST", /^api\/auth\/logout$/, function () { return { ok: true }; }],
    ["GET", /^api\/auth\/me$/, function () {
      return { user: DB.user, version: DB.version, brand: DB.brand };
    }],
    ["GET", /^api\/board$/, function () { return DB.board; }],
    ["GET", /^api\/materials$/, function () {
      return { list: DB.materials, total: DB.materials.length };
    }],
    ["POST", /^api\/materials$/, function (m) {
      if (!m.code || !m.name) throw "物料编码与名称必填";
      if (DB.materials.some(function (x) { return x.code === m.code; })) throw "编码重复";
      DB.materials.push({ code: m.code, name: m.name, spec: m.spec || "", unit: m.unit || "件",
        supplier: m.supplier || "", critical: m.critical ? 1 : 0, enabled: 1 });
      log("新建物料", m.code);
      return { ok: true };
    }],
    ["PUT", /^api\/materials\/([\w\-]+)$/, function (m, match) {
      DB.materials.forEach(function (x) { if (x.code === match[1]) { x.name = m.name || x.name; } });
      log("修改物料", match[1]);
      return { ok: true };
    }],
    ["GET", /^api\/suppliers$/, function () {
      return { list: DB.suppliers, total: DB.suppliers.length };
    }],
    ["GET", /^api\/plans$/, function () { return { list: DB.plans, total: DB.plans.length }; }],
    ["GET", /^api\/defects$/, function () { return { list: DB.defects, total: DB.defects.length }; }],
    ["GET", /^api\/qdocs$/, function () { return { list: DB.qdocs, total: DB.qdocs.length }; }],

    ["GET", /^api\/inspections$/, function (m) {
      var list = DB.inspections.filter(function (r) {
        return (!m.itype || r.itype === m.itype) && (!m.status || r.status === m.status);
      });
      return { list: list, total: list.length };
    }],
    ["GET", /^api\/inspections\/([\w\-]+)$/, function (m, match) {
      var r = DB.inspections.filter(function (x) { return x.no === match[1]; })[0];
      if (!r) throw "检验单不存在";
      var v = clone(insView(r));
      v.planOptions = DB.plans.filter(function (p) { return p.itype === r.itype; })
        .map(function (p) { return { code: p.code, name: p.name }; });
      return v;
    }],
    ["POST", /^api\/inspections$/, function (m) {
      var mat = DB.materials.filter(function (x) { return x.code === m.matCode; })[0];
      if (!mat) throw "物料不存在";
      var plan = DB.plans.filter(function (p) { return p.itype === m.itype && p.mat_code === m.matCode; })[0] ||
        DB.plans.filter(function (p) { return p.itype === m.itype && !p.mat_code; })[0] ||
        DB.plans.filter(function (p) { return p.itype === m.itype; })[0];
      var n = no({ IQC: "IQ", IPQC: "IP", FQC: "FQ", OQC: "OQ" }[m.itype] || "IQ");
      var lot = Number(m.lotSize || 0);
      var r = { no: n, itype: m.itype, typeName: { IQC: "来料检验", IPQC: "过程检验",
          FQC: "成品检验", OQC: "出货检验" }[m.itype],
        matCode: m.matCode, matName: mat.name, supplier: m.supplier || "",
        orderNo: m.orderNo || "", process: m.process || "", batchNo: m.batchNo || "",
        lotSize: lot, sampleSize: plan ? Math.min(200, Math.max(5, Math.round(lot * 0.06)))
          : Math.max(5, Math.round(lot * 0.05)),
        aql: (plan && plan.aql !== "-") ? plan.aql : "1.0",
        status: "待检验", inspector: "", started: "", finished: "", result: "",
        criticalBad: 0, majorBad: 0, minorBad: 0, verdict: "", disposition: "",
        ncrNo: "", judgedBy: "", closed: "", remark: "",
        created: new Date().toLocaleString("zh-CN", { hour12: false }),
        items: plan ? JSON.parse(JSON.stringify(plan.items)).map(function (it, i) {
          return { seq: i + 1, item: it.item, standard: it.standard, tool: it.tool,
            severity: it.severity, value_text: "", result: "", bad_qty: 0, defect_code: "" };
        }) : [] };
      r.count = r.items.length;
      DB.inspections.unshift(r);
      log("新建检验单", n);
      return { no: n, sampleSize: r.sampleSize, planCode: plan ? plan.code : "" };
    }],
    ["POST", /^api\/inspections\/([\w\-]+)\/start$/, function (m, match) {
      var r = find(match[1]);
      if (r.status !== "待检验") throw "仅「待检验」单可开始检验（当前 " + r.status + "）";
      r.status = "检验中"; r.inspector = DB.user.username;
      log("开始检验", match[1]);
      return { ok: true, status: "检验中" };
    }],
    ["POST", /^api\/inspections\/([\w\-]+)\/record$/, function (m, match) {
      var r = find(match[1]);
      if (["检验中", "待判定"].indexOf(r.status) < 0) throw "仅检验中/待判定状态可录入";
      (m.records || []).forEach(function (rec) {
        if (["OK", "NG"].indexOf(rec.result) < 0) throw "录入结果须为 OK/NG";
        r.items.forEach(function (it) {
          if (it.seq === Number(rec.seq)) {
            it.result = rec.result;
            it.bad_qty = rec.result === "NG" ? Number(rec.badQty || 1) : 0;
            it.defect_code = rec.defectCode || "";
          }
        });
      });
      r.criticalBad = sum(r.items, "A"); r.majorBad = sum(r.items, "B"); r.minorBad = sum(r.items, "C");
      log("录入检验结果", match[1]);
      return { ok: true, aggregated: { A: r.criticalBad, B: r.majorBad, C: r.minorBad } };
    }],
    ["POST", /^api\/inspections\/([\w\-]+)\/stage$/, function (m, match) {
      var r = find(match[1]);
      var target = m.target;
      var allowed = { "待检验": ["检验中"], "检验中": ["待判定"], "待判定": ["已判定"],
        "已判定": ["已放行", "已关闭"], "已放行": ["已关闭"] };
      if ((allowed[r.status] || []).indexOf(target) < 0 && target !== "已取消")
        throw "不允许从「" + r.status + "」推进到「" + target + "」";
      if (target === "已判定") {
        r.verdict = m.verdict || "合格";
        r.result = r.verdict;
        r.judgedBy = DB.user.username;
        r.finished = new Date().toLocaleString("zh-CN", { hour12: false });
        if (r.verdict === "不合格") {
          r.ncrNo = no("NCR");
          DB.ncrs.unshift({ no: r.ncrNo, insNo: r.no, matCode: r.matCode,
            batchNo: r.batchNo, qty: r.lotSize,
            badQty: r.criticalBad + r.majorBad + r.minorBad,
            severity: r.criticalBad > 0 ? "A" : "B",
            description: "检验单 " + r.no + " 判定不合格自动生成", status: "待评审",
            review: "", disposition: "", owner: "", due: "", verified: "", verifier: "",
            closed: "", cost: 0, remark: "" });
        }
      }
      if (target === "已放行") r.disposition = "合格放行";
      if (target === "已关闭" || target === "已取消") r.closed = r.finished || "—";
      r.status = target;
      log("检验单推进", match[1] + "→" + target);
      var out = { ok: true, status: target };
      if (r.ncrNo) out.ncrNo = r.ncrNo;
      return out;
    }],

    ["GET", /^api\/ncrs$/, function (m) {
      var list = DB.ncrs.filter(function (r) { return !m.status || r.status === m.status; })
        .map(ncrView);
      return { list: list, total: list.length };
    }],
    ["GET", /^api\/ncrs\/([\w\-]+)$/, function (m, match) {
      var r = DB.ncrs.filter(function (x) { return x.no === match[1]; })[0];
      if (!r) throw "NCR 不存在";
      return ncrView(r);
    }],
    ["POST", /^api\/ncrs$/, function (m) {
      if (!m.matCode || !m.badQty) throw "物料与不良数必填";
      var n = no("NCR");
      DB.ncrs.unshift({ no: n, insNo: "", matCode: m.matCode, batchNo: m.batchNo || "",
        qty: Number(m.qty || 0), badQty: Number(m.badQty), severity: m.severity || "B",
        description: m.description || "", status: "待评审", review: "", disposition: "",
        owner: "", due: "", verified: "", verifier: "", closed: "", cost: 0, remark: "" });
      log("开立NCR", n);
      return { no: n };
    }],
    ["POST", /^api\/ncrs\/([\w\-]+)\/stage$/, function (m, match) {
      var r = DB.ncrs.filter(function (x) { return x.no === match[1]; })[0];
      if (!r) throw "NCR 不存在";
      var allowed = { "待评审": ["已评审"], "已评审": ["处置中"], "处置中": ["待验证"],
        "待验证": ["已关闭"] };
      if ((allowed[r.status] || []).indexOf(m.target) < 0)
        throw "不允许从「" + r.status + "」推进到「" + m.target + "」";
      r._review = m.review || r.review; r.review = r._review;
      if (m.disposition) r.disposition = m.disposition;
      if (m.target === "已评审" && r.disposition === "让步接收") {
        var rate = r.badQty / Math.max(1, r.qty);
        if (rate > 0.03) throw "让步接收不良率 " + (rate * 100).toFixed(2) + "% 超上限 3.00%";
      }
      if (m.target === "处置中") {
        r._owner = m.owner || r.owner; r.owner = r._owner;
        r._due = m.due || r.due; r.due = r._due;
        if (!r.owner) throw "须指定处置责任人";
      }
      if (m.target === "待验证") {
        r._done = m.doneDesc;
        if (!r._done) throw "处置完成须填写处置结果";
      }
      if (m.target === "已关闭") {
        r._verified = m.verified; r.verified = r._verified; r.verifier = m.verifier || DB.user.username;
        if (!r.verified) throw "关闭前须完成效果验证";
        r.closed = new Date().toLocaleString("zh-CN", { hour12: false });
      }
      r.status = m.target;
      log("NCR推进", match[1] + "→" + m.target);
      return { ok: true, status: m.target };
    }],

    ["GET", /^api\/capas$/, function () {
      var list = DB.capas.map(capaView);
      return { list: list, total: list.length, steps: CAPA_STEPS, stepNames: STEP_NAMES };
    }],
    ["GET", /^api\/capas\/([\w\-]+)$/, function (m, match) {
      var r = DB.capas.filter(function (x) { return x.no === match[1]; })[0];
      if (!r) throw "CAPA 不存在";
      return capaView(r);
    }],
    ["POST", /^api\/capas$/, function (m) {
      if (!m.problem || m.problem.length < 8) throw "问题描述不少于 8 字";
      var n = no("CAPA");
      DB.capas.unshift({ no: n, source: m.source || "内部", ncrNo: m.ncrNo || "",
        problem: m.problem, step: "D1", leader: m.leader || "", members: m.members || "",
        description: m.description || "", rootCause: "", actions: "", effect: "",
        target: m.target || "", status: "进行中", due: m.due || "", closed: "",
        created: new Date().toLocaleString("zh-CN", { hour12: false }), tasks: [] });
      log("发起CAPA", n);
      return { no: n };
    }],
    ["POST", /^api\/capas\/([\w\-]+)\/step$/, function (m, match) {
      var r = DB.capas.filter(function (x) { return x.no === match[1]; })[0];
      if (!r) throw "CAPA 不存在";
      if (r.status === "已关闭") throw "CAPA 已关闭";
      var next = CAPA_STEPS[Math.min(CAPA_STEPS.indexOf(r.step) + 1, 7)];
      if (m.leader) r.leader = m.leader;
      if (m.members) r.members = m.members;
      if (m.description) r.description = m.description;
      if (m.rootCause) r.rootCause = m.rootCause;
      if (m.actions) r.actions = m.actions;
      if (m.effect) r.effect = m.effect;
      var g = capaGate(next, r);
      if (g) throw g;
      if (next === "D8") { r.status = "已关闭"; r.closed = new Date().toLocaleString("zh-CN", { hour12: false }); }
      r.step = next;
      (m.tasks || []).forEach(function (t) {
        r.tasks.push({ phase: next, action: t.action, owner: t.owner || "", due: t.due || "",
          status: "待执行", done: "" });
      });
      log("CAPA推进", match[1] + "→" + next);
      return { ok: true, step: next, stepName: STEP_NAMES[next] };
    }],

    ["GET", /^api\/spc\/series$/, function (m) { return DB.spc; }],
    ["GET", /^api\/spc\/processes$/, function () { return { list: DB.spcProc }; }],
    ["GET", /^api\/analysis\/pareto$/, function () { return DB.pareto; }],
    ["GET", /^api\/analysis\/fpy$/, function () { return DB.fpy; }],
    ["GET", /^api\/analysis\/trend$/, function () { return { list: DB.trend }; }],
    ["GET", /^api\/supplier\/quality$/, function () { return DB.supplierQuality; }],
    ["GET", /^api\/supplier\/ppm$/, function () { return { list: DB.supplierPpm }; }],
    ["POST", /^api\/supplier\/score$/, function (m) {
      var s = { q: Number(m.q || 80), d: Number(m.d || 80), r: Number(m.r || 80) };
      s.total = Math.round((s.q * 0.5 + s.d * 0.3 + s.r * 0.2) * 10) / 10;
      s.grade = s.total >= 90 ? "A" : (s.total >= 80 ? "B" : (s.total >= 70 ? "C" : "D"));
      DB.supplierQuality.list.forEach(function (x) {
        if (x.supplier === m.supplier) { x.q = s.q; x.d = s.d; x.r = s.r;
          x.total = s.total; x.grade = s.grade; }
      });
      log("供应商评分", m.supplier + " → " + s.total);
      return { ok: true, total: s.total, grade: s.grade };
    }],
    ["GET", /^api\/coq$/, function () { return DB.coq; }],
    ["GET", /^api\/coq\/trend$/, function () { return { list: DB.coqTrend }; }],
    ["GET", /^api\/reports\/kpi$/, function () { return DB.reports; }],
    ["GET", /^api\/settings$/, function () { return { list: DB.settings }; }],
    ["PUT", /^api\/settings$/, function (m) {
      (m.items || []).forEach(function (it) {
        DB.settings.forEach(function (s) { if (s.code === it.code) s.value = it.value; });
      });
      log("修改设置", "");
      return { ok: true };
    }],
    ["GET", /^api\/users$/, function () {
      return { list: DB.users, roles: ["admin", "quality_mgr", "qa_engineer", "inspector",
        "process_engineer", "purchaser", "supplier_qa", "viewer"], perms: [], matrix: {} };
    }],
    ["POST", /^api\/users$/, function (m) {
      if (!m.username || !m.name) throw "用户名与姓名必填";
      if (DB.users.some(function (u) { return u.username === m.username; })) throw "用户名重复";
      DB.users.push({ username: m.username, name: m.name, role: m.role || "viewer",
        roleName: m.role || "访客", dept: m.dept || "", enabled: true, perms: ["board.view"] });
      log("新建用户", m.username);
      return { ok: true };
    }],
    ["GET", /^api\/logs$/, function () { return { list: DB.logs.slice(0, 200) }; }],
    ["GET", /^api\/integration\/keys$/, function () { return { list: DB.keys }; }],
    ["POST", /^api\/integration\/keys$/, function (m) {
      if (!m.name) throw "名称必填";
      var key = "fck_demo" + Math.random().toString(36).slice(2, 14);
      DB.keys.push({ id: DB.keys.length + 1, name: m.name, prefix: key.slice(0, 10),
        scope: m.scope || "read", enabled: 1, created: "—", last_used: "" });
      log("生成API Key", m.name);
      return { key: key, note: "明文仅显示一次" };
    }],
    ["GET", /^api\/integration\/webhooks$/, function () { return DB.hooks; }],
    ["POST", /^api\/integration\/webhooks$/, function (m) {
      if (!m.name || !m.url) throw "名称与 URL 必填";
      DB.hooks.list.push({ id: DB.hooks.list.length + 1, name: m.name, url: m.url,
        events: "", enabled: 1, last_status: "", created: "—" });
      log("新建Webhook", m.name);
      return { secret: "whsec_demo" + Math.random().toString(36).slice(2, 12) };
    }],
    ["GET", /^api\/integration\/maps$/, function () { return { list: DB.maps }; }],
    ["POST", /^api\/integration\/maps$/, function (m) {
      if (!m.system || !m.extId || !m.intId) throw "system/extId/intId 必填";
      DB.maps.unshift({ system: m.system, entity: m.entity || "", ext_id: m.extId,
        int_id: m.intId, created: "—" });
      log("新增映射", m.system + "/" + m.extId);
      return { ok: true };
    }],
    ["GET", /^api\/sync\/changes$/, function () { return DB.sync; }],
    ["GET", /^api\/health$/, function () {
      return { status: "ok", brand: DB.brand, version: DB.version, demo: true };
    }],
    ["GET", /^api\/version$/, function () {
      return { brand: DB.brand, version: DB.version, demo: true };
    }],
    ["GET", /^api\/openapi\.json$/, function () { return { paths: {}, demo: true }; }]
  ];

  function sum(items, sev) {
    return items.filter(function (i) { return i.result === "NG" && i.severity === sev; })
      .reduce(function (a, i) { return a + Number(i.bad_qty || 0); }, 0);
  }
  function find(no2) {
    var r = DB.inspections.filter(function (x) { return x.no === no2; })[0];
    if (!r) throw "检验单不存在";
    return r;
  }

  /* ------------------------------------------------------ 拦截 fetch */
  var origFetch = window.fetch;
  window.fetch = function (url, opt) {
    opt = opt || {};
    var path = String(url).replace(/^https?:\/\/[^/]+/, "").replace(/^\//, "")
      .split("?")[0];
    var qs = {};
    String(url).replace(/^[^?]*\??/, "").split("&").forEach(function (kv) {
      if (!kv) return;
      var j = kv.indexOf("=");
      qs[decodeURIComponent(j < 0 ? kv : kv.slice(0, j))] = decodeURIComponent(j < 0 ? "" : kv.slice(j + 1));
    });
    var method = (opt.method || "GET").toUpperCase();
    var body = {};
    if (opt.body) { try { body = JSON.parse(opt.body); } catch (e) { body = {}; } }
    for (var i = 0; i < ROUTES.length; i++) {
      if (ROUTES[i][0] !== method) continue;
      var m = ROUTES[i][1].exec(path);
      if (!m) continue;
      try {
        var result = ROUTES[i][2](Object.assign({}, qs, body), m);
        save();
        return Promise.resolve(ok(result));
      } catch (e) {
        return Promise.resolve(err(400, String(e)));
      }
    }
    /* 未命中路由：尝试快照兜底 */
    if (SNAP.extra && SNAP.extra[method + " " + path]) {
      return Promise.resolve(ok(SNAP.extra[method + " " + path]));
    }
    return origFetch ? origFetch.apply(this, arguments)
      : Promise.resolve(err(404, "DEMO 未实现：" + method + " " + path));
  };

  /* 绕过登录直接进入 */
  try { localStorage.setItem("qms_token", "demo-token"); } catch (e) { /* ignore */ }

  load();
  window.__QMS_DEMO_RESET__ = function () {
    try { sessionStorage.removeItem(KEY); } catch (e) { /* ignore */ }
    location.reload();
  };
})();
