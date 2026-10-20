# -*- coding: utf-8 -*-
"""飞控QMS系统 · 文档批量上传知识库（分类 33 企业管理系统）

用法：
    python tools/kb_upload.py            # 仅上传（会与旧文档并存）
    python tools/kb_upload.py --replace  # 先删同名旧文档再上传（改版推荐）
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile

ROOT = r"C:/Users/maxl/WorkBuddy/Claw/feikong-qms"
BASE = "http://42.193.158.63"
CAT = 33
PASSWORD = "YCSpyVwt@J2UByom3#n6gb"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
TOKEN = None
REPLACE = "--replace" in sys.argv

DOCS = [
    ("docs/feikong-design.md", "飞控QMS系统建设方案",
     "「飞控QMS系统」完整建设方案 V1.0：建设背景与目标、四类检验（IQC/IPQC/FQC/OQC）业务蓝图、"
     "零依赖总体架构（标准库 http.server + sqlite3）、检验单七态状态机与六道闸口（致命缺陷一票否决）、"
     "NCR 五态闭环与 CAPA 8D 七步闸口、核心算法口径（ISO 2859-1 AQL 抽样、缺陷加权 10/5/1、"
     "SPC x̄-R 控制限与 Cp/Cpk、FPY 连乘、PPM、供应商评分 质量50+交付30+响应20、PAF 质量成本四类）、"
     "26 表数据模型、8 类角色 × 11 权限矩阵、12 条业务规则、"
     "三通道集成（API Key fck_ / Webhook HMAC 签名 15 事件 / 增量同步游标）、96 条 REST 路由总览、17 页前端设计、"
     "非功能设计（幂等、限流 240/min、连接兜底回收）、六阶段实施计划与验收标准。",
     "飞控QMS,企业管理系统,QMS,质量管理,IQC,IPQC,NCR,CAPA,8D,SPC,建设方案"),
    ("docs/feikong_design_v1.docx", "飞控QMS系统建设方案（docx 版）",
     "《飞控QMS系统建设方案》排版版本（Word V1.0，14 页），含封面、目录与全部 12 章内容。",
     "飞控QMS,企业管理系统,建设方案,docx"),
    ("docs/api.md", "飞控QMS系统 REST 接口契约",
     "96 条路由的完整契约：统一响应与状态码、多通道鉴权（会话令牌 5 种携带 / API Key fck_ read/write）、"
     "Idempotency-Key 幂等、限流 240 次每分钟、认证与驾驶舱 KPI、主数据（物料/供应商/检验方案/缺陷代码）、"
     "检验单（新建自动匹配方案与 AQL 抽样/开始/录入/判定/放行/关闭，不合格自动开 NCR）、"
     "NCR 五态推进、CAPA 8D 推进、供应商质量（评分/PPM）、SPC（控制图/Cpk/录点）、"
     "分析（帕累托/FPY/趋势）、质量成本 PAF 四类、质量文件、报表与 CSV 导出、设置与日志、"
     "集成中心（Key/Webhook/映射/反查/增量同步）、Webhook HMAC-SHA256 签名协议（15 种事件）与验签示例、"
     "对接实施建议五条。",
     "飞控QMS,API,接口契约,REST,Webhook,增量同步,对接"),
    ("docs/feikong_api_v1.docx", "飞控QMS系统 REST 接口契约（docx 版）",
     "《飞控QMS系统 REST 接口契约》排版版本（Word V1.0，17 页），面向对接方提供。",
     "飞控QMS,API,docx,对接"),
    ("docs/test-report.md", "飞控QMS系统测试报告",
     "三层自动化测试 72 项全部通过（业务内核单元 39 / REST 接口 24 / 端到端 UI 9），"
     "另有业务主线冒烟 41 检查点、UI 巡检 17 页与离线 DEMO 冒烟（17 页 + 3 类写操作）；质量门禁 PASS。"
     "含分层策略与测试环境、覆盖矩阵、关键验证点（三套状态机与闸口、AQL 抽样、致命一票否决、"
     "NCR 全链路与让步上限、CAPA 8D 七道闸口、SPC/Cpk、权限隔离、Key 鉴权、幂等、多通道令牌、CSV 导出）、"
     "8 项缺陷台账（现象/根因/修复，含连接泄漏兜底回收）、非功能验证、验收对照与复现命令。",
     "飞控QMS,测试报告,质量门禁,自动化测试,Playwright"),
    ("docs/feikong_test_v1.docx", "飞控QMS系统测试报告（docx 版）",
     "《飞控QMS系统测试报告》排版版本（Word V1.0，8 页），含封面、目录与完整测试结论（72 项 + 41 检查点）。",
     "飞控QMS,测试报告,docx"),
    ("docs/user-guide.md", "飞控QMS系统项目说明与操作手册",
     "面向岗位的操作手册：启动与环境变量、八账号登录、界面骨架、17 个页面逐页操作说明、"
     "四类角色场景演练（检验员一个上午 / 质量工程师判定与 NCR / SQE 供应商辅导 / 质量经理月度复盘）、"
     "离线 DEMO 使用、8 条常见问题（致命一票否决、让步上限、8D 闸口缺项、方案匹配、掉线兜底等）、"
     "运维指南（备份恢复、重置演示数据、健康检查、部署）。",
     "飞控QMS,操作手册,用户指南,QMS,质量管理"),
    ("docs/feikong_manual_v1.docx", "飞控QMS系统项目说明与操作手册（docx 版）",
     "《飞控QMS系统项目说明与操作手册》排版版本（Word V1.0，10 页）。",
     "飞控QMS,操作手册,docx"),
    ("demo/feikong-qms-demo.zip", "飞控QMS系统离线演示（DEMO）",
     "单文件离线演示：解压后双击 HTML 即可用浏览器打开，无需服务与网络。内置确定性演示数据"
     "（8 供应商 / 16 物料 / 6 检验方案 / 14 检验单 / 6 NCR / 4 CAPA / 60 SPC 测量点 / 供应商月度评分与质量成本），"
     "新建检验单（自动匹配方案并 AQL 抽样）、录入判定、NCR 评审处置闭环、CAPA 8D 推进、"
     "API Key 生成都在浏览器内存里按与后端一致的口径真实计算。",
     "飞控QMS,DEMO,离线演示,QMS,质量管理"),
]


def req(path, method="GET", body=None, token=None, ctype="application/json"):
    data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
    r = urllib.request.Request(BASE + path, data=data, method=method)
    r.add_header("Content-Type", ctype)
    if token:
        r.add_header("Authorization", "Bearer " + token)
    try:
        with OP.open(r, timeout=90) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}


def curl_upload(path, title, desc, tags):
    full = os.path.join(ROOT, path)
    mime = "application/zip" if full.endswith(".zip") else (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        if full.endswith(".docx") else "text/markdown")
    cmd = ["curl", "-s", "--noproxy", "*",
           "-H", "Authorization: Bearer " + TOKEN,
           "-F", "file=@%s;type=%s" % (full, mime),
           "-F", "title=" + title,
           "-F", "description=" + desc,
           "-F", "categoryId=%d" % CAT,
           "-F", "tags=" + tags,
           BASE + "/api/documents/upload"]
    out = subprocess.run(cmd, capture_output=True, timeout=300)
    try:
        return json.loads(out.stdout.decode("utf-8", "ignore"))
    except Exception:
        return {"code": -1, "raw": out.stdout.decode("utf-8", "ignore")[:400],
                "err": out.stderr.decode("utf-8", "ignore")[:200]}


def existing(cat=CAT):
    st, j = req("/api/documents?categoryId=%d&pageNum=1&pageSize=200" % cat, token=TOKEN)
    data = j.get("data") or {}
    if isinstance(data, list):
        return data
    return data.get("records") or data.get("list") or []


def delete_doc(doc_id):
    return req("/api/documents/%s" % doc_id, "DELETE", token=TOKEN)


def build_demo_zip():
    src = os.path.join(ROOT, "demo", "feikong-qms-demo.html")
    out = os.path.join(ROOT, "demo", "feikong-qms-demo.zip")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(src, "feikong-qms-demo.html")
        z.writestr("使用说明.txt",
                   "飞控QMS系统 · 离线演示\r\n"
                   "1. 解压后双击「feikong-qms-demo.html」，用浏览器打开即可，无需安装、无需联网。\r\n"
                   "2. 内置确定性演示数据：8 供应商 / 16 物料 / 6 检验方案 / 14 检验单 / 6 NCR / 4 CAPA /\r\n"
                   "   60 SPC 测量点 / 供应商月度评分与质量成本。\r\n"
                   "3. 新建检验单（自动匹配方案并 AQL 抽样）、录入判定、NCR 评审处置闭环、CAPA 8D 推进、\r\n"
                   "   API Key 生成，都在浏览器内存里按与后端一致的口径真实计算。\r\n"
                   "4. 账号：离线版固定以 admin（系统管理员）进入，便于一个人体验完整流程。\r\n"
                   "5. 完整版本（多账号 + 真实权限 + 落地数据）请部署 backend/server.py 后访问 http://127.0.0.1:8024/。\r\n")
    print("DEMO zip 重建：%.1f KB" % (os.path.getsize(out) / 1024.0))


def main():
    global TOKEN
    st, j = req("/api/auth/login", "POST", {"username": "admin", "password": PASSWORD})
    assert j.get("code") == 200, j
    TOKEN = j["data"]["token"]

    build_demo_zip()

    if REPLACE:
        want = {t for _, t, _, _ in DOCS}
        for r in existing():
            if r.get("title") in want:
                st, j = delete_doc(r.get("id"))
                print("删除旧文档 %s id=%s -> %s" % (r.get("title"), r.get("id"), st))
                time.sleep(0.4)

    results = []
    for path, title, desc, tags in DOCS:
        j = curl_upload(path, title, desc, tags)
        code = j.get("code")
        doc_id = (j.get("data") or {}).get("id") if isinstance(j.get("data"), dict) else j.get("data")
        size = os.path.getsize(os.path.join(ROOT, path))
        print("%-32s code=%s id=%s %.1fKB" % (os.path.basename(path), code, doc_id, size / 1024.0))
        if code != 200:
            print("   !!", str(j)[:300])
        results.append((path, title, code, doc_id))
        time.sleep(1.2)

    ok = [r for r in results if r[2] == 200]
    print("\n上传成功 %d / %d" % (len(ok), len(results)))
    os.makedirs(os.path.join(ROOT, "reports"), exist_ok=True)
    with open(os.path.join(ROOT, "reports", "kb_upload_result.json"), "w", encoding="utf-8") as f:
        json.dump([{"file": r[0], "title": r[1], "code": r[2], "id": r[3]} for r in results],
                  f, ensure_ascii=False, indent=2)
    st, j = req("/api/document-categories", token=TOKEN)
    for c in (j.get("data") or []):
        if isinstance(c, dict) and c.get("id") == CAT:
            print("cat%d docCount:" % CAT, c.get("docCount"))


if __name__ == "__main__":
    main()
