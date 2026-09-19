#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""百分百复刻：为 373 镜生成「原声切片 + 参考帧 + 工作流」。

与旧版的三点根本差异：
1. 音频 = 原片该镜音轨切片（尾部补静音到 length），不是 TTS → 音色/环境音/口型全对
2. 参考图 = 原片该镜关键帧（裁底部 10% 防硬字幕）→ 构图/人物/服装照抄
3. length = 原片镜长向上吸附 17n+5 → 不拖沓，且帧数降到 1/4（单镜 18–110s）
"""
import json, os, subprocess, shutil

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18"
TPL = f"{HERE}/wf_skel/wf_dy1_s01_open_kick.json"
OUT_WF = f"{HERE}/wf_full"
OUT_A = f"{HERE}/full_a"
OUT_R = f"{HERE}/full_ref"
FF = "/usr/local/bin/ffmpeg"

KEY = {"01_报恩": ("dy1", "7661613126736204025"),
       "02_继母": ("dy2", "7686341460064787045"),
       "03_挑食": ("dy3", "7664454812574337402")}

# ===== 画面规范（沿用上一版已审查通过的文本，保持效果一致）=====
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

def lens_of(framing):
    if "远" in framing: return "24 mm wide lens, deep focus"
    if "特写" in framing or "近景" in framing: return "50 mm lens, shallow depth of field"
    if "中近" in framing: return "50 mm lens, shallow depth of field"
    return "35 mm lens, moderate depth of field"

def make_prompt(r, sec):
    ts = f"00:00.000 - 00:{sec:06.3f}"
    speaks = bool(r["line"].strip())
    perf = (f"{r['speaker']} delivers the line; the mouth movement is driven strictly by the supplied "
            f"reference audio and stops the instant the audio goes quiet. "
            if speaks else
            "No one speaks in this shot; ambient room tone and action only, mouths closed and still. ")
    size = r["framing"] or "medium shot"
    return (
        "integrated_multimodal_description:\n"
        f"<Reference frame: <Picture 1> is a real frame captured from this exact shot of the original footage. "
        f"It is the authoritative reference for what appears in frame - reproduce its camera framing, shot size, "
        f"subject placement, wardrobe, hairstyle, props, lighting and colour faithfully. Do not redesign the shot.>\n\n"
        f"<Scene: {r['scene']}>\n\n"
        f"<Shot: {size}, cinematic 9:16 vertical framing, {lens_of(size)}, photorealistic live-action footage, "
        f"the shot runs the full {sec:.3f} seconds>\n\n"
        f"<Performance: {perf}Keep natural micro-expressions and small continuous body motion; never freeze into a still frame.>\n\n"
        f"<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, "
        f"ARRI Alexa look, fine film grain, {ANTI_GREASY}{NO_TEXT_SHORT}>\n\n"
        f"[{ts}] The shot holds the reference framing continuously; {perf.rstrip()} "
        f"Subtle handheld breathing and continuous ambient motion throughout.\n\n"
        f"{STRICT}"
    )

def cut_audio(mp4, start, dur, target, out):
    """切原片该镜音轨 → 尾部补静音到 target（保证 ≥ 原片镜长）"""
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [FF, "-v", "error", "-y", "-ss", f"{start:.3f}", "-t", f"{dur:.3f}", "-i", mp4,
           "-af", f"apad,atrim=0:{target:.3f},asetpts=N/SR/TB",
           "-ar", "16000", "-ac", "1", out]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and os.path.exists(out)

def prep_ref(kf_dir, kf, out):
    """参考帧：裁掉底部 10%（防原片硬字幕）并缩放到输出分辨率"""
    src = os.path.join(kf_dir, kf)
    if not os.path.exists(src):
        return False
    os.makedirs(os.path.dirname(out), exist_ok=True)
    cmd = [FF, "-v", "error", "-y", "-i", src,
           "-vf", "crop=iw:ih*0.90:0:0,scale=768:1344:force_original_aspect_ratio=increase,crop=768:1344",
           "-q:v", "3", out]
    r = subprocess.run(cmd, capture_output=True)
    return r.returncode == 0 and os.path.exists(out)

def main():
    rows = json.load(open(f"{HERE}/shots_all.json", encoding="utf-8"))
    tpl = json.load(open(TPL, encoding="utf-8"))
    os.makedirs(OUT_WF, exist_ok=True)

    # 模板只保留 ref_image_0（删掉第二张参考图节点 301）
    for k in ("301",):
        tpl.pop(k, None)
    tpl["6"]["inputs"].pop("ref_images.ref_image_1", None)

    made = fail_a = fail_r = 0
    manifest = {}
    for film, lst in rows.items():
        tag, vid = KEY[film]
        mp4 = f"{BASE}/{vid}.mp4"
        kfd = f"{BASE}/{vid}/keyframes"
        for r in lst:
            idx = r["index"]; sec = r["sec"]; nm = f"{tag}_s{idx:03d}"
            wav = f"{OUT_A}/{nm}.wav"
            ref = f"{OUT_R}/{nm}.jpg"
            ok_a = cut_audio(mp4, r["start"], r["dur"], sec, wav)
            ok_r = prep_ref(kfd, r["kf"], ref)
            if not ok_a: fail_a += 1; print(f"  ✗ 音频失败 {nm}"); continue
            if not ok_r: fail_r += 1; print(f"  ✗ 参考帧失败 {nm}"); continue

            d = json.loads(json.dumps(tpl))
            d["14"]["inputs"]["scene_duration_seconds"] = sec
            d["13"]["inputs"]["audio"] = f"dy_full_a/{nm}.wav"
            d["300"]["inputs"]["image"] = f"dy_full_ref/{nm}.jpg"
            d["12"]["inputs"]["filename_prefix"] = f"dy_full/{nm}"
            d["6"]["inputs"]["prompt"] = make_prompt(r, sec)
            d["9"]["inputs"]["noise_seed"] = 20261022 + idx * 7 + hash(tag) % 1000
            json.dump(d, open(f"{OUT_WF}/wf_{nm}.json", "w", encoding="utf-8"), ensure_ascii=False)
            manifest[nm] = dict(film=film, index=idx, frames=r["frames"], sec=sec,
                                dur=r["dur"], speaker=r["speaker"], line=r["line"], seg=r["seg"])
            made += 1
        print(f"[{film}] {len(lst)} 镜 → {tag}_s001..{tag}_s{len(lst):03d}")

    json.dump(manifest, open(f"{HERE}/wf_full/_manifest.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print(f"\n[✓] 生成 {made} 套（音频缺失 {fail_a} / 参考帧缺失 {fail_r}）")
    print(f"    wf    {OUT_WF}")
    print(f"    音频  {OUT_A}")
    print(f"    参考图 {OUT_R}")

if __name__ == "__main__":
    main()
