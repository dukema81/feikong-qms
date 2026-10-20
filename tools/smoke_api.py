# -*- coding: utf-8 -*-
"""飞控QMS · 全链路冒烟：认证/主数据/检验/NCR/CAPA/SPC/分析/COQ/供应商/导出/集成。
用法：python tools/smoke_api.py [BASE]（默认 http://127.0.0.1:8024，演示库）"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8024"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
CHECKS = []


def call(method, path, body=None, headers=None, token=None):
    req = urllib.request.Request(BASE + path, method=method,
                                 data=json.dumps(body).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    tok = token if token is not None else TOKEN
    if tok:
        req.add_header("Authorization", "Bearer " + tok)
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with OP.open(req, timeout=20) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read())
        except Exception:                                     # noqa: BLE001
            return e.code, {}


def ck(name, cond, extra=""):
    CHECKS.append((name, bool(cond), extra))
    print(("  ✓ " if cond else "  ✗ ") + name + (("  " + str(extra)) if (extra and not cond) else ""))


def section(title):
    print("\n■ " + title)


def main():
    global TOKEN
    section("认证与健康")
    st, r = call("GET", "/api/health", token="")
    ck("health ok", st == 200 and r.get("status") == "ok")
    st, r = call("GET", "/api/version", token="")
    ck("版本与路由数", st == 200 and r.get("routes", 0) >= 60, r.get("routes"))
    st, r = call("POST", "/api/auth/login", {"username": "admin", "password": "bad"}, token="")
    ck("错误密码 401", st == 401)
    st, r = call("POST", "/api/auth/login", {"username": "admin", "password": "qms@2026"})
    ck("admin 登录", st == 200 and r.get("token"))
    TOKEN = r.get("token", "")
    st, r = call("GET", "/api/auth/me")
    ck("me 含权限", st == 200 and len(r.get("user", {}).get("perms", [])) == 11)

    section("驾驶舱")
    st, board = call("GET", "/api/board")
    ck("KPI 完整", all(k in board.get("kpi", {}) for k in
                       ("inspections", "pending", "iqcPassRate", "ncrOpen", "capaOpen")))
    ck("帕累托非空", len(board.get("pareto", [])) > 0)
    ck("SPC 控制限", board.get("spc", {}).get("ucl", 0) > board.get("spc", {}).get("lcl", 1))

    section("主数据")
    st, r = call("GET", "/api/materials")
    ck("物料 16+", r.get("total", 0) >= 16)
    st, r = call("GET", "/api/suppliers")
    ck("供应商 8 家", r.get("total", 0) == 8)
    st, r = call("GET", "/api/plans")
    ck("检验方案 6 套", r.get("total", 0) == 6)
    ck("方案含项目", any(len(x.get("items", [])) >= 4 for x in r.get("list", [])))
    st, r = call("GET", "/api/defects")
    ck("缺陷代码 18+", r.get("total", 0) >= 18)

    section("检验全链路（新建→开始→录入→判定→放行→关闭）")
    st, r = call("POST", "/api/inspections", {"itype": "IQC", "matCode": "MAT001",
                                              "supplier": "SUP001", "batchNo": "LOT-SM-%d" % time.time(),
                                              "lotSize": 3200})
    no = r.get("no", "")
    ck("创建 IQC 并抽样 200", st == 200 and r.get("sampleSize") == 200, r)
    call("POST", "/api/inspections/%s/start" % no, {})
    st, d = call("GET", "/api/inspections/" + no)
    ck("项目自动载入 4 项", d.get("count") == 4)
    records = [{"seq": it["seq"], "result": "OK"} for it in d.get("items", [])]
    st, r = call("POST", "/api/inspections/%s/record" % no, {"records": records})
    ck("录入汇总无不良", r.get("aggregated", {}).get("A") == 0)
    call("POST", "/api/inspections/%s/stage" % no, {"target": "待判定"})
    st, r = call("POST", "/api/inspections/%s/stage" % no, {"target": "已判定", "verdict": "合格"})
    ck("判定合格", r.get("status") == "已判定")
    print("    AQL 方案:", d.get("plan"))
    st, r = call("POST", "/api/inspections/%s/stage" % no, {"target": "已放行"})
    ck("放行", r.get("status") == "已放行")
    st, r = call("POST", "/api/inspections/%s/stage" % no, {"target": "已关闭"})
    ck("关闭", r.get("status") == "已关闭")

    section("不合格自动开 NCR 与闭环")
    st, r = call("POST", "/api/inspections", {"itype": "IQC", "matCode": "MAT001",
                                              "supplier": "SUP001", "batchNo": "LOT-SM2-%d" % time.time(),
                                              "lotSize": 1000})
    no2 = r["no"]
    call("POST", "/api/inspections/%s/start" % no2, {})
    st, d = call("GET", "/api/inspections/" + no2)
    records = [{"seq": it["seq"], "result": "NG" if it["seq"] == 2 else "OK",
                "badQty": 1 if it["seq"] == 2 else 0,
                "defectCode": "DC001" if it["seq"] == 2 else ""} for it in d.get("items", [])]
    call("POST", "/api/inspections/%s/record" % no2, {"records": records})
    call("POST", "/api/inspections/%s/stage" % no2, {"target": "待判定"})
    st, r = call("POST", "/api/inspections/%s/stage" % no2, {"target": "已判定", "verdict": "不合格"})
    ncr_no = r.get("ncrNo", "")
    ck("自动生成 NCR", bool(ncr_no), r)
    st, ncr = call("GET", "/api/ncrs/" + ncr_no)
    ck("NCR 待评审", ncr.get("status") == "待评审")
    call("POST", "/api/ncrs/%s/stage" % ncr_no,
         {"target": "已评审", "review": "返工处理", "disposition": "返工"})
    call("POST", "/api/ncrs/%s/stage" % ncr_no, {"target": "处置中", "owner": "wangfang",
                                                 "due": "2099-01-01"})
    call("POST", "/api/ncrs/%s/stage" % ncr_no, {"target": "待验证", "doneDesc": "返工完成"})
    st, r = call("POST", "/api/ncrs/%s/stage" % ncr_no,
                 {"target": "已关闭", "verified": "复检合格", "verifier": "liming"})
    ck("NCR 闭环", r.get("status") == "已关闭")

    section("CAPA 8D")
    st, r = call("POST", "/api/capas", {"problem": "冒烟：8D 全链路验证问题描述", "source": "内部"})
    capa = r.get("no", "")
    call("POST", "/api/capas/%s/step" % capa, {"leader": "liming", "members": "wangfang"})
    call("POST", "/api/capas/%s/step" % capa,
         {"description": "冒烟测试问题描述：连接器插拔 5000 次后接触不良，客户端累计投诉 3 起"})
    call("POST", "/api/capas/%s/step" % capa, {"containment": "库存全检"})
    call("POST", "/api/capas/%s/step" % capa, {"rootCause": "冒烟根因：验证 5Why 长度闸口逻辑"})
    call("POST", "/api/capas/%s/step" % capa, {"tasks": [{"action": "整改", "owner": "wf"}]})
    call("POST", "/api/capas/%s/step" % capa, {"effect": "复测合格"})
    st, r = call("POST", "/api/capas/%s/step" % capa, {"prevention": "标准化固化"})
    ck("8D 推进到 D8 并关闭", r.get("step") == "D8")
    st, r = call("GET", "/api/capas/" + capa)
    ck("CAPA 已关闭", r.get("status") == "已关闭")

    section("SPC / 分析 / COQ / 供应商")
    st, r = call("GET", "/api/spc/series")
    ck("SPC 60 点 + Cpk>1", len(r.get("points", [])) == 60 and r.get("cpk", {}).get("cpk", 0) > 1,
       r.get("cpk"))
    print("    Cp/Cpk:", r.get("cpk", {}).get("cp"), "/", r.get("cpk", {}).get("cpk"))
    st, r = call("GET", "/api/analysis/pareto")
    ck("帕累托累计 100%", r["list"][-1]["cumPct"] == 100.0)
    st, r = call("GET", "/api/analysis/fpy")
    ck("FPY 口径", 0 < r.get("fpy", 0) <= 100, r.get("fpy"))
    st, r = call("GET", "/api/coq")
    ck("COQ 四类汇总", len(r.get("summary", {}).get("items", [])) == 4)
    st, r = call("GET", "/api/supplier/quality")
    ck("供应商评分含 A 级", any(x.get("grade") == "A" for x in r.get("list", [])))
    st, r = call("GET", "/api/supplier/ppm")
    ck("PPM 排行", len(r.get("list", [])) > 0)

    section("幂等 / 权限 / 多通道令牌")
    key = {"Idempotency-Key": "smoke-%d" % time.time()}
    body = {"code": "MATSM%d" % (time.time() % 100000), "name": "冒烟物料"}
    r1 = call("POST", "/api/materials", body, headers=key)[1]
    r2 = call("POST", "/api/materials", body, headers=key)[1]
    ck("幂等重放一致", r1 == r2)
    st, _ = call("GET", "/api/board", token="")
    ck("无令牌 401", st == 401)
    st, r = call("GET", "/api/board?token=" + TOKEN, token="")
    ck("查询串令牌", st == 200)
    st, r = call("POST", "/api/users", {"username": "x", "name": "x", "role": "viewer"},
                 token=None)
    tok_view = call("POST", "/api/auth/login",
                    {"username": "zhouyu", "password": "qms@2026"})[1]["token"]
    st, _ = call("POST", "/api/materials", {"code": "MATVD", "name": "x"}, token=tok_view)
    ck("只读角色 403", st == 403)

    section("导出 / 报表 / 集成 / OpenAPI")
    req = urllib.request.Request(BASE + "/api/reports/inspections.csv")
    req.add_header("Authorization", "Bearer " + TOKEN)
    with OP.open(req, timeout=20) as resp:
        text = resp.read().decode("utf-8-sig")
    ck("检验单 CSV 导出", text.splitlines()[0].startswith("单号") and len(text.splitlines()) > 10)
    st, r = call("GET", "/api/reports/kpi")
    ck("KPI 报表", "byType" in r and "capa" in r)
    st, r = call("POST", "/api/integration/keys", {"name": "smoke-%d" % time.time()})
    ck("API Key fck_ 前缀", r.get("key", "").startswith("fck_"))
    st, r = call("POST", "/api/integration/webhooks",
                 {"name": "smoke-%d" % time.time(), "url": "http://127.0.0.1:9/x"})
    ck("Webhook secret", r.get("secret", "").startswith("whsec_"))
    st, r = call("GET", "/api/integration/webhooks")
    ck("15 种事件", len(r.get("events", [])) == 15)
    st, r = call("GET", "/api/sync/changes?since=0")
    ck("增量同步游标", "cursor" in r)
    st, r = call("GET", "/api/openapi.json", token="")
    ck("OpenAPI 40+ path", len(r.get("paths", {})) >= 40, len(r.get("paths", {})))

    failed = [c for c in CHECKS if not c[1]]
    print("\n" + "=" * 60)
    print("冒烟结果：%d/%d 通过" % (len(CHECKS) - len(failed), len(CHECKS)))
    for name, _, extra in failed:
        print("  ✗ " + name + " " + str(extra))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
