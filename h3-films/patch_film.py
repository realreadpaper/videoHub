#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在远端为一部新片建立工程目录。

以 /workspace/films/laozi_buqule 为模板，改掉 4 处硬编码后落到新 slug 目录：
  1. FILM 名             -> slug
  2. SEED                -> 新 seed
  3. stage1 分辨率 672x384      -> 384x672   （竖版）
  4. stage2 分辨率 1344x768     -> 768x1344  （竖版）
另改 concat 输出名与运行标题。H3_LENGTH 保持 362（24fps 栅格已验证，30fps 本地转）。

用法： python3 patch_film.py <slug> <seed> <标题> <输出文件名>
"""
import os
import re
import shutil
import sys

SRC = "/workspace/films/laozi_buqule"
ROOT = "/workspace/films"


def patch(slug, seed, title, outname):
    src_py = os.path.join(SRC, "10_run_film.py")
    if not os.path.exists(src_py):
        print("FAIL: 模板不存在 %s" % src_py)
        return False
    dst_dir = os.path.join(ROOT, slug)
    os.makedirs(dst_dir, exist_ok=True)
    dst_py = os.path.join(dst_dir, "10_run_film.py")

    t = open(src_py, encoding="utf-8").read()
    checks = []

    t2 = re.sub(r'^FILM\s*=\s*"[^"]*"', 'FILM       = "%s"' % slug, t, count=1, flags=re.M)
    checks.append(("FILM", t2 != t)); t = t2

    t2 = re.sub(r'^SEED\s*=\s*\d+', 'SEED = %d' % seed, t, count=1, flags=re.M)
    checks.append(("SEED", t2 != t)); t = t2

    t2 = t.replace('("6.width", 672), ("6.height", 384)',
                   '("6.width", 384), ("6.height", 672)')
    checks.append(("stage1 竖版", t2 != t)); t = t2

    t2 = t.replace('("3.target_width", 1344), ("3.target_height", 768)',
                   '("3.target_width", 768), ("3.target_height", 1344)')
    checks.append(("stage2 竖版", t2 != t)); t = t2

    t2 = t.replace('老子不娶了_全片.mp4', outname)
    checks.append(("concat 输出名", t2 != t)); t = t2

    t2 = t.replace('《老子不娶了》批量生产', title)
    checks.append(("运行标题", t2 != t)); t = t2

    open(dst_py, "w", encoding="utf-8").write(t)

    wsrc = os.path.join(SRC, "workflows")
    wdst = os.path.join(dst_dir, "workflows")
    if os.path.isdir(wsrc) and not os.path.isdir(wdst):
        shutil.copytree(wsrc, wdst)
        checks.append(("workflows 复制", True))

    print("--- %s ---" % slug)
    bad = 0
    for name, okk in checks:
        print("  %s %s" % ("OK  " if okk else "MISS", name))
        if not okk:
            bad += 1
    for key in ["6.width", "3.target_width", "H3_LENGTH = 362"]:
        hit = [ln.strip() for ln in t.splitlines() if key in ln]
        if hit:
            print("    %s" % hit[0][:110])
    return bad == 0


if __name__ == "__main__":
    import json
    spec_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/h3dep/spec.json"
    if os.path.exists(spec_path):
        specs = json.load(open(spec_path, encoding="utf-8"))
        allok = True
        for sp in specs:
            allok = patch(sp["slug"], sp["seed"], sp["title"], sp["outname"]) and allok
        sys.exit(0 if allok else 2)
    if len(sys.argv) < 5:
        print(__doc__)
        sys.exit(1)
    okk = patch(sys.argv[1], int(sys.argv[2]), sys.argv[3], sys.argv[4])
    sys.exit(0 if okk else 2)
