# -*- coding: utf-8 -*-
"""飞控QMS · REST 接口测试（独立临时库 8945 端口）"""
import time


# ---------------------------------------------------------------- 认证与权限
def test_health_and_version(api):
    h = api.ok("GET", "/api/health")
    assert h["status"] == "ok" and "飞控QMS" in h["brand"]
    v = api.ok("GET", "/api/version")
    assert v["routes"] >= 60 and len(v["events"]) >= 15


def test_login_wrong_password(api):
    st, r = api.call("POST", "/api/auth/login", {"username": "admin", "password": "bad"})
    assert st == 401


def test_unauthorized_blocked(api):
    st, _ = api.call("GET", "/api/board", token="")
    assert st == 401


def test_role_isolation_inspector(api, tok_maker):
    t = tok_maker("zhangqiang")                      # 检验员
    st, _ = api.call("POST", "/api/ncrs", {"matCode": "MAT001", "badQty": 1}, token=t)
    assert st == 403
    st, _ = api.call("POST", "/api/users", {"username": "x1", "name": "x"}, token=t)
    assert st == 403
    st, _ = api.call("PUT", "/api/settings", {"items": []}, token=t)
    assert st == 403


def test_viewer_readonly(api, tok_maker):
    t = tok_maker("zhouyu")
    assert api.ok("GET", "/api/board", token=t)["kpi"]["inspections"] > 0
    st, _ = api.call("POST", "/api/inspections",
                     {"itype": "IQC", "matCode": "MAT001", "lotSize": 100}, token=t)
    assert st == 403


# ---------------------------------------------------------------- 主数据
def test_material_crud(api):
    d = api.ok("GET", "/api/materials")
    assert d["total"] >= 16
    api.ok("POST", "/api/materials", {"code": "MAT900", "name": "测试物料"})
    st, _ = api.call("POST", "/api/materials", {"code": "MAT900", "name": "重复"})
    assert st == 400
    api.ok("PUT", "/api/materials/MAT900", {"name": "测试物料改", "enabled": 1})


def test_plans_and_defects(api):
    p = api.ok("GET", "/api/plans")
    assert any(x["code"] == "QP001" and len(x["items"]) == 4 for x in p["list"])
    d = api.ok("GET", "/api/defects")
    assert any(x["severity"] == "A" for x in d["list"])


# ---------------------------------------------------------------- 检验全链路
def _record_all(api, no, bad_seq=None, bad_qty=1, defect="DC002"):
    d = api.ok("GET", "/api/inspections/" + no)
    records = []
    for it in d["items"]:
        if bad_seq and it["seq"] == bad_seq:
            records.append({"seq": it["seq"], "result": "NG", "badQty": bad_qty,
                            "defectCode": defect})
        else:
            records.append({"seq": it["seq"], "result": "OK"})
    return api.ok("POST", "/api/inspections/%s/record" % no, {"records": records})


def test_inspection_full_chain_pass(api):
    r = api.ok("POST", "/api/inspections", {"itype": "IQC", "matCode": "MAT001",
                                            "supplier": "SUP001", "orderNo": "PO-T1",
                                            "batchNo": "LOT-T1", "lotSize": 3200})
    no = r["no"]
    assert r["sampleSize"] == 200                       # AQL 查表 L 码
    api.err("POST", "/api/inspections/%s/stage" % no, {"target": "已判定"})  # 跳步拦截
    api.ok("POST", "/api/inspections/%s/start" % no, {})
    _record_all(api, no)
    st, e = api.call("POST", "/api/inspections/%s/stage" % no, {"target": "已判定"})
    assert st == 400                                    # 未提交判定不可直跳
    api.ok("POST", "/api/inspections/%s/stage" % no, {"target": "待判定"})
    st, e = api.call("POST", "/api/inspections/%s/stage" % no,
                     {"target": "已判定", "verdict": "不合格"})
    assert st == 400                                    # 无不良判不合格被拦
    d = api.ok("POST", "/api/inspections/%s/stage" % no,
               {"target": "已判定", "verdict": "合格"})
    assert d["status"] == "已判定"
    api.ok("POST", "/api/inspections/%s/stage" % no, {"target": "已放行"})
    api.ok("POST", "/api/inspections/%s/stage" % no, {"target": "已关闭"})


def test_inspection_fail_auto_ncr_and_critical_block(api):
    r = api.ok("POST", "/api/inspections", {"itype": "IQC", "matCode": "MAT001",
                                            "supplier": "SUP001", "batchNo": "LOT-T2",
                                            "lotSize": 1000})
    no = r["no"]
    api.ok("POST", "/api/inspections/%s/start" % no, {})
    _record_all(api, no, bad_seq=2, bad_qty=1, defect="DC001")   # A 级致命不良 1 件
    api.ok("POST", "/api/inspections/%s/stage" % no, {"target": "待判定"})
    api.err("POST", "/api/inspections/%s/stage" % no,
            {"target": "已判定", "verdict": "合格"})     # 致命缺陷判合格→一票否决
    d = api.ok("POST", "/api/inspections/%s/stage" % no,
               {"target": "已判定", "verdict": "不合格"})
    assert d.get("ncrNo"), "不合格判定应自动开 NCR"
    ncr = api.ok("GET", "/api/ncrs/" + d["ncrNo"])
    assert ncr["status"] == "待评审" and ncr["badQty"] >= 1


def test_ncr_full_chain(api):
    r = api.ok("POST", "/api/ncrs", {"matCode": "MAT007", "batchNo": "LOT-T3",
                                     "qty": 1000, "badQty": 20, "severity": "B",
                                     "description": "色差超限"})
    no = r["no"]
    api.err("POST", "/api/ncrs/%s/stage" % no, {"target": "处置中"})        # 跳步
    api.ok("POST", "/api/ncrs/%s/stage" % no,
           {"target": "已评审", "review": "挑选使用", "disposition": "让步接收"})
    api.ok("POST", "/api/ncrs/%s/stage" % no,
           {"target": "处置中", "owner": "wangfang", "due": "2026-12-31"})
    api.err("POST", "/api/ncrs/%s/stage" % no, {"target": "待验证"})        # 缺处置结果
    api.ok("POST", "/api/ncrs/%s/stage" % no, {"target": "待验证", "doneDesc": "挑选完成"})
    api.ok("POST", "/api/ncrs/%s/stage" % no,
           {"target": "已关闭", "verified": "复检合格", "verifier": "liming"})


def test_ncr_concession_limit_api(api):
    r = api.ok("POST", "/api/ncrs", {"matCode": "MAT001", "qty": 100, "badQty": 20,
                                     "severity": "B", "description": "超限让步"})
    st, e = api.call("POST", "/api/ncrs/%s/stage" % r["no"],
                     {"target": "已评审", "review": "让步", "disposition": "让步接收"})
    assert st == 400 and "超上限" in e["message"]


def test_capa_eight_d_chain(api):
    r = api.ok("POST", "/api/capas", {"problem": "测试 8D 全链路：连接器插拔不良",
                                      "source": "NCR"})
    no = r["no"]
    api.err("POST", "/api/capas/%s/step" % no, {})       # D1 缺组长与成员
    d = api.ok("POST", "/api/capas/%s/step" % no,
               {"leader": "wangfang", "members": "chenjing"})
    assert d["step"] == "D2"
    api.err("POST", "/api/capas/%s/step" % no, {"description": "短"})
    d = api.ok("POST", "/api/capas/%s/step" % no,
               {"description": "连接器插拔 5000 次后出现接触不良，客户端投诉 3 起"})
    assert d["step"] == "D3"
    api.err("POST", "/api/capas/%s/step" % no, {"containment": ""})          # 缺围堵
    d = api.ok("POST", "/api/capas/%s/step" % no, {"containment": "全检库存"})
    assert d["step"] == "D4"
    api.err("POST", "/api/capas/%s/step" % no, {"rootCause": "太短"})
    d = api.ok("POST", "/api/capas/%s/step" % no,
               {"rootCause": "端子压接高度偏低导致接触电阻偏大", "actions": "调整压接参数"})
    assert d["step"] == "D5"
    d = api.ok("POST", "/api/capas/%s/step" % no,
               {"tasks": [{"action": "调整压接机", "owner": "chenjing", "due": "2026-12-01"}]})
    assert d["step"] == "D6"
    api.err("POST", "/api/capas/%s/step" % no, {"effect": ""})
    d = api.ok("POST", "/api/capas/%s/step" % no, {"effect": "接触电阻复测合格"})
    assert d["step"] == "D7"
    api.err("POST", "/api/capas/%s/step" % no, {})       # 缺预防措施
    d = api.ok("POST", "/api/capas/%s/step" % no, {"prevention": "压接参数纳入首件检"})
    assert d["step"] == "D8"
    final = api.ok("GET", "/api/capas/" + no)
    assert final["status"] == "已关闭" and final["closed"]


# ---------------------------------------------------------------- SPC / 分析 / COQ
def test_spc_series_and_add(api):
    d = api.ok("GET", "/api/spc/series")
    assert len(d["points"]) == 60 and d["cpk"]["cpk"] > 1.0
    r = api.ok("POST", "/api/spc/series", {"process": "组装", "char": "锁附扭矩",
                                           "value": 4.52, "usl": 5.0, "lsl": 4.0})
    assert r["total"] == 61


def test_analysis_endpoints(api):
    p = api.ok("GET", "/api/analysis/pareto")
    assert p["list"] and p["list"][-1]["cumPct"] == 100.0
    f = api.ok("GET", "/api/analysis/fpy")
    assert 0 < f["fpy"] <= 100
    t = api.ok("GET", "/api/analysis/trend")
    assert t["list"]


def test_coq(api):
    d = api.ok("GET", "/api/coq")
    assert d["summary"]["total"] > 0
    st, _ = api.call("POST", "/api/coq", {"category": "未知类别", "item": "x"})
    assert st == 400
    api.ok("POST", "/api/coq", {"category": "内部损失", "item": "测试报废", "amount": 500})


def test_supplier_quality(api):
    d = api.ok("GET", "/api/supplier/quality")
    assert d["total"] == 8 and any(x["grade"] == "A" for x in d["list"])
    r = api.ok("POST", "/api/supplier/score", {"supplier": "SUP004", "q": 85, "d": 80, "r": 90})
    assert r["grade"] in ("A", "B")
    ppm = api.ok("GET", "/api/supplier/ppm")
    assert ppm["list"]


# ---------------------------------------------------------------- 幂等 / 多通道
def test_idempotency_key(api):
    key = "idem-%d" % time.time()
    body = {"code": "MAT910", "name": "幂等物料"}
    h = {"Idempotency-Key": key}
    r1 = api.ok("POST", "/api/materials", body, headers=h)
    r2 = api.ok("POST", "/api/materials", body, headers=h)     # 重放返回缓存
    assert r1 == r2
    st, _ = api.call("POST", "/api/materials", {"code": "MAT911", "name": "x"})
    assert st == 200


def test_multi_channel_token(api, tok_maker):
    t = tok_maker("wangfang")
    st, r1 = api.call("GET", "/api/board", token=t)
    assert st == 200
    st, r2 = api.call("GET", "/api/board?token=" + t)
    assert st == 200 and r2["kpi"] == r1["kpi"]
    st, r3 = api.call("GET", "/api/board", headers={"X-Auth-Token": t})
    assert st == 200


# ---------------------------------------------------------------- 集成通道
def test_api_key_auth(api):
    r = api.ok("POST", "/api/integration/keys", {"name": "erp-push-%d" % time.time(),
                                                 "scope": "read"})
    assert r["key"].startswith("fck_")
    st, board = api.call("GET", "/api/board", headers={"X-Qms-Key": r["key"]})
    assert st == 200 and "kpi" in board
    st, _ = api.call("GET", "/api/board", token="", headers={"X-Qms-Key": "fck_wrong"})
    assert st == 401
    api.ok("GET", "/api/integration/keys")


def test_webhook_and_events(api):
    d = api.ok("GET", "/api/integration/webhooks")
    assert "test.ping" in d["events"] and "inspection.stage" in d["events"]
    r = api.ok("POST", "/api/integration/webhooks",
               {"name": "t-%d" % time.time(), "url": "http://127.0.0.1:9/x"})
    assert r["secret"].startswith("whsec_")
    api.ok("POST", "/api/integration/webhooks/1/test", {})
    s = api.ok("GET", "/api/sync/changes?since=0")
    assert "cursor" in s and isinstance(s["changes"], list)


def test_map_and_lookup(api):
    api.ok("POST", "/api/integration/maps", {"system": "ERP", "entity": "inspection",
                                             "extId": "EXT-%d" % time.time(), "intId": "IQ2610-0001"})
    r = api.ok("GET", "/api/integration/keys")


# ---------------------------------------------------------------- 导出 / 设置 / 日志
def test_csv_exports(api):
    st, headers, raw = api.raw("GET", "/api/reports/inspections.csv")
    assert st == 200 and "filename" in headers.get("Content-Disposition", "")
    text = raw.decode("utf-8-sig")
    assert text.splitlines()[0].startswith("单号") and "IQ" in text
    st, _, raw2 = api.raw("GET", "/api/reports/ncrs.csv")
    assert st == 200 and raw2.decode("utf-8-sig").splitlines()[0].startswith("单号")


def test_settings_and_logs(api):
    d = api.ok("GET", "/api/settings")
    assert any(x["code"] == "concession_max" for x in d["list"])
    api.ok("PUT", "/api/settings", {"items": [{"code": "ipqc_interval", "value": "90"}]})
    d2 = api.ok("GET", "/api/logs")
    assert any("修改设置" in x["action"] for x in d2["list"])


def test_openapi(api):
    spec = api.ok("GET", "/api/openapi.json")
    assert spec["openapi"].startswith("3.0") and len(spec["paths"]) >= 40
    assert "/api/inspections" in spec["paths"]
