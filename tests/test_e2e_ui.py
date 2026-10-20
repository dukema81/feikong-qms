# -*- coding: utf-8 -*-
"""飞控QMS · 端到端 UI 测试（sync_playwright 直连，独立服务 8946 端口）"""
import os

import pytest
from playwright.sync_api import sync_playwright

BASE = os.environ.get("QMS_TEST_E2E_BASE") or "http://127.0.0.1:8946"
PWD = "qms@2026"

PAGES = ["dashboard", "iqc", "ipqc", "fqc", "ncr", "capa", "plans", "defects",
         "spc", "analysis", "supplier", "coq", "qdocs", "reports", "integration",
         "settings", "logs"]


@pytest.fixture(scope="module")
def page(e2e_base):
    with sync_playwright() as pw:
        browser = None
        for kw in ({}, {"channel": "msedge"}, {"channel": "chrome"}):
            try:
                browser = pw.chromium.launch(**kw)
                break
            except Exception:                                 # noqa: BLE001
                continue
        assert browser, "无可用浏览器"
        pg = browser.new_page(viewport={"width": 1440, "height": 900})
        pg._errors = []
        pg.on("pageerror", lambda e: pg._errors.append(str(e)))
        pg.on("console", lambda m: pg._errors.append(m.text) if m.type == "error" else None)
        pg.goto(BASE + "/login.html")
        pg.fill("#u", "admin")
        pg.fill("#p", PWD)
        pg.click("#btn")
        pg.wait_for_url("**/index.html", timeout=10000)
        pg.wait_for_timeout(1000)
        yield pg
        browser.close()


def _visit(page, route):
    page._errors.clear()
    page.evaluate("location.hash = '#%s'" % route)
    page.wait_for_timeout(800)


def test_17_pages_render(page):
    for route in PAGES:
        _visit(page, route)
        text = page.inner_text("#view")
        assert len(text) >= 20, "页面 %s 渲染内容过短" % route
        assert not page._errors, "页面 %s 有错误：%s" % (route, page._errors[:2])


def test_dashboard_kpis(page):
    _visit(page, "dashboard")
    page.wait_for_timeout(500)
    text = page.inner_text("#view")
    assert "检验单总数" in text and "批次合格率" in text.replace("\n", "")


def test_iqc_list_and_detail(page):
    _visit(page, "iqc")
    page.wait_for_selector("#view tbody tr", timeout=5000)
    rows = page.locator("#view tbody tr:not(.empty-row)")
    assert rows.count() >= 5
    rows.first.click()
    page.wait_for_selector("#mask.on", timeout=5000)
    dlg = page.inner_text("#dialog")
    assert "检验项目" in dlg or "抽样方案" in dlg
    page.click("[data-close-x]")


def test_ncr_page_shows_seed(page):
    _visit(page, "ncr")
    page.wait_for_timeout(500)
    text = page.inner_text("#view")
    assert "NCR" in text and "待评审" in text or "已关闭" in text


def test_capa_8d_progress(page):
    _visit(page, "capa")
    page.wait_for_timeout(500)
    text = page.inner_text("#view")
    assert "D6" in text or "D8" in text           # 种子里有推进到 D6/D8 的 CAPA


def test_spc_cpk(page):
    _visit(page, "spc")
    page.wait_for_timeout(600)
    text = page.inner_text("#view")
    assert "Cpk" in text and "过程能力" in text


def test_new_material_via_ui(page):
    _visit(page, "settings")
    page.wait_for_timeout(600)
    if page.locator("#uNew").count():
        page.click("#uNew")
        page.fill("#nuName", "e2euser")
        page.fill("#nuDisplay", "E2E 用户")
        page.click("#nuOk")
        page.wait_for_timeout(600)
        assert "e2euser" in page.inner_text("#view")


def test_integration_tabs(page):
    if page.locator("#mask.on").count():                 # 防御：关闭遗留弹层
        page.evaluate("F.closeDialog()")
        page.wait_for_timeout(300)
    _visit(page, "integration")
    page.wait_for_timeout(600)
    assert "API Key" in page.inner_text("#view")
    page.click('[data-tab="hooks"]')
    page.wait_for_timeout(500)
    assert "inspection.stage" in page.inner_text("#view")


def test_login_error_hint(page):
    """登录失败提示（复用共享浏览器开新页面，避免二次进入 sync API）。"""
    pg = page.context.browser.new_page()
    try:
        pg.goto(BASE + "/login.html")
        pg.fill("#u", "admin")
        pg.fill("#p", "wrong-password")
        pg.click("#btn")
        pg.wait_for_timeout(800)
        assert "错误" in pg.inner_text("#err") or "失败" in pg.inner_text("#err")
    finally:
        pg.close()
