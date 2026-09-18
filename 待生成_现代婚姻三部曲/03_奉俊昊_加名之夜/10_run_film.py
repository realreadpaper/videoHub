#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
《加名之夜》（奉俊昊风格）批量生产驱动 —— H3 两阶段管线 (单镜 15s = 362 帧)
  阶段1: MiniMax H3 T2VA 草稿 (672x384 x 362 帧 x 4 步, turbo LoRA)
  阶段2: LTX-2.5 精修 (target 1344x768 x 361 帧)

【A1 · 解码器修正】2026-09-15
  Stage2 官方工作流最后一步用 TAEHV（预览级微型解码器）出片，是当前画面偏软的
  头号原因 —— 完整 LTX VAE 明明已加载在工作流里，却只用于编码侧。本脚本默认
  改用 A1 补丁版工作流（标准 VAEDecode），详见下方 W_STAGE2 常量处的说明。

用法:
  python3 10_run_film.py --list
  python3 10_run_film.py --shots 6            # 只跑第 6 镜（草稿+精修）
  python3 10_run_film.py --shots 1-8          # 跑 1..8 镜
  python3 10_run_film.py --shots 1-8 --stage draft   # 只跑草稿
  python3 10_run_film.py --shots 1-8 --stage refine  # 只跑精修（草稿须已存在）
  python3 10_run_film.py --shots 1 --stage refine --keep-taehv
                                              # 强制官方 TAEHV 版，做 A/B 对照
  python3 10_run_film.py --concat             # 用已有精修片段合成全片
"""
import json, os, re, shutil, subprocess, sys, time, urllib.request

COMFY   = "/workspace/ComfyUI"
CN      = COMFY + "/custom_nodes/comfyui-minimax-h3-audio-T8/examples/workflows"
W_STAGE1 = CN + "/01-basic-generation/2026-08-06_H3_Turbo_Stable_4V4A.json"
# ---- Stage2 精修工作流 -----------------------------------------------------
# A1 改动（2026-09-15）：
#   官方工作流最后一步用 MiniMaxH3SolEngineTAEHVDecodeT8Advanced 解码。TAEHV 是
#   ComfyUI 里的「微型视频自编码器」，为快速预览设计，解码质量明显低于完整 VAE。
#   而完整 VAE（ltx-2.5-video-vae-conv-bf16）其实已经作为 VAELoader 加载在
#   工作流里了，却只被 VAEEncode 用于编码侧，解码侧根本没接 —— 等于 22B 模型
#   加 3 步精修辛苦算出来的 latent，在最后一步被一个预览级解码器糊掉了。
#
#   处置：_后期/patch_stage2_vaedecode.py 把解码节点换成标准 VAEDecode
#   （samples 沿用原 latent 连线，vae 接上已有的 VAELoader），输出
#   workflows/stage2_vaedecode.json。本脚本**优先用它**，找不到才回退官方原版。
#   加 --keep-taehv 可强制走官方原版（做 A/B 对照用）。
W_STAGE2_OFFICIAL = CN + "/22-sol-engine-h3-super/2026-08-29_H3_Sol_Engine_Super_Acceleration_LTX25_Advanced_EXP.json"
W_STAGE2 = W_STAGE2_OFFICIAL      # 运行时由 resolve_stage2_workflow() 决定
RUNNER   = "/workspace/h3scripts/80_run_workflow_remote.py"
PY       = "/workspace/venv/bin/python"
API      = "http://127.0.0.1:8188"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
W_STAGE2_PATCHED = os.path.join(SCRIPT_DIR, "workflows", "stage2_vaedecode.json")
MANIFEST   = os.path.join(SCRIPT_DIR, "manifest.json")
FILM       = "jiaming_zhiye"
OUTDIR     = COMFY + "/output/MiniMaxH3/" + FILM
INDIR      = COMFY + "/input"
WORK       = "/workspace/films/" + FILM
FINALDIR   = WORK + "/final"

UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
LORA = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
CLIP = "minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
SEED = 20260922
H3_LENGTH = 362  # 缺省值 15.042s @ 24fps (17n+5 网格)；逐镜以 manifest 里的 shot["h3_length"] 为准（10–15s 弹性排期，见 _后期/retime_shots.py）

C_OK, C_BAD, C_DIM, C_0 = "\033[32m", "\033[31m", "\033[2m", "\033[0m"
def ok(s):  print(C_OK  + "  ✔ " + C_0 + s, flush=True)
def bad(s): print(C_BAD + "  ✘ " + C_0 + s, flush=True)
def dim(s): print(C_DIM + "    "   + C_0 + s, flush=True)
def hdr(s): print("\n" + "═" * 96 + "\n  " + s + "\n" + "═" * 96, flush=True)


def resolve_stage2_workflow(force_official=False):
    """选定 Stage2 精修工作流，返回 (路径, 人类可读说明)。

    优先 A1 补丁版（完整 VAE 解码）；找不到就回退官方原版（TAEHV 解码）。
    生成补丁版：python3 _后期/patch_stage2_vaedecode.py --src <官方.json> \
                    --out 01_周星驰_三十八万八/workflows/stage2_vaedecode.json
    """
    has_patched = os.path.exists(W_STAGE2_PATCHED)
    if has_patched and not force_official:
        return W_STAGE2_PATCHED, "A1 补丁版 · 完整 VAE 解码（画质优先）"
    if has_patched and force_official:
        return W_STAGE2_OFFICIAL, "官方原版 · TAEHV 解码（--keep-taehv 强制回退，用于 A/B 对照）"
    return W_STAGE2_OFFICIAL, "官方原版 · TAEHV 解码（未找到补丁版 %s）" % \
        os.path.basename(W_STAGE2_PATCHED)

def post(path, payload):
    req = urllib.request.Request(API + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    return urllib.request.urlopen(req, timeout=60).read().decode()

def free_vram():
    try:
        post("/free", {"unload_models": True, "free_memory": True})
    except Exception as e:
        dim("释放显存失败(忽略): %s" % e)

def gpu_used():
    try:
        o = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader"],
                           capture_output=True, text=True, timeout=15).stdout.strip()
        return o
    except Exception:
        return "?"

def run_workflow(workflow, sets, tag):
    cmd = [PY, RUNNER, workflow]
    for k, v in sets:
        cmd += ["--set", "%s=%s" % (k, v)]
    t0 = time.time()
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=COMFY)
    el = time.time() - t0
    out = (p.stdout or "") + (p.stderr or "")
    log = WORK + "/logs/%s.log" % tag
    os.makedirs(os.path.dirname(log), exist_ok=True)
    open(log, "w", encoding="utf-8").write(out)

    vram = re.search(r"峰值显存[:：]?\s*([\d.]+)", out)
    ram  = re.search(r"峰值内存[:：]?\s*([\d.]+)", out)
    prod = re.findall(r"->\s*(\S+\.mp4)", out)
    success = p.returncode == 0 and bool(prod)
    return success, (vram.group(1) if vram else "?"), (ram.group(1) if ram else "?"), el, (prod[-1] if prod else ""), out

def stage1_draft(shot, force=False):
    tag = "draft_%s" % shot["file"]
    dest = os.path.join(OUTDIR, tag + "_00001_.mp4")
    if os.path.exists(dest) and not force:
        ok("%s 草稿已存在，跳过" % shot["file"]); return dest
    L = int(shot.get("h3_length", H3_LENGTH))
    hdr("阶段1 草稿 · 镜 %02d · %s · 672x384 x %d帧(%.3fs) x 4步" % (shot["no"], shot["framing"], L, L / 24.0))
    sets = [
        ("1.unet_name", UNET), ("2.lora_name", LORA), ("3.clip_name", CLIP),
        ("6.prompt", shot["prompt"]),
        ("6.width", 672), ("6.height", 384), ("6.length", L), ("6.task_type", "T2VA"),
        ("9.noise_seed", SEED),
        ("12.filename_prefix", "MiniMaxH3/%s/%s" % (FILM, tag)),
    ]
    good, vram, ram, el, prod, out = run_workflow(W_STAGE1, sets, tag)
    if not good:
        bad("%s 草稿失败，日志 %s/logs/%s.log" % (shot["file"], WORK, tag))
        print("\n".join(out.splitlines()[-25:]))
        return None
    ok("%s 草稿完成 %.1fs | 峰值显存 %s GiB | 峰值内存 %s GiB | %s" % (shot["file"], el, vram, ram, prod))
    return dest

def stage2_refine(shot, draft_path, force=False):
    tag = "shot%02d" % shot["no"]
    final = os.path.join(FINALDIR, tag + ".mp4")
    if os.path.exists(final) and not force:
        ok("%s 精修已存在，跳过" % tag); return final
    if not draft_path or not os.path.exists(draft_path):
        bad("%s 找不到草稿，无法精修" % tag); return None
    ipath = os.path.join(INDIR, "draft_%s.mp4" % shot["file"])
    shutil.copyfile(draft_path, ipath)
    hdr("阶段2 精修 · 镜 %02d · %s -> 1344x768" % (shot["no"], shot["framing"]))
    dim("工作流: %s" % os.path.basename(W_STAGE2))
    sets = [
        ("1.file", "draft_%s.mp4" % shot["file"]),
        ("3.target_width", 1344), ("3.target_height", 768),
        ("12.text", shot["prompt"]),
        ("20.filename_prefix", "MiniMaxH3/%s/%s" % (FILM, tag)),
    ]
    good, vram, ram, el, prod, out = run_workflow(W_STAGE2, sets, tag)
    if not good:
        bad("%s 精修失败，日志 %s/logs/%s.log" % (tag, WORK, tag))
        print("\n".join(out.splitlines()[-25:]))
        return None
    os.makedirs(FINALDIR, exist_ok=True)
    src = os.path.join(OUTDIR, prod)
    if not os.path.exists(src):
        cand = [f for f in os.listdir(OUTDIR) if f.startswith(tag + "_") and f.endswith(".mp4")]
        if not cand:
            bad("%s 精修产物未找到" % tag); return None
        src = os.path.join(OUTDIR, sorted(cand)[-1])
    shutil.copyfile(src, final)
    ok("%s 精修完成 %.1fs | 峰值显存 %s GiB | 峰值内存 %s GiB -> %s" % (tag, el, vram, ram, final))
    return final

def concat():
    hdr("合成全片")
    order = sorted([f for f in os.listdir(FINALDIR) if re.match(r"shot\d+\.mp4$", f)],
                   key=lambda x: int(re.search(r"\d+", x).group()))
    if not order:
        bad("没有精修片段可合成"); return None
    lst = WORK + "/concat.txt"
    os.makedirs(WORK, exist_ok=True)
    with open(lst, "w") as fh:
        for f in order:
            fh.write("file '%s'\n" % os.path.join(FINALDIR, f))
    out = WORK + "/加名之夜_全片.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", lst,
                    "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                    "-pix_fmt", "yuv420p",
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                    "-c:a", "aac", "-b:a", "192k", out],
                   capture_output=True, text=True)
    if os.path.exists(out):
        n = len(order)
        ok("合成完成 %d 镜 -> %s (%.1f MB)" % (n, out, os.path.getsize(out) / 1048576))
    else:
        bad("ffmpeg 合成失败")
    return out

def main():
    global W_STAGE2
    man = json.load(open(MANIFEST, encoding="utf-8"))
    shots = man["shots"]
    args = sys.argv[1:]
    if "--list" in args:
        for s in shots:
            print("%02d | %-30s | %ds | %s" % (s["no"], s["framing"], s["duration"],
                                               s["dialogue_cn"] or "—"))
        return
    if "--concat" in args:
        concat(); return

    stage, force, rng = "both", "--force" in args, None
    if "--stage" in args:
        stage = args[args.index("--stage") + 1]
    if "--shots" in args:
        v = args[args.index("--shots") + 1]
        if "-" in v:
            a, b = v.split("-"); rng = set(range(int(a), int(b) + 1))
        else:
            rng = {int(v)}
    sel = [s for s in shots if rng is None or s["no"] in rng]

    os.makedirs(OUTDIR, exist_ok=True); os.makedirs(FINALDIR, exist_ok=True)
    os.makedirs(WORK + "/logs", exist_ok=True)

    # Stage2 工作流选型：A1 补丁版（完整 VAE 解码）优先，--keep-taehv 可强制回退做对照
    W_STAGE2, why = resolve_stage2_workflow(force_official="--keep-taehv" in args)

    _ls = [int(x.get("h3_length", H3_LENGTH)) for x in sel]
    hdr("《加名之夜》批量生产 | %d 镜 | 阶段=%s | seed=%d | 单镜 %d–%d 帧 (%.3f–%.3fs)" %
        (len(sel), stage, SEED, min(_ls), max(_ls), min(_ls) / 24.0, max(_ls) / 24.0))
    dim("Stage2 工作流: %s" % why)
    dim("  %s" % W_STAGE2)

    report = []
    for s in sel:
        t0 = time.time()
        draft = None
        if stage in ("both", "draft"):
            draft = stage1_draft(s, force)
            if draft is None:
                report.append((s["no"], "草稿失败", "", "", "")); continue
        if stage in ("both", "refine"):
            if draft is None:
                cand = os.path.join(OUTDIR, "draft_%s_00001_.mp4" % s["file"])
                draft = cand if os.path.exists(cand) else None
            fin = stage2_refine(s, draft, force)
            report.append((s["no"], "完成" if fin else "精修失败", "", "", "%.0fs" % (time.time() - t0)))
        else:
            report.append((s["no"], "草稿完成", "", "", "%.0fs" % (time.time() - t0)))

    hdr("汇总")
    for no, st, _, _, el in report:
        mark = C_OK + "✔" + C_0 if "完成" in st else C_BAD + "✘" + C_0
        print("  %s 镜 %02d  %s" % (mark, no, st))
    print("  显存收尾: %s" % gpu_used())

if __name__ == "__main__":
    main()
