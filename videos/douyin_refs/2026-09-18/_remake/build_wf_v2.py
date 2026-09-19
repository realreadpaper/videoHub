#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 生产脚本：治「多人糊成一团 / 构图漂移 / 原片文字被复刻」。

解决三件事：
1. 多人调度：prompt 里显式声明「画面里有几个人、各自在什么景深」，并明令
   不许排成一排、不许糊成一团、不许把群像推成单人特写。（旧版 prompt 对此零约束）
2. 构图锁死：可选 first_frame（精确第 0 帧 = 原片该帧）→ task_type 变 hybrid。
3. 参考图精度：ref_image_size 由 match 提到 max（原图分辨率，不降采样）。

变体：
  --variant B  ref2va + ref_image_size=max + prompt v2
  --variant C  hybrid + first_frame + ref_image_size=max + prompt v2
  --tag       输出目录后缀（默认 v2）
"""
import json, os, sys, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
TPL_PATH = f"{HERE}/wf_skel/wf_dy1_s01_open_kick.json"
FF = "/usr/local/bin/ffmpeg"

ANTI_GREASY = (
    "true-to-life East Asian skin with visible pores, fine lines and a matte finish, "
    "neutral white balance, muted naturalistic colour, gentle filmic contrast with a soft highlight roll-off. "
    "No oily sheen and no glossy specular highlights on any face, no beauty-filter smoothing, no airbrushing, "
    "no waxy or plastic skin, no HDR glow, no bloom, no over-sharpening, no over-saturated colour, "
    "no orange or teal colour cast, no heavy vignette, no digital gloss or plastic AI sheen. "
)
NO_TEXT_SHORT = (
    "No subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no logo, no timestamp, no UI overlay. "
    "Never imitate or reproduce a subtitle strip or any text overlay from the source material; do not add any "
    "floating or superimposed lettering of any script - Chinese, Latin, digits or symbols - anywhere in the frame. "
    "Any paper, sign, plaque, package or printed surface in frame is blank or shows only soft unreadable blurred marks."
)
STRICT = (
    "strict_output_constraints: Absolutely no subtitles, no captions, no burned-in text, "
    "no on-screen text of any kind, no watermark, no logo, no timestamp, no UI overlay, no lower-third. "
    "Any sign, plaque, paper, lettering, package or printed surface appearing in frame must render as "
    "completely illegible abstract marks - no readable characters, digits or words in any language whatsoever. "
    "Text-bearing props are set dressing only and must never be legible. "
    "Speech is driven only by the supplied reference audio; do not render any mouth shapes for lines that are not audible."
)
# 参考图里被抹掉文字的地方会留一块柔焦区，明确告诉模型那是背景，别补字
RESIDUAL = (
    "The reference frame may show one soft, defocused patch where an overlay used to be; render it as ordinary "
    "continuous background texture - never as characters, boxes, bars, plates or panels. "
)

# ── 字幕抑制的两种策略（实测：反复写 no subtitles 反而诱发字幕条）──
# PV2 = 纯正向：通篇不出现 subtitle/caption/text/logo/watermark 等词
NO_TEXT_PV2 = (
    "Raw ungraded camera negative: the image is clean photography from edge to edge, and every surface in "
    "frame is either a physical object or continuous background texture. "
)
STRICT_PV2 = (
    "strict_output_constraints: The frame is pure photography with no composited graphic layer anywhere. "
    "Every surface in frame renders as ordinary photographic texture; any printed object stays soft and unreadable. "
    "Speech is driven only by the supplied reference audio; do not render any mouth shapes for lines that are not audible."
)
# PV3 = 原策略 + 明确描述下半幅是「空的连续表面」
NO_TEXT_PV3 = NO_TEXT_SHORT + (
    "The lower band of the frame is plain continuous surface - floor, table, clothing or ground - empty and unmarked. "
)

UNIVERSAL_BLOCKING = (
    "Universal blocking rules, apply for the whole shot:\n"
    "- Keep the reference camera position, lens, shot size, camera height and subject distance exactly. "
    "Never push in, zoom, recentre or reframe. A group shot must stay a group shot - never turn it into a "
    "single-person close-up and never single out one face for a portrait.\n"
    "- Keep the exact number of people given above. Do not add anyone who is not in the reference and do not "
    "drop anyone who is in it; no bystanders, no extras, no mirrored or reflected figures.\n"
    "- Do not line people up shoulder to shoulder in a flat horizontal row at equal distance from the camera, "
    "and do not stack them into a symmetrical wall of faces. Stagger them in depth and vary their scale the "
    "way the reference frame does.\n"
    "- Every visible person keeps a separate, fully formed head with their own distinct facial features, "
    "hairstyle, clothing and skin tone. Never merge, fuse, blend or duplicate faces, and never let one person's "
    "face melt into another's or into the background.\n"
    "- Every face stays clearly resolved - separated eyes, nose, mouth and jawline - even when small or in the "
    "background. No smeared, mushy, waxy, indistinct or half-formed faces.\n"
    "- Do not enlarge any face beyond its reference size; do not shrink faces into unreadable specks."
)


def cast_block(n_faces, face_ratio):
    r = f"{face_ratio*100:.0f}%" if face_ratio else "the same size as in the reference"
    if not n_faces:
        head = ("Exactly ZERO people are visible in this shot. This is an object / environment shot - "
                "do not introduce any human figure, face, hand or silhouette that is not in the reference. ")
    elif n_faces == 1:
        head = ("Exactly ONE person is visible in this shot - the single subject of the reference, in the same "
                f"position and at the same scale (the face occupies roughly {r} of the frame area). No second "
                "person, no passer-by, no background figure, no reflection of a person. ")
    elif n_faces == 2:
        head = ("Exactly TWO people are visible in this shot, at clearly different depths: the nearer one larger "
                f"in frame (face roughly {r} of the frame area) and the further one smaller and deeper in the "
                "scene, partially occluded or softened by depth of field. They are not shoulder to shoulder. ")
    elif n_faces == 3:
        head = ("Exactly THREE people are visible in this shot, staged at clearly different depths: one in the "
                "foreground (largest, seen from behind or cropped by a frame edge), the speaking subject in the "
                f"middle ground (sharpest, face roughly {r} of the frame area), and one further back, smaller and "
                "partially occluded. They must not form a flat row. ")
    else:
        head = (f"Exactly {n_faces} people are visible in this shot, kept at clearly different depths and scales "
                f"as in the reference (the largest face roughly {r} of the frame area). Arrange them the way the "
                "reference frame arranges them - do not flatten the group into a row. ")
    return f"<Cast and blocking - exact, this must be preserved:\n{head}\n{UNIVERSAL_BLOCKING}>\n\n"


def lens_of(framing):
    if "远" in framing: return "24 mm wide lens, deep focus"
    if "特写" in framing or "近景" in framing: return "50 mm lens, shallow depth of field"
    if "中近" in framing: return "50 mm lens, shallow depth of field"
    return "35 mm lens, moderate depth of field"


def action_block(action_en, camera_en, sec):
    if not action_en:
        return ""
    return (
        "<Action and camera for this shot - stage it exactly as written, once, and let it complete:\n"
        f"- Action: {action_en} This action must be visibly underway inside the shot and reach its end before "
        "the shot cuts. Do not hold a static pose, do not freeze halfway, do not repeat or mime it.\n"
        f"- Camera: {camera_en}. One continuous move only; no cut, no whip, no snap zoom inside the shot.\n"
        "- Any dialogue is carried on top of this action, not instead of it; the body keeps working while the "
        "mouth moves.\n>\n\n"
    )


def make_prompt(r, sec, n_faces, face_ratio, act_en="", cam_en="", pv=1, head_override=None, char_en=""):
    ts = f"00:00.000 - 00:{sec:06.3f}"
    speaks = bool(r["line"].strip())
    perf = (f"{r['speaker']} delivers the line; the mouth movement is driven strictly by the supplied "
            f"reference audio and stops the instant the audio goes quiet. "
            if speaks else
            "No one speaks in this shot; ambient room tone and action only, mouths closed and still. ")
    size = r["framing"] or "medium shot"
    no_text = {1: NO_TEXT_SHORT, 2: NO_TEXT_PV2, 3: NO_TEXT_PV3}[pv]
    strict = {1: STRICT, 2: STRICT_PV2, 3: STRICT}[pv]
    cast_text = (f"<Cast and blocking - exact, this must be preserved:\n{head_override}\n{UNIVERSAL_BLOCKING}>\n\n"
                 if head_override else cast_block(n_faces, face_ratio))
    return (
        "integrated_multimodal_description:\n"
        f"<Reference frame: <Picture 1> is a real frame captured from this exact shot of the original footage. "
        f"It is the authoritative reference for what appears in frame - reproduce its camera framing, shot size, "
        f"subject placement, subject count, wardrobe, hairstyle, props, lighting and colour faithfully. "
        f"Do not redesign the shot. {RESIDUAL}>\n\n"
        f"{char_en}"
        f"{cast_text}"
        f"{action_block(act_en, cam_en, sec)}"
        f"<Scene: {r['scene']}>\n\n"
        f"<Shot: {size}, cinematic 9:16 vertical framing, {lens_of(size)}, photorealistic live-action footage, "
        f"the shot runs the full {sec:.3f} seconds>\n\n"
        f"<Performance: {perf}Keep natural micro-expressions and small continuous body motion; never freeze into a still frame.>\n\n"
        f"<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, "
        f"ARRI Alexa look, fine film grain, {ANTI_GREASY}{no_text}>\n\n"
        f"[{ts}] The shot holds the reference framing continuously; {perf.rstrip()} "
        f"Subtle handheld breathing and continuous ambient motion throughout.\n\n"
        f"{strict}"
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--variant", default="B", choices=["B", "C", "D"])
    ap.add_argument("--tag", default="v2")
    ap.add_argument("--ref_suffix", default="_v3", help="参考图目录后缀，如 _v3 / _v5")
    ap.add_argument("--first_dir", default="dy_full_first4",
                    help="变体D 首帧钉图目录（v5=重清洗后的干净首帧）")
    ap.add_argument("--last_dir", default="dy_full_last4",
                    help="变体D 末帧钉图目录")
    ap.add_argument("--shots", nargs="*", help="只生成指定镜，如 dy1_s003 dy3_s001")
    ap.add_argument("--pv", type=int, default=1, choices=[1,2,3], help="字幕抑制策略")
    ap.add_argument("--steps", type=int, default=4, help="采样步数")
    ap.add_argument("--six", default="", help="六镜审查的角色/关系覆盖 JSON（six.json）")
    ap.add_argument("--action_file", default="", help="人工撰写的动作/运镜覆盖 JSON（six_action.json）")
    args = ap.parse_args()

    SIX = json.load(open(args.six, encoding="utf-8")) if args.six else {}
    ACT_OV = json.load(open(args.action_file, encoding="utf-8")) if args.action_file else {}

    OUT = f"{HERE}/wf_{args.tag}"
    os.makedirs(OUT, exist_ok=True)
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    faces = json.load(open(f"{HERE}/faces_all.json", encoding="utf-8"))
    direct = json.load(open(f"{HERE}/directing_all.json", encoding="utf-8"))
    den = json.load(open(f"{HERE}/directing_en.json", encoding="utf-8"))
    ref_suffix = getattr(args, "ref_suffix", "")
    tpl = json.load(open(TPL_PATH, encoding="utf-8"))
    tpl.pop("301", None)
    tpl["6"]["inputs"].pop("ref_images.ref_image_1", None)
    # 加 first/last frame 载入节点（变体 C / D 用）
    tpl["302"] = {"class_type": "LoadImage", "inputs": {"image": "dy_full_first/placeholder.jpg"}}
    tpl["303"] = {"class_type": "LoadImage", "inputs": {"image": "dy_full_last4/placeholder.jpg"}}

    made = 0
    for film, lst in rows.items():
        tag = {"01_报恩": "dy1", "02_继母": "dy2", "03_挑食": "dy3"}[film]
        fmap = {x["index"]: x for x in faces[film]}
        dmap = {x["index"]: x for x in direct[film]}
        for r in lst:
            nm = f"{tag}_s{r['index']:03d}"
            if args.shots and nm not in args.shots:
                continue
            sec = r["sec"]
            f = fmap.get(r["index"], {})
            dd = dmap.get(r["index"], {})
            act_en = den.get(dd.get("action", ""), dd.get("action", ""))
            cam_en = den.get(dd.get("camera", ""), dd.get("camera", ""))
            ao = ACT_OV.get(nm, {})
            act_en = ao.get("action", act_en)
            cam_en = ao.get("camera", cam_en)
            d = json.loads(json.dumps(tpl))
            d["14"]["inputs"]["scene_duration_seconds"] = sec
            d["13"]["inputs"]["audio"] = f"dy_full_a/{nm}.wav"
            d["300"]["inputs"]["image"] = f"dy_full_ref{ref_suffix}/{nm}.jpg"
            d["12"]["inputs"]["filename_prefix"] = f"dy_{args.tag}/{nm}"
            ov = SIX.get(nm, {})
            d["6"]["inputs"]["prompt"] = make_prompt(r, sec, f.get("faces", 0), f.get("face_ratio"),
                                                     act_en, cam_en, args.pv,
                                                     head_override=ov.get("head_en"),
                                                     char_en=ov.get("char_en", ""))
            d["6"]["inputs"]["ref_image_size"] = "max"
            d["7"]["inputs"]["steps"] = args.steps
            d["9"]["inputs"]["noise_seed"] = 20261022 + r["index"] * 7 + hash(tag) % 1000
            if args.variant == "C":
                d["302"]["inputs"]["image"] = f"dy_full_first{ref_suffix}/{nm}.jpg"
                d["6"]["inputs"]["first_frame"] = ["302", 0]
                d["6"]["inputs"]["task_type"] = "Hybrid"
            elif args.variant == "D":
                # 双端锁定：首帧 + 末帧都钉成原片对应帧，模型被夹住无法推镜
                # ★ v5：rescrub_sub.py 二次清洗后的版本（v3/v4 漏掉的硬字幕已铲干净）
                d["302"]["inputs"]["image"] = f"{args.first_dir}/{nm}.jpg"
                d["303"]["inputs"]["image"] = f"{args.last_dir}/{nm}.jpg"
                d["6"]["inputs"]["first_frame"] = ["302", 0]
                d["6"]["inputs"]["last_frame"] = ["303", 0]
                d["6"]["inputs"]["task_type"] = "Hybrid"
            json.dump(d, open(f"{OUT}/wf_{nm}.json", "w", encoding="utf-8"), ensure_ascii=False)
            made += 1
    print(f"[✓] 变体 {args.variant} → {OUT}  共 {made} 套")


if __name__ == "__main__":
    main()
