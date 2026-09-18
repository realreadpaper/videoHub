#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""构造「中文人声驱动」的 stage1 工作流（lock_source），输出到远端工程目录。

为什么：H3 的 T2VA 联合生成中文台词不稳（官方仅 1 句中文验证；实测部分镜头说的是
非中文）。lock_source 把**外部中文 TTS 干声**作为音轨锁定输入 —— 成片音轨即该干声，
语音 100% 中文且音色可控；画面按音频时序生成。

图条件（MiniMaxH3AudioConditioningT8 是「六合一」统一节点，task_type=auto 从接线推断）
------------------------------------------------------------------------------------
  不接图            → T2VA   纯文字（片1 现状：产品靠文字描述，模型只能瞎编）
  first_frame/last_frame → FL2VA/I2VA/L2VA
                     「关键帧」占**真实帧位**（第 0 帧或末帧），必须和目标画布同比例；
                     所以只能锁 t=0 或 t=末 —— 产品只在镜头中段出现时用不了。
  ref_images        → Ref2VA「参考图」**不占帧位**，可用自己的分辨率，
                     只「引导身份/外观」而不成为某一帧 → **产品可出现在任意时段**，
                     最多 9 图（<Picture 1..9>）、3 视频、3 音频。
                     这才是「拿产品图针对性生成」的正解。

用法：
  python3 build_voice_workflow.py --shot 5 [--dry tts_dry/film1/shot05_dry.wav] [--film film1]
  python3 build_voice_workflow.py --shot 18 --first-frame frames/f18.png     # 首帧锚定
  python3 build_voice_workflow.py --shot 15 --ref-images refs/prod1.png      # 参考图
  python3 build_voice_workflow.py --shot 15 --ref-images a.png,b.png --ref-size max
产物：_remote/stage1_voice_<film>_s<NN>.json 或 --out 指定（随后 scp 到远端交给 runner）
"""
import argparse, importlib.util, json, os

ROOT = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(ROOT, "_remote", "stage1_audio_lock.json")
OUTDIR = os.path.join(ROOT, "_remote")

# ── 槽位顺序（连接输入）──────────────────────────────────────────────
# 实测自模板 JSON 的 node6.inputs（2026-09-17 核对），与 T8 节点 /object_info 一致。
# 未连接的 optional 槽不会写进 JSON，所以 ref_* 要按这个顺序 append。
# ★ 远端恢复后先跑 probe_h3_nodes.py --dump-slots h3_slots.json，生成器优先读该文件。
SLOT_FALLBACK = ["clip", "video_vae", "audio_vae", "length", "drive_audio", "final_audio",
                 "first_frame", "last_frame",
                 "ref_images", "ref_videos", "ref_video_audios", "ref_audios"]
SLOTS_FILE = os.path.join(ROOT, "h3_slots.json")

# ── widget 顺序（widgets_values 各位置）──────────────────────────────
# 实测自模板 JSON node6.widgets_values（12 项，2026-09-17）。改动前用 sanity check 校验。
WIDGET = ["prompt", "width", "height", "length", "task_type", "audio_mode",
          "audio_denoise_strength", "add_source_as_reference", "prompt_primary_audio_ordinal",
          "strict_prompt_tags", "ref_image_size", "reference_video_policy"]


def _slot_index(name):
    """槽名 → 索引。优先读 probe 导出的 h3_slots.json，缺失则回退 SLOT_FALLBACK。"""
    if os.path.exists(SLOTS_FILE):
        try:
            m = json.load(open(SLOTS_FILE, encoding="utf-8")).get("cond_slot_index") or {}
            if name in m:
                return int(m[name]), "h3_slots.json"
        except Exception:
            pass
    if name in SLOT_FALLBACK:
        return SLOT_FALLBACK.index(name), "fallback"
    raise SystemExit("✘ 未知槽名 %s（既不在 h3_slots.json 也不在 SLOT_FALLBACK）" % name)


def _wid(wf, name):
    """widget 名 → widgets_values 下标（带 sanity check，防止版本升级静默错位）。"""
    c = node(wf, 6)
    vals = c["widgets_values"]
    if len(vals) != len(WIDGET):
        print("  ⚠ widgets_values 项数 %d ≠ 预期 %d，widget 顺序可能已变；"
              "请重新 probe 并更新 WIDGET" % (len(vals), len(WIDGET)))
    return WIDGET.index(name)

UNET = "minimax_h3_fl2va_pruned_int8_convrot.safetensors"
LORA = "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors"
# 官方示例模板写的是裸文件名，但本机模型在 text_encoders/minimax_h3/ 子目录下，
# 必须带目录前缀，否则 /prompt 校验报 value_not_in_list（UNET 在根目录，不能加前缀）。
CLIP = "minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors"
RES = (384, 672)        # stage1 竖版
FRAMES = 362            # 17n+5 栅格 -> 15.0833s @24fps
FPS = 24

PREFIX = ("<Audio 1> holds the voice of the person speaking on screen: a clear Mandarin Chinese "
          "line. Keep the visual timing, phrasing and rhythm locked to <Audio 1>, with natural "
          "matching mouth movement and body performance. Follow the shot description below "
          "exactly.\n\n")


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def node(wf, nid):
    for n in wf["nodes"]:
        if n["id"] == nid:
            return n
    raise KeyError("no node %s" % nid)


def _ensure_slot(wf, target_id, slot_name):
    """确保目标节点存在该输入槽并返回 (节点, 索引)。

    已存在 → 直接返回。不存在（未连接的 optional 槽）→ 按 SLOT_FALLBACK 顺序
    把中间的占位槽一起补齐，保证 inputs 数组顺序与节点定义一致 —— 否则 ComfyUI
    载入时会把参数绑到错的槽上，**静默生成错结果**。
    """
    t = node(wf, target_id)
    for i, inp in enumerate(t["inputs"]):
        if inp["name"] == slot_name:
            return t, i
    want, src = _slot_index(slot_name)
    if len(t["inputs"]) > want:
        raise SystemExit("✘ 槽 %s 期望索引 %d，但节点已有 %d 个槽 —— "
                         "节点定义已变，请重跑 probe_h3_nodes.py"
                         % (slot_name, want, len(t["inputs"])))
    while len(t["inputs"]) < want:
        nm = SLOT_FALLBACK[len(t["inputs"])] if len(t["inputs"]) < len(SLOT_FALLBACK) else "pad%d" % len(t["inputs"])
        t["inputs"].append({"name": nm, "type": "IMAGE", "link": None})
        print("  · 补占位槽 [%d] %s（未连接，仅为对齐顺序）" % (len(t["inputs"]) - 1, nm))
    t["inputs"].append({"name": slot_name, "type": "IMAGE", "link": None})
    print("  · 新增槽 [%d] %s （索引来源：%s）" % (len(t["inputs"]) - 1, slot_name, src))
    return t, len(t["inputs"]) - 1


def attach_image(wf, target_id, slot_name, image_name, nth=0, total=1, tag=None):
    """往工作流里插 LoadImage 节点，连到 target 节点的指定输入槽。

    ★ 与「关键帧」的区别（决定怎么用）：
      first_frame / last_frame 是 fl2va 的**关键帧** —— 占真实帧位，必须与目标画布同比例；
      ref_images 是 ref2va 的**参考图** —— 不占帧位、可用自身分辨率、只引导身份/外观，
      所以产品可以出现在镜头的任意时段，最多 9 张。
    """
    t, idx = _ensure_slot(wf, target_id, slot_name)

    nid = wf["last_node_id"] + 1
    lid = wf["last_link_id"] + 1
    wf["last_node_id"] = nid
    wf["last_link_id"] = lid
    # 一个输入槽可承载多条 link（ComfyUI 会把它们当成 list 一并喂给节点），
    # 所以多张参考图共用一个 ref_images 槽是允许的。
    if t["inputs"][idx].get("link") is None:
        t["inputs"][idx]["link"] = lid
    else:
        old = t["inputs"][idx]["link"]
        if not isinstance(old, list):
            old = [old]
        t["inputs"][idx]["link"] = old + [lid]
    label = tag or slot_name
    wf["nodes"].append({
        "id": nid, "type": "LoadImage",
        "title": "Ref/Key · %s%s" % (label, "" if total == 1 else " (%d/%d)" % (nth + 1, total)),
        "pos": [0, 1400 + 200 * idx + 240 * nth], "size": [320, 314], "flags": {},
        "order": 4, "mode": 0, "inputs": [],
        "outputs": [{"name": "IMAGE", "type": "IMAGE", "links": [lid]},
                    {"name": "MASK", "type": "MASK", "links": []}],
        "properties": {"Node name for S&R": "LoadImage"},
        "widgets_values": [image_name, "image"],
    })
    wf["links"].append([lid, nid, 0, target_id, idx, "IMAGE"])
    print("  ✔ %-34s → 节点%s.%s (slot %d, link %d)" % (image_name, target_id, slot_name, idx, lid))
    return idx


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shot", type=int, required=True)
    ap.add_argument("--film", default="film1", choices=["film1", "film2"])
    ap.add_argument("--dry", default=None, help="远端 input 下的干声相对路径")
    ap.add_argument("--first-frame", default=None,
                    help="首帧锚定图（远端 input 下相对路径，如 frames/film1_shot13_first.png）")
    ap.add_argument("--last-frame", default=None,
                    help="尾帧锚定图（同上）")
    ap.add_argument("--ref-images", default=None,
                    help="参考图（Ref2VA，逗号分隔多张；远端 input 下相对路径）。"
                         "不占帧位 → 产品可出现在镜头任意时段，最多 9 张")
    ap.add_argument("--ref-size", default=None, choices=["match", "max"],
                    help="参考图分辨率策略：match=缩到画布像素面积(默认,快)；max=保留 2048px 短边(保真最好,慢数倍)")
    ap.add_argument("--task-type", default=None,
                    help="显式指定任务类型（默认保持模板的 auto，由接线自动推断）")
    ap.add_argument("--dur", type=float, default=FRAMES / FPS)
    ap.add_argument("--out", default=None, help="输出路径（默认 _remote/stage1_voice_<film>_s<NN>.json）")
    a = ap.parse_args()

    py = "p1_data" if a.film == "film1" else "p2_data"
    mod = load(py)
    shot = next((s for s in mod.SHOTS if s["no"] == a.shot), None)
    if shot is None:
        raise SystemExit("镜头 %d 不存在" % a.shot)

    dry = a.dry or ("tts_dry/%s/shot%02d_dry.wav" % (a.film, a.shot))
    wf = json.load(open(TPL, encoding="utf-8"))

    # 6 = MiniMaxH3AudioConditioningT8（widget 顺序见 WIDGET，已按模板实测核对）
    c = node(wf, 6)
    c["widgets_values"][_wid(wf, "prompt")] = PREFIX + shot["prompt"]
    c["widgets_values"][_wid(wf, "width")] = RES[0]
    c["widgets_values"][_wid(wf, "height")] = RES[1]
    c["widgets_values"][_wid(wf, "length")] = FRAMES
    c["widgets_values"][_wid(wf, "audio_mode")] = "lock_source"
    c["widgets_values"][_wid(wf, "add_source_as_reference")] = True
    if a.task_type:
        c["widgets_values"][_wid(wf, "task_type")] = a.task_type
    if a.ref_size:
        c["widgets_values"][_wid(wf, "ref_image_size")] = a.ref_size

    node(wf, 1)["widgets_values"][0] = UNET
    node(wf, 2)["widgets_values"][0] = LORA
    node(wf, 3)["widgets_values"][0] = CLIP
    node(wf, 7)["widgets_values"][0] = 4          # steps
    node(wf, 9)["widgets_values"][0] = mod.FILM["seed"] + a.shot
    node(wf, 13)["widgets_values"][0] = dry
    # 14 = AudioWindow: [scene_start, scene_dur, warmup, cooldown, ensure_min]
    node(wf, 14)["widgets_values"][0] = 0.0
    node(wf, 14)["widgets_values"][1] = round(a.dur, 4)
    # 15 = OutputTrim: [start, duration, fps]
    node(wf, 15)["widgets_values"][0] = 0.0
    node(wf, 15)["widgets_values"][1] = round(a.dur, 4)
    node(wf, 15)["widgets_values"][2] = FPS
    # ── 图条件接线 ──────────────────────────────────────────────────
    # 关键帧（占帧位，只能锁 t=0 / t=末）
    if a.first_frame:
        attach_image(wf, 6, "first_frame", a.first_frame, tag="Keyframe@first")
    if a.last_frame:
        attach_image(wf, 6, "last_frame", a.last_frame, tag="Keyframe@last")
    # 参考图（不占帧位，产品可出现在任意时段）—— Ref2VA 正解
    refs = [x.strip() for x in (a.ref_images or "").split(",") if x.strip()]
    if len(refs) > 9:
        raise SystemExit("✘ H3 Ref2VA 参考图上限 9 张，收到 %d 张" % len(refs))
    for i, r in enumerate(refs):
        attach_image(wf, 6, "ref_images", r, nth=i, total=len(refs),
                     tag="Picture %d" % (i + 1))
    if refs:
        print("  ↳ Ref2VA：prompt 用 %s 指代参考图（严格模式会校验编号连续性）"
              % ("<Picture 1>" if len(refs) == 1
                 else "<Picture 1>…<%d>" % len(refs)))
        print("  ↳ task_type=%s（auto = 按接线自动推断）｜ref_image_size=%s"
              % (c["widgets_values"][_wid(wf, "task_type")],
                 c["widgets_values"][_wid(wf, "ref_image_size")]))
    node(wf, 12)["widgets_values"]["filename_prefix"] = "MiniMaxH3/%s/voice_shot%02d" % (
        "douyin-office" if a.film == "film1" else "douyin-blinddate", a.shot)

    os.makedirs(OUTDIR, exist_ok=True)
    out = a.out or os.path.join(OUTDIR, "stage1_voice_%s_s%02d.json" % (a.film, a.shot))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    json.dump(wf, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("✓ %s" % out)
    print("  干声: %s  (%.3fs)" % (dry, a.dur))
    print("  prompt 头: %s" % (PREFIX + shot["prompt"])[:90].replace("\n", " "))


if __name__ == "__main__":
    main()
