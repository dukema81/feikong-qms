# -*- coding: utf-8 -*-
"""飞控QMS · 业务内核单元测试（qms.py 纯函数，无 I/O）"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "backend"))

import qms  # noqa: E402


# ---------------------------------------------------------------- 状态机
def test_ins_states_order():
    assert qms.INS_STATES[:5] == ["待检验", "检验中", "待判定", "已判定", "已放行"]
    assert "已取消" in qms.INS_STATES


def test_ins_can_move_forward():
    assert qms.can_move("待检验", "检验中", qms.INS_ARROWS)
    assert qms.can_move("已判定", "已放行", qms.INS_ARROWS)
    assert qms.can_move("已判定", "已关闭", qms.INS_ARROWS)
    assert not qms.can_move("待检验", "已判定", qms.INS_ARROWS)
    assert not qms.can_move("已关闭", "检验中", qms.INS_ARROWS)


def test_ncr_states_and_arrows():
    assert qms.NCR_STATES == ["待评审", "已评审", "处置中", "待验证", "已关闭"]
    assert qms.can_move("待评审", "已评审", qms.NCR_ARROWS)
    assert not qms.can_move("待评审", "已关闭", qms.NCR_ARROWS)


def test_capa_steps():
    assert qms.CAPA_STEPS[0] == "D1" and qms.CAPA_STEPS[-1] == "D8"
    assert qms.capa_next("D1") == "D2"
    assert qms.capa_next("D7") == "D8"
    assert qms.capa_next("D8") == "D8"


# ---------------------------------------------------------------- 检验闸口
def test_gate_start_requires_lot():
    ok, _ = qms.ins_gate("检验中", {"lotSize": 0})
    assert not ok
    ok, _ = qms.ins_gate("检验中", {"lotSize": 1000})
    assert ok


def test_gate_judge_requires_all_items():
    items = [{"result": "OK"}, {"result": ""}]
    ok, msg = qms.ins_gate("待判定", {"items": items})
    assert not ok and "未录入" in msg
    ok, _ = qms.ins_gate("待判定", {"items": [{"result": "OK"}]})
    assert ok


def test_gate_critical_block():
    ok, msg = qms.ins_gate("已判定", {"verdict": "合格", "criticalBad": 2, "criticalBlock": True})
    assert not ok and "致命" in msg


def test_gate_judge_requires_judge_name():
    ok, _ = qms.ins_gate("已判定", {"verdict": "合格", "judgedBy": "", "criticalBad": 0})
    assert not ok
    ok, _ = qms.ins_gate("已判定", {"verdict": "合格", "judgedBy": "zq", "criticalBad": 0})
    assert ok


def test_gate_release_only_pass():
    ok, _ = qms.ins_gate("已放行", {"verdict": "不合格"})
    assert not ok
    ok, _ = qms.ins_gate("已放行", {"verdict": "合格"})
    assert ok


def test_gate_close_requires_ncr():
    ok, _ = qms.ins_gate("已关闭", {"verdict": "不合格", "ncrNo": ""})
    assert not ok
    ok, _ = qms.ins_gate("已关闭", {"verdict": "不合格", "ncrNo": "NCR2601-0001"})
    assert ok


# ---------------------------------------------------------------- NCR 闸口
def test_ncr_review_required():
    ok, _ = qms.ncr_gate("已评审", {"review": "", "needDisposition": True})
    assert not ok
    ok, _ = qms.ncr_gate("已评审", {"review": "退货处理", "needDisposition": True,
                                    "disposition": "退货"})
    assert ok


def test_ncr_concession_rate_limit():
    ctx = {"review": "x", "disposition": "让步接收", "qty": 100, "badQty": 5,
           "concessionMax": 0.03}
    ok, msg = qms.ncr_gate("已评审", ctx)
    assert not ok and "超上限" in msg
    ctx["badQty"] = 2
    ok, _ = qms.ncr_gate("已评审", ctx)
    assert ok


def test_ncr_dispose_requires_owner():
    ok, _ = qms.ncr_gate("处置中", {"owner": "", "due": "2026-01-01"})
    assert not ok
    ok, _ = qms.ncr_gate("处置中", {"owner": "w1", "due": ""})
    assert not ok
    ok, _ = qms.ncr_gate("处置中", {"owner": "w1", "due": "2026-01-01"})
    assert ok


def test_ncr_close_requires_verify():
    ok, _ = qms.ncr_gate("已关闭", {"verified": "", "verifier": ""})
    assert not ok
    ok, _ = qms.ncr_gate("已关闭", {"verified": "有效", "verifier": "lm"})
    assert ok


# ---------------------------------------------------------------- CAPA 闸口
def test_capa_d1_requires_team():
    ok, _ = qms.capa_gate("D2", {"leader": "", "members": ""})
    assert not ok
    ok, _ = qms.capa_gate("D2", {"leader": "lm", "members": "wf,cj"})
    assert ok


def test_capa_d2_description_len():
    ok, _ = qms.capa_gate("D3", {"description": "太短"})
    assert not ok
    ok, _ = qms.capa_gate("D3", {"description": "2025年12月起华南客户反馈充电发热，共3起投诉"})
    assert ok


def test_capa_d4_root_cause_len():
    ok, _ = qms.capa_gate("D5", {"rootCause": "模具坏"})
    assert not ok
    ok, _ = qms.capa_gate("D5", {"rootCause": "冲压模具磨损导致插针圆度超差"})
    assert ok


def test_capa_d6_effect_required():
    ok, _ = qms.capa_gate("D7", {"effect": ""})
    assert not ok
    ok, _ = qms.capa_gate("D7", {"effect": "复测全部合格"})
    assert ok


# ---------------------------------------------------------------- AQL 抽样
def test_aql_sample_code_levels():
    assert qms.sample_code(3200) == "L"
    assert qms.sample_code(50) == "E"
    assert qms.sample_code(100000) == "P"
    assert qms.sample_code(3200, "I") == "J"
    assert qms.sample_code(3200, "III") == "N"


def test_aql_plan_basic():
    p = qms.aql_plan(3200, "1.0")
    assert p["code"] == "L" and p["sampleSize"] == 200
    assert p["re"] == p["ac"] + 1
    assert p["criticalAc"] == 0


def test_aql_stricter_for_lower_aql():
    hi = qms.aql_plan(3200, "1.0")["ac"]
    lo = qms.aql_plan(3200, "0.25")["ac"]
    assert lo <= hi


def test_verdict_by_aql():
    p = qms.aql_plan(3200, "1.0")
    v, why = qms.verdict_by_aql({"A": 0, "B": 2, "C": 1}, p)
    assert v == "合格"
    v, why = qms.verdict_by_aql({"A": 1, "B": 0, "C": 0}, p)
    assert v == "不合格" and "致命" in why


# ---------------------------------------------------------------- SPC
def test_spc_limits_basic():
    vs = [4.5, 4.6, 4.4, 4.5, 4.7] * 4
    r = qms.spc_limits(vs)
    assert r["ucl"] > r["cl"] > r["lcl"]
    assert r["outliers"] == []


def test_spc_detects_outlier():
    vs = [4.5] * 19 + [5.5]
    r = qms.spc_limits(vs)
    assert len(r["outliers"]) >= 1


def test_cpk_good_process():
    import random
    rnd = random.Random(7)
    vs = [rnd.gauss(4.5, 0.1) for _ in range(60)]
    r = qms.cpk(5.0, 4.0, vs)
    assert r["cpk"] > 1.0 and r["grade"] in ("优", "良")


def test_cpk_shifted_process():
    import random
    rnd = random.Random(7)
    vs = [rnd.gauss(4.9, 0.1) for _ in range(60)]
    r = qms.cpk(5.0, 4.0, vs)
    assert r["cpu"] < r["cpl"]
    assert r["cpk"] == r["cpu"]


def test_cpk_degenerate():
    r = qms.cpk(5.0, 4.0, [4.5])
    assert r["grade"] == "数据不足"
    r = qms.cpk(5.0, 4.0, [4.5, 4.5, 4.5])
    assert r["grade"] == "无变异"


# ---------------------------------------------------------------- 分析口径
def test_pareto_sorted_with_cum():
    out = qms.pareto([("a", 5), ("b", 3), ("c", 2)])
    assert out[0]["name"] == "a" and out[0]["cumPct"] == 50.0
    assert out[-1]["cumPct"] == 100.0


def test_weighted_defects():
    assert qms.weighted_defects(1, 2, 3) == 23
    assert qms.weighted_defects(0, 0, 0) == 0


def test_fpy_multiplicative():
    r = qms.fpy([("IQC", 100, 90), ("IPQC", 90, 81), ("FQC", 81, 72)])
    assert r["fpy"] == 72.0
    assert r["stages"][0]["rty"] == 90.0


def test_ppm():
    assert qms.ppm(10000, 3) == 300.0
    assert qms.ppm(0, 5) == 0.0


def test_supplier_score_grades():
    assert qms.supplier_score(95, 90, 85)["grade"] == "A"
    assert qms.supplier_score(80, 80, 80)["grade"] == "B"
    assert qms.supplier_score(60, 60, 60)["grade"] == "D"
    s = qms.supplier_score(100, 100, 100)
    assert s["total"] == 100.0


def test_irr():
    assert qms.irr(9, 10) == 90.0
    assert qms.irr(0, 0) == 100.0


def test_coq_summary():
    s = qms.coq_summary([("预防成本", 10), ("鉴定成本", 20), ("内部损失", 30), ("外部损失", 40)])
    assert s["total"] == 100
    assert s["failRate"] == 70.0


def test_due_check():
    assert qms.due_check("2020-01-01", "2026-10-21") == "已逾期"
    assert qms.due_check("2026-10-21", "2026-10-21") == "今日到期"
    assert qms.due_check("2099-01-01", "2026-10-21") == "正常"
    assert qms.due_check("") == "未设时限"


# ---------------------------------------------------------------- 权限
def test_perm_matrix_shape():
    assert len(qms.PERMS) == 11 and len(qms.ROLES) == 8
    for role in qms.ROLES:
        assert role in qms.PERM_MATRIX


def test_perm_admin_full_viewer_min():
    assert len(qms.perm_of("admin")) == len(qms.PERMS)
    assert qms.perm_of("viewer") == ["board.view"]


def test_inspector_cannot_manage_ncr():
    assert not qms.check_perm("inspector", "ncr.manage")
    assert qms.check_perm("qa_engineer", "ncr.manage")


def test_types_and_severities():
    assert set(qms.INS_TYPES) == {"IQC", "IPQC", "FQC", "OQC"}
    assert qms.SEV_WEIGHT["A"] > qms.SEV_WEIGHT["B"] > qms.SEV_WEIGHT["C"]
    assert len(qms.USERS_SEED) == 9
