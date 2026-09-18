#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""画面「禁字」检测门 —— 铁律的**预警器**（权威判据见 scan_text_band.py）。

背景
----
prompt 里已经写死 `no subtitles, no captions, no on-screen text ...`，
但 H3 是**临摹型**生成器：训练数据里大量带烧死字幕的短视频，它会把「字幕条 + 字符纹理」
当画面元素画出来（实测片1 集中在 22–32s 与 178–250s，约占全片 23% 的画面时间）。
纯负向 prompt 压不住 —— 所以必须有**独立于 prompt 的机器检测**。

⚠ 这个工具的实测边界（别对它期望过高）
--------------------------------------
tesseract 对 H3 画出的**伪汉字**几乎没有识别能力（真有字幕的帧常常 OCR 出 0 个汉字），
而对轮椅辐条 / 肉块 / 金属划痕产生大量误报。实测 6 项 OCR 几何特征（token 数、字符数、
横向跨度、字高离散、间距离散、置信度）在正负样本上**完全重叠**，无法分离；
片1 首轮 12 处报错经逐帧目视核实**全部是误报**。
所以本工具的定位是：**预警 + 定位 + 生成复核素材**，不是终审。

★ 时域一致性（本工具唯一可靠的降噪手段）
--------------------------------------
单帧命中多半是纹理巧合；而字幕条**在一个镜头内是持续存在的**。
因此：镜内 ≥2 帧命中 → FAIL；仅 1 帧命中 → REVIEW（待人工确认）；0 帧 → PASS。
片1 改用该判据后，12 处误报全部降为 REVIEW。

权威判据：`scan_text_band.py` 生成字幕带接触表 → 人眼逐格 30 秒扫完。
两者配合使用：scan_text_band 定生死，check_no_text 给时间码线索。

用法
----
  # 逐镜体检（推荐：定位到具体哪一镜）
  python3 check_no_text.py --shots _deliver/shots_film1

  # 整片体检（自动换算镜号 = t // 15.0417 + 1）
  python3 check_no_text.py --video _deliver/xx_全片.mp4 --n 8

  # 单帧调试
  python3 check_no_text.py --frame _review/zoom/s12_full.jpg

  # 输出 JSON（给流水线用，PARSE 一个字段即可判断）
  python3 check_no_text.py --video xx.mp4 --json out.json

退出码：0 = 全过；1 = 有命中（CI/流水线据此拦截）
"""
import argparse
import csv
import io
import json
import os
import subprocess
import sys
import tempfile

try:
    from PIL import Image, ImageOps
except ImportError:
    sys.exit("需要 Pillow：pip install Pillow")

# ---- 判定参数（宽松侧，宁可误报） ----
CONF_THR = 30          # token 置信度下限（tesseract 0-100）
MIN_TOKENS = 3         # 成行所需最少 token 数
MIN_CHARS = 4          # 成行簇最少总字符数
MIN_H = 8              # token 最小字高（px，放大后）
BAND_TOP = 0.52        # 只认画面下 48% 区域（字幕基本不超过画面中线太多）
XSPAN_MIN = 0.22       # 成行簇横向跨度 ≥ 画面宽 22%（字幕是横贯的一条，
                       # 衣服纹理/建筑线条凑出的"假行"通常很窄）
UPSCALE = 1.6          # 预处理放大倍数
SHOT_SEC = 15.0417     # 单镜时长（361 帧 @24fps）


def prep(img_path):
    im = Image.open(img_path).convert("L")
    w, h = im.size
    im = im.resize((int(w * UPSCALE), int(h * UPSCALE)), Image.LANCZOS)
    return ImageOps.autocontrast(im, cutoff=1)


def toks_of(im):
    tmp = tempfile.mktemp(suffix=".png")
    im.save(tmp)
    try:
        r = subprocess.run(
            ["tesseract", tmp, "stdout", "-l", "eng+chi_sim", "--psm", "11", "tsv"],
            capture_output=True, text=True, timeout=90)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)
    out = []
    for d in csv.DictReader(io.StringIO(r.stdout), delimiter="\t"):
        try:
            c = float(d.get("conf") or -1)
        except (TypeError, ValueError):
            continue
        t = (d.get("text") or "").strip()
        if c < CONF_THR or not t:
            continue
        try:
            L, T, W, H = (int(d["left"]), int(d["top"]),
                          int(d["width"]), int(d["height"]))
        except (KeyError, TypeError, ValueError):
            continue
        if H < MIN_H:
            continue
        out.append({"t": t, "conf": c, "left": L, "top": T, "w": W, "h": H})
    return out


def lines_of(toks, w, h):
    """把 token 聚成「水平成行簇」——字幕的本质特征。"""
    res = []
    for a in toks:
        grp = [b for b in toks
               if abs(b["top"] - a["top"]) <= max(a["h"], b["h"]) * 0.8
               and 0.35 <= b["h"] / max(a["h"], 1) <= 2.8]
        if len(grp) < MIN_TOKENS:
            continue
        grp.sort(key=lambda x: x["left"])
        chars = sum(len(x["t"]) for x in grp)
        if chars < MIN_CHARS:
            continue
        key = (round(grp[0]["top"] / 14), chars)
        if key in [r["key"] for r in res]:
            continue
        x0 = grp[0]["left"]
        x1 = grp[-1]["left"] + grp[-1]["w"]
        if (x1 - x0) < w * XSPAN_MIN:
            continue
        res.append({
            "key": key,
            "text": " ".join(x["t"] for x in grp),
            "chars": chars,
            "y_ratio": round(grp[0]["top"] / h, 3),
            "conf": round(sum(x["conf"] for x in grp) / len(grp), 1),
            "x_span": (x0, x1),
            "x_span_ratio": round((x1 - x0) / w, 3),
        })
    return [r for r in res if r["y_ratio"] > BAND_TOP]


def check_frame(img_path):
    im = prep(img_path)
    toks = toks_of(im)
    hits = lines_of(toks, *im.size)
    return {"frame": img_path, "tokens": len(toks), "hits": hits,
            "verdict": "FAIL" if hits else "PASS"}


def frames_of(video, n, start=0.0, dur=None):
    """均匀抽 n 帧，跳过极少数黑场/转场首帧。"""
    if dur is None:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                            "-of", "csv=p=0", video], capture_output=True, text=True)
        dur = float(r.stdout.strip() or 15.0)
    out = []
    for i in range(n):
        t = start + dur * (i + 0.5) / n
        p = tempfile.mktemp(suffix=".png")
        subprocess.run(["ffmpeg", "-v", "error", "-ss", "%.3f" % t, "-i", video,
                        "-frames:v", "1", "-pix_fmt", "gray", p, "-y"],
                       capture_output=True)
        if os.path.exists(p) and os.path.getsize(p) > 0:
            out.append((round(t, 2), p))
    return out


def cleanup(paths):
    for p in paths:
        if os.path.exists(p):
            os.unlink(p)


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--video", help="整片 mp4")
    g.add_argument("--shots", help="逐镜 mp4 目录")
    g.add_argument("--frame", help="单帧图片（调试用）")
    ap.add_argument("--n", type=int, default=6, help="每镜/整片抽帧数")
    ap.add_argument("--json", dest="json_out", default=None)
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    if not subprocess.run(["which", "tesseract"], capture_output=True).returncode == 0:
        sys.exit("未找到 tesseract：brew install tesseract")

    results = []

    if a.frame:
        r = check_frame(a.frame)
        results.append({"id": os.path.basename(a.frame), **r})

    elif a.shots:
        files = sorted(f for f in os.listdir(a.shots) if f.endswith(".mp4"))
        for i, fn in enumerate(files):
            path = os.path.join(a.shots, fn)
            fr = frames_of(path, a.n)
            hit_frames = []
            for t, p in fr:
                r = check_frame(p)
                if r["hits"]:
                    hit_frames.append((t, r))
            cleanup([p for _, p in fr])
            # ★ 时域一致性：单帧命中多半是纹理巧合（实测 12/12 误报）；
            #   字幕条在镜内是持续的 → ≥2 帧命中才判 FAIL。
            if len(hit_frames) >= 2:
                t, r = max(hit_frames, key=lambda x: len(x[1]["hits"]))
                results.append({"id": fn, "t": t, "verdict": "FAIL",
                                "n_hit_frames": len(hit_frames), **r})
            elif len(hit_frames) == 1:
                t, r = hit_frames[0]
                results.append({"id": fn, "t": t, "verdict": "REVIEW",
                                "n_hit_frames": 1, **r})
            else:
                results.append({"id": fn, "t": None, "hits": [], "verdict": "PASS",
                                "tokens": None, "n_hit_frames": 0})
            if not a.quiet:
                last = results[-1]
                print("  [%2d/%2d] %-26s %-6s %s" % (
                    i + 1, len(files), fn, last["verdict"],
                    ("t=%.1fs×%d帧 " % (last["t"], last["n_hit_frames"])
                     + last["hits"][0]["text"][:44]) if last["hits"] else ""))

    else:  # --video
        fr = frames_of(a.video, a.n)
        hit_frames = []
        for t, p in fr:
            r = check_frame(p)
            if r["hits"]:
                hit_frames.append((t, r))
        cleanup([p for _, p in fr])
        if len(hit_frames) >= 2:
            for t, r in hit_frames[:12]:
                results.append({"id": "shot%02d" % (int(t // SHOT_SEC) + 1),
                                "t": t, "verdict": "FAIL", **r})
        elif len(hit_frames) == 1:
            t, r = hit_frames[0]
            results.append({"id": "shot%02d" % (int(t // SHOT_SEC) + 1),
                            "t": t, "verdict": "REVIEW", **r})
        elif not a.quiet:
            print("  （整片抽帧无命中）")

    bad = [r for r in results if r.get("verdict") == "FAIL"]
    rev = [r for r in results if r.get("verdict") == "REVIEW"]
    n_checked = len(results)

    print()
    print("=" * 72)
    print("禁字预警器：检查 %d 项 ｜ FAIL %d ｜ REVIEW(待人工确认) %d"
          % (n_checked, len(bad), len(rev)))
    if bad:
        print("-" * 72)
        for r in bad:
            h = r["hits"][0]
            tt = ("t=%.2fs " % r["t"]) if r.get("t") is not None else ""
            print("  ❌ %-24s %s×%d帧 y=%.0f%% 「%s」"
                  % (r["id"], tt, r.get("n_hit_frames", "?"),
                     h["y_ratio"] * 100, h["text"][:52]))
    if rev:
        print("-" * 72)
        print("  ⚠ REVIEW（单帧命中，多为纹理误报，请对照字幕带接触表确认）：")
        for r in rev[:12]:
            print("     %-24s t=%.2fs「%s」" % (r["id"], r["t"], r["hits"][0]["text"][:40]))
    print("-" * 72)
    print("★ 权威判据是 scan_text_band.py 的字幕带接触表（人眼逐格扫）。")
    print("  本工具只做预警与时间码定位 —— tesseract 对伪汉字识别弱、对纹理误报多。")
    if bad:
        print("  处置：① 改 seed / 加强 prompt 重跑该镜（首选）")
        print("        ② 固定字幕带局部处理：ffmpeg delogo / boxblur（兜底）")
        print("        ③ 裁掉下方字幕带后重构图（代价小、构图略变）")
    print("=" * 72)

    if a.json_out:
        with open(a.json_out, "w", encoding="utf-8") as f:
            json.dump({"checked": n_checked, "failed": len(bad), "results": results},
                      f, ensure_ascii=False, indent=2)
        print("JSON → %s" % a.json_out)

    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
