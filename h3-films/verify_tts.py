#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐镜回听质检：把 TTS 干声用 whisper 转写回来，与分镜原文比对。

作用：提前抓出「念错 / 漏念 / 空音 / 非中文」的镜，避免整批跑完才发现。
用法：
  python3 verify_tts.py                 # 两片全部（40 镜）
  python3 verify_tts.py --film film1
输出：_lines/tts_质检报告.md
"""
import argparse, importlib.util, os, re, subprocess, sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
MODEL = os.path.expanduser("~/.cache/whisper.cpp/ggml-large-v3-turbo-q5_0.bin")
WHISPER = "/opt/homebrew/bin/whisper-cli"
PUNCT = re.compile(r"[\s，。、？！：；「」『』（）()…—·,.?!:;\"'“”‘’\-]+")


def clean(s):
    return PUNCT.sub("", s)


def load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, mod + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def asr(wav):
    r = subprocess.run([WHISPER, "-m", MODEL, "-f", wav, "-l", "zh", "-nt", "--no-prints"],
                       capture_output=True, text=True)
    return clean(r.stdout or "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="all")
    a = ap.parse_args()
    films = [("film1", "p1_data"), ("film2", "p2_data")]
    if a.film != "all":
        films = [f for f in films if f[0] == a.film]

    L = ["# TTS 干声质检报告", "",
         "> 方法：每条 `shotNN_dry.wav` 用 whisper.cpp large-v3-turbo 转写回中文，",
         "> 与分镜原文去标点后逐字比对。相似度 < 0.90 判为可疑，需人工回听。", ""]
    bad = []
    for tag, mod in films:
        m = load(mod)
        L += ["## %s · %s" % (tag, m.FILM["film_title"]), "",
              "| 镜 | 字数 | 相似度 | 判定 | 转写（去标点） |", "| --- | --- | --- | --- | --- |"]
        for s in m.SHOTS:
            wav = os.path.join(ROOT, "_tts", tag, "shot%02d_dry.wav" % s["no"])
            if not os.path.exists(wav):
                L.append("| %d | — | — | ✘ 缺文件 | — |" % s["no"]); bad.append((tag, s["no"], "缺文件")); continue
            want = clean("".join(t for _, t in s["dialogue"]))
            got = asr(wav)
            ratio = SequenceMatcher(None, want, got).ratio() if got else 0.0
            verdict = "✔" if ratio >= 0.90 else "⚠ 可疑"
            if ratio < 0.90:
                bad.append((tag, s["no"], "%.3f" % ratio))
            L.append("| %d | %d | %.3f | %s | %s |" % (s["no"], len(want), ratio, verdict, got[:60]))
            print("%s 镜%-3d 相似度 %.3f %s" % (tag, s["no"], ratio, verdict))
        L.append("")

    L += ["## 结论", ""]
    if bad:
        L.append("**%d 条需复核**：" % len(bad))
        for t, n, r in bad:
            L.append("- %s 镜 %d（%s）" % (t, n, r))
    else:
        L.append("全部通过（相似度 ≥ 0.90），无念错/漏念/空音。")
    out = os.path.join(ROOT, "_lines", "tts_质检报告.md")
    open(out, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n[ok] -> %s" % out)


if __name__ == "__main__":
    main()
