#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""生成**外挂字幕**（.srt / .vtt）—— 画面里绝不出字，字幕单独交付。

为什么这里能做到「句级精确」：
  本片走的是 audio-lock 路线，`_tts/<film>/shotNN_lines.json` 里落着**每句的实测落点**
  （`t` = 句首在镜内的秒数，`dur` = 该句裁剪/变速后的真实时长）。所以不需要靠音轨分析
  或「按字数均分」去猜，直接算即可 —— 这是 audio-lock 顺带白拿的好处。

时间轴口径（最易错的一处，务必记牢）：
  成片绝对时间 = **(镜号 - 1) × 单镜成片时长 + 镜内时间**
  单镜成片时长取 **精修后**的 `refined_frames / fps`（stage2 会把 362 帧裁到 361 帧，
  即 15.0833s → 15.0417s），写成草稿时长会让整条字幕逐镜累积漂移。

用法：
  python3 make_subs.py                     # 两片
  python3 make_subs.py --film film1
  python3 make_subs.py --speaker           # 台词前加角色名「顾董：」
产物：<工程目录>/<片名>_字幕.srt 与 <片名>_字幕.vtt
"""
import argparse
import importlib.util
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(ROOT, "_tts")

# 角色显示名（只在 --speaker 时用）
NAMES = {
    "film1": {"S1": "顾董", "S2": "林晚晴", "S2K": "林晚晴", "S3": "面试者",
              "S4": "女主管", "S5": "助理"},
    "film2": {"S1": "顾承舟", "S2": "小舟", "S2_STAND": "小舟", "S3": "相亲女",
              "S4": "苏晚", "S5": "助理"},
}


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def ts(t, sep):
    """秒 → HH:MM:SS<sep>mmm"""
    if t < 0:
        t = 0.0
    h = int(t // 3600)
    mnt = int((t % 3600) // 60)
    s = t % 60
    return "%02d:%02d:%02d%s%03d" % (h, mnt, int(s), sep, round((s - int(s)) * 1000))


def safe_name(title):
    """片名 → 文件名：去掉「（原片复刻）」这类括号尾巴与空格"""
    t = re.sub(r"[（(].*?[)）]", "", title).strip()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", t)


def cues_for(film, mod, use_speaker, shot_frames=None):
    """返回 [(开始秒, 结束秒, 文本, 镜号), ...]（已按时间排序、已夹在镜内）"""
    fps = mod.FILM["fps"]
    # 单镜成片时长：默认取精修后帧数；草稿版(362 帧)预览时用 shot_frames 覆盖
    shot_dur = (shot_frames or mod.FILM["refined_frames"]) / fps
    names = NAMES.get(film, {})
    cues = []
    for s in mod.SHOTS:
        no = s["no"]
        base = (no - 1) * shot_dur
        jf = os.path.join(TTS, film, "shot%02d_lines.json" % no)
        if os.path.exists(jf):
            rows = json.load(open(jf, encoding="utf-8"))
            items = [(r["t"], r["dur"], r["text"], r.get("speaker", "")) for r in rows]
        else:
            # 兜底：没有实测表就按镜内均分（仅应急，正常不该走到这里）
            dlg = s["dialogue"]
            step = (shot_dur * 0.9) / max(len(dlg), 1)
            items = [(shot_dur * 0.05 + i * step, step * 0.92, tx, sp)
                     for i, (sp, tx) in enumerate(dlg)]
        for t, dur, tx, sp in items:
            a = base + t
            b = min(base + t + dur, base + shot_dur)     # 不越镜
            if b <= a:
                b = a + 0.6
            txt = ("%s：%s" % (names.get(sp, sp), tx)) if use_speaker else tx
            cues.append((a, b, txt, no))
    cues.sort(key=lambda c: c[0])
    return cues, shot_dur


def write_srt(cues, path):
    L = []
    for i, (a, b, txt, _) in enumerate(cues, 1):
        L += ["%d" % i, "%s --> %s" % (ts(a, ","), ts(b, ",")), txt, ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def write_vtt(cues, path):
    L = ["WEBVTT", ""]
    for i, (a, b, txt, _) in enumerate(cues, 1):
        L += ["%d" % i, "%s --> %s" % (ts(a, "."), ts(b, ".")), txt, ""]
    open(path, "w", encoding="utf-8").write("\n".join(L))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="all", choices=["all", "film1", "film2"])
    ap.add_argument("--speaker", action="store_true", help="台词前加角色名")
    ap.add_argument("--shot-frames", type=int, default=None,
                    help="单镜帧数覆盖（草稿版=362；默认取精修后帧数）")
    ap.add_argument("--suffix", default="_字幕", help="文件名后缀，默认 _字幕")
    a = ap.parse_args()

    films = [("film1", "p1_data"), ("film2", "p2_data")]
    if a.film != "all":
        films = [f for f in films if f[0] == a.film]

    for tag, modname in films:
        m = load(modname)
        cues, shot_dur = cues_for(tag, m, a.speaker, a.shot_frames)
        if not cues:
            print("✘ %s 无台词" % tag); continue
        stem = safe_name(m.FILM["film_title"])
        srt = os.path.join(ROOT, "%s%s.srt" % (stem, a.suffix))
        vtt = os.path.join(ROOT, "%s%s.vtt" % (stem, a.suffix))
        write_srt(cues, srt)
        write_vtt(cues, vtt)
        total = max(c[1] for c in cues)
        print("✔ %-7s %2d 条字幕 ｜ 单镜 %.4fs ｜ 末句收于 %.2fs（片长 %.2fs）"
              % (tag, len(cues), shot_dur, total, len(m.SHOTS) * shot_dur))
        print("   %s" % srt)
        print("   %s" % vtt)


if __name__ == "__main__":
    main()
