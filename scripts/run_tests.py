# -*- coding: utf-8 -*-
"""飞控QMS · 三层测试门禁：单元 → 接口 → 端到端。--fast 跳过浏览器层。"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def run(args, title):
    print("=" * 62)
    print("◆ " + title)
    print("=" * 62)
    r = subprocess.run([sys.executable, "-m", "pytest"] + args + ["-q"], cwd=HERE)
    return r.returncode == 0


def main():
    fast = "--fast" in sys.argv
    ok = True
    ok &= run([os.path.join("tests", "test_unit_core.py")], "① 单元测试 · 业务内核（qms.py 纯函数）")
    ok &= run([os.path.join("tests", "test_api.py")], "② 接口测试 · REST 全链路（独立临时库）")
    if not fast:
        ok &= run([os.path.join("tests", "test_e2e_ui.py")], "③ 端到端 · 浏览器 17 页")
    print("=" * 62)
    print("✓ 门禁通过" if ok else "✗ 门禁未通过")
    print("=" * 62)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
