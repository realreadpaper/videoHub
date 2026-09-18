#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
通用终版合成器 —— 单镜 15s 长片后期总装
用法:
  python3 finish_film.py --film 01_周星驰_三十八万八        # 默认：无字幕成片 + 外挂字幕文件
  python3 finish_film.py --film 02_姜文_老子不娶了 --burn   # 额外再烧一版硬字幕
  python3 finish_film.py --film 02_姜文_老子不娶了 --dry    # 只算时间窗，不出片

字幕策略（2026-09-14 定稿）:
  **成片不烧字幕**。字幕一律以独立外挂文件交付（.srt / .vtt），
  由播放器或剪辑软件自行挂载。理由：
    - 平台审核/二创/多语种都要能关掉字幕，烧死就不可逆；
    - 模型自发字幕是乱码，本来就得清掉，与其补一层不如不补；
    - 外挂字幕改一个字不用重编码整片。
  只有明确要投短视频平台竖版直发时，才用 --burn 再出一版硬的。

前置:
  shots/shot01.mp4 ... shot08.mp4   （从远端 final/ 拉回）
  ../<film>/manifest.json           （含 dialogue_cn）

做什么:
  1) 用 ffmpeg silencedetect 尝试定位每镜语音区间 -> 字幕时间窗
     （H3 音轨实测被环境音盖满，多数落回整镜内缩覆盖）
  2) 按各镜在成片中的累计起点，生成 .srt / .vtt 外挂字幕
  3) concat 无损拼接 -> 两遍 loudnorm 精确 EBU R128 (I=-16/TP=-1.5/LRA=11)
     单遍 loudnorm 是动态模式靠估计，实测只能到 -18.5 LUFS，必须两遍
  4) [--burn] 额外用 Pillow 渲染中文硬字幕 + overlay 烧一版
     （本机 homebrew ffmpeg 没编 drawtext，走 PIL+overlay 绕开）
产出:
  <片名>_全片.mp4          无字幕成片（主交付）
  <片名>_字幕.srt          外挂字幕
  <片名>_字幕.vtt          外挂字幕（Web 版）
  <片名>_全片_硬字幕版.mp4  [仅 --burn]
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))

# 字幕逻辑全部委托 make_subs.py —— 单一真源。
# 成片要烧的字幕与外挂字幕必须同一套时间窗，否则两边对不上。
sys.path.insert(0, HERE)
from make_subs import (detect_voice, window_full, window_voice,
                       ffprobe_dur as _ffprobe_dur, write_srt, write_vtt)

W, H = 1344, 768
FONT_SIZE = 46
BOTTOM_MARGIN = 62
STROKE = 3
WRAP = 18

FONTS = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/STHeiti Light.ttc",
    "/Library/Fonts/Arial Unicode.ttf",
]

# ---------- 基础工具 ----------
def srcp_of(shots_dir, no):
    """取某镜的底片：优先用 `shots_clean/` 里 delogo 清理过的版本（若存在）。
    残字检测见 detect_residual_sub.py —— 模型自发乱码字幕必须先抹掉再合成。"""
    c = os.path.join(shots_dir + "_clean", "shot%02d.mp4" % no)
    return c if os.path.exists(c) else os.path.join(shots_dir, "shot%02d.mp4" % no)


def ffprobe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip().split(",")[0])
    except Exception:
        return 0.0


def load_font(size):
    from PIL import ImageFont
    for p in FONTS:
        if not os.path.exists(p):
            continue
        for kw in ({"index": 0}, {}):
            try:
                return ImageFont.truetype(p, size, **kw)
            except Exception:
                continue
    raise SystemExit("找不到可用的中文字体")


# ---------- 1. 语音区间检测（实现在 make_subs.py，此处只保留别名） ----------
def pick_window(mp4, dur):
    """挑台词时间窗 —— 与外挂字幕共用同一套（详见 make_subs.window_voice）"""
    return window_voice(mp4, dur)


# ---------- 2. 字幕渲染 ----------
def render_png(text, path):
    from PIL import Image, ImageDraw
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    f = load_font(FONT_SIZE)
    lines, cur = [], ""
    for ch in text:
        cur += ch
        if len(cur) >= WRAP:
            lines.append(cur); cur = ""
    if cur:
        lines.append(cur)
    lh = int(FONT_SIZE * 1.42)
    y = H - BOTTOM_MARGIN - lh * len(lines)
    for ln in lines:
        bb = d.textbbox((0, 0), ln, font=f, stroke_width=STROKE)
        x = (W - (bb[2] - bb[0])) // 2 - bb[0]
        d.text((x, y), ln, font=f, fill=(255, 255, 255, 255),
               stroke_width=STROKE + 2, stroke_fill=(0, 0, 0, 240))
        d.text((x, y), ln, font=f, fill=(255, 255, 255, 255), stroke_width=0)
        y += lh
    img.save(path)
    return path


def burn(inp, png, t1, t2, out):
    if os.path.exists(out) and os.path.getsize(out) > 10000:
        return True
    vf = "[0:v][1:v]overlay=0:0:enable='between(t,%.2f,%.2f)'[v]" % (t1, t2)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", inp, "-i", png,
                        "-filter_complex", vf, "-map", "[v]", "-map", "0:a",
                        "-c:v", "libx264", "-crf", "16", "-preset", "medium",
                        "-pix_fmt", "yuv420p", "-c:a", "copy", out],
                       capture_output=True, text=True)
    if r.returncode:
        print("     ffmpeg err:", r.stderr[-300:])
    return os.path.exists(out)


# ---------- 3. 拼接 + 两遍响度归一 ----------
def measure(mp4):
    r = subprocess.run(["ffmpeg", "-hide_banner", "-i", mp4, "-af",
                        "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                        "-f", "null", "-"], capture_output=True, text=True)
    t = r.stderr
    return json.loads(t[t.rfind("{"):t.rfind("}") + 1])


def concat(files, out, tmp, tag):
    lst = os.path.join(tmp, "concat_%s.txt" % tag)
    with open(lst, "w") as f:
        for p in files:
            f.write("file '%s'\n" % p)
    raw = os.path.join(tmp, "raw_%s.mp4" % tag)
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
                        "-i", lst, "-c", "copy", raw], capture_output=True, text=True)
    if r.returncode or not os.path.exists(raw):
        print("   拼接失败:", r.stderr[-300:]); return False
    m = measure(raw)
    af = ("loudnorm=I=-16:TP=-1.5:LRA=11:measured_I=%s:measured_TP=%s:"
          "measured_LRA=%s:measured_thresh=%s:offset=%s:linear=true:print_format=summary"
          % (m["input_i"], m["input_tp"], m["input_lra"], m["input_thresh"], m["target_offset"]))
    r = subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", raw, "-c:v", "copy",
                        "-af", af, "-c:a", "aac", "-b:a", "192k", out],
                       capture_output=True, text=True)
    if r.returncode:
        print("   归一失败:", r.stderr[-300:])
    if os.path.exists(raw):
        os.remove(raw)
    return os.path.exists(out)


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", required=True, help="如 01_周星驰_三十八万八")
    ap.add_argument("--dry", action="store_true", help="只算时间窗不出片")
    ap.add_argument("--burn", action="store_true",
                    help="额外烧一版硬字幕（默认不烧，只给外挂字幕文件）")
    a = ap.parse_args()

    film_dir = os.path.join(BASE, a.film)
    man_p = os.path.join(film_dir, "manifest.json")
    shots = os.path.join(film_dir, "shots")
    tmp = os.path.join(film_dir, "_subtmp")
    if not os.path.exists(man_p):
        sys.exit("缺 manifest: %s" % man_p)
    if not os.path.exists(shots):
        sys.exit("缺 shots/ 目录: %s（先把远端 final/ 拉回来）" % shots)
    os.makedirs(tmp, exist_ok=True)

    m = json.load(open(man_p, encoding="utf-8"))
    title = a.film.split("_", 1)[-1]
    out_clean = os.path.join(film_dir, "%s_全片.mp4" % title)
    out_sub = os.path.join(film_dir, "%s_全片_硬字幕版.mp4" % title)

    clean_dir = shots + "_clean"      # 用 detach_residual_sub 判出残字、delogo 处理过的镜放这里
    clean_used = []
    if os.path.isdir(clean_dir):
        clean_used = sorted(f for f in os.listdir(clean_dir) if f.endswith(".mp4"))
        if clean_used:
            print("  已启用清理版镜头（shots_clean/）: %s" % ", ".join(clean_used))

    missing = [s for s in m["shots"]
               if not os.path.exists(srcp_of(shots, s["no"]))]
    if missing:
        sys.exit("缺底片: %s" % [("shot%02d.mp4" % s["no"]) for s in missing])

    print("═" * 78)
    print("  %s · 后期总装（%d 镜）" % (title, len(m["shots"])))
    print("═" * 78)

    subbed, timing, cues = {}, {}, []
    cursor = 0.0                      # 各镜在成片中的累计起点
    for sh in m["shots"]:
        no = sh["no"]
        srcp = srcp_of(shots, no)
        dur = ffprobe_dur(srcp)
        dlg = (sh.get("dialogue_cn") or "").strip()
        if not dlg:
            print("  镜 %02d  无台词，原样通过 (%.2fs)" % (no, dur))
            cursor += dur
            continue
        (t1, t2), why = pick_window(srcp, dur)
        timing[no] = (t1, t2)
        # 外挂字幕时间轴 = 成片绝对时间
        cues.append((cursor + t1, cursor + t2, dlg.split("／")[0].strip()))
        print("  镜 %02d  字幕窗 %.2f ~ %.2fs (成片 %.2f~%.2f) [%s]「%s」"
              % (no, t1, t2, cursor + t1, cursor + t2, why, dlg[:22]))
        cursor += dur
        if a.dry:
            continue
        if a.burn:
            png = render_png(dlg.split("／")[0].strip(),
                             os.path.join(tmp, "sub%02d.png" % no))
            outp = os.path.join(tmp, "sub_shot%02d.mp4" % no)
            if burn(srcp, png, t1, t2, outp):
                subbed[no] = outp

    if a.dry:
        print("\n[dry] 未出片，时间窗已列出。确认无误后去掉 --dry 重跑。")
        return

    # —— 外挂字幕（主交付形态）——
    srt_p = os.path.join(film_dir, "%s_字幕.srt" % title)
    vtt_p = os.path.join(film_dir, "%s_字幕.vtt" % title)
    write_srt(cues, srt_p)
    write_vtt(cues, vtt_p)
    print("  ✔ 外挂字幕  ->", os.path.basename(srt_p), "/", os.path.basename(vtt_p))

    order = [s["no"] for s in m["shots"]]
    clean_files = [srcp_of(shots, n) for n in order]

    print("\n  合成中...")
    if concat(clean_files, out_clean, tmp, "clean"):
        print("  ✔ 无字幕成片 ->", os.path.basename(out_clean))
    if a.burn:
        sub_files = [subbed.get(n, srcp_of(shots, n))
                     for n in order]
        if concat(sub_files, out_sub, tmp, "sub"):
            print("  ✔ 硬字幕版  ->", os.path.basename(out_sub))
    json.dump({str(k): v for k, v in timing.items()},
              open(os.path.join(film_dir, "subtitle_timing.json"), "w"),
              ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
