#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐镜「节奏对齐」—— 把成片从 300.83s 收到原片的 286.13s。

问题
----
原片 286.13s，我们的成片 20 镜 × 15.0417s = 300.83s，多 14.70s。
但 audio-lock 下**每镜语音结束点由 TTS 实测决定**，多数镜贴在 14.82s（离镜尾仅 0.22s）
—— 机械「每镜裁尾 0.7s」会直接切掉最后半句台词。**这条路是死的，必须换。**

两种可落地模式
--------------
1. `--mode voice-safe`（零代价，推荐先看）
   只裁「末句结束 + tail」之后的纯静音。片1 实测 300.84 → 291.79s（省 9.05s）。
   剪掉的正是「话说完画面还在动」的空白 —— 观感改善最直接。

2. `--mode auto --target-total 286.13`（精确对齐，推荐最终用）
   对**整镜做等比提速 k**（`setpts=PTS/k` + `atempo=k`），再按 (末句结束/k + tail) 裁尾。
   因为音频与画面按同一倍数压缩，**音画对应关系逐帧不变 → 口型完全同步**，
   且 `atempo` 变速不变调（音色不变）。片1 解出 k≈1.027（只快 2.7%，基本无感），
   总长精确命中 286.13s。代价仅是人物动作快 2.7%。

   为什么这样能对齐：整片时长 = Σ min(d0, v_end/k + tail·k)/k，
   对 k 单调递减，二分即可求解。

3. `--speed 1.05` 手动指定倍率。

用法
----
  python3 trim_shots.py --shots _deliver/shots_film1 --lines _tts/film1 \
      --out _post/shots_film1 --mode auto --target-total 286.13 \
      --json _post/trim_report.json
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

SHOT_SEC = 15.0417   # 精修后单镜成片时长（361 帧 / 24fps）


def dur_of(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def load_lines(lines_dir, n):
    p = os.path.join(lines_dir, "shot%02d_lines.json" % n)
    if not os.path.exists(p):
        return []
    d = json.load(open(p, encoding="utf-8"))
    return d["lines"] if isinstance(d, dict) and "lines" in d else d


def plan_for(k, items, tail, min_keep):
    """给定倍率 k，算出每镜保留时长。"""
    plan, total = [], 0.0
    for it in items:
        d0, v_end = it["src"], it["voice_end"]
        compressed = d0 / k
        if v_end > 0:
            keep = min(compressed, v_end / k + tail)
        else:
            keep = compressed
        keep = max(keep, min_keep / k)
        keep = min(keep, compressed)
        plan.append({**it, "keep": keep, "cut": d0 - keep})
        total += keep
    return plan, total


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", required=True)
    ap.add_argument("--lines", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--json", default=None)
    ap.add_argument("--mode", choices=["voice-safe", "speed", "auto"], default="voice-safe")
    ap.add_argument("--speed", type=float, default=1.0, help="--mode speed 的倍率")
    ap.add_argument("--target-total", type=float, default=None, help="--mode auto 的目标总时长")
    ap.add_argument("--tail", type=float, default=0.32, help="句末保留静音（秒）")
    ap.add_argument("--min-keep", type=float, default=6.0, help="单镜最短保留时长（压缩前口径）")
    ap.add_argument("--min-margin", type=float, default=0.12, help="裁后距末句的最小安全余量")
    ap.add_argument("--crf", type=int, default=16)
    ap.add_argument("--audio-bitrate", default="192k")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    files = sorted(f for f in os.listdir(a.shots) if f.endswith(".mp4"))
    if not files:
        sys.exit("分镜目录为空: %s" % a.shots)

    items = []
    for i, fn in enumerate(files, 1):
        src = os.path.join(a.shots, fn)
        d0 = dur_of(src) or SHOT_SEC
        lines = load_lines(a.lines, i)
        v_end = max((l["t"] + l["dur"]) for l in lines) if lines else 0.0
        items.append({"shot": i, "file": fn, "src": round(d0, 4),
                      "voice_end": round(v_end, 4), "path": src})

    src_total = sum(it["src"] for it in items)

    # ── 求倍率 k ──────────────────────────────────────────────
    if a.mode == "voice-safe":
        k = 1.0
    elif a.mode == "speed":
        k = a.speed
    else:
        if not a.target_total:
            sys.exit("--mode auto 需要 --target-total")
        lo, hi = 1.0, 1.6
        for _ in range(60):
            mid = (lo + hi) / 2
            _, tot = plan_for(mid, items, a.tail, a.min_keep)
            if tot > a.target_total:
                lo = mid
            else:
                hi = mid
        k = (lo + hi) / 2

    plan, new_total = plan_for(k, items, a.tail, a.min_keep)

    print("倍率 k = %.4f  (%s)" % (k, "不加速" if abs(k - 1) < 1e-6 else "+%.2f%% 语速/画面" % ((k - 1) * 100)))
    print()
    print("镜 | 原长 | 语音结束 | 新长 | 裁掉 | 余量")
    print("-" * 62)
    for p in plan:
        marg = p["keep"] * k - p["voice_end"] if p["voice_end"] else 0
        print(" %2d | %6.3f | %8.3f | %6.3f | %5.3f | %5.3f"
              % (p["shot"], p["src"], p["voice_end"], p["keep"], p["cut"], marg))
    print("-" * 62)
    print("原总长 %.2fs → 新总长 %.2fs   裁掉 %.2fs (%.2f%%)"
          % (src_total, new_total, src_total - new_total, (src_total - new_total) / src_total * 100))

    # ── 安全校验：只对「实际发生裁切」的镜判定 ────────────────
    bad = [(p["file"], p["voice_end"], p["keep"] * k)
           for p in plan
           if p["voice_end"] and p["cut"] > 1e-3 and (p["keep"] * k - p["voice_end"]) < a.min_margin]
    if bad:
        print("\n✘ 安全校验未通过（裁后距末句 < %.2fs，会切语音）：" % a.min_margin)
        for fn, v, kk in bad:
            print("   %s  末句 %.3f / 裁后 %.3f" % (fn, v, kk))
        sys.exit(2)
    print("✔ 安全校验通过：所有裁切镜均保留 ≥ %.2fs 句末余量" % a.min_margin)

    if a.dry_run:
        print("\n(dry-run，未写出)")
        return

    os.makedirs(a.out, exist_ok=True)
    vf = "setpts=PTS/%.6f" % k
    af = "atempo=%.6f" % k
    for p in plan:
        dst = os.path.join(a.out, p["file"])
        if abs(p["cut"]) < 1e-3 and abs(k - 1.0) < 1e-6:
            shutil.copy2(p["path"], dst)
            continue
        cmd = ["ffmpeg", "-v", "error", "-i", p["path"],
               "-filter_complex", "[0:v]%s[v];[0:a]%s[a]" % (vf, af),
               "-map", "[v]", "-map", "[a]", "-t", "%.4f" % p["keep"],
               "-c:v", "libx264", "-preset", "medium", "-crf", str(a.crf),
               "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", a.audio_bitrate,
               "-ar", "48000", "-movflags", "+faststart", dst, "-y"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            sys.exit("处理失败 %s\n%s" % (p["file"], r.stderr[-700:]))
        print("  ✔ %s  %.3f → %.3f  (裁 %.3fs)" % (p["file"], p["src"], dur_of(dst), p["cut"]))

    if a.json:
        os.makedirs(os.path.dirname(os.path.abspath(a.json)), exist_ok=True)
        json.dump({"mode": a.mode, "speed": round(k, 6), "tail": a.tail,
                   "src_total": round(src_total, 3), "new_total": round(new_total, 3),
                   "plan": [{kk: (round(vv, 4) if isinstance(vv, float) else vv)
                             for kk, vv in p.items() if kk != "path"} for p in plan]},
                  open(a.json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("→ %s" % a.json)
    print("✔ 输出目录 %s  新总长 %.2fs" % (a.out, new_total))


if __name__ == "__main__":
    main()
