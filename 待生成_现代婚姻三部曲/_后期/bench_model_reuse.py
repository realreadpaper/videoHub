#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""连续两次精修，验证「模型装载开销」是否是每镜重复支付的固定成本。

若第 2 次显著快于第 1 次 → 模型装载是每镜固定开销，合并阶段可省。
输出到 MiniMaxH3/_bench/，不碰任何正式产物。
"""
import json, re, subprocess, time

PY     = "/workspace/venv/bin/python"
RUNNER = "/workspace/h3scripts/80_run_workflow_remote.py"
W      = "/workspace/films/thirty_eight_eight/workflows/stage2_vaedecode.json"
MAN    = "/workspace/films/thirty_eight_eight/manifest.json"

man  = json.load(open(MAN, encoding="utf-8"))
shot = man["shots"][0]
print("bench shot: %s" % shot["file"], flush=True)

for i in (1, 2):
    cmd = [PY, RUNNER, W,
           "--set", "1.file=draft_%s.mp4" % shot["file"],
           "--set", "3.target_width=1344",
           "--set", "3.target_height=768",
           "--set", "12.text=%s" % shot["prompt"],
           "--set", "20.filename_prefix=MiniMaxH3/_bench/pass%d" % i]
    t0  = time.time()
    p   = subprocess.run(cmd, capture_output=True, text=True, cwd="/workspace/ComfyUI")
    el  = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    m   = re.search(r"用时\s*([\d.]+)s", out)
    v   = re.search(r"峰值显存\s*([\d.]+)", out)
    print("PASS%d  内部计时 %s s | 墙钟 %.1f s | 峰值显存 %s GiB"
          % (i, m.group(1) if m else "?", el, v.group(1) if v else "?"), flush=True)
