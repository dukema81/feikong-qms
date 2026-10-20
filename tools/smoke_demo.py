# -*- coding: utf-8 -*-
"""飞控QMS · 离线 DEMO 冒烟：file:// 打开单文件，验证页面渲染与内存写操作。"""
import os
import sys

from playwright.sync_api import sync_playwright

DEMO = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "demo", "feikong-qms-demo.html")

PAGES = ["dashboard", "iqc", "ipqc", "fqc", "ncr", "capa", "plans", "defects",
         "spc", "analysis", "supplier", "coq", "qdocs", "reports", "integration",
         "settings", "logs"]


def launch(pw):
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return pw.chromium.launch(**kw)
        except Exception:                                     # noqa: BLE001
            continue
    raise RuntimeError("无可用浏览器")


def main():
    url = "file:///" + DEMO.replace("\\", "/")
    fails = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page._errors = []
        page.on("pageerror", lambda e: page._errors.append(str(e)))
        page.on("console", lambda m: page._errors.append(m.text)
                if m.type == "error" else None)

        page.goto(url)
        page.wait_for_timeout(1500)
        if "质量驾驶舱" not in page.inner_text("body"):
            fails.append("登录/驾驶舱加载失败")
        print("DEMO 打开 OK")

        for name in PAGES:
            page._errors.clear()
            page.evaluate("location.hash = '#%s'" % name)
            page.wait_for_timeout(700)
            text = page.inner_text("#view")
            if len(text) < 20 or page._errors:
                fails.append("%s: %s" % (name, page._errors[:1]))
                print("%-12s FAIL %s" % (name, page._errors[:1]))
            else:
                print("%-12s ok  chars=%d" % (name, len(text)))

        # 写操作 1：新建检验单（IQC）
        page.evaluate("location.hash = '#iqc'")
        page.wait_for_timeout(700)
        page.click("#newIns")
        page.select_option("#niMat", "MAT001")
        page.fill("#niBatch", "LOT-DEMO-1")
        page.fill("#niLot", "3200")
        page.click("#niOk")
        page.wait_for_timeout(800)
        page.evaluate("location.hash = '#dashboard'")       # 同 hash 不重渲染，先跳走
        page.wait_for_timeout(500)
        page.evaluate("location.hash = '#iqc'")
        page.wait_for_timeout(800)
        if "IQ2610-90" not in page.inner_text("#view"):
            fails.append("新建检验单未生效")
        else:
            print("写操作① 新建检验单 ok")

        # 写操作 2：开立 NCR
        page.evaluate("location.hash = '#ncr'")
        page.wait_for_timeout(700)
        page.click("#nNew")
        page.fill("#nnMat", "MAT007")
        page.fill("#nnBad", "3")
        page.click("#nnOk")
        page.wait_for_timeout(800)
        if "待评审" not in page.inner_text("#view"):
            fails.append("开立 NCR 未生效")
        else:
            print("写操作② 开立NCR ok")

        # 写操作 3：生成 API Key
        page.evaluate("location.hash = '#integration'")
        page.wait_for_timeout(800)
        page.click("#ikNew")
        page.fill("#ikName", "demo-erp")
        page.click("#ikOk")
        page.wait_for_timeout(600)
        if "fck_demo" not in page.inner_text("#dialog"):
            fails.append("API Key 生成未生效")
        else:
            print("写操作③ API Key ok")
        page.evaluate("F.closeDialog && F.closeDialog()")

        browser.close()

    print("=" * 56)
    if fails:
        print("DEMO 冒烟失败：%s" % fails)
        sys.exit(1)
    print("DEMO 冒烟全部通过：%d 页渲染 + 3 类写操作" % len(PAGES))


if __name__ == "__main__":
    main()
