#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""冷/热两态对照：量化「模型装载」在每镜耗时里占多少。

做法：prompt 末尾加一个空格强制重算（避免 ComfyUI 节点缓存命中）。
  冷 = 刚 /free 清空显存后第一跑
  热 = 紧接着再跑（模型仍在显存）

产出全部写到 MiniMaxH3/_bench/，不碰任何正式产物。
"""
import json, re, subprocess, time, urllib.request

PY     = "/workspace/venv/bin/python"
RUNNER = "/workspace/h3scripts/80_run_workflow_remote.py"
API    = "http://127.0.0.1:8188"
WORK   = "/workspace/films/thirty_eight_eight"
W1     = "/workspace/ComfyUI/custom_nodes/comfyui-minimax-h3-audio-T8/examples/workflows/01-basic-generation/2026-08-06_H3_Turbo_Stable_4V4A.json"
W2     = WORK + "/workflows/stage2_vaedecode.json"
UNET   = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
LORA   = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
CLIP   = "minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
SEED   = 20260918

man  = json.load(open(WORK + "/manifest.json", encoding="utf-8"))
shot = man["shots"][0]
base = shot["prompt"]
FILE = shot["file"]


def free_vram():
    req = urllib.request.Request(API + "/free",
                                 data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=60).read()
    time.sleep(5)


def run(wf, sets, label):
    cmd = [PY, RUNNER, wf]
    for k, v in sets:
        cmd += ["--set", "%s=%s" % (k, v)]
    t0  = time.time()
    p   = subprocess.run(cmd, capture_output=True, text=True, cwd="/workspace/ComfyUI")
    el  = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    m   = re.search(r"用时\s*([\d.]+)s", out)
    v   = re.search(r"峰值显存\s*([\d.]+)", out)
    print("%-22s 内部 %7s s | 墙钟 %6.1f s | 峰值显存 %s GiB"
          % (label, m.group(1) if m else "?", el, v.group(1) if v else "?"), flush=True)
    return float(m.group(1)) if m else el


draft_sets = lambda p, tag: [
    ("1.unet_name", UNET), ("2.lora_name", LORA), ("3.clip_name", CLIP),
    ("6.prompt", p), ("6.width", 672), ("6.height", 384),
    ("6.length", 362), ("6.task_type", "T2VA"), ("9.noise_seed", SEED),
    ("12.filename_prefix", "MiniMaxH3/_bench/%s" % tag),
]
refine_sets = lambda p, tag: [
    ("1.file", "draft_%s.mp4" % FILE),
    ("3.target_width", 1344), ("3.target_height", 768),
    ("12.text", p), ("20.filename_prefix", "MiniMaxH3/_bench/%s" % tag),
]

print("=== 冷/热对照 · shot01 ===\n", flush=True)

print("[1/4] 清空显存 → 草稿冷跑", flush=True)
free_vram()
d_cold = run(W1, draft_sets(base, "d_cold"), "草稿·冷")

print("[2/4] 直接再跑草稿（模型驻留）", flush=True)
d_hot = run(W1, draft_sets(base + " ", "d_hot"), "草稿·热")

print("[3/4] 换成精修（须装载 LTX 模型）", flush=True)
r_cold = run(W2, refine_sets(base, "r_cold"), "精修·冷")

print("[4/4] 直接再跑精修（模型驻留）", flush=True)
r_hot = run(W2, refine_sets(base + " ", "r_hot"), "精修·热")

print("\n=== 装载开销 ===", flush=True)
print("草稿  冷 %.1f  热 %.1f  →  装载 %.1f s" % (d_cold, d_hot, d_cold - d_hot), flush=True)
print("精修  冷 %.1f  热 %.1f  →  装载 %.1f s" % (r_cold, r_hot, r_cold - r_hot), flush=True)
print("单镜合计装载 %.1f s ／ 8 镜 %.1f min" % ((d_cold - d_hot) + (r_cold - r_hot),
      ((d_cold - d_hot) + (r_cold - r_hot)) * 8 / 60), flush=True)
