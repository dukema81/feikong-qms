# -*- coding: utf-8 -*-
"""打部署包：feikong_app.tar.gz（backend/frontend/deploy/docs/demo/tests/scripts/tools + README）。"""
import os
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = r"C:/Users/maxl/WorkBuddy/Claw/Temp/feikong_app.tar.gz"

INCLUDE = ["backend", "frontend", "deploy", "docs", "demo", "tests", "scripts", "tools",
           "README.md", ".gitignore"]
SKIP_DIRS = {"__pycache__", ".pytest_cache", "screenshots", "data"}
SKIP_EXT = {".pyc", ".db", ".db-wal", ".db-shm", ".tar.gz"}


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    n = 0
    with tarfile.open(OUT, "w:gz") as z:
        for item in INCLUDE:
            full = os.path.join(ROOT, item)
            if os.path.isfile(full):
                z.add(full, item)
                n += 1
                continue
            for dirpath, dirnames, filenames in os.walk(full):
                dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
                for fn in filenames:
                    if os.path.splitext(fn)[1] in SKIP_EXT or fn == "server.log":
                        continue
                    p = os.path.join(dirpath, fn)
                    z.add(p, os.path.relpath(p, ROOT))
                    n += 1
    print("部署包：%s（%.1f KB，%d 个文件）" % (OUT, os.path.getsize(OUT) / 1024.0, n))


if __name__ == "__main__":
    main()
