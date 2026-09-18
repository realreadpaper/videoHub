#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
独立外挂字幕生成器 —— 「视频里不出字，字幕单独做」这一硬规矩的执行器

为什么单独拆一个脚本：
  字幕是**独立交付物**，不应该只在后期总装时被顺带生成。改一句台词、调一个时间
  点、加一版英文，都不该重编码整片。所以字幕生成必须能脱离视频合成单独跑，
  且不依赖 Pillow（本机 /usr/bin/python3 的 PIL 是 x86 架构，Apple Silicon 上 import 即崩）。

用法:
  # 常规：读 manifest + shots/ 实际时长，输出 srt/vtt
  python3 make_subs.py --film 01_周星驰_三十八万八

  # 底片还没拉回来（或只想先出字幕），按统一时长 15.04s 推算
  python3 make_subs.py --film 01_周星驰_三十八万八 --uniform 15.04

  # 纯兜底模式：不分析音轨，每镜整镜内缩 5%~95%（最快，H3 素材多数实际就落到这里）
  python3 make_subs.py --film 02_姜文_老子不娶了 --mode full

  # 复用 finish_film.py 算好的时间窗（subtitle_timing.json 是镜内相对秒）
  python3 make_subs.py --film 02_姜文_老子不娶了 --timing subtitle_timing.json

  # 完全脱离工程目录
  python3 make_subs.py --manifest m.json --shots shots/ --out out.srt

  # 只校验已有字幕文件，不生成
  python3 make_subs.py --check 周星驰_三十八万八_字幕.srt --duration 120.34

时间轴口径（容易错，务必记牢）:
  SRT 里写的是**成片绝对时间** = 该镜之前所有镜的时长累加 + 镜内时间窗。
  不是镜内相对时间。写成相对时间会导致整条字幕全部错位到片头。

产出:
  <片名>_字幕.srt    UTF-8 无 BOM（需要 BOM 给老播放器时加 --bom）
  <片名>_字幕.vtt    WebVTT，时间用点号分隔
"""
import argparse, json, os, re, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.normpath(os.path.join(HERE, ".."))

# 整镜内缩比例（H3 音轨被环境音盖满，silencedetect 多数失效时的兜底）
INSET = 0.05
MIN_HEAD = 0.5      # 至少留 0.5s 才看得见
MIN_TAIL = 1.0      # 结尾至少提前 1.0s 收，避免字幕卡在切点上


# ---------- 基础 ----------
def ffprobe_dur(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0",
                        "-show_entries", "stream=duration", "-of", "csv=p=0", p],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip().split(",")[0])
    except Exception:
        return 0.0


def ts_srt(t):
    t = max(0.0, t)
    h = int(t // 3600); m = int((t % 3600) // 60); s = int(t % 60)
    ms = int(round((t - int(t)) * 1000))
    if ms == 1000:
        ms = 999
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def ts_vtt(t):
    return ts_srt(t).replace(",", ".")


def write_srt(items, path, bom=False):
    """items: [(start, end, text), ...]"""
    enc = "utf-8-sig" if bom else "utf-8"
    with open(path, "w", encoding=enc) as f:
        for i, (s, e, tx) in enumerate(items, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts_srt(s), ts_srt(e), tx))
    return path


def write_vtt(items, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("WEBVTT\n\n")
        for i, (s, e, tx) in enumerate(items, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, ts_vtt(s), ts_vtt(e), tx))
    return path


# ---------- 时间窗 ----------
def detect_voice(mp4, noise="-35dB", min_d=0.30):
    """返回 [(start,end),...] 非静音区间。检测不到返回 [(0,dur)]"""
    r = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", mp4,
                        "-af", "silencedetect=noise=%s:d=%s" % (noise, min_d),
                        "-f", "null", "-"], capture_output=True, text=True)
    txt = r.stderr
    starts = [float(x) for x in re.findall(r"silence_start:\s*([0-9.]+)", txt)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*([0-9.]+)", txt)]
    dur = ffprobe_dur(mp4) or 15.0
    segs, t = [], 0.0
    for s, e in zip(starts, ends + [None]):
        if s > t:
            segs.append((t, s))
        t = e if e is not None else t
    if not starts and not ends:
        return [(0.0, dur)]
    if t < dur:
        segs.append((t, dur))
    merged = []
    for s, e in segs:
        if merged and s - merged[-1][1] < 0.6:
            merged[-1] = (merged[-1][0], e)
        else:
            merged.append((s, e))
    return merged


def window_full(dur):
    return (max(MIN_HEAD, dur * INSET), max(MIN_TAIL, dur - dur * INSET))


def window_voice(mp4, dur):
    """先试 silencedetect；环境音盖满（有声占比 >=85%）就落回整镜覆盖。

    这是全工程**唯一**的字幕时间窗口径 —— finish_film.py 也 import 本函数，
    别在别处再写一份，否则成片字幕与外挂字幕会错位。
    """
    segs = detect_voice(mp4)
    cover = sum(e - s for s, e in segs) if segs else 0.0
    full = window_full(dur)
    if not segs or cover >= dur * 0.85:
        return full, "整镜覆盖(环境音盖满, 有声占比%.0f%%)" % (100.0 * cover / max(dur, 0.01))
    segs.sort(key=lambda x: x[1] - x[0], reverse=True)
    s, e = segs[0]
    if e - s < 1.5:
        return full, "整镜覆盖(最长有声段仅 %.2fs)" % (e - s)
    pad_a, pad_b = 0.15, 0.35
    return (max(0.30, s - pad_a), min(dur - 0.30, e + pad_b)), "对齐语音 %.2f-%.2fs" % (s, e)


# ---------- 校验 ----------
def check_srt(path, total=None, verbose=True):
    """校验字幕文件：时间递增 / 不超片长 / 中文可读。返回 (ok, 问题列表)"""
    raw = open(path, "rb").read()
    txt = raw.decode("utf-8-sig", errors="replace")
    if raw[:3] == b"\xef\xbb\xbf":
        txt = raw.decode("utf-8-sig", errors="replace")
    blocks = [b for b in re.split(r"\n\s*\n", txt) if b.strip()]
    probs = []
    cues = []
    for b in blocks:
        lines = [l for l in b.strip().split("\n") if l.strip()]
        if len(lines) < 2:
            continue
        m = re.search(r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
                      r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})", lines[1])
        if not m:
            continue
        g = [int(x) for x in m.groups()]
        s = g[0] * 3600 + g[1] * 60 + g[2] + g[3] / 1000.0
        e = g[4] * 3600 + g[5] * 60 + g[6] + g[7] / 1000.0
        cues.append((s, e, "\n".join(lines[2:])))
    if not cues:
        probs.append("没解析出任何字幕条")
    for i, (s, e, tx) in enumerate(cues, 1):
        if e <= s:
            probs.append("第 %d 条 结束时间 <= 开始时间" % i)
        if i > 1 and s < cues[i - 2][1] - 0.001:
            probs.append("第 %d 条 与上一条重叠/倒序" % i)
        if total and e > total + 0.5:
            probs.append("第 %d 条 超出成片时长 (%.2f > %.2f)" % (i, e, total))
        if not re.search(r"[\u4e00-\u9fff]", tx or ""):
            probs.append("第 %d 条 不含中文，检查是否乱码: %r" % (i, (tx or "")[:20]))
        if re.search(r"[\ufffd]", tx or ""):
            probs.append("第 %d 条 含替换字符（编码损坏）" % i)
    if verbose:
        print("  校验 %s：%d 条，%s" % (os.path.basename(path), len(cues),
                                        "✔ 通过" if not probs else "✗ %d 个问题" % len(probs)))
        for p in probs:
            print("     -", p)
    return (not probs), probs


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", help="工程目录名，如 01_周星驰_三十八万八")
    ap.add_argument("--manifest")
    ap.add_argument("--shots", help="底片目录（优先取 shots_clean/）")
    ap.add_argument("--out", help="输出 srt 路径（不含扩展名）")
    ap.add_argument("--uniform", type=float, help="不读视频，每镜按该时长推算")
    ap.add_argument("--mode", choices=["auto", "voice", "full"], default="auto",
                    help="auto=先试语音对齐，失败落回整镜；voice=强制语音；full=强制整镜")
    ap.add_argument("--timing", help="复用已有时间窗 JSON（镜内相对秒，键为镜号）")
    ap.add_argument("--bom", action="store_true", help="srt 写 UTF-8 BOM（给老播放器）")
    ap.add_argument("--check", help="只校验一个已有 srt，不生成")
    ap.add_argument("--duration", type=float, help="配合 --check：成片总时长")
    a = ap.parse_args()

    # —— 纯校验模式 ——
    if a.check:
        ok, _ = check_srt(a.check, a.duration)
        sys.exit(0 if ok else 1)

    # —— 定位工程 ——
    if a.film:
        film_dir = a.film if os.path.isdir(a.film) else os.path.join(BASE, a.film)
        man_p = a.manifest or os.path.join(film_dir, "manifest.json")
        shots = a.shots or os.path.join(film_dir, "shots")
        title = os.path.basename(film_dir.rstrip("/")).split("_", 1)[-1]
        out_base = a.out or os.path.join(film_dir, "%s_字幕" % title)
    else:
        if not (a.manifest and a.shots):
            sys.exit("脱离工程目录时必须给 --manifest 和 --shots")
        man_p, shots = a.manifest, a.shots
        out_base = a.out or os.path.join(os.path.dirname(man_p), "字幕")

    if not os.path.exists(man_p):
        sys.exit("缺 manifest: %s" % man_p)
    m = json.load(open(man_p, encoding="utf-8"))

    clean = (shots.rstrip("/") + "_clean")
    timing = {}
    if a.timing:
        tp = a.timing if os.path.isabs(a.timing) else os.path.join(
            os.path.dirname(man_p), os.path.basename(a.timing))
        if os.path.exists(tp):
            timing = {int(k): tuple(v) for k, v in json.load(open(tp)).items()}
            print("  复用时间窗:", os.path.basename(tp))

    print("═" * 70)
    print("  外挂字幕生成 · %s（%d 镜）" % (os.path.basename(out_base), len(m["shots"])))
    print("═" * 70)

    cues, cursor, total = [], 0.0, 0.0
    for sh in m["shots"]:
        no = sh["no"]
        dlg = (sh.get("dialogue_cn") or "").strip()
        # 底片：优先 delogo 清理版
        src = None
        for cand in (os.path.join(clean, "shot%02d.mp4" % no),
                     os.path.join(shots, "shot%02d.mp4" % no)):
            if os.path.exists(cand):
                src = cand
                break
        # 逐镜时长口径（2026-09-18 改）：
        #   1) --uniform 显式指定 → 用它（调试用，正常不该给）
        #   2) 底片在 → ffprobe 实测，这是唯一权威值
        #   3) 都没有 → 回落到 manifest 的 duration（重定时后的成片秒数），
        #      不再写死 15.04 —— 全片已改成 11.375–15.042s 弹性排期
        man_dur = sh.get("duration")
        if a.uniform:
            dur = a.uniform
        elif src:
            dur = ffprobe_dur(src)
            if not dur:
                dur = man_dur or 15.042
                print("  ⚠ 镜 %02d 读不到时长，回落 manifest %.3fs" % (no, dur))
        else:
            if man_dur:
                dur = man_dur
                print("  镜 %02d 无底片，按 manifest %.3fs 推算" % (no, dur))
            else:
                sys.exit("镜 %02d 找不到底片且 manifest 无 duration（%s）" % (no, shots))

        if not dlg:
            print("  镜 %02d  无台词，跳过 (%.2fs)" % (no, dur))
            cursor += dur; total += dur
            continue

        if no in timing:
            t1, t2 = timing[no]; why = "复用已有时间窗"
        elif a.mode == "full":
            t1, t2 = window_full(dur); why = "整镜覆盖"
        elif a.mode == "voice":
            (t1, t2), why = window_voice(src, dur)
        else:
            if src:
                (t1, t2), why = window_voice(src, dur)
            else:
                t1, t2 = window_full(dur); why = "整镜覆盖(无底片)"

        cues.append((cursor + t1, cursor + t2, dlg.split("／")[0].strip()))
        print("  镜 %02d  成片 %.2f ~ %.2fs  [%s] 「%s」"
              % (no, cursor + t1, cursor + t2, why, dlg[:24]))
        cursor += dur; total += dur

    srt_p = out_base + ".srt"
    vtt_p = out_base + ".vtt"
    write_srt(cues, srt_p, a.bom)
    write_vtt(cues, vtt_p)
    print("\n  ✔ %s (%d 条)" % (os.path.basename(srt_p), len(cues)))
    print("  ✔ %s" % os.path.basename(vtt_p))
    print("  成片总时长推算: %.2fs" % total)
    ok, _ = check_srt(srt_p, total)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
