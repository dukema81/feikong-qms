# -*- coding: utf-8 -*-
"""飞控QMS · UI 巡检：Playwright 登录后逐页校验渲染与控制台错误。"""
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("FC_BASE", "http://127.0.0.1:8024")
USER = os.environ.get("FC_USER", "admin")
PWD = os.environ.get("FC_PWD", "qms@2026")

PAGES = ["dashboard", "iqc", "ipqc", "fqc", "ncr", "capa", "plans", "defects",
         "spc", "analysis", "supplier", "coq", "qdocs", "reports", "integration",
         "settings", "logs"]

SHOT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "reports", "screenshots")


def launch(p):
    for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
        try:
            return p.chromium.launch(**kw)
        except Exception:                                     # noqa: BLE001
            continue
    raise RuntimeError("无可用的 Chromium/Edge/Chrome")


def main():
    os.makedirs(SHOT_DIR, exist_ok=True)
    failures = []
    with sync_playwright() as pw:
        browser = launch(pw)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append("pageerror: %s" % e))
        page.on("console", lambda m: errors.append("console: %s" % m.text)
                if m.type == "error" else None)

        page.goto(BASE + "/login.html")
        page.fill("#u", USER)
        page.fill("#p", PWD)
        page.click("#btn")
        page.wait_for_url("**/index.html", timeout=8000)
        page.wait_for_timeout(1200)
        print("登录 OK：%s" % page.title())

        for name in PAGES:
            errors.clear()
            page.evaluate("location.hash = '#%s'" % name)
            page.wait_for_timeout(900)
            content = page.content()
            ok_len = len(page.inner_text("#view")) >= 20
            if not ok_len or errors:
                failures.append((name, len(content), errors[:2]))
                print("%-12s FAIL  len=%d %s" % (name, len(content), errors[:1]))
            else:
                page.screenshot(path=os.path.join(SHOT_DIR, "ui_%s.png" % name))
                print("%-12s ok    chars=%d" % (name, len(page.inner_text("#view"))))
        browser.close()
    if failures:
        print("UI 巡检失败：%s" % failures)
        sys.exit(1)
    print("UI 巡检全部通过：%d 页" % len(PAGES))


if __name__ == "__main__":
    main()
