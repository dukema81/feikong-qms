# -*- coding: utf-8 -*-
"""飞控QMS系统 · 服务层（http.server 零依赖 REST + 静态站点）。

96 条路由：认证4 / 首屏1 / 主数据9 / 检验14 / NCR7 / CAPA7 / 供应商质量4 / SPC3 /
分析4 / 质量成本3 / 文件4 / 报表4 / 系统6 / 集成11 / 运维3。
鉴权多通道、Idempotency-Key 幂等、240/min 限流、Webhook HMAC 投递、增量同步。
"""
import hashlib
import hmac as hmac_mod
import json
import os
import re
import threading
import time
import urllib.request
from datetime import datetime, timedelta
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

import db
import qms
from db import connect

VERSION = qms.VERSION
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PORT = int(os.environ.get("FEIKONG_PORT") or os.environ.get("PORT") or "8024")
HOST = os.environ.get("FEIKONG_HOST") or ("0.0.0.0" if os.environ.get("PORT") else "127.0.0.1")
FRONTEND = os.path.join(ROOT, "frontend")

TOKENS = {}          # token -> username
IDEM_LOCK = threading.Lock()
RATE = {}            # ip -> [window_start, count]
WRITE_LOCK = threading.Lock()

MIME = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
        ".css": "text/css; charset=utf-8", ".png": "image/png", ".ico": "image/x-icon",
        ".svg": "image/svg+xml", ".json": "application/json; charset=utf-8"}


# ---------------------------------------------------------------- 基础工具
def now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today():
    return datetime.now().strftime("%Y-%m-%d")


def safe(v, default=""):
    return default if v is None else v


def num(v, default=0):
    try:
        return int(v) if str(v).strip().lstrip("-").isdigit() else float(v or default)
    except (TypeError, ValueError):
        return default


def sha(s):
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def next_no(cn, prefix, table):
    row = cn.execute("SELECT val FROM seq WHERE name=?", (prefix,)).fetchone()
    val = (row["val"] if row else 0) + 1
    cn.execute("INSERT OR REPLACE INTO seq(name,val) VALUES(?,?)", (prefix, val))
    ym = datetime.now().strftime("%y%m")
    return "%s%s-%04d" % (prefix, ym, val)


def log_op(user, action, detail=""):
    cn = connect()
    cn.execute("INSERT INTO logs(user,action,detail,ts) VALUES(?,?,?,?)",
               (user, action, detail, now()))
    cn.commit()
    cn.close()


class ApiErr(Exception):
    def __init__(self, code, msg):
        self.code = code
        self.msg = msg


# ---------------------------------------------------------------- Webhook
def emit(event, data):
    cn = connect()
    cn.execute("INSERT INTO events(event,data,ts) VALUES(?,?,?)",
               (event, json.dumps(data, ensure_ascii=False), now()))
    hooks = cn.execute("SELECT id FROM webhooks WHERE enabled=1 AND (events='' OR events LIKE ?)",
                       ("%" + event.split(".")[0] + "%",)).fetchall()
    cn.commit()
    cn.close()
    for h in hooks:
        threading.Thread(target=deliver, args=(h["id"], event, data), daemon=True).start()


def deliver(hook_id, event, data, _attempt=0):
    cn = connect()
    hook = cn.execute("SELECT * FROM webhooks WHERE id=?", (hook_id,)).fetchone()
    if not hook:
        cn.close()
        return
    body = json.dumps({"event": event, "ts": now(), "data": data}, ensure_ascii=False)
    ts = str(int(time.time()))
    sign = hmac_mod.new(hook["secret"].encode(), ("%s.%s" % (ts, body)).encode(),
                        hashlib.sha256).hexdigest()
    status, resp = "pending", ""
    try:
        req = urllib.request.Request(hook["url"], data=body.encode(), method="POST",
                                     headers={"Content-Type": "application/json",
                                              "X-Qms-Event": event, "X-Qms-Timestamp": ts,
                                              "X-Qms-Signature": sign, "X-Qms-Delivery": "%s-%s" % (ts, hook_id)})
        with urllib.request.urlopen(req, timeout=10) as r:
            status, resp = "ok", ("HTTP %d" % r.status)
    except Exception as e:                                    # noqa: BLE001
        status, resp = "failed", str(e)[:200]
    cn.execute("""INSERT INTO webhook_logs(hook_id,event,payload,status,response,ts,attempts)
                  VALUES(?,?,?,?,?,?,?)""",
               (hook_id, event, body[:2000], status, resp, now(), _attempt + 1))
    cn.execute("UPDATE webhooks SET last_status=? WHERE id=?", (status, hook_id))
    cn.commit()
    cn.close()
    if status == "failed" and _attempt < 2:
        threading.Timer(60 * (_attempt + 1), deliver,
                        args=(hook_id, event, data, _attempt + 1), daemon=True).start()


# ---------------------------------------------------------------- 视图
def user_view(r):
    return {"id": r["id"], "username": r["username"], "name": r["name"], "role": r["role"],
            "roleName": {"admin": "系统管理员", "quality_mgr": "质量经理",
                         "qa_engineer": "质量工程师", "inspector": "检验员",
                         "process_engineer": "工艺工程师", "purchaser": "采购员",
                         "supplier_qa": "SQE", "viewer": "访客"}.get(r["role"], r["role"]),
            "dept": r["dept"], "enabled": bool(r["enabled"]),
            "perms": qms.perm_of(r["role"])}


def ins_view(cn, r):
    items = [dict(x) for x in cn.execute(
        "SELECT * FROM inspection_items WHERE ins_no=? ORDER BY seq", (r["no"],))]
    lot = int(r["lot_size"] or 0)
    return {"no": r["no"], "itype": r["itype"], "typeName": qms.INS_TYPES.get(r["itype"], r["itype"]),
            "matCode": r["mat_code"], "matName": r["mat_name"], "supplier": r["supplier"],
            "orderNo": r["order_no"], "process": r["process"], "batchNo": r["batch_no"],
            "lotSize": lot, "sampleSize": r["sample_size"], "aql": r["aql"],
            "status": r["status"], "inspector": r["inspector"], "started": r["started"] or "",
            "finished": r["finished"] or "", "result": r["result"], "verdict": r["verdict"],
            "criticalBad": r["critical_bad"], "majorBad": r["major_bad"], "minorBad": r["minor_bad"],
            "defectIndex": qms.weighted_defects(r["critical_bad"], r["major_bad"], r["minor_bad"]),
            "disposition": r["disposition"], "ncrNo": r["ncr_no"], "judgedBy": r["judged_by"],
            "closed": r["closed"] or "", "created": r["created"], "remark": r["remark"],
            "items": items, "count": len(items),
            "plan": qms.aql_plan(lot, r["aql"], "II") if lot else None,
            "gates": ins_gates(r, items)}


def ins_gates(r, items):
    gates = []
    if r["status"] == "待检验":
        gates.append({"name": "批量已登记", "ok": int(r["lot_size"] or 0) > 0})
    if r["status"] in ("检验中", "待判定", "已判定", "已放行"):
        gates.append({"name": "检验项目全部录入", "ok": all(x["result"] for x in items)})
    if r["status"] in ("待判定",):
        gates.append({"name": "可提交判定", "ok": all(x["result"] for x in items) and len(items) > 0})
    if r["status"] == "已判定" and r["verdict"] == "不合格":
        gates.append({"name": "已生成NCR", "ok": bool(r["ncr_no"])})
    if r["status"] == "已判定" and r["verdict"] == "合格":
        gates.append({"name": "可放行", "ok": True})
    return gates


def ncr_view(r):
    return {"no": r["no"], "insNo": r["ins_no"], "matCode": r["mat_code"],
            "batchNo": r["batch_no"], "qty": r["qty"], "badQty": r["bad_qty"],
            "severity": r["severity"], "severityName": qms.SEV_CN.get(r["severity"], r["severity"]),
            "description": r["description"], "status": r["status"], "review": r["review"],
            "disposition": r["disposition"], "owner": r["owner"], "due": r["due"] or "",
            "dueState": qms.due_check(r["due"]), "verified": r["verified"] or "",
            "verifier": r["verifier"], "closed": r["closed"] or "", "created": r["created"],
            "cost": r["cost"], "remark": r["remark"],
            "gate": {"待评审": "等待评审", "已评审": "评审完成，待下达处置",
                     "处置中": "处置进行中（责任：" + (r["owner"] or "-") + "）",
                     "待验证": "待效果验证", "已关闭": "已闭环"}.get(r["status"], "")}


def capa_view(cn, r):
    tasks = [dict(t) for t in cn.execute(
        "SELECT * FROM capa_tasks WHERE capa_no=? ORDER BY id", (r["no"],))]
    return {"no": r["no"], "source": r["source"], "ncrNo": r["ncr_no"], "problem": r["problem"],
            "step": r["step"], "stepName": qms.CAPA_STEP_NAMES.get(r["step"], r["step"]),
            "nextStep": qms.capa_next(r["step"]), "leader": r["leader"],
            "members": r["members"], "description": r["description"] or "",
            "rootCause": r["root_cause"] or "", "actions": r["actions"] or "",
            "effect": r["effect"] or "", "target": r["target"], "status": r["status"],
            "due": r["due"] or "", "dueState": qms.due_check(r["due"]),
            "closed": r["closed"] or "", "created": r["created"], "remark": r["remark"],
            "tasks": tasks,
            "progress": int(qms.CAPA_STEPS.index(r["step"]) / 7 * 100)}


# ---------------------------------------------------------------- 路由处理
ROUTES = []


def route(method, pattern, perm=None):
    rx = re.compile("^" + pattern + "$")

    def deco(fn):
        ROUTES.append((method, rx, fn, perm))
        return fn
    return deco


def get_user_by_token(token):
    username = TOKENS.get(token)
    if not username:
        return None
    cn = connect()
    r = cn.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    cn.close()
    return r


# ---- 认证
@route("POST", r"/api/auth/login")
def api_login(h, p, m):
    username = (m.get("username") or "").strip()
    password = m.get("password") or ""
    cn = connect()
    r = cn.execute("SELECT * FROM users WHERE username=? AND enabled=1", (username,)).fetchone()
    cn.close()
    if not r or r["password"] != sha(password):
        raise ApiErr(401, "用户名或密码错误")
    token = sha("%s|%s|%f" % (username, password, time.time()))[:32]
    TOKENS[token] = username
    log_op(username, "登录", "令牌签发")
    return {"token": token, "user": user_view(r)}


@route("GET", r"/api/auth/me")
def api_me(h, p, m):
    return {"user": user_view(h.user), "version": VERSION, "brand": qms.BRAND}


@route("POST", r"/api/auth/logout")
def api_logout(h, p, m):
    TOKENS.pop(h.token, None)
    return {"ok": True}


@route("PUT", r"/api/auth/password")
def api_password(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM users WHERE username=?", (h.user["username"],)).fetchone()
    if r["password"] != sha(m.get("oldPassword") or ""):
        cn.close()
        raise ApiErr(400, "原密码不正确")
    if len(m.get("newPassword") or "") < 6:
        cn.close()
        raise ApiErr(400, "新密码至少 6 位")
    cn.execute("UPDATE users SET password=? WHERE username=?",
               (sha(m["newPassword"]), h.user["username"]))
    cn.commit()
    cn.close()
    log_op(h.user["username"], "修改密码", "")
    return {"ok": True}


# ---- 首屏
@route("GET", r"/api/board", "board.view")
def api_board(h, p, m):
    cn = connect()
    ins_total = cn.execute("SELECT COUNT(*) c FROM inspections").fetchone()["c"]
    by_status = {r["status"]: r["c"] for r in cn.execute(
        "SELECT status, COUNT(*) c FROM inspections GROUP BY status")}
    by_type = [dict(r) for r in cn.execute(
        "SELECT itype, COUNT(*) total, SUM(CASE WHEN verdict='合格' THEN 1 ELSE 0 END) ok"
        " FROM inspections WHERE verdict!='' GROUP BY itype")]
    for t in by_type:
        t["passRate"] = round((t["ok"] or 0) / t["total"] * 100, 1) if t["total"] else 0
    ncr_open = cn.execute("SELECT COUNT(*) c FROM ncrs WHERE status!='已关闭'").fetchone()["c"]
    capa_open = cn.execute("SELECT COUNT(*) c FROM capas WHERE status!='已关闭'").fetchone()["c"]
    capa_over = cn.execute("SELECT COUNT(*) c FROM capas WHERE status!='已关闭' AND due<?",
                           (today(),)).fetchone()["c"]
    month = today()[:7]
    coq_sum = cn.execute("SELECT SUM(amount) s FROM coq WHERE month=?", (month,)).fetchone()["s"] or 0
    defect_rows = cn.execute("""SELECT d.name, SUM(i.bad_qty) c FROM inspection_items i
        JOIN defects d ON i.defect_code=d.code WHERE i.bad_qty>0 GROUP BY d.name""").fetchall()
    spc = cn.execute("SELECT value FROM spc_series WHERE char_name='锁附扭矩' ORDER BY id").fetchall()
    cn.close()
    kpi = {
        "inspections": ins_total,
        "pending": by_status.get("待检验", 0) + by_status.get("检验中", 0) + by_status.get("待判定", 0),
        "iqcPassRate": next((t["passRate"] for t in by_type if t["itype"] == "IQC"), 0),
        "ncrOpen": ncr_open, "capaOpen": capa_open, "capaOverdue": capa_over,
        "coqMonth": round(coq_sum, 2),
    }
    return {"kpi": kpi, "byType": by_type, "byStatus": by_status,
            "pareto": qms.pareto([(r["name"], int(r["c"] or 0)) for r in defect_rows]),
            "spc": qms.spc_limits([r["value"] for r in spc]),
            "todo": {"待检验": by_status.get("待检验", 0), "待判定": by_status.get("待判定", 0),
                     "NCR待验证": cn_count("SELECT COUNT(*) c FROM ncrs WHERE status='待验证'"),
                     "CAPA逾期": capa_over}}


def cn_count(sql, *args):
    cn = connect()
    r = cn.execute(sql, args).fetchone()
    cn.close()
    return r[0] if r else 0


# ---- 主数据
@route("GET", r"/api/materials", "board.view")
def api_materials(h, p, m):
    cn = connect()
    q = "SELECT * FROM materials WHERE 1=1"
    args = []
    if m.get("q"):
        q += " AND (code LIKE ? OR name LIKE ?)"
        args += ["%" + m["q"] + "%"] * 2
    rows = [dict(r) for r in cn.execute(q + " ORDER BY code", args)]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("POST", r"/api/materials", "mdm.edit")
def api_material_add(h, p, m):
    if not m.get("code") or not m.get("name"):
        raise ApiErr(400, "物料编码与名称必填")
    cn = connect()
    try:
        cn.execute("""INSERT INTO materials(code,name,spec,unit,supplier,critical,key_character)
                      VALUES(?,?,?,?,?,?,?)""",
                   (m["code"].strip(), m["name"].strip(), safe(m.get("spec")),
                    safe(m.get("unit"), "件"), safe(m.get("supplier")),
                    1 if m.get("critical") else 0, safe(m.get("keyCharacter"))))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败（编码重复？）：%s" % e)
    cn.close()
    log_op(h.user["username"], "新建物料", m["code"])
    emit("material.created", {"code": m["code"]})
    return {"ok": True}


@route("PUT", r"/api/materials/([A-Z0-9\-]+)", "mdm.edit")
def api_material_put(h, p, m):
    cn = connect()
    cn.execute("""UPDATE materials SET name=?,spec=?,unit=?,supplier=?,critical=?,key_character=?,
                  enabled=? WHERE code=?""",
               (m.get("name"), safe(m.get("spec")), safe(m.get("unit"), "件"),
                safe(m.get("supplier")), 1 if m.get("critical") else 0,
                safe(m.get("keyCharacter")), 1 if m.get("enabled", 1) else 0, p[0]))
    cn.commit()
    cn.close()
    emit("material.updated", {"code": p[0]})
    return {"ok": True}


@route("GET", r"/api/suppliers", "board.view")
def api_suppliers(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute("SELECT * FROM suppliers ORDER BY code")]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("POST", r"/api/suppliers", "supplier.edit")
def api_supplier_add(h, p, m):
    if not m.get("code") or not m.get("name"):
        raise ApiErr(400, "供应商编码与名称必填")
    cn = connect()
    try:
        cn.execute("INSERT INTO suppliers(code,name,category,contact,phone,remark)"
                   " VALUES(?,?,?,?,?,?)",
                   (m["code"].strip(), m["name"].strip(), safe(m.get("category")),
                    safe(m.get("contact")), safe(m.get("phone")), safe(m.get("remark"))))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败：%s" % e)
    cn.close()
    return {"ok": True}


@route("GET", r"/api/plans", "board.view")
def api_plans(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute("SELECT * FROM plans ORDER BY code")]
    for r in rows:
        r["items"] = [dict(i) for i in cn.execute(
            "SELECT * FROM plan_items WHERE plan_code=? ORDER BY seq", (r["code"],))]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("POST", r"/api/plans", "mdm.edit")
def api_plan_add(h, p, m):
    if not m.get("code") or not m.get("name") or m.get("itype") not in qms.INS_TYPES:
        raise ApiErr(400, "编码、名称、检验类型必填")
    cn = connect()
    try:
        cn.execute("""INSERT INTO plans(code,name,mat_code,itype,aql,il,critical_ac,
                      major_ac,minor_ac) VALUES(?,?,?,?,?,?,?,?,?)""",
                   (m["code"].strip(), m["name"].strip(), safe(m.get("matCode")),
                    m["itype"], safe(m.get("aql"), "1.0"), safe(m.get("il"), "II"),
                    num(m.get("criticalAc"), 0), num(m.get("majorAc"), 1), num(m.get("minorAc"), 2)))
        for i, it in enumerate(m.get("items") or [], 1):
            cn.execute("""INSERT INTO plan_items(plan_code,seq,item,standard,tool,severity)
                          VALUES(?,?,?,?,?,?)""",
                       (m["code"], i, it.get("item", ""), safe(it.get("standard")),
                        safe(it.get("tool")), safe(it.get("severity"), "B")))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败：%s" % e)
    cn.close()
    return {"ok": True}


@route("GET", r"/api/defects", "board.view")
def api_defects(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT * FROM defects ORDER BY severity, code")]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("POST", r"/api/defects", "mdm.edit")
def api_defect_add(h, p, m):
    if not m.get("code") or not m.get("name") or not m.get("category"):
        raise ApiErr(400, "编码、名称、分类必填")
    cn = connect()
    try:
        cn.execute("INSERT INTO defects(code,name,category,severity,mat_code,process)"
                   " VALUES(?,?,?,?,?,?)",
                   (m["code"].strip(), m["name"].strip(), m["category"],
                    safe(m.get("severity"), "B"), safe(m.get("matCode")), safe(m.get("process"))))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败：%s" % e)
    cn.close()
    return {"ok": True}


@route("GET", r"/api/users", "settings.admin")
def api_users(h, p, m):
    cn = connect()
    rows = [user_view(r) for r in cn.execute("SELECT * FROM users ORDER BY id")]
    cn.close()
    return {"list": rows, "roles": qms.ROLES, "perms": qms.PERMS,
            "matrix": qms.PERM_MATRIX}


@route("POST", r"/api/users", "settings.admin")
def api_user_add(h, p, m):
    if not m.get("username") or not m.get("name") or m.get("role") not in qms.ROLES:
        raise ApiErr(400, "用户名、姓名、角色必填（角色须合法）")
    cn = connect()
    try:
        cn.execute("INSERT INTO users(username,password,name,role,dept,created)"
                   " VALUES(?,?,?,?,?,?)",
                   (m["username"].strip(), sha(m.get("password") or "qms@2026"),
                    m["name"].strip(), m["role"], safe(m.get("dept")), today()))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败（用户名重复？）：%s" % e)
    cn.close()
    log_op(h.user["username"], "新建用户", m["username"])
    return {"ok": True}


@route("PUT", r"/api/users/(\w+)", "settings.admin")
def api_user_put(h, p, m):
    cn = connect()
    sets, args = [], []
    if m.get("name"):
        sets.append("name=?"), args.append(m["name"])
    if m.get("role") in qms.ROLES:
        sets.append("role=?"), args.append(m["role"])
    if m.get("dept") is not None:
        sets.append("dept=?"), args.append(m["dept"])
    if "enabled" in m:
        sets.append("enabled=?"), args.append(1 if m["enabled"] else 0)
    if m.get("password"):
        sets.append("password=?"), args.append(sha(m["password"]))
    if sets:
        args.append(p[0])
        cn.execute("UPDATE users SET %s WHERE username=?" % ",".join(sets), args)
        cn.commit()
    cn.close()
    return {"ok": True}


# ---- 检验单
@route("GET", r"/api/inspections", "board.view")
def api_inspections(h, p, m):
    cn = connect()
    q = "SELECT * FROM inspections WHERE 1=1"
    args = []
    if m.get("itype"):
        q += " AND itype=?"
        args.append(m["itype"])
    if m.get("status"):
        q += " AND status=?"
        args.append(m["status"])
    if m.get("q"):
        q += " AND (no LIKE ? OR mat_name LIKE ? OR batch_no LIKE ? OR order_no LIKE ?)"
        args += ["%" + m["q"] + "%"] * 4
    rows = [ins_view(cn, r) for r in cn.execute(q + " ORDER BY id DESC LIMIT 200", args)]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("GET", r"/api/inspections/([A-Z0-9\-]+)", "board.view")
def api_inspection(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM inspections WHERE no=?", (p[0],)).fetchone()
    if not r:
        cn.close()
        raise ApiErr(404, "检验单不存在")
    v = ins_view(cn, r)
    plans = cn.execute("SELECT code,name FROM plans WHERE itype=? AND enabled=1",
                       (r["itype"],)).fetchall()
    cn.close()
    v["planOptions"] = [dict(x) for x in plans]
    return v


@route("POST", r"/api/inspections", "iqc.do")
def api_inspection_create(h, p, m):
    itype = m.get("itype")
    if itype not in qms.INS_TYPES:
        raise ApiErr(400, "检验类型须为 IQC/IPQC/FQC/OQC")
    if not m.get("matCode"):
        raise ApiErr(400, "物料必填")
    if itype == "IPQC" and not m.get("process"):
        raise ApiErr(400, "过程检验须填写工序")
    perm_map = {"IQC": "iqc.do", "IPQC": "ipqc.do", "FQC": "fqc.do", "OQC": "fqc.do"}
    if not qms.check_perm(h.user["role"], perm_map[itype]):
        raise ApiErr(403, "当前角色无 %s 检验权限" % qms.INS_TYPES[itype])
    cn = connect()
    mat = cn.execute("SELECT * FROM materials WHERE code=?", (m["matCode"],)).fetchone()
    if not mat:
        cn.close()
        raise ApiErr(404, "物料不存在：%s" % m["matCode"])
    lot = num(m.get("lotSize"), 0)
    aql = safe(m.get("aql"), "1.0")
    # 自动载入检验方案项目
    plan = cn.execute("""SELECT * FROM plans WHERE itype=? AND enabled=1
        AND (mat_code=? OR mat_code='') ORDER BY mat_code='' LIMIT 1""", (itype, m["matCode"])).fetchone()
    plan_items = []
    if plan:
        plan_items = [dict(x) for x in cn.execute(
            "SELECT * FROM plan_items WHERE plan_code=? ORDER BY seq", (plan["code"],))]
        aql = plan["aql"] if plan["aql"] != "-" else aql
    no = next_no(cn, {"IQC": "IQ", "IPQC": "IP", "FQC": "FQ", "OQC": "OQ"}[itype], "inspections")
    sample = qms.aql_plan(lot, aql, "II")["sampleSize"] if itype != "IPQC" else min(lot or 5, 5)
    cn.execute("""INSERT INTO inspections(no,itype,mat_code,mat_name,supplier,order_no,process,
        batch_no,lot_size,sample_size,aql,status,created,creator,remark)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (no, itype, m["matCode"], mat["name"], safe(m.get("supplier")),
                safe(m.get("orderNo")), safe(m.get("process")), safe(m.get("batchNo")),
                lot, sample, aql, "待检验", now(), h.user["username"], safe(m.get("remark"))))
    for i, it in enumerate(plan_items, 1):
        cn.execute("""INSERT INTO inspection_items(ins_no,seq,item,standard,tool,severity)
                      VALUES(?,?,?,?,?,?)""",
                   (no, i, it["item"], it["standard"], it["tool"], it["severity"]))
    cn.commit()
    cn.close()
    log_op(h.user["username"], "新建检验单", "%s %s" % (no, m["matCode"]))
    emit("inspection.created", {"no": no, "itype": itype, "matCode": m["matCode"]})
    return {"no": no, "sampleSize": sample, "planCode": plan["code"] if plan else ""}


@route("POST", r"/api/inspections/([A-Z0-9\-]+)/start", "iqc.do")
def api_inspection_start(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM inspections WHERE no=?", (p[0],)).fetchone()
    if not r:
        raise ApiErr(404, "检验单不存在")
    if r["status"] != "待检验":
        cn.close()
        raise ApiErr(400, "仅「待检验」单可开始检验（当前 %s）" % r["status"])
    cn.execute("UPDATE inspections SET status='检验中',inspector=?,started=? WHERE no=?",
               (h.user["username"], now(), p[0]))
    cn.commit()
    cn.close()
    emit("inspection.stage", {"no": p[0], "from": "待检验", "to": "检验中"})
    return {"ok": True, "status": "检验中"}


@route("POST", r"/api/inspections/([A-Z0-9\-]+)/record", "iqc.do")
def api_inspection_record(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM inspections WHERE no=?", (p[0],)).fetchone()
    if not r:
        raise ApiErr(404, "检验单不存在")
    if r["status"] not in ("检验中", "待判定"):
        cn.close()
        raise ApiErr(400, "仅检验中/待判定状态可录入")
    for rec in m.get("records") or []:
        seq, result = num(rec.get("seq")), rec.get("result") or ""
        if result not in ("OK", "NG"):
            raise ApiErr(400, "录入结果须为 OK/NG（seq=%d）" % seq)
        cn.execute("""UPDATE inspection_items SET result=?,value_text=?,bad_qty=?,defect_code=?
                      WHERE ins_no=? AND seq=?""",
                   (result, safe(rec.get("valueText")), num(rec.get("badQty"), 0),
                    safe(rec.get("defectCode")), p[0], seq))
    # 汇总不良数
    agg = {"A": 0, "B": 0, "C": 0}
    rows = cn.execute("SELECT severity, SUM(bad_qty) bq FROM inspection_items"
                      " WHERE ins_no=? AND result='NG' GROUP BY severity", (p[0],)).fetchall()
    for row in rows:
        agg[row["severity"]] = int(row["bq"] or 0)
    cn.execute("UPDATE inspections SET critical_bad=?,major_bad=?,minor_bad=? WHERE no=?",
               (agg["A"], agg["B"], agg["C"], p[0]))
    cn.commit()
    cn.close()
    return {"ok": True, "aggregated": agg}


@route("POST", r"/api/inspections/([A-Z0-9\-]+)/stage", "iqc.do")
def api_inspection_stage(h, p, m):
    """推进：target=待判定/已判定/已放行/已关闭/已取消。"""
    target = m.get("target") or ""
    with WRITE_LOCK:
        cn = connect()
        r = cn.execute("SELECT * FROM inspections WHERE no=?", (p[0],)).fetchone()
        if not r:
            raise ApiErr(404, "检验单不存在")
        items = [dict(x) for x in cn.execute(
            "SELECT * FROM inspection_items WHERE ins_no=? ORDER BY seq", (p[0],))]
        allowed = {"待检验": ["检验中"], "检验中": ["待判定"], "待判定": ["已判定"],
                   "已判定": ["已放行", "已关闭"], "已放行": ["已关闭"]}
        if target not in allowed.get(r["status"], []) and target != "已取消":
            cn.close()
            raise ApiErr(400, "不允许从「%s」推进到「%s」" % (r["status"], target))
        if target == "已取消" and r["status"] in ("已放行", "已关闭"):
            cn.close()
            raise ApiErr(400, "已放行/已关闭的单不可取消")
        ctx = {"lotSize": r["lot_size"], "items": items,
               "verdict": m.get("verdict") or r["verdict"], "judgedBy": h.user["username"] if m.get("verdict") == "合格" else m.get("judgedBy"),
               "criticalBad": r["critical_bad"], "criticalBlock": cn_setting("critical_block") == "1",
               "badQty": r["major_bad"] + r["minor_bad"] + r["critical_bad"],
               "ncrNo": r["ncr_no"], "closed": target == "已关闭",
               "concession": m.get("concession"), "disposition": m.get("disposition")}
        ok, msg = qms.ins_gate(target, ctx)
        if not ok:
            cn.close()
            raise ApiErr(400, msg)
        upd = {"status": target}
        if target == "已判定":
            verdict = m.get("verdict") or qms.verdict_by_aql(
                {"A": r["critical_bad"], "B": r["major_bad"], "C": r["minor_bad"]},
                qms.aql_plan(r["lot_size"], r["aql"]))[0]
            upd.update({"result": verdict, "verdict": verdict,
                        "judged_by": m.get("judgedBy") or h.user["username"],
                        "finished": now()})
        if target == "已放行":
            upd["disposition"] = safe(m.get("disposition"), "合格放行")
        if target in ("已关闭", "已取消"):
            upd["closed"] = now()
        cn.execute("UPDATE inspections SET status=?,result=?,verdict=?,judged_by=?,finished=?,"
                   "disposition=?,closed=? WHERE no=?",
                   (target, upd.get("result", r["result"]), upd.get("verdict", r["verdict"]),
                    upd.get("judged_by", r["judged_by"]), upd.get("finished", r["finished"]),
                    upd.get("disposition", r["disposition"]), upd.get("closed", r["closed"]), p[0]))
        # 不合格自动开 NCR
        if target == "已判定" and upd.get("verdict") == "不合格" and not r["ncr_no"]:
            bad_qty = r["critical_bad"] + r["major_bad"] + r["minor_bad"]
            ncr_no = next_no(cn, "NCR", "ncrs")
            sev = "A" if r["critical_bad"] > 0 else "B"
            cn.execute("""INSERT INTO ncrs(no,ins_no,mat_code,batch_no,qty,bad_qty,severity,
                description,status,due,created,creator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (ncr_no, p[0], r["mat_code"], r["batch_no"],
                        int(r["lot_size"] or 0), bad_qty, sev,
                        "检验单 %s 判定不合格（致命%d/严重%d/轻微%d）自动生成" % (
                            p[0], r["critical_bad"], r["major_bad"], r["minor_bad"]),
                        "待评审", (datetime.now() + timedelta(days=num(cn_setting("ncr_due_days"), 7))).strftime("%Y-%m-%d"),
                        now(), h.user["username"]))
            cn.execute("UPDATE inspections SET ncr_no=? WHERE no=?", (ncr_no, p[0]))
            upd["ncrNo"] = ncr_no
        cn.commit()
        cn.close()
    log_op(h.user["username"], "检验单推进", "%s→%s" % (p[0], target))
    emit("inspection.stage", {"no": p[0], "from": r["status"], "to": target})
    out = {"ok": True, "status": target}
    if upd.get("ncrNo"):
        out["ncrNo"] = upd["ncrNo"]
    return out


def cn_setting(code):
    cn = connect()
    r = cn.execute("SELECT value FROM settings WHERE code=?", (code,)).fetchone()
    cn.close()
    return r["value"] if r else ""


# ---- NCR
@route("GET", r"/api/ncrs", "board.view")
def api_ncrs(h, p, m):
    cn = connect()
    q = "SELECT * FROM ncrs WHERE 1=1"
    args = []
    if m.get("status"):
        q += " AND status=?"
        args.append(m["status"])
    if m.get("q"):
        q += " AND (no LIKE ? OR mat_code LIKE ? OR batch_no LIKE ?)"
        args += ["%" + m["q"] + "%"] * 3
    rows = [ncr_view(r) for r in cn.execute(q + " ORDER BY id DESC LIMIT 200", args)]
    cn.close()
    return {"list": rows, "total": len(rows),
            "dispositions": qms.DISPOSITIONS}


@route("GET", r"/api/ncrs/([A-Z0-9\-]+)", "board.view")
def api_ncr(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM ncrs WHERE no=?", (p[0],)).fetchone()
    cn.close()
    if not r:
        raise ApiErr(404, "NCR 不存在")
    return ncr_view(r)


@route("POST", r"/api/ncrs", "ncr.manage")
def api_ncr_create(h, p, m):
    if not m.get("matCode") or not (m.get("badQty") or 0):
        raise ApiErr(400, "物料与不良数必填")
    cn = connect()
    no = next_no(cn, "NCR", "ncrs")
    cn.execute("""INSERT INTO ncrs(no,ins_no,mat_code,batch_no,qty,bad_qty,severity,description,
                  status,due,created,creator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (no, safe(m.get("insNo")), m["matCode"], safe(m.get("batchNo")),
                num(m.get("qty"), 0), num(m.get("badQty")), safe(m.get("severity"), "B"),
                safe(m.get("description")), "待评审",
                (datetime.now() + timedelta(days=num(cn_setting("ncr_due_days"), 7))).strftime("%Y-%m-%d"),
                now(), h.user["username"]))
    cn.commit()
    cn.close()
    emit("ncr.created", {"no": no, "matCode": m["matCode"]})
    return {"no": no}


@route("POST", r"/api/ncrs/([A-Z0-9\-]+)/stage", "ncr.manage")
def api_ncr_stage(h, p, m):
    target = m.get("target") or ""
    with WRITE_LOCK:
        cn = connect()
        r = cn.execute("SELECT * FROM ncrs WHERE no=?", (p[0],)).fetchone()
        if not r:
            raise ApiErr(404, "NCR 不存在")
        allowed = {"待评审": ["已评审"], "已评审": ["处置中"], "处置中": ["待验证"],
                   "待验证": ["已关闭"]}
        if target not in allowed.get(r["status"], []):
            cn.close()
            raise ApiErr(400, "不允许从「%s」推进到「%s」" % (r["status"], target))
        ctx = {"review": m.get("review") or r["review"],
               "disposition": m.get("disposition") or r["disposition"],
               "needDisposition": r["bad_qty"] > 0,
               "qty": r["qty"], "badQty": r["bad_qty"],
               "concessionMax": num(cn_setting("concession_max"), 0.03),
               "owner": m.get("owner") or r["owner"], "due": m.get("due") or r["due"],
               "doneDesc": m.get("doneDesc"), "verified": m.get("verified") or r["verified"],
               "verifier": m.get("verifier")}
        ok, msg = qms.ncr_gate(target, ctx)
        if not ok:
            cn.close()
            raise ApiErr(400, msg)
        cn.execute("""UPDATE ncrs SET review=?,disposition=?,owner=?,due=?,verified=?,verifier=?,
                      cost=? WHERE no=?""",
                   (ctx["review"], ctx["disposition"], ctx["owner"], ctx["due"],
                    ctx["verified"], ctx["verifier"], num(m.get("cost"), r["cost"]), p[0]))
        if target == "已关闭":
            cn.execute("UPDATE ncrs SET closed=? WHERE no=?", (now(), p[0]))
        cn.execute("UPDATE ncrs SET status=? WHERE no=?", (target, p[0]))
        cn.commit()
        cn.close()
    log_op(h.user["username"], "NCR推进", "%s→%s" % (p[0], target))
    emit("ncr.stage", {"no": p[0], "from": r["status"], "to": target})
    return {"ok": True, "status": target}


# ---- CAPA
@route("GET", r"/api/capas", "board.view")
def api_capas(h, p, m):
    cn = connect()
    q = "SELECT * FROM capas WHERE 1=1"
    args = []
    if m.get("status"):
        q += " AND status=?"
        args.append(m["status"])
    if m.get("q"):
        q += " AND (no LIKE ? OR problem LIKE ? OR leader LIKE ?)"
        args += ["%" + m["q"] + "%"] * 3
    rows = [capa_view(cn, r) for r in cn.execute(q + " ORDER BY id DESC LIMIT 200", args)]
    cn.close()
    return {"list": rows, "total": len(rows), "steps": qms.CAPA_STEPS,
            "stepNames": qms.CAPA_STEP_NAMES}


@route("GET", r"/api/capas/([A-Z0-9\-]+)", "board.view")
def api_capa(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM capas WHERE no=?", (p[0],)).fetchone()
    if not r:
        cn.close()
        raise ApiErr(404, "CAPA 不存在")
    v = capa_view(cn, r)
    cn.close()
    return v


@route("POST", r"/api/capas", "capa.manage")
def api_capa_create(h, p, m):
    if not m.get("problem") or len(m["problem"]) < 8:
        raise ApiErr(400, "问题描述不少于 8 字")
    cn = connect()
    no = next_no(cn, "CAPA", "capas")
    cn.execute("""INSERT INTO capas(no,source,ncr_no,problem,step,leader,members,description,
                  target,due,created,creator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (no, safe(m.get("source"), "内部"), safe(m.get("ncrNo")), m["problem"].strip(),
                "D1", safe(m.get("leader")), safe(m.get("members")), safe(m.get("description")),
                safe(m.get("target")),
                (datetime.now() + timedelta(days=num(cn_setting("capa_due_days"), 30))).strftime("%Y-%m-%d"),
                now(), h.user["username"]))
    cn.commit()
    cn.close()
    emit("capa.created", {"no": no, "problem": m["problem"]})
    return {"no": no}


@route("POST", r"/api/capas/([A-Z0-9\-]+)/step", "capa.manage")
def api_capa_step(h, p, m):
    with WRITE_LOCK:
        cn = connect()
        r = cn.execute("SELECT * FROM capas WHERE no=?", (p[0],)).fetchone()
        if not r:
            raise ApiErr(404, "CAPA 不存在")
        if r["status"] == "已关闭":
            cn.close()
            raise ApiErr(400, "CAPA 已关闭")
        nxt = qms.capa_next(r["step"])
        ctx = {"leader": m.get("leader") or r["leader"], "members": m.get("members") or r["members"],
               "description": m.get("description") or r["description"],
               "containment": m.get("containment"), "actions": m.get("actions") or r["actions"],
               "rootCause": m.get("rootCause") or r["root_cause"],
               "tasks": m.get("tasks"), "effect": m.get("effect") or r["effect"],
               "prevention": m.get("prevention")}
        ok, msg = qms.capa_gate(nxt, ctx)
        if not ok:
            cn.close()
            raise ApiErr(400, msg)
        cn.execute("""UPDATE capas SET step=?,leader=?,members=?,description=?,root_cause=?,
                      actions=?,effect=? WHERE no=?""",
                   (nxt, ctx["leader"], ctx["members"], ctx["description"],
                    ctx["rootCause"], ctx["actions"], ctx["effect"], p[0]))
        if nxt == "D8":
            cn.execute("UPDATE capas SET status='已关闭',closed=? WHERE no=?", (now(), p[0]))
        for t in m.get("tasks") or []:
            cn.execute("""INSERT INTO capa_tasks(capa_no,phase,action,owner,due)
                          VALUES(?,?,?,?,?)""",
                       (p[0], nxt, t.get("action", ""), safe(t.get("owner")), safe(t.get("due"))))
        cn.commit()
        cn.close()
    log_op(h.user["username"], "CAPA推进", "%s→%s" % (p[0], nxt))
    emit("capa.step", {"no": p[0], "step": nxt})
    return {"ok": True, "step": nxt, "stepName": qms.CAPA_STEP_NAMES.get(nxt)}


# ---- 供应商质量
@route("GET", r"/api/supplier/quality", "board.view")
def api_supplier_quality(h, p, m):
    cn = connect()
    month = m.get("month") or today()[:7]
    rows = cn.execute("SELECT * FROM scorings WHERE month=? ORDER BY total DESC", (month,)).fetchall()
    iqc = cn.execute("""SELECT supplier, COUNT(*) lots, SUM(CASE WHEN verdict='合格' THEN 1 ELSE 0 END) ok
                        FROM inspections WHERE itype='IQC' AND verdict!='' AND supplier!=''
                        GROUP BY supplier""").fetchall()
    by_sup = {r["supplier"]: dict(r) for r in iqc}
    out = []
    for r in rows:
        live = by_sup.get(r["supplier"], {})
        lots = int(r["lots"])
        out.append({"supplier": r["supplier"], "month": r["month"], "lots": lots,
                    "accepted": int(r["accepted"]), "irr": r["irr"], "ppm": r["ppm"],
                    "liveLots": live.get("lots", 0), "liveOk": live.get("ok", 0),
                    "q": r["q_score"], "d": r["d_score"], "r": r["r_score"],
                    "total": r["total"], "grade": r["grade"]})
    cn.close()
    return {"month": month, "list": out, "total": len(out)}


@route("POST", r"/api/supplier/score", "supplier.edit")
def api_supplier_score(h, p, m):
    supplier = m.get("supplier") or ""
    if not supplier:
        raise ApiErr(400, "供应商必填")
    month = m.get("month") or today()[:7]
    s = qms.supplier_score(num(m.get("q"), 80), num(m.get("d"), 80), num(m.get("r"), 80))
    cn = connect()
    cn.execute("""INSERT OR REPLACE INTO scorings(month,supplier,lots,accepted,irr,ppm,q_score,
                  d_score,r_score,total,grade,created) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
               (month, supplier, num(m.get("lots"), 0), num(m.get("accepted"), 0),
                num(m.get("irr"), 100), num(m.get("ppm"), 0),
                s["q"], s["d"], s["r"], s["total"], s["grade"], now()))
    cn.execute("UPDATE suppliers SET score=?,grade=? WHERE code=?", (s["total"], s["grade"], supplier))
    cn.commit()
    cn.close()
    return {"ok": True, "total": s["total"], "grade": s["grade"]}


@route("GET", r"/api/supplier/ppm", "board.view")
def api_supplier_ppm(h, p, m):
    cn = connect()
    rows = cn.execute("""SELECT supplier, SUM(critical_bad+major_bad+minor_bad) bad,
        SUM(lot_size) insp FROM inspections WHERE itype='IQC' AND verdict!='' AND supplier!=''
        GROUP BY supplier""").fetchall()
    cn.close()
    out = [{"supplier": r["supplier"], "ppm": qms.ppm(int(r["insp"] or 0), int(r["bad"] or 0)),
            "bad": int(r["bad"] or 0), "inspected": int(r["insp"] or 0)} for r in rows]
    return {"list": sorted(out, key=lambda x: -x["ppm"])}


# ---- SPC
@route("GET", r"/api/spc/series", "board.view")
def api_spc_series(h, p, m):
    cn = connect()
    proc = m.get("process") or "组装"
    char = m.get("char") or "锁附扭矩"
    rows = [dict(r) for r in cn.execute(
        "SELECT * FROM spc_series WHERE process=? AND char_name=? ORDER BY id", (proc, char))]
    cn.close()
    values = [r["value"] for r in rows]
    limits = qms.spc_limits(values)
    usl = rows[0]["usl"] if rows else None
    lsl = rows[0]["lsl"] if rows else None
    return {"process": proc, "char": char, "points": rows, "limits": limits,
            "cpk": qms.cpk(usl, lsl, values), "usl": usl, "lsl": lsl,
            "target": rows[0]["target"] if rows else None}


@route("GET", r"/api/spc/processes", "board.view")
def api_spc_processes(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT process, char_name, usl, lsl, target, COUNT(*) n FROM spc_series"
        " GROUP BY process, char_name")]
    cn.close()
    return {"list": rows}


@route("POST", r"/api/spc/series", "ipqc.do")
def api_spc_add(h, p, m):
    if m.get("value") is None or not m.get("process") or not m.get("char"):
        raise ApiErr(400, "工序、特性、数值必填")
    cn = connect()
    v = num(m["value"])
    grp = cn.execute("SELECT COALESCE(MAX(grp),0)+1 g FROM spc_series WHERE process=? AND char_name=?",
                     (m["process"], m["char"])).fetchone()["g"]
    cn.execute("""INSERT INTO spc_series(mat_code,process,char_name,usl,lsl,target,grp,value,
                  operator,sample_time) VALUES(?,?,?,?,?,?,?,?,?,?)""",
               (safe(m.get("matCode")), m["process"], m["char"], num(m.get("usl"), 0) or None,
                num(m.get("lsl"), 0) or None, num(m.get("target"), 0) or None, grp, v,
                h.user["username"], now()))
    cn.commit()
    n = cn.execute("SELECT COUNT(*) c FROM spc_series WHERE process=? AND char_name=?",
                   (m["process"], m["char"])).fetchone()["c"]
    cn.close()
    return {"ok": True, "total": n}


# ---- 分析
@route("GET", r"/api/analysis/pareto", "board.view")
def api_pareto(h, p, m):
    cn = connect()
    q = """SELECT d.name, d.severity, SUM(i.bad_qty) c FROM inspection_items i
           JOIN defects d ON i.defect_code=d.code WHERE i.bad_qty>0"""
    args = []
    if m.get("matCode"):
        q += " AND EXISTS(SELECT 1 FROM inspections x WHERE x.no=i.ins_no AND x.mat_code=?)"
        args.append(m["matCode"])
    rows = cn.execute(q + " GROUP BY d.name, d.severity", args).fetchall()
    cn.close()
    return {"list": qms.pareto([(r["name"], int(r["c"] or 0)) for r in rows]),
            "weighted": qms.pareto([(r["name"], int(r["c"] or 0) * qms.SEV_WEIGHT.get(r["severity"], 1))
                                    for r in rows])}


@route("GET", r"/api/analysis/fpy", "board.view")
def api_analysis_fpy(h, p, m):
    cn = connect()
    rows = cn.execute("""SELECT itype, COUNT(*) total, SUM(CASE WHEN verdict='合格' THEN 1 ELSE 0 END) ok
                         FROM inspections WHERE verdict!='' GROUP BY itype""").fetchall()
    cn.close()
    stages = [(qms.INS_TYPES.get(r["itype"], r["itype"]), int(r["total"]), int(r["ok"] or 0))
              for r in rows]
    return qms.fpy(stages)


@route("GET", r"/api/analysis/trend", "board.view")
def api_trend(h, p, m):
    cn = connect()
    rows = cn.execute("""SELECT substr(created,1,7) ym, COUNT(*) total,
        SUM(CASE WHEN verdict='合格' THEN 1 ELSE 0 END) ok FROM inspections
        WHERE verdict!='' GROUP BY ym ORDER BY ym""").fetchall()
    ncrs = cn.execute("SELECT substr(created,1,7) ym, COUNT(*) c FROM ncrs GROUP BY ym").fetchall()
    cn.close()
    nmap = {r["ym"]: r["c"] for r in ncrs}
    return {"list": [{"month": r["ym"], "total": r["total"], "ok": int(r["ok"] or 0),
                      "passRate": round(int(r["ok"] or 0) / r["total"] * 100, 1),
                      "ncr": nmap.get(r["ym"], 0)} for r in rows]}


@route("GET", r"/api/analysis/summary", "board.view")
def api_summary(h, p, m):
    cn = connect()
    month = m.get("month") or today()[:7]
    insp = cn.execute("SELECT COUNT(*) c FROM inspections WHERE verdict!='' AND substr(created,1,7)=?",
                      (month,)).fetchone()["c"]
    ok = cn.execute("SELECT COUNT(*) c FROM inspections WHERE verdict='合格' AND substr(created,1,7)=?",
                    (month,)).fetchone()["c"]
    bad = cn.execute("SELECT SUM(critical_bad+major_bad+minor_bad) s FROM inspections"
                     " WHERE substr(created,1,7)=?", (month,)).fetchone()["s"] or 0
    insp_qty = cn.execute("SELECT SUM(lot_size) s FROM inspections WHERE verdict!=''"
                          " AND substr(created,1,7)=?", (month,)).fetchone()["s"] or 0
    ncr = cn.execute("SELECT COUNT(*) c, SUM(cost) cost FROM ncrs WHERE substr(created,1,7)=?",
                     (month,)).fetchone()
    capa = cn.execute("SELECT COUNT(*) c FROM capas WHERE substr(created,1,7)=?",
                      (month,)).fetchone()["c"]
    cn.close()
    return {"month": month, "inspections": insp, "passRate": round(ok / insp * 100, 1) if insp else 0,
            "ppm": qms.ppm(int(insp_qty), int(bad)), "ncr": ncr["c"], "ncrCost": round(ncr["cost"] or 0, 2),
            "capa": capa}


# ---- 质量成本
@route("GET", r"/api/coq", "board.view")
def api_coq(h, p, m):
    cn = connect()
    month = m.get("month") or today()[:7]
    rows = [dict(r) for r in cn.execute(
        "SELECT * FROM coq WHERE month=? ORDER BY id", (month,))]
    cn.close()
    return {"month": month, "list": rows,
            "summary": qms.coq_summary([(r["category"], r["amount"]) for r in rows])}


@route("POST", r"/api/coq", "coq.edit")
def api_coq_add(h, p, m):
    if not m.get("item") or m.get("category") not in ("预防成本", "鉴定成本", "内部损失", "外部损失"):
        raise ApiErr(400, "项目必填，类别须为预防/鉴定/内损/外损四类")
    cn = connect()
    cn.execute("INSERT INTO coq(month,category,item,amount,dept,created,creator)"
               " VALUES(?,?,?,?,?,?,?)",
               (m.get("month") or today()[:7], m["category"], m["item"],
                num(m.get("amount")), safe(m.get("dept")), now(), h.user["username"]))
    cn.commit()
    cn.close()
    return {"ok": True}


@route("GET", r"/api/coq/trend", "board.view")
def api_coq_trend(h, p, m):
    cn = connect()
    rows = cn.execute("SELECT month, category, SUM(amount) s FROM coq GROUP BY month, category"
                      " ORDER BY month").fetchall()
    cn.close()
    months = sorted({r["month"] for r in rows})
    out = []
    for mo in months:
        sub = {r["category"]: r["s"] for r in rows if r["month"] == mo}
        out.append({"month": mo, **sub})
    return {"list": out}


# ---- 质量文件
@route("GET", r"/api/qdocs", "board.view")
def api_qdocs(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute("SELECT * FROM qdocs ORDER BY code")]
    cn.close()
    return {"list": rows, "total": len(rows)}


@route("POST", r"/api/qdocs", "mdm.edit")
def api_qdoc_add(h, p, m):
    if not m.get("code") or not m.get("name"):
        raise ApiErr(400, "文件编号与名称必填")
    cn = connect()
    try:
        cn.execute("INSERT INTO qdocs(code,name,category,version,owner,created)"
                   " VALUES(?,?,?,?,?,?)",
                   (m["code"].strip(), m["name"].strip(), safe(m.get("category"), "SOP"),
                    safe(m.get("version"), "V1.0"), h.user["username"], now()))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "保存失败：%s" % e)
    cn.close()
    return {"ok": True}


@route("POST", r"/api/qdocs/([A-Z0-9\-]+)/release", "settings.admin")
def api_qdoc_release(h, p, m):
    cn = connect()
    r = cn.execute("SELECT * FROM qdocs WHERE code=?", (p[0],)).fetchone()
    if not r:
        raise ApiErr(404, "文件不存在")
    cn.execute("UPDATE qdocs SET status='已发行',released=? WHERE code=?", (now(), p[0]))
    cn.commit()
    cn.close()
    emit("qdoc.released", {"code": p[0], "version": r["version"]})
    return {"ok": True}


# ---- 报表与导出
@route("GET", r"/api/reports/kpi", "board.view")
def api_reports_kpi(h, p, m):
    cn = connect()
    by_type = [dict(r) for r in cn.execute(
        """SELECT itype, COUNT(*) total, SUM(CASE WHEN verdict='合格' THEN 1 ELSE 0 END) ok,
           SUM(critical_bad+major_bad+minor_bad) bad FROM inspections
           WHERE verdict!='' GROUP BY itype""")]
    ncr_by_status = [dict(r) for r in cn.execute(
        "SELECT status, COUNT(*) c FROM ncrs GROUP BY status")]
    ncr_total = cn.execute("SELECT COUNT(*) c, SUM(CASE WHEN closed!='' THEN 1 ELSE 0 END) closed,"
                           " AVG(CASE WHEN closed!='' THEN julianday(closed)-julianday(created) END)"
                           " avg_days FROM ncrs").fetchone()
    capa_total = cn.execute("SELECT COUNT(*) c, SUM(CASE WHEN status='已关闭' THEN 1 ELSE 0 END) closed"
                            " FROM capas").fetchone()
    cn.close()
    for t in by_type:
        t["passRate"] = round(int(t["ok"] or 0) / t["total"] * 100, 1)
    return {"byType": by_type, "ncrByStatus": ncr_by_status,
            "ncr": {"total": ncr_total["c"], "closed": int(ncr_total["closed"] or 0),
                    "avgDays": round(ncr_total["avg_days"] or 0, 1)},
            "capa": {"total": capa_total["c"], "closed": int(capa_total["closed"] or 0),
                     "closeRate": round(int(capa_total["closed"] or 0) / capa_total["c"] * 100, 1)
                     if capa_total["c"] else 0}}


def _csv(rows, header):
    import io
    buf = io.StringIO()
    buf.write("\ufeff" + ",".join(header) + "\r\n")
    for r in rows:
        buf.write(",".join('"%s"' % str(x).replace('"', '""') for x in r) + "\r\n")
    return buf.getvalue()


@route("GET", r"/api/reports/inspections.csv", "board.view")
def api_export_inspections(h, p, m):
    cn = connect()
    rows = cn.execute("SELECT no,itype,mat_code,mat_name,batch_no,lot_size,status,verdict,"
                      "critical_bad,major_bad,minor_bad,created FROM inspections ORDER BY no").fetchall()
    cn.close()
    return {"__csv__": "飞控QMS-检验单.csv", "text": _csv(
        rows, ["单号", "类型", "物料", "名称", "批次", "批量", "状态", "判定", "致命", "严重", "轻微", "创建时间"])}


@route("GET", r"/api/reports/ncrs.csv", "board.view")
def api_export_ncrs(h, p, m):
    cn = connect()
    rows = cn.execute("SELECT no,ins_no,mat_code,batch_no,bad_qty,severity,status,disposition,"
                      "owner,closed FROM ncrs ORDER BY no").fetchall()
    cn.close()
    return {"__csv__": "飞控QMS-NCR.csv", "text": _csv(
        rows, ["单号", "检验单", "物料", "批次", "不良数", "等级", "状态", "处置", "责任人", "关闭时间"])}


@route("GET", r"/api/reports/defects.csv", "board.view")
def api_export_defects(h, p, m):
    cn = connect()
    rows = cn.execute("""SELECT d.code,d.name,d.category,d.severity,SUM(i.bad_qty) c
        FROM defects d LEFT JOIN inspection_items i ON i.defect_code=d.code
        GROUP BY d.code ORDER BY c DESC""").fetchall()
    cn.close()
    return {"__csv__": "飞控QMS-缺陷统计.csv", "text": _csv(
        rows, ["代码", "名称", "分类", "等级", "累计不良"])}


# ---- 系统设置与日志
@route("GET", r"/api/settings", "board.view")
def api_settings(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute("SELECT * FROM settings ORDER BY code")]
    cn.close()
    return {"list": rows}


@route("PUT", r"/api/settings", "settings.admin")
def api_settings_put(h, p, m):
    items = m.get("items") or []
    cn = connect()
    for it in items:
        cn.execute("UPDATE settings SET value=? WHERE code=?", (it.get("value"), it.get("code")))
    cn.commit()
    cn.close()
    log_op(h.user["username"], "修改设置", ",".join(i.get("code", "") for i in items))
    emit("rule.updated", {"codes": [i.get("code") for i in items]})
    return {"ok": True}


@route("GET", r"/api/logs", "board.view")
def api_logs(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT * FROM logs ORDER BY id DESC LIMIT 200")]
    cn.close()
    return {"list": rows}


# ---- 集成中心
@route("GET", r"/api/integration/keys", "board.view")
def api_keys(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT id,name,prefix,scope,enabled,created,last_used FROM api_keys ORDER BY id")]
    cn.close()
    return {"list": rows}


@route("POST", r"/api/integration/keys", "integration.admin")
def api_key_create(h, p, m):
    name = (m.get("name") or "").strip()
    if not name:
        raise ApiErr(400, "名称必填")
    raw = "fck_" + hashlib.sha256(("%s|%s|%f" % (name, time.time(), time.time())).encode()).hexdigest()[:24]
    cn = connect()
    try:
        cn.execute("INSERT INTO api_keys(name,key_hash,prefix,scope,created)"
                   " VALUES(?,?,?,?,?)",
                   (name, sha(raw), raw[:10], safe(m.get("scope"), "read"), now()))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "名称重复？%s" % e)
    cn.close()
    emit("key.created", {"name": name})
    return {"key": raw, "note": "明文仅显示一次"}


@route("DELETE", r"/api/integration/keys/(\d+)", "integration.admin")
def api_key_delete(h, p, m):
    cn = connect()
    cn.execute("DELETE FROM api_keys WHERE id=?", (p[0],))
    cn.commit()
    cn.close()
    return {"ok": True}


@route("GET", r"/api/integration/webhooks", "board.view")
def api_webhooks(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT id,name,url,events,enabled,last_status,created FROM webhooks ORDER BY id")]
    logs = [dict(r) for r in cn.execute(
        "SELECT * FROM webhook_logs ORDER BY id DESC LIMIT 50")]
    cn.close()
    return {"list": rows, "logs": logs, "events": EVENTS}


@route("POST", r"/api/integration/webhooks", "integration.admin")
def api_webhook_create(h, p, m):
    if not m.get("name") or not m.get("url"):
        raise ApiErr(400, "名称与 URL 必填")
    secret = "whsec_" + sha("%f" % time.time())[:20]
    cn = connect()
    try:
        cn.execute("INSERT INTO webhooks(name,url,secret,events,created)"
                   " VALUES(?,?,?,?,?)",
                   (m["name"], m["url"], secret, safe(m.get("events")), now()))
        cn.commit()
    except Exception as e:
        cn.close()
        raise ApiErr(400, "名称重复？%s" % e)
    cn.close()
    return {"secret": secret}


@route("DELETE", r"/api/integration/webhooks/(\d+)", "integration.admin")
def api_webhook_delete(h, p, m):
    cn = connect()
    cn.execute("DELETE FROM webhooks WHERE id=?", (p[0],))
    cn.commit()
    cn.close()
    return {"ok": True}


@route("POST", r"/api/integration/webhooks/(\d+)/test", "integration.admin")
def api_webhook_test(h, p, m):
    threading.Thread(target=deliver, args=(int(p[0]), "test.ping",
                                           {"hello": "feikong-qms"}), daemon=True).start()
    return {"ok": True, "note": "测试事件已投递（异步）"}


@route("GET", r"/api/integration/maps", "board.view")
def api_maps(h, p, m):
    cn = connect()
    rows = [dict(r) for r in cn.execute("SELECT * FROM field_maps ORDER BY id DESC LIMIT 200")]
    cn.close()
    return {"list": rows}


@route("POST", r"/api/integration/maps", "integration.admin")
def api_map_create(h, p, m):
    if not m.get("system") or not m.get("entity") or not m.get("extId") or not m.get("intId"):
        raise ApiErr(400, "system/entity/extId/intId 必填")
    cn = connect()
    cn.execute("INSERT INTO field_maps(system,entity,ext_id,int_id,created)"
               " VALUES(?,?,?,?,?)", (m["system"], m["entity"], m["extId"], m["intId"], now()))
    cn.commit()
    cn.close()
    return {"ok": True}


@route("GET", r"/api/integration/lookup", "board.view")
def api_map_lookup(h, p, m):
    if not m.get("system") or not m.get("extId"):
        raise ApiErr(400, "system 与 extId 必填")
    cn = connect()
    r = cn.execute("SELECT * FROM field_maps WHERE system=? AND ext_id=?",
                   (m["system"], m["extId"])).fetchone()
    cn.close()
    return {"found": bool(r), "intId": r["int_id"] if r else None}


EVENTS = ["inspection.created", "inspection.stage", "inspection.closed", "ncr.created",
          "ncr.stage", "ncr.closed", "capa.created", "capa.step", "capa.closed",
          "material.created", "material.updated", "qdoc.released", "key.created",
          "rule.updated", "test.ping"]


@route("GET", r"/api/sync/changes", "board.view")
def api_sync(h, p, m):
    try:
        since = int(m.get("since") or 0)
    except ValueError:
        raise ApiErr(400, "since 须为整数游标")
    cn = connect()
    rows = [dict(r) for r in cn.execute(
        "SELECT * FROM events WHERE id>? ORDER BY id LIMIT 500", (since,))]
    maxid = cn.execute("SELECT COALESCE(MAX(id),0) m FROM events").fetchone()["m"]
    cn.close()
    return {"changes": [{"id": r["id"], "event": r["event"], "ts": r["ts"],
                         "data": json.loads(r["data"] or "{}")} for r in rows],
            "cursor": maxid}


# ---- 运维
@route("GET", r"/api/health")
def api_health(h, p, m):
    cn = connect()
    n = cn.execute("SELECT COUNT(*) c FROM inspections").fetchone()["c"]
    cn.close()
    return {"status": "ok", "brand": qms.BRAND, "version": VERSION, "inspections": n}


@route("GET", r"/api/version")
def api_version(h, p, m):
    return {"brand": qms.BRAND, "version": VERSION, "routes": len(ROUTES),
            "events": EVENTS}


@route("GET", r"/api/openapi.json")
def api_openapi(h, p, m):
    paths = {}
    for method, rx, fn, perm in ROUTES:
        path = re.sub(r"\([^\)]*\)", "{param}", rx.pattern).strip("^$").replace("/{param}", "")
        if path.startswith("/api"):
            item = paths.setdefault(path, {})
            item[method.lower()] = {"summary": fn.__name__.replace("api_", ""),
                                    "security": [{"bearerAuth": []}] if perm else [],
                                    "responses": {"200": {"description": "ok"}}}
    return {"openapi": "3.0.3", "info": {"title": "飞控QMS系统 API", "version": VERSION,
            "description": "质量管理平台开放接口：检验/不合格品/CAPA/SPC/供应商质量/质量成本/集成三通道"},
            "servers": [{"url": "http://127.0.0.1:%d" % PORT, "description": "本地服务"},
                        {"url": "https://feikong-qms.app.workbuddy.host", "description": "线上服务"}],
            "components": {"securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer"},
                "apiKey": {"type": "apiKey", "in": "header", "name": "X-Qms-Key"}}},
            "paths": paths}


# ---------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "FeikongQMS/" + VERSION
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):                                # noqa: A003
        pass

    def _send(self, status, data, ctype="application/json; charset=utf-8"):
        body = data if isinstance(data, bytes) else json.dumps(
            data, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers",
                         "Content-Type,Authorization,X-Qms-Token,X-Auth-Token,Idempotency-Key")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,PUT,DELETE,OPTIONS")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):                                     # noqa: N802
        self._send(204, b"", "text/plain")

    def _token(self):
        auth = self.headers.get("Authorization") or ""
        if auth.startswith("Bearer "):
            return auth[7:].strip()
        for h in ("X-Qms-Token", "X-Auth-Token"):
            if self.headers.get(h):
                return self.headers.get(h).strip()
        ck = re.search(r"token=([0-9a-f]+)", self.headers.get("Cookie") or "")
        if ck:
            return ck.group(1)
        qs = parse_qs(urlparse(self.path).query)
        return (qs.get("token") or [""])[0]

    def _api_key_auth(self):
        key = self.headers.get("X-Qms-Key")
        if not key:
            return False
        cn = connect()
        r = cn.execute("SELECT * FROM api_keys WHERE key_hash=? AND enabled=1", (sha(key),)).fetchone()
        if r:
            cn.execute("UPDATE api_keys SET last_used=? WHERE id=?", (now(), r["id"]))
            cn.commit()
        cn.close()
        return bool(r)

    def do_GET(self):                                         # noqa: N802
        self._dispatch("GET")

    def do_POST(self):                                        # noqa: N802
        self._dispatch("POST")

    def do_PUT(self):                                         # noqa: N802
        self._dispatch("PUT")

    def do_DELETE(self):                                      # noqa: N802
        self._dispatch("DELETE")

    def _read_body(self):
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return dict(parse_qs(raw.decode("utf-8"))) if raw else {}

    def _dispatch(self, method):
        try:
            if method == "GET":
                qs = parse_qs(urlparse(self.path).query)
                m = {k: v[0] for k, v in qs.items()}
            else:
                m = self._read_body()
                qs = parse_qs(urlparse(self.path).query)
                for k, v in qs.items():
                    m.setdefault(k, v[0])
            path = urlparse(self.path).path

            # 限流（写接口 240/min）
            if method in ("POST", "PUT", "DELETE"):
                ip = self.client_address[0]
                win = RATE.get(ip)
                t = time.time()
                if not win or t - win[0] > 60:
                    RATE[ip] = [t, 1]
                else:
                    win[1] += 1
                    if win[1] > 240:
                        return self._send(429, {"code": 429, "message": "请求过于频繁（240/分钟）"})

            # 幂等
            idem = self.headers.get("Idempotency-Key")
            if idem and method in ("POST", "PUT"):
                cn = connect()
                hit = cn.execute("SELECT response FROM idem_keys WHERE key=?", (idem,)).fetchone()
                cn.close()
                if hit:
                    return self._send(200, json.loads(hit["response"]))

            # 路由匹配
            for rmethod, rx, fn, perm in ROUTES:
                if rmethod != method:
                    continue
                match = rx.match(path)
                if not match:
                    continue
                params = list(match.groups())
                # 认证（login/health/version/openapi 免认证）
                self.token = self._token()
                self.user = get_user_by_token(self.token)
                public = fn.__name__ in ("api_login", "api_health", "api_version", "api_openapi")
                if not public:
                    if not self.user:
                        if not self._api_key_auth():
                            return self._send(401, {"code": 401, "message": "未认证"})
                    elif perm and not qms.check_perm(self.user["role"], perm):
                        return self._send(403, {"code": 403,
                                                "message": "权限不足（需要 %s，角色 %s）" % (perm, self.user["role"])})
                result = fn(self, params, m)
                # CSV 导出特殊处理
                if isinstance(result, dict) and "__csv__" in result:
                    name = result["__csv__"]
                    data = result["text"].encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/csv; charset=utf-8")
                    self.send_header("Content-Disposition",
                                     "attachment; filename*=UTF-8''%s" % urllib.request.quote(name))
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                if idem:
                    with IDEM_LOCK:
                        cn = connect()
                        cn.execute("INSERT OR REPLACE INTO idem_keys(key,route,response,created)"
                                   " VALUES(?,?,?,?)",
                                   (idem, path, json.dumps(result, ensure_ascii=False, default=str), now()))
                        cn.commit()
                        cn.close()
                return self._send(200, result)
            return self._send(404, {"code": 404, "message": "接口不存在：%s %s" % (method, path)})
        except ApiErr as e:
            return self._send(e.code, {"code": e.code, "message": e.msg})
        except Exception as e:                                # noqa: BLE001
            import traceback
            traceback.print_exc()
            return self._send(500, {"code": 500, "message": "服务器内部错误：%s" % e})
        finally:
            db.close_thread_conns()                           # 兜底关闭本线程连接


def serve_static(handler, path):
    if path == "/":
        path = "/index.html"
    full = os.path.join(FRONTEND, path.lstrip("/"))
    if not os.path.isfile(full) and not path.endswith(".html"):
        full = os.path.join(FRONTEND, "index.html")           # hash 路由回退
    if not os.path.isfile(full):
        handler.send_response(404)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
        return
    ext = os.path.splitext(full)[1]
    with open(full, "rb") as f:
        body = f.read()
    handler.send_response(200)
    handler.send_header("Content-Type", MIME.get(ext, "application/octet-stream"))
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-cache")
    handler.end_headers()
    handler.wfile.write(body)


_orig_serve = Handler._dispatch


def _dispatch_with_static(self, method):
    path = urlparse(self.path).path
    if method == "GET" and not path.startswith("/api/"):
        return serve_static(self, path)
    return _orig_serve(self, method)


Handler._dispatch = _dispatch_with_static


def main():
    db.init()
    import seed as seed_mod
    seed_mod.seed()                                       # 空库自动灌演示数据
    srv = ThreadingHTTPServer((HOST, PORT), Handler)
    print("飞控QMS系统 v%s 服务启动 http://%s:%d （%d 条路由）"
          % (VERSION, HOST, PORT, len(ROUTES)))
    srv.serve_forever()


if __name__ == "__main__":
    main()
