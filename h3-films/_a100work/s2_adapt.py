#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""s2_adapt.py — 把 LTX-2.5 官方精修工作流适配成「本机可跑」版本，并按镜参数化。

背景
----
节点包自带的官方 Stage2 工作流 (`22-sol-engine-h3-super/*.json`) 引用三件本机
没有的资产：

  1. `ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors`  20.03 GB
  2. `ltx-2.5-22b-distilled-lora-450-bf16.safetensors`             8.29 GB
  3. `taeltx2_3_wide.pth`（TAEHV 预览级解码器）

而本机已有 `ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors`
（20.03 GB）——它就是 dev + distilled-lora-450 的**融合版**，体积与 (1) 完全一致。

RefinerSetup 节点的官方 tooltip 原文是：
  "LTX-2.5 dev transformer with the distilled refiner LoRA applied at 0.8"
→ 说明该节点期望的输入模型 = 已融合蒸馏 LoRA 的模型。用融合版直接喂进去是等价路径。

三处改造
--------
  A. UNETLoader  dev-transformer  →  distilled-transformer（融合版）
  B. 删除 LoraLoaderModelOnly，RefinerSetup.model 改指 UNETLoader
  C. TAEHVDecode → 标准 VAEDecode（接完整 ltx video vae；TAEHV 是预览级，
     会把 22B 算出的 latent 在最后一步糊掉）；同时删除 TAEHVLoader

用法
----
  python3 s2_adapt.py --template stage2_official_api.json --out s2_template.json
  python3 s2_adapt.py --template s2_template.json --shot 13 \
      --draft drafts/s13_ref.mp4 --prompt-file p.txt --seed 100013 \
      --prefix MiniMaxH3/film1-refined/s13 --width 768 --height 1344 \
      --out api_s13.json
"""
import argparse
import copy
import json
import os
import sys

DEV_UNET = "ltx-2.5-22b-dev-transformer-comfy-int8-convrot.safetensors"
DISTILLED_UNET = "ltx-2.5-22b-distilled-transformer-comfy-int8-convrot.safetensors"

# 官方工作流里需要摘掉的节点
DROP_NODES = ("9", "25")  # 9=LoraLoaderModelOnly  25=TAEHVLoader


# ── 精修强度预设 ────────────────────────────────────────────────────────────
# 官方 README 原文：
#   · 对齐版 sigmas `0.909375 → 0.725 → 0.421875 → 0`（NVIDIA 发布口径）
#   · 保脸版 sigmas `0.5 → 0.412 → 0.350 → 0`
#   · "人脸变化过大时改用低 Sigma 版"
# 节点说明原文："the 0.5 start mixes 0.5 x noise + 0.5 x the upscaled latent"
# → 0.909375 起点等于 latent 里 91% 被噪声顶掉，等于**近乎从零重画**；
#   这是袋面印刷 / 人脸在精修后被画坏的直接机理。0.5 起则保留一半原 latent。
PRESETS = {
    "official": {
        "class_type": "MiniMaxH3SolEngineLTXRefinerSetupT8Advanced",
        "inputs": {
            "enabled": True,
            "attention_backend": "auto_sol_attn",
            "min_tokens": 4096,
            "kernel_precision": "bf16_official",
            "verbose": False,
        },
        "sigmas": "0.909375, 0.725, 0.421875, 0",  # 仅供日志展示
        "desc": "官方对齐版（满强度重画，细节/身份改动大）",
    },
    "identity": {
        "class_type": "MiniMaxH3SolEngineLTXIdentityRefinerSetupT8Advanced",
        "inputs": {
            "enabled": True,
            "schedule_mode": "identity_preserve_0p5",
            "manual_sigmas": "0.5, 0.412, 0.350, 0",
            "attention_backend": "dense_reference",
            "min_tokens": 4096,
            "kernel_precision": "bf16_official",
            "verbose": False,
        },
        "sigmas": "0.5, 0.412, 0.350, 0",
        "desc": "低 Sigma 保脸版（原 latent 保留一半，主体/文字保真优先）",
    },
}

GUIDE_LOAD_ID = "90"
GUIDE_NODE_ID = "91"


def adapt_template(tpl, preset=None):
    """把官方 API 工作流改造成本机可跑版本（幂等）。"""
    d = copy.deepcopy(tpl)
    changed = []

    # B. 删除 LoRA 与 TAEHV loader，并把 RefinerSetup 的 model 接到 UNETLoader
    for nid in DROP_NODES:
        if nid in d:
            cls = d[nid]["class_type"]
            del d[nid]
            changed.append("删除 #%s %s" % (nid, cls))
    REFINER_TYPES = ("MiniMaxH3SolEngineLTXRefinerSetupT8Advanced",
                     "MiniMaxH3SolEngineLTXIdentityRefinerSetupT8Advanced")
    refiner = d.get("10")
    if refiner and refiner["class_type"] in REFINER_TYPES:
        if refiner["inputs"].get("model") in (["9", 0], "9"):
            refiner["inputs"]["model"] = ["8", 0]
            changed.append("RefinerSetup.model: #9 → #8（直连融合版 UNET）")

    # A. UNETLoader 换融合版
    unet = d.get("8", {}).get("inputs", {})
    if unet.get("unet_name") == DEV_UNET:
        unet["unet_name"] = DISTILLED_UNET
        changed.append("UNETLoader: dev → distilled（融合蒸馏 LoRA）")

    # C. TAEHV 解码 → 标准 VAEDecode
    dec = d.get("17")
    if dec and dec["class_type"] == "MiniMaxH3SolEngineTAEHVDecodeT8Advanced":
        d["17"] = {
            "class_type": "VAEDecode",
            "inputs": {"samples": ["16", 0], "vae": ["4", 0]},
            "_meta": {"title": "VAEDecode (A1 patch: 替代 TAEHV 预览解码器)"},
        }
        changed.append("解码器: TAEHV → VAEDecode(完整 ltx video vae)")

    # D. SaveVideo 的 format / codec 是 COMFY_DYNAMICCOMBO_V3（前端动态组合控件）。
    #    ui_to_api.py 的 widget 类型白名单不含它，转换时这两个参数会整对丢失，
    #    提交后报：SaveVideo.execute() missing 1 required positional argument: 'format'
    sv = d.get("20", {})
    if sv.get("class_type") == "SaveVideo":
        for k, v in (("format", "auto"), ("codec", "auto")):
            if k not in sv["inputs"]:
                sv["inputs"][k] = v
                changed.append("SaveVideo: 补 %s=%s（DYNAMICCOMBO 转换丢失）" % (k, v))

    # E. 精修强度预设：切换 #10 精修器版本。sigma 起点决定"重画 vs 保留"的比例，
    #    是主体保真度最大的单一杠杆。
    r = d.get("10")
    if r and r["class_type"] in REFINER_TYPES and preset in PRESETS:
        p = PRESETS[preset]
        if r["class_type"] != p["class_type"]:
            model_ref = r["inputs"].get("model") or ["8", 0]
            d["10"] = {
                "class_type": p["class_type"],
                "inputs": dict(p["inputs"], model=model_ref),
                "_meta": {"preset": preset, "sigmas": p["sigmas"]},
            }
            changed.append("精修器 → %s（sigmas %s，%s）"
                           % (p["class_type"], p["sigmas"], p["desc"]))

    return d, changed


def inject_guide(d, image, frame_idx=0, strength=1.0):
    """把参考图作为引导帧注入精修采样（in-context conditioning）。

    精修工作流原本**零图片输入** —— LTX 只能靠 gemma 文本先验"想象"袋面/人脸，
    这是包装文字被画成镜像乱码、主体漂移的另一半原因。LTXVAddGuide 让参考图以
    像素形式进入 latent，采样时作为 in-context 条件参与 attention。

    接线：positive/negative 取自 #26(LTXVConditioning)，latent 取自
    #7(LTXVLatentUpsampler)；输出三路（positive/negative/latent）回到
    #14(CFGGuider) 与 #16(SamplerCustomAdvanced.latent_image)。
    """
    d[GUIDE_LOAD_ID] = {
        "class_type": "LoadImage",
        "inputs": {"image": image},
        "_meta": {"title": "参考图 %s" % image},
    }
    d[GUIDE_NODE_ID] = {
        "class_type": "LTXVAddGuide",
        "inputs": {
            "positive": ["26", 0],
            "negative": ["26", 1],
            "vae": ["4", 0],
            "latent": ["7", 0],
            "image": [GUIDE_LOAD_ID, 0],
            "frame_idx": int(frame_idx),
            "strength": float(strength),
        },
        "_meta": {"title": "参考图引导 frame=%d strength=%s" % (frame_idx, strength)},
    }
    d["14"]["inputs"]["positive"] = [GUIDE_NODE_ID, 0]
    d["14"]["inputs"]["negative"] = [GUIDE_NODE_ID, 1]
    d["16"]["inputs"]["latent_image"] = [GUIDE_NODE_ID, 2]
    return ["注入参考图引导: %s @frame %d strength %s" % (image, frame_idx, strength)]


def parametrize(d, shot, draft, prompt, seed, prefix, width, height):
    """按镜注入参数（就地修改）。"""
    d["3"]["inputs"]["target_width"] = int(width)
    d["3"]["inputs"]["target_height"] = int(height)
    d["1"]["inputs"]["file"] = draft
    d["12"]["inputs"]["text"] = prompt
    d["15"]["inputs"]["noise_seed"] = int(seed)
    d["20"]["inputs"]["filename_prefix"] = prefix
    # 注意：不要在顶层写 "_meta" —— ComfyUI 的 /prompt 会把顶层每个键都当节点，
    # 遇到无 class_type 的键直接 400 missing_node_type。镜号信息挂在节点 _meta 上。
    d["20"].setdefault("_meta", {})["title"] = "shot%02d refine" % int(shot)
    d["8"].setdefault("_meta", {})["shot"] = int(shot)
    return d


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--template", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--shot")
    ap.add_argument("--draft")
    ap.add_argument("--prompt-file")
    ap.add_argument("--prompt")
    ap.add_argument("--seed", default="42")
    ap.add_argument("--prefix", default="MiniMaxH3/film1-refined/shot")
    ap.add_argument("--width", default=768)
    ap.add_argument("--height", default=1344)
    ap.add_argument("--preset", choices=sorted(PRESETS), default=None,
                    help="精修强度预设：official=官方对齐版 / identity=低Sigma保脸版")
    ap.add_argument("--guide",
                    help="参考图（相对 ComfyUI/input），如 refs/prod_P1_front.png")
    ap.add_argument("--guide-frame", type=int, default=0)
    ap.add_argument("--guide-strength", type=float, default=1.0)
    a = ap.parse_args()

    tpl = json.load(open(a.template))
    d, changed = adapt_template(tpl, preset=a.preset)

    if not changed:
        print("[i] 模板已是适配态，未做改动")
    for c in changed:
        print("  ·", c)

    if a.guide:
        for c in inject_guide(d, a.guide, a.guide_frame, a.guide_strength):
            print("  ·", c)

    if a.shot is not None:
        prompt = a.prompt
        if a.prompt_file:
            prompt = open(a.prompt_file, encoding="utf-8").read().strip()
        if prompt is None:
            sys.exit("--shot 模式下必须给 --prompt 或 --prompt-file")
        if not a.draft:
            sys.exit("--shot 模式下必须给 --draft")
        parametrize(d, a.shot, a.draft, prompt, a.seed, a.prefix,
                    a.width, a.height)
        print("[i] 已注入: shot=%s draft=%s seed=%s %sx%s"
              % (a.shot, a.draft, a.seed, a.width, a.height))

    os.makedirs(os.path.dirname(os.path.abspath(a.out)) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(d, f, ensure_ascii=False, indent=1)
    print("[✓] 写出", a.out, "（%d 节点）" % len([k for k in d if k != "_meta"]))


if __name__ == "__main__":
    main()
