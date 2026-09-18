#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验两片干声是否全部落在 15.0833s 镜窗内（防止尾巴盖到下一镜）。

用法: python3 check_tts_len.py
"""
import glob, json, os, subprocess

DUR = 15.0833


def probe(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", p], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


def main():
    bad_total = 0
    for film in ["film1", "film2"]:
        over, miss = [], []
        js = sorted(glob.glob(os.path.join("_tts", film, "shot*_lines.json")))
        for j in js:
            rows = json.load(open(j, encoding="utf-8"))
            if not rows:
                miss.append(os.path.basename(j)); continue
            # 用 lines.json 里落盘的实测 dur（裁剪/变速后的真实时长），
            # 不要用原始 mp3 时长 —— 那句里含着 0.4~0.9s 首尾静音，会误判超窗。
            end = max(r["t"] + r["dur"] for r in rows)
            if end > DUR - 0.05:
                over.append("%s %.2fs" % (os.path.basename(j).replace("_lines.json", ""), end))
        print("%-7s %2d 镜 ｜ 超窗 %d %s ｜ 空表 %d %s"
              % (film, len(js), len(over), over or "", len(miss), miss or ""))
        bad_total += len(over) + len(miss)
    print("\n%s" % ("✔ 全部落在 15.0833s 窗内" if bad_total == 0 else "⚠ 有 %d 项待处理" % bad_total))


if __name__ == "__main__":
    main()
