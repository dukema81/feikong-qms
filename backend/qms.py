# -*- coding: utf-8 -*-
"""飞控QMS系统 · 业务内核（纯函数，无 I/O）。

包含：AQL 抽样（ISO 2859-1 正常检验一次抽样主表）、检验单/NCR/CAPA 三套状态机与闸口、
SPC 控制限与 Cp/Cpk、帕累托与 FPY/PPM 口径、供应商综合评分、8D 七步闸口、权限矩阵。
"""
from datetime import datetime, timedelta

VERSION = "1.0.0"
BRAND = "飞控QMS系统"

# ---------------------------------------------------------------- 状态机
INS_STATES = ["待检验", "检验中", "待判定", "已判定", "已放行", "已关闭", "已取消"]
NCR_STATES = ["待评审", "已评审", "处置中", "待验证", "已关闭"]
CAPA_STEPS = ["D1", "D2", "D3", "D4", "D5", "D6", "D7", "D8"]
CAPA_STEP_NAMES = {
    "D1": "组建小组", "D2": "问题描述", "D3": "围堵措施", "D4": "根因分析",
    "D5": "纠正措施", "D6": "实施验证", "D7": "预防再发", "D8": "总结关闭"}
INS_TYPES = {"IQC": "来料检验", "IPQC": "过程检验", "FQC": "成品检验", "OQC": "出货检验"}
SEVERITIES = ["A", "B", "C"]
SEV_WEIGHT = {"A": 10, "B": 5, "C": 1}
SEV_CN = {"A": "致命", "B": "严重", "C": "轻微"}
VERDICTS = ["合格", "不合格"]
DISPOSITIONS = ["返工", "返修", "让步接收", "报废", "退货", "挑选使用"]

INS_ARROWS = {("待检验", "检验中"): "开始检验",
              ("检验中", "待判定"): "提交判定",
              ("待判定", "已判定"): "判定",
              ("已判定", "已放行"): "放行",
              ("已判定", "已关闭"): "关闭（不合格转NCR）",
              ("已放行", "已关闭"): "关闭"}


def can_move(cur, target, arrows):
    return (cur, target) in arrows


def ins_gate(target, ctx):
    """检验单推进闸口：返回 (ok, msg)。"""
    if target == "检验中":
        if ctx.get("lotSize", 0) <= 0:
            return False, "批量不能为空"
        return True, ""
    if target == "待判定":
        items = ctx.get("items") or []
        if not items:
            return False, "检验方案未载入检验项目"
        rec = [i for i in items if (i.get("result") or "") not in ("", None)]
        if len(rec) < len(items):
            return False, "尚有 %d 项检验项目未录入结果" % (len(items) - len(rec))
        bad = sum(int(i.get("badQty") or 0) for i in items)
        if bad > 0 and not (ctx.get("badDesc") or ctx.get("defectCodes")):
            return False, "存在不良数但未登记缺陷代码"
        return True, ""
    if target == "已判定":
        verdict = ctx.get("verdict") or ""
        if verdict not in VERDICTS:
            return False, "判定结论必须为「合格」或「不合格」"
        if verdict == "合格" and (ctx.get("criticalBad") or 0) > 0 and ctx.get("criticalBlock"):
            return False, "存在致命缺陷（A类），不允许判定合格"
        if verdict == "合格" and not ctx.get("judgedBy"):
            return False, "合格判定须由授权检验员签署"
        if verdict == "不合格" and (ctx.get("badQty", 0) or 0) <= 0:
            return False, "判定不合格但未录入不良数"
        return True, ""
    if target == "已放行":
        if ctx.get("verdict") != "合格":
            return False, "仅合格单可放行"
        if not ctx.get("disposition") and ctx.get("concession"):
            return False, "让步接收须填写处置说明"
        return True, ""
    if target == "已关闭":
        if ctx.get("verdict") == "不合格" and not (ctx.get("ncrNo") or ctx.get("closed")):
            return False, "不合格单须已生成 NCR 方可关闭"
        return True, ""
    return True, ""


NCR_ARROWS = {("待评审", "已评审"): "评审",
              ("已评审", "处置中"): "下达处置",
              ("处置中", "待验证"): "处置完成",
              ("待验证", "已关闭"): "验证关闭"}


def ncr_gate(target, ctx):
    if target == "已评审":
        if not ctx.get("review"):
            return False, "评审意见必填"
        if not ctx.get("disposition") and ctx.get("needDisposition"):
            return False, "须评审处置方式（返工/让步/报废/退货）"
        if ctx.get("disposition") == "让步接收":
            rate = (ctx.get("badQty") or 0) / max(1, (ctx.get("qty") or 1))
            if rate > ctx.get("concessionMax", 0.03):
                return False, "让步接收不良率 %.2f%% 超上限 %.2f%%" % (rate * 100, ctx.get("concessionMax", 0.03) * 100)
        return True, ""
    if target == "处置中":
        if not ctx.get("owner"):
            return False, "须指定处置责任人"
        if not ctx.get("due"):
            return False, "须明确处置时限"
        return True, ""
    if target == "待验证":
        if not ctx.get("doneDesc"):
            return False, "处置完成须填写处置结果"
        return True, ""
    if target == "已关闭":
        if not ctx.get("verified"):
            return False, "关闭前须完成效果验证"
        if not ctx.get("verifier"):
            return False, "验证人必填"
        return True, ""
    return True, ""


def capa_gate(next_step, ctx):
    """8D 七步闸口（D1 组建 → D8 关闭）。"""
    if next_step == "D2" and not (ctx.get("leader") and ctx.get("members")):
        return False, "D1：须指定组长与成员"
    if next_step == "D3" and len(ctx.get("description") or "") < 20:
        return False, "D2：问题描述不少于 20 字（5W2H）"
    if next_step == "D4" and not (ctx.get("containment") or ctx.get("actions")):
        return False, "D3：围堵措施必填"
    if next_step == "D5" and len(ctx.get("rootCause") or "") < 10:
        return False, "D4：根因分析不少于 10 字（5Why）"
    if next_step == "D6" and not (ctx.get("tasks") or ctx.get("actions")):
        return False, "D5：纠正措施或任务清单必填"
    if next_step == "D7" and not ctx.get("effect"):
        return False, "D6：实施效果验证必填"
    if next_step == "D8" and not ctx.get("prevention"):
        return False, "D7：预防再发措施必填"
    return True, ""


def capa_next(step):
    i = CAPA_STEPS.index(step) if step in CAPA_STEPS else -1
    return CAPA_STEPS[min(i + 1, 7)]


# ---------------------------------------------------------------- AQL 抽样
# ISO 2859-1 批量 → 样本量字码（一般检验水平 II）
def sample_code(lot_size, level="II"):
    n = int(lot_size or 0)
    if n <= 2:
        code = "A"
    elif n <= 8:
        code = "B"
    elif n <= 15:
        code = "C"
    elif n <= 25:
        code = "D"
    elif n <= 50:
        code = "E"
    elif n <= 90:
        code = "F"
    elif n <= 150:
        code = "G"
    elif n <= 280:
        code = "H"
    elif n <= 500:
        code = "J"
    elif n <= 1200:
        code = "K"
    elif n <= 3200:
        code = "L"
    elif n <= 10000:
        code = "M"
    elif n <= 35000:
        code = "N"
    elif n <= 150000:
        code = "P"
    elif n <= 500000:
        code = "Q"
    else:
        code = "R"
    if level == "I":
        order = "ABCDEFGHIJKLMNOPQR"
        code = order[max(0, order.index(code) - 2)]
    elif level == "III":
        order = "ABCDEFGHIJKLMNOPQR"
        code = order[min(15, order.index(code) + 2)]
    return code


# 样本量字码 → (样本量, {(AQL等级): (Ac, Re)})
SAMPLE_TABLE = {
    "A": (2, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "B": (3, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "C": (5, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "D": (8, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "E": (13, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "F": (20, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "G": (32, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "H": (50, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "J": (80, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "K": (125, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "L": (200, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "M": (315, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "N": (500, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "P": (800, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "Q": (1250, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
    "R": (2000, {"0.065": (0, 1), "0.25": (0, 1), "1.0": (0, 1)}),
}


def aql_plan(lot_size, aql="1.0", level="II"):
    """返回 {code, sampleSize, ac, re}。单件缺陷按致命 Ac=0。"""
    code = sample_code(lot_size, level)
    size, _ = SAMPLE_TABLE.get(code, (13, {}))
    # 简化主表：按 AQL 等级给出 Ac（正常检验一次抽样近似）
    try:
        aql_f = float(aql)
    except (TypeError, ValueError):
        aql_f = 1.0
    if aql_f <= 0.065:
        ac_table = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2]
    elif aql_f <= 0.10:
        ac_table = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 3]
    elif aql_f <= 0.25:
        ac_table = [0, 0, 0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 5, 7, 10]
    elif aql_f <= 0.40:
        ac_table = [0, 0, 0, 0, 0, 0, 1, 1, 1, 2, 3, 5, 7, 10, 14, 21]
    elif aql_f <= 0.65:
        ac_table = [0, 0, 0, 0, 1, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21]
    elif aql_f <= 1.0:
        ac_table = [0, 0, 0, 1, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21]
    elif aql_f <= 1.5:
        ac_table = [0, 0, 1, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21]
    elif aql_f <= 2.5:
        ac_table = [0, 1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21, 21, 21]
    else:
        ac_table = [1, 1, 2, 3, 5, 7, 10, 14, 21, 21, 21, 21, 21, 21, 21, 21]
    order = "ABCDEFGHIJKLMNOPQR"
    idx = order.index(code) if code in order else 7
    ac = ac_table[min(idx, 15)]
    # 致命缺陷（A类）恒 Ac=0
    return {"code": code, "sampleSize": size, "ac": ac, "re": ac + 1,
            "criticalAc": 0, "criticalRe": 1}


def verdict_by_aql(defects, plan):
    """按抽样方案给出初判：累计不良 > Ac 判不合格。"""
    total = defects.get("A", 0) + defects.get("B", 0) + defects.get("C", 0)
    if defects.get("A", 0) > plan.get("criticalAc", 0):
        return "不合格", "致命缺陷 %d 件" % defects.get("A", 0)
    bad = defects.get("B", 0) + defects.get("C", 0) * 0.5  # 轻微按 0.5 折算
    if bad > plan.get("ac", 0):
        return "不合格", "累计不良 %d 超出 Ac=%d" % (int(bad), plan.get("ac", 0))
    return "合格", "累计不良 %d 未超出 Ac=%d" % (int(bad), plan.get("ac", 0))


# ---------------------------------------------------------------- SPC
def spc_limits(values):
    """x̄-R 控制图限：values 为分组均值列表时按组计算，此处对原始值按 5 一组。"""
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2:
        return {"n": len(vs), "cl": vs[0] if vs else 0, "ucl": 0, "lcl": 0, "outliers": []}
    groups = [vs[i:i + 5] for i in range(0, len(vs), 5)]
    xbars = [sum(g) / len(g) for g in groups]
    rs = [max(g) - min(g) for g in groups]
    xbar = sum(xbars) / len(xbars)
    rbar = sum(rs) / len(rs) if rs else 0
    a2, d3, d4 = 0.577, 0.0, 2.114  # n=5 系数
    ucl, lcl = xbar + a2 * rbar, xbar - a2 * rbar
    outliers = [{"idx": i, "value": v}
                for i, v in enumerate(vs) if v > ucl or v < lcl]
    return {"n": len(vs), "cl": round(xbar, 6), "ucl": round(ucl, 6),
            "lcl": round(lcl, 6), "rBar": round(rbar, 6), "outliers": outliers,
            "xbars": [round(x, 6) for x in xbars]}


def cpk(usl, lsl, values):
    vs = [float(v) for v in values if v is not None]
    if len(vs) < 2 or usl is None or lsl is None or usl <= lsl:
        return {"cp": 0, "cpk": 0, "mean": 0, "std": 0, "grade": "数据不足"}
    n = len(vs)
    mean = sum(vs) / n
    var = sum((v - mean) ** 2 for v in vs) / (n - 1)
    std = var ** 0.5
    if std == 0:
        return {"cp": 0, "cpk": 0, "mean": round(mean, 6), "std": 0, "grade": "无变异"}
    cp = (usl - lsl) / (6 * std)
    cpu, cpl = (usl - mean) / (3 * std), (mean - lsl) / (3 * std)
    cpk = min(cpu, cpl)
    grade = "优" if cpk >= 1.67 else ("良" if cpk >= 1.33 else ("中" if cpk >= 1.0 else "差"))
    return {"cp": round(cp, 4), "cpk": round(cpk, 4), "mean": round(mean, 4),
            "std": round(std, 4), "cpu": round(cpu, 4), "cpl": round(cpl, 4),
            "grade": grade, "outSpec": sum(1 for v in vs if v > usl or v < lsl)}


# ---------------------------------------------------------------- 分析口径
def pareto(pairs):
    """pairs: [(name, count)] → 按次数降序 + 累计占比。"""
    items = sorted(pairs, key=lambda p: -p[1])
    total = sum(c for _, c in items) or 1
    cum = 0
    out = []
    for name, c in items:
        cum += c
        out.append({"name": name, "count": c, "pct": round(c / total * 100, 2),
                    "cumPct": round(cum / total * 100, 2)})
    return out


def fpy(stages):
    """stages: [(工序, 送检数, 合格数)] → 各站直通率与整机一次合格率。"""
    out, product = [], 1.0
    for name, total, ok in stages:
        rate = ok / total if total else 1.0
        product *= rate
        out.append({"stage": name, "total": total, "ok": ok,
                    "rty": round(rate * 100, 2)})
    return {"stages": out, "fpy": round(product * 100, 2)}


def ppm(inspected, defective):
    return round(defective * 1e6 / inspected, 1) if inspected else 0.0


def weighted_defects(critical, major, minor):
    """缺陷加权指数：A×10 + B×5 + C×1。"""
    return critical * SEV_WEIGHT["A"] + major * SEV_WEIGHT["B"] + minor * SEV_WEIGHT["C"]


def supplier_score(q, d, r):
    """质量50% 交付30% 响应20%，等级 A≥90 B≥80 C≥70 D<70。"""
    total = q * 0.5 + d * 0.3 + r * 0.2
    grade = "A" if total >= 90 else ("B" if total >= 80 else ("C" if total >= 70 else "D"))
    return {"q": round(q, 1), "d": round(d, 1), "r": round(r, 1),
            "total": round(total, 1), "grade": grade}


def irr(lots_accepted, lots_total):
    return round(lots_accepted / lots_total * 100, 2) if lots_total else 100.0


def coq_summary(rows):
    """rows: [(category, amount)] → 预防/鉴定/内损/外损 四类汇总与占比。"""
    keys = ["预防成本", "鉴定成本", "内部损失", "外部损失"]
    sums = {k: 0.0 for k in keys}
    for cat, amt in rows:
        if cat in sums:
            sums[cat] += float(amt or 0)
    total = sum(sums.values())
    out = [{"category": k, "amount": round(v, 2),
            "pct": round(v / total * 100, 1) if total else 0} for k, v in sums.items()]
    fail = sums["内部损失"] + sums["外部损失"]
    return {"items": out, "total": round(total, 2),
            "failRate": round(fail / total * 100, 1) if total else 0}


def due_check(due, today=None):
    today = today or datetime.now().strftime("%Y-%m-%d")
    if not due:
        return "未设时限"
    return "已逾期" if due < today else ("今日到期" if due == today else "正常")


# ---------------------------------------------------------------- 权限
PERMS = ["board.view", "iqc.do", "ipqc.do", "fqc.do", "ncr.manage", "capa.manage",
         "mdm.edit", "supplier.edit", "coq.edit", "integration.admin", "settings.admin"]

ROLES = ["admin", "quality_mgr", "qa_engineer", "inspector",
         "process_engineer", "purchaser", "supplier_qa", "viewer"]

PERM_MATRIX = {
    "admin":           ["board.view", "iqc.do", "ipqc.do", "fqc.do", "ncr.manage", "capa.manage",
                        "mdm.edit", "supplier.edit", "coq.edit", "integration.admin", "settings.admin"],
    "quality_mgr":     ["board.view", "iqc.do", "ipqc.do", "fqc.do", "ncr.manage", "capa.manage",
                        "supplier.edit", "coq.edit"],
    "qa_engineer":     ["board.view", "iqc.do", "ipqc.do", "fqc.do", "ncr.manage", "capa.manage"],
    "inspector":       ["board.view", "iqc.do", "ipqc.do", "fqc.do"],
    "process_engineer": ["board.view", "ipqc.do", "capa.manage"],
    "purchaser":       ["board.view", "supplier.edit"],
    "supplier_qa":     ["board.view", "iqc.do", "ncr.manage"],
    "viewer":          ["board.view"],
}


def perm_of(role):
    return PERM_MATRIX.get(role, [])


def check_perm(role, perm):
    return perm in perm_of(role)


USERS_SEED = [
    ("admin",   "系统管理员", "admin",     "质量管理部"),
    ("liming",  "李明",    "quality_mgr", "质量管理部"),
    ("wangfang", "王芳",   "qa_engineer", "质量管理部"),
    ("zhangqiang", "张强", "inspector",  "检验科"),
    ("liuyun",  "刘云",    "inspector",  "检验科"),
    ("chenjing", "陈静",  "process_engineer", "工艺部"),
    ("zhaoxin", "赵鑫",    "purchaser",  "采购部"),
    ("sunwei",  "孙伟",    "supplier_qa", "SQE组"),
    ("zhouyu",  "周宇",    "viewer",     "总经理办公室"),
]
