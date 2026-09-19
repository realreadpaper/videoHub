#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
试拍 4 镜的资产准备 v2：原声干声 + 三张参考图（ref / first / last）。

★ v2 变更（对齐服务器现行 Hybrid 做法，见 /workspace/dy_key/wf_S8/）：
  现行工作流在 node 6 上挂三张图，缺一不可：
    ref_images.ref_image_0  → 身份/产品参考（dy_full_ref_v3）
    first_frame             → 单元首帧，钉住"起"的画面
    last_frame              → 单元末帧，钉住"合"的画面
  从原片 mp4 精确抽 first/last（单元起点/终点），比从 keyframes 取中点帧准确。

干声路线 = 「从原片按单元区间直切原声」（与 dy_full_a/ 产线一致，不是 TTS）。
镜长统一 107 帧 = 4.458s；语音结束后余量用 apad 补静音，给"合"拍点留反应空间。
"""
import json
import os
import re
import subprocess
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)          # .../2026-09-19
OUT = os.path.join(HERE, "pilot")

FPS = 24
FRAMES = 107
DUR = FRAMES / FPS                    # 4.458333...

PICKS = [
    # key, 视频ID, uid, 类型, ref 来源（keyframes 选帧 / 产品图）
    ("dy4_u007_stomp",   "7661791104643797617", "u007", "剧情", "kf"),
    ("dy4_u060_tearopen", "7661791104643797617", "u060", "产品", "prod"),
    ("dy5_u055_expose",  "7663019839170397945", "u055", "剧情", "kf"),
    ("dy5_u042_tender",  "7663019839170397945", "u042", "产品", "kf"),
]


def run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("FAILED: %s\n%s" % (" ".join(cmd), r.stderr[-800:]))
    return r


def wav_dur(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def mid_frame(kf_dir, t0, t1):
    """keyframes 命名 frame-<秒>s.jpg；取落在 [t0,t1] 内、最接近区间中点的一帧。"""
    best = None
    for fn in os.listdir(kf_dir):
        m = re.match(r"frame-(\d+)_(\d+)s\.jpg$", fn) or re.match(r"frame-(\d+)s\.jpg$", fn)
        if not m:
            continue
        g = m.groups()
        t = float(g[0] + ("." + g[1] if len(g) > 1 else ""))
        if not (t0 - 0.3 <= t <= t1 + 0.3):
            continue
        score = abs(t - (t0 + t1) / 2)
        if best is None or score < best[0]:
            best = (score, fn, t)
    return (best[1], best[2]) if best else (None, None)


def main():
    os.makedirs(os.path.join(OUT, "voice"), exist_ok=True)
    for sub in ("ref", "first", "last"):
        os.makedirs(os.path.join(OUT, sub), exist_ok=True)
    manifest = {"frames": FRAMES, "fps": FPS, "duration": round(DUR, 4), "shots": []}

    for key, vid, uid, kind, refsrc in PICKS:
        d = os.path.join(BASE, vid)
        mp4 = os.path.join(BASE, vid + ".mp4")
        units = json.load(open(os.path.join(d, "units.json")))["units"]
        u = next(x for x in units if x["uid"] == uid)
        t0, t1 = u["t_start"], u["t_end"]
        vdur = t1 - t0

        # ---- 1. 原声干声：切 [t0, t1] 并 apad 到镜长 ----
        dst = os.path.join(OUT, "voice", key + ".wav")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.4f" % t0, "-t", "%.4f" % vdur,
             "-i", os.path.join(d, "audio_16k.wav"), "-af", "apad=whole_dur=%.4f" % DUR,
             "-ar", "16000", "-ac", "1", dst])

        # ---- 2. first / last：从原片 mp4 精确抽帧，统一成 768x1344 ----
        f_first = os.path.join(OUT, "first", key + ".jpg")
        f_last = os.path.join(OUT, "last", key + ".jpg")
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.4f" % t0, "-i", mp4,
             "-frames:v", "1", "-vf", "scale=768:1344", "-q:v", "2", f_first])
        run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.4f" % max(0.0, t1 - 1.0 / 30),
             "-i", mp4, "-frames:v", "1", "-vf", "scale=768:1344", "-q:v", "2", f_last])

        # ---- 3. ref：身份/产品锚点 ----
        if refsrc == "prod":
            src_ref = os.path.normpath(os.path.join(BASE, "..", "..", "..",
                                                    "C9D9F4F4735AD97DE259A3A3A0B02009.jpg"))
            f_ref = os.path.join(OUT, "ref", key + ".jpg")
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", src_ref,
                 "-vf", "scale=768:1344:force_original_aspect_ratio=decrease,"
                        "pad=768:1344:(ow-iw)/2:(oh-ih)/2:color=white",
                 "-q:v", "2", f_ref])
            ref_note = "产品原图（等比缩放到框内，白底补齐）"
        else:
            fn, ft = mid_frame(os.path.join(d, "keyframes"), t0, t1)
            f_ref = os.path.join(OUT, "ref", key + ".jpg")
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(d, "keyframes", fn),
                 "-vf", "scale=768:1344", "-q:v", "2", f_ref])
            ref_note = "%s @%.2fs" % (fn, ft)

        manifest["shots"].append({
            "key": key, "video": vid, "uid": uid, "kind": kind,
            "dialogue": u["dialogue"], "t_start": t0, "t_end": t1,
            "voice_dur": round(vdur, 3), "pad_tail": round(DUR - vdur, 3),
            "src_shots": u["src_shots"], "beats": u["beats"], "ref_note": ref_note,
            "voice": "dy4_voice/%s.wav" % key,
            "ref": "dy4_ref/%s.jpg" % key,
            "first": "dy4_first/%s.jpg" % key,
            "last": "dy4_last/%s.jpg" % key,
        })
        print("[ok] %-22s %-4s %6.2f-%6.2f 语音%5.2fs 补%5.2fs | ref=%s"
              % (key, kind, t0, t1, vdur, DUR - vdur, ref_note))

    json.dump(manifest, open(os.path.join(OUT, "pilot.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    cost = 0.812 * FRAMES + 0.002129 * FRAMES ** 2 - 1.3        # 4 步拟合
    print("\n[done] → pilot/pilot.json")
    print("       镜长 %.4fs / %d 帧 | 4 步单镜≈%.0fs | 双卡 4 镜≈%.1f 分钟（8 步约 ×1.7）"
          % (DUR, FRAMES, cost, 2 * cost / 60))


if __name__ == "__main__":
    main()
