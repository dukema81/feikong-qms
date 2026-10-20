# -*- coding: utf-8 -*-
"""飞控QMS系统 · 确定性演示数据（8 供应商 / 16 物料 / 6 检验方案 / 18 缺陷代码 /
14 检验单 / 6 NCR / 4 CAPA / 12 SPC / 8 文件 / 供应商月度评分与质量成本）。"""
import hashlib
from datetime import datetime

from db import connect
import qms

PWD = hashlib.sha256("qms@2026".encode()).hexdigest()


def no_for(cn, prefix, table, n=4):
    row = cn.execute("SELECT val FROM seq WHERE name=?", (prefix,)).fetchone()
    nxt = (row["val"] + 1) if row else 1
    cn.execute("INSERT OR REPLACE INTO seq(name,val) VALUES(?,?)", (prefix, nxt))
    return "%s%s-%04d" % (prefix, datetime.now().strftime("%Y%m"), nxt if n == 4 else n)


def seed():
    cn = connect()
    if cn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"] > 0:
        cn.close()
        print("数据库已有数据，跳过种子")
        return
    today = datetime.now().strftime("%Y-%m-%d")
    now = lambda: datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # ---- 用户
    for username, name, role, dept in qms.USERS_SEED:
        cn.execute("INSERT INTO users(username,password,name,role,dept,created)"
                   " VALUES(?,?,?,?,?,?)", (username, PWD, name, role, dept, today))

    # ---- 供应商
    suppliers = [
        ("SUP001", "苏州精密五金有限公司", "五金冲压", "陈厂长", "13905120001", "A", 92.5),
        ("SUP002", "昆山华信电子科技", "电子元器件", "林经理", "13905120002", "A", 90.2),
        ("SUP003", "无锡恒达塑胶", "注塑成型", "黄总", "13905120003", "B", 83.4),
        ("SUP004", "上海祥泰紧固件", "标准件", "吴经理", "13905120004", "B", 79.8),
        ("SUP005", "宁波联信连接器", "连接器", "郑工", "13905120005", "B", 76.5),
        ("SUP006", "常州宏图钣金", "钣金加工", "冯厂长", "13905120006", "C", 68.2),
        ("SUP007", "东莞德昌线材", "线材", "何经理", "13905120007", "B", 81.0),
        ("SUP008", "杭州迅达传感器", "传感器", "潘工", "13905120008", "C", 65.7),
    ]
    for code, name, cat, contact, phone, grade, score in suppliers:
        cn.execute("INSERT INTO suppliers(code,name,category,contact,phone,grade,score)"
                   " VALUES(?,?,?,?,?,?,?)", (code, name, cat, contact, phone, grade, score))

    # ---- 物料
    materials = [
        ("MAT001", "精密齿轮", "POM ⌀24×0.5模", "件", "SUP001", 1, "齿形误差≤0.02mm"),
        ("MAT002", "铝合金外壳", "AL6061-T6 120×80×25", "件", "SUP006", 0, "外观A面无划伤"),
        ("MAT003", "主控芯片", "STM32F407VGT6", "片", "SUP002", 1, "MSL3 湿敏等级"),
        ("MAT004", "贴片电阻", "0402 10KΩ 1%", "片", "SUP002", 0, ""),
        ("MAT005", "电源适配器", "12V2A CCC", "个", "SUP005", 1, "耐压3000V"),
        ("MAT006", "M3×8 螺丝", "GB818 不锈钢", "件", "SUP004", 0, "盐雾48h"),
        ("MAT007", "注塑面板", "ABS 防火V0", "件", "SUP003", 0, "色差ΔE≤1.5"),
        ("MAT008", "连接器", "Type-C 16Pin", "个", "SUP005", 1, "插拔10000次"),
        ("MAT009", "钣金底座", "SPCC 1.2mm", "件", "SUP006", 0, ""),
        ("MAT010", "传感器探头", "NTC 10K B3950", "个", "SUP008", 1, "B值±1%"),
        ("MAT011", "线束总成", "UL2464 22AWG×8", "条", "SUP007", 0, "导通100%测试"),
        ("MAT012", "轴承", "608ZZ", "个", "SUP001", 1, "噪音Z4级"),
        ("MAT013", "散热片", "AL1070 40×40×11", "件", "SUP006", 0, ""),
        ("MAT014", "薄膜按键", "PC 0.125mm", "片", "SUP003", 0, "按键力180±30g"),
        ("MAT015", "排针", "2.54mm 2×10P", "个", "SUP005", 0, ""),
        ("MAT016", "包装纸箱", "K=K 五层", "个", "SUP004", 0, "边压≥6000N"),
    ]
    for code, name, spec, unit, sup, critical, kc in materials:
        cn.execute("INSERT INTO materials(code,name,spec,unit,supplier,critical,key_character)"
                   " VALUES(?,?,?,?,?,?,?)", (code, name, spec, unit, sup, critical, kc))

    # ---- 检验方案 + 项目
    plans = [
        ("QP001", "精密齿轮 IQC 方案", "MAT001", "IQC", "1.0", "II", [
            ("外观检查", "无裂纹/毛刺/缺齿", "目视 40W", "B"),
            ("齿形误差", "≤0.02mm", "齿轮测量中心", "A"),
            ("孔径", "⌀8.00 +0.015/0", "三坐标", "B"),
            ("硬度", "HRC 58-62", "洛氏硬度计", "B")]),
        ("QP002", "主控芯片 IQC 方案", "MAT003", "IQC", "0.25", "II", [
            ("MSL检查", "湿敏标签与干燥剂完好", "目视", "B"),
            ("外观", "引脚共面≤0.08mm 无氧化", "显微镜", "B"),
            ("丝印核对", "与BOM一致", "目视", "A")]),
        ("QP003", "注塑面板 IQC 方案", "MAT007", "IQC", "1.5", "II", [
            ("外观A面", "无划伤/流痕/缩水", "标准光源箱", "B"),
            ("色差", "ΔE≤1.5", "色差仪", "B"),
            ("尺寸", "图纸YF-2026-03", "卡尺", "C")]),
        ("QP004", "SMT 首件 IPQC 方案", "", "IPQC", "-", "-", [
            ("首件核对", "BOM位号/极性/方向", "目视+放大镜", "A"),
            ("锡膏印刷", "钢网张力≥35N 偏移≤10%", "锡膏测厚仪", "B"),
            ("炉温曲线", "峰值245±5℃ 液上时间60-90s", "炉温测试仪", "A")]),
        ("QP005", "整机 FQC 方案", "MAT005", "FQC", "0.65", "II", [
            ("外观", "A面无划伤 装配到位", "目视", "B"),
            ("功能测试", "老化2h 输出12V±0.2", "自动测试台", "A"),
            ("耐压测试", "3000VAC 5mA 60s 不击穿", "耐压测试仪", "A"),
            ("包装", "配件齐全 标签正确", "目视", "C")]),
        ("QP006", "出货 OQC 方案", "", "OQC", "0.4", "II", [
            ("抽样开箱", "包装完好 防静电袋密封", "目视", "B"),
            ("随机文件", "检验报告/合格证齐套", "目视", "B")]),
    ]
    for code, name, mat, itype, aql, il, items in plans:
        cn.execute("INSERT INTO plans(code,name,mat_code,itype,aql,il) VALUES(?,?,?,?,?,?)",
                   (code, name, mat, itype, aql, il))
        for i, (item, std, tool, sev) in enumerate(items, 1):
            cn.execute("INSERT INTO plan_items(plan_code,seq,item,standard,tool,severity)"
                       " VALUES(?,?,?,?,?,?)", (code, i, item, std, tool, sev))

    # ---- 缺陷代码
    defects = [
        ("DC001", "齿形超差", "尺寸", "A", "MAT001"), ("DC002", "孔径超上差", "尺寸", "B", "MAT001"),
        ("DC003", "崩齿", "外观", "A", "MAT001"), ("DC004", "毛刺", "外观", "C", "MAT001"),
        ("DC010", "引脚氧化", "外观", "B", "MAT003"), ("DC011", "丝印错版", "标识", "A", "MAT003"),
        ("DC012", "编带反折", "包装", "C", "MAT003"),
        ("DC020", "划伤A面", "外观", "B", "MAT002"), ("DC021", "色差超限", "外观", "B", "MAT007"),
        ("DC022", "流痕", "外观", "C", "MAT007"), ("DC023", "缩水", "成型", "B", "MAT007"),
        ("DC030", "虚焊", "焊接", "A", ""), ("DC031", "连锡短路", "焊接", "A", ""),
        ("DC032", "立碑", "焊接", "B", ""), ("DC033", "偏移", "贴装", "B", ""),
        ("DC040", "功能失效", "功能", "A", ""), ("DC041", "耐压击穿", "安全", "A", ""),
        ("DC042", "标签错误", "标识", "C", ""),
    ]
    for code, name, cat, sev, mat in defects:
        cn.execute("INSERT INTO defects(code,name,category,severity,mat_code)"
                   " VALUES(?,?,?,?,?)", (code, name, cat, sev, mat))

    # ---- 检验单（IQC/IPQC/FQC/OQC 混合多状态）
    inspections = [
        # (no, itype, mat_code, mat_name, supplier, order_no, process, batch, lot, status, result, A, B, C, inspector, judged_by, disposition, ncr)
        ("IQ2601-0001", "IQC", "MAT001", "精密齿轮", "SUP001", "PO-2601-0012", "", "LOT-A0112", 3200, "已关闭", "合格", 0, 1, 2, "zhangqiang", "wangfang", "", ""),
        ("IQ2601-0002", "IQC", "MAT001", "精密齿轮", "SUP001", "PO-2601-0031", "", "LOT-A0118", 5000, "已关闭", "不合格", 1, 3, 5, "liuyun", "wangfang", "退货", "NCR2601-0001"),
        ("IQ2601-0003", "IQC", "MAT003", "主控芯片", "SUP002", "PO-2601-0008", "", "LOT-B0205", 1600, "已关闭", "合格", 0, 0, 0, "zhangqiang", "wangfang", "", ""),
        ("IQ2601-0004", "IQC", "MAT007", "注塑面板", "SUP003", "PO-2601-0019", "", "LOT-C0301", 2800, "已判定", "不合格", 0, 8, 4, "liuyun", "liming", "", "NCR2601-0002"),
        ("IQ2601-0005", "IQC", "MAT006", "M3×8 螺丝", "SUP004", "PO-2601-0022", "", "LOT-D0402", 12000, "已放行", "合格", 0, 0, 1, "zhangqiang", "wangfang", "", ""),
        ("IQ2601-0006", "IQC", "MAT005", "电源适配器", "SUP005", "PO-2601-0025", "", "LOT-E0501", 2000, "待判定", "", 0, 0, 0, "liuyun", "", "", ""),
        ("IQ2601-0007", "IQC", "MAT008", "连接器", "SUP005", "PO-2601-0028", "", "LOT-F0601", 4000, "检验中", "", 0, 0, 0, "zhangqiang", "", "", ""),
        ("IQ2601-0008", "IQC", "MAT002", "铝合金外壳", "SUP006", "PO-2601-0030", "", "LOT-G0601", 1500, "待检验", "", 0, 0, 0, "", "", "", ""),
        ("IP2601-0001", "IPQC", "MAT005", "电源适配器", "", "MO-2601-0101", "SMT", "WO-101", 0, "已关闭", "合格", 0, 0, 0, "chenjing", "chenjing", "", ""),
        ("IP2601-0002", "IPQC", "MAT005", "电源适配器", "", "MO-2601-0101", "组装", "WO-101", 0, "检验中", "", 0, 0, 0, "liuyun", "", "", ""),
        ("IP2601-0003", "IPQC", "MAT005", "电源适配器", "", "MO-2601-0102", "组装", "WO-102", 0, "已判定", "不合格", 0, 2, 1, "liuyun", "liming", "", "NCR2601-0003"),
        ("FQ2601-0001", "FQC", "MAT005", "电源适配器", "", "MO-2601-0099", "", "FG-9901", 800, "已关闭", "合格", 0, 0, 1, "zhangqiang", "liming", "", ""),
        ("FQ2601-0002", "FQC", "MAT005", "电源适配器", "", "MO-2601-0100", "", "FG-9902", 1200, "待判定", "", 0, 0, 0, "liuyun", "", "", ""),
        ("OQ2601-0001", "OQC", "MAT005", "电源适配器", "", "SO-2601-0055", "", "SHIP-01", 2400, "待检验", "", 0, 0, 0, "", "", "", ""),
    ]
    for (ino, itype, mat, mname, sup, ono, proc, batch, lot, status,
         result, a, b, c, insp, judge, disp, ncr) in inspections:
        st_date = today if status in ("已判定", "已放行", "已关闭") else ""
        cn.execute("""INSERT INTO inspections(no,itype,mat_code,mat_name,supplier,order_no,
            process,batch_no,lot_size,status,inspector,started,result,
            critical_bad,major_bad,minor_bad,verdict,disposition,ncr_no,judged_by,
            finished,created,creator) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (ino, itype, mat, mname, sup, ono, proc, batch, lot, status, insp,
                    st_date, result, a, b, c, result, disp, ncr, judge,
                    st_date, "2026-01-%02d 09:%02d:00" % (7 + hash(ino) % 12, hash(ono) % 60), insp or "admin"))
        # 检验项目：按方案载入，关闭/放行/判定单全部录完
        plan_code = {"IQC": {"MAT001": "QP001", "MAT003": "QP002", "MAT007": "QP003",
                             "MAT006": "QP001", "MAT005": "QP002", "MAT008": "QP002",
                             "MAT002": "QP003"},
                     "IPQC": "QP004", "FQC": "QP005", "OQC": "QP006"}
        pc = plan_code[itype] if itype != "IQC" else plan_code["IQC"].get(mat, "QP001")
        rows = cn.execute("SELECT item,standard,tool,severity FROM plan_items"
                          " WHERE plan_code=? ORDER BY seq", (pc,)).fetchall()
        done = status in ("待判定", "已判定", "已放行", "已关闭")
        sev_dc = {"A": "DC001", "B": "DC002", "C": "DC004"}
        for i, r in enumerate(rows, 1):
            res, bq, dc = "", 0, ""
            if done:
                res = "OK"
                if (b > 0 or a > 0) and i == 2 and (a + b + c) > 0:
                    res, bq = "NG", min(b + a, lot // 100 + 1)
                    dc = sev_dc["A"] if a > 0 else "DC002"
                elif (a + b + c) > 0 and i == len(rows) and c > 0:
                    res, bq = "NG", c
                    dc = "DC004"
            cn.execute("INSERT INTO inspection_items(ins_no,seq,item,standard,tool,"
                       "severity,value_text,result,bad_qty,defect_code) VALUES(?,?,?,?,?,?,?,?,?,?)",
                       (ino, i, r["item"], r["standard"], r["tool"], r["severity"],
                        "实测OK" if res == "OK" else "", res, bq, dc))

    # ---- NCR
    ncrs = [
        ("NCR2601-0001", "IQ2601-0002", "MAT001", "LOT-A0118", 5000, 9, "A",
         "精密齿轮崩齿1件（致命），另齿形超差3件、毛刺5件，超出Ac判定不合格。", "已关闭",
         "整批退货，供应商索赔并要求8D报告", "sunwei", "2026-01-20", "验证有效，供应商已提交8D报告并完成整改", "liming", "2026-01-19"),
        ("NCR2601-0002", "IQ2601-0004", "MAT007", "LOT-C0301", 2800, 12, "B",
         "注塑面板色差ΔE=2.3超限8件、缩水4件，判定不合格。", "处置中",
         "挑选使用，良品先入库满足产线需求", "wangfang", today, "", "", ""),
        ("NCR2601-0003", "IP2601-0003", "MAT005", "WO-102", 500, 3, "B",
         "组装工序连续3件电源线压接不到位，存在虚接风险。", "待验证",
         "返工重压，调整压接机参数并首件确认", "chenjing", today, "返工完成，压力曲线复测合格", "", ""),
    ]
    for (nno, ino, mat, batch, qty, bad, sev, desc, status, review, owner,
         due, verified, verifier, closed) in ncrs:
        cn.execute("""INSERT INTO ncrs(no,ins_no,mat_code,batch_no,qty,bad_qty,severity,
            description,status,review,owner,due,verified,verifier,closed,created,creator)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (nno, ino, mat, batch, qty, bad, sev, desc, status, review, owner,
                    due, verified, verifier, closed, "2026-01-%02d 10:00:00" % (hash(nno) % 28 + 1), "wangfang"))

    # ---- CAPA（含一条推进到 D6 的完整 8D）
    capas = [
        ("CAPA2601-0001", "客户投诉", "", "客户端反馈适配器插头发热异常，涉及批次FG-98xx",
         "D6", "liming", "wangfang,chenjing,sunwei",
         "2025年12月起华南客户反馈充电发热，3起投诉集中在同一插头供应商批次",
         "插头接触电阻偏大：冲压模具磨损导致插针圆度超差（5Why至模具保养周期缺失）",
         "更换模具+插头全检+供应商过程巡检加频",
         "接触电阻复测全部<20mΩ，投诉清零", "客户投诉率<0.1%", "进行中", "2026-02-15"),
        ("CAPA2601-0002", "NCR", "NCR2601-0001", "齿轮供应商崩齿问题纠正预防",
         "D8", "wangfang", "sunwei", "SUP001精密齿轮崩齿，批次LOT-A0118致命缺陷",
         "齿轮运输磕碰：周转吸塑盘设计强度不足",
         "重新设计吸塑盘+运输振动测试+供方驻厂检验",
         "后续3批来料崩齿为零", "同类缺陷PPM<50", "已关闭", "2026-02-01",
         "预防措施纳入供应商质量协议", "2026-01-25"),
        ("CAPA2601-0003", "内审", "", "SMT车间锡膏冷藏管理不规范（内审发现项）",
         "D4", "chenjing", "wangfang", "内审发现锡膏回温记录缺失2次，存在批量虚焊风险",
         "回温记录由人工填写，无时间戳校验",
         "上线锡膏管理扫码系统", "", "", "进行中", "2026-02-28"),
        ("CAPA2601-0004", "数据分析", "", "虚焊不良率连续两周呈上升趋势（SPC触发）",
         "D2", "wangfang", "chenjing,liuyun", "炉后AOI虚焊率从0.3%升至0.8%",
         "", "", "", "", "进行中", "2026-02-10"),
    ]
    for row in capas:
        nno, source, ncr_ref, problem, step, leader, members, desc, rc, acts, effect, target, status, due = row[:14]
        closed = row[14] if len(row) > 14 else ""
        remark = row[15] if len(row) > 15 else ""
        cn.execute("""INSERT INTO capas(no,source,ncr_no,problem,step,leader,members,
            description,root_cause,actions,effect,target,status,due,created,creator,closed,remark)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                   (nno, source, ncr_ref, problem, step, leader, members, desc, rc, acts,
                    effect, target, status, due, "2026-01-%02d 14:00:00" % (hash(nno) % 28 + 1),
                    leader, closed, remark))

    # ---- 供应商月度评分（近3个月，相对当月）
    base = datetime.now().replace(day=1)
    months = []
    for k in (2, 1, 0):
        m = base.replace(month=base.month - k if base.month > k else base.month - k + 12,
                         year=base.year - (1 if base.month <= k else 0))
        months.append(m.strftime("%Y-%m"))
    for m in months:
        for code, name, cat, contact, phone, grade, score in suppliers:
            irr_v = 100.0 if grade == "A" else (93.0 if grade == "B" else 85.0)
            lots = 12 + hash((m, code)) % 20
            acc = int(lots * irr_v / 100)
            base_q = {"A": 95, "B": 85, "C": 74}[grade]
            base_d = {"A": 92, "B": 82, "C": 72}[grade]
            base_r = {"A": 90, "B": 80, "C": 70}[grade]
            j = hash((code, m)) % 5 - 2
            s = qms.supplier_score(base_q + j, base_d + j, base_r + j)
            cn.execute("""INSERT OR IGNORE INTO scorings(month,supplier,lots,accepted,irr,ppm,
                q_score,d_score,r_score,total,grade,created)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                       (m, code, lots, acc, irr_v, qms.ppm(lots * 300, max(0, lots - acc) * 8),
                        s["q"], s["d"], s["r"], s["total"], s["grade"], today))

    cur_month, prev_month, prev2_month = months[2], months[1], months[0]
    coq_rows = [
        (cur_month, "预防成本", "供应商质量培训", 18000), (cur_month, "预防成本", "检验设备校准", 12000),
        (cur_month, "鉴定成本", "IQC/过程/成品检验人工", 96000), (cur_month, "鉴定成本", "可靠性试验", 30000),
        (cur_month, "内部损失", "返工工时", 46000), (cur_month, "内部损失", "报废损失", 28000),
        (cur_month, "内部损失", "停线损失", 15000), (cur_month, "外部损失", "客户投诉处理", 22000),
        (cur_month, "外部损失", "退货物流与赔偿", 18000),
        (prev_month, "预防成本", "体系审核", 25000), (prev_month, "鉴定成本", "检验人工", 90000),
        (prev_month, "内部损失", "返工工时", 52000), (prev_month, "外部损失", "客户赔偿", 30000),
    ]
    for m, cat, item, amt in coq_rows:
        cn.execute("INSERT INTO coq(month,category,item,amount,created,creator)"
                   " VALUES(?,?,?,?,?,?)", (m, cat, item, amt, today, "liming"))

    # ---- SPC 数据：组装工位锁螺丝扭矩（目标 4.5±0.5 N·m）
    import random
    rnd = random.Random(20260101)
    for g in range(1, 13):
        for k in range(5):
            v = round(4.5 + rnd.uniform(-0.18, 0.22), 2)
            cn.execute("""INSERT INTO spc_series(mat_code,process,char_name,usl,lsl,target,
                grp,value,operator,sample_time) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                       ("MAT005", "组装", "锁附扭矩", 5.0, 4.0, 4.5, g, v,
                        "liuyun", "2026-01-%02d %02d:%02d:00" % (g, 8 + k, 10 * k)))

    # ---- 质量文件
    qdocs = [
        ("QF-001", "IQC 来料检验规范", "SIP", "V2.1", "wangfang", "已发行"),
        ("QF-002", "IPQC 过程检验规范", "SIP", "V1.3", "chenjing", "已发行"),
        ("QF-003", "FQC 成品检验规范", "SIP", "V2.0", "liming", "已发行"),
        ("QF-004", "不合格品控制程序", "SOP", "V3.0", "liming", "已发行"),
        ("QF-005", "纠正预防措施管理程序", "SOP", "V2.2", "liming", "已发行"),
        ("QF-006", "供应商质量管理程序", "SOP", "V1.5", "sunwei", "已发行"),
        ("QF-007", "SPC 统计过程控制手册", "SIP", "V1.0", "chenjing", "编制中"),
        ("QF-008", "质量成本核算办法", "SOP", "V1.1", "liming", "已发行"),
    ]
    for code, name, cat, ver, owner, status in qdocs:
        cn.execute("INSERT INTO qdocs(code,name,category,version,owner,status,released,created)"
                   " VALUES(?,?,?,?,?,?,?,?)",
                   (code, name, cat, ver, owner, status, today if status == "已发行" else "", today))

    cn.commit()
    cn.close()
    print("飞控QMS 种子数据写入完成")


if __name__ == "__main__":
    import db
    db.init()
    seed()
