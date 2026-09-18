#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""逐处复核「原片转写」与「抄写稿」的差异，打印上下文供人工判定。

判定口径（爸爸的要求：100% 抄写）：
  - 允许：同音错字等长订正（港→岗、波→锅），因为 ASR 错听，TTS 会念错
  - 不允许：增字、删字、改词序（那是改写，不是抄写）

用法: python3 review_diff.py [film1|film2|all]
"""
import importlib.util, json, os, re, sys
from difflib import SequenceMatcher

ROOT = os.path.dirname(os.path.abspath(__file__))
SRTS = {
    "film1": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad/references/zui-guoli-ribs/transcript.srt",
    "film2": "/Users/hejianglong/Desktop/videoHub/videos/douyin-ad-2/references/homecook/transcript.srt",
}
MODS = {"film1": "p1_data", "film2": "p2_data"}
TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")
PUNCT = re.compile(r"[\s，。、？！：；「」『』（）()…—·,.?!:;\"'“”‘’\-]+")


def clean(s):
    return PUNCT.sub("", s)


def parse_srt(path):
    raw = open(path, encoding="utf-8").read().replace("\r\n", "\n")
    out = []
    for block in raw.strip().split("\n\n"):
        lines = [l for l in block.split("\n") if l.strip()]
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        out.append("".join(lines[2:]).strip())
    return clean("".join(out))


def load(mod):
    spec = importlib.util.spec_from_file_location(mod, os.path.join(ROOT, mod + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def main():
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    films = ["film1", "film2"] if which == "all" else [which]
    for f in films:
        orig = parse_srt(SRTS[f])
        m = load(MODS[f])
        mine = clean("".join(t for _, t in
                             (ln for s in m.SHOTS for ln in s["dialogue"])))
        print("=" * 100)
        print("%s  原文 %d 字 / 抄写 %d 字" % (f, len(orig), len(mine)))
        print("=" * 100)
        sm = SequenceMatcher(None, orig, mine, autojunk=False)
        n_eq = n_ne = 0
        for tag, i1, i2, j1, j2 in sm.get_opcodes():
            if tag == "equal":
                n_eq += i2 - i1
                continue
            n_ne += max(i2 - i1, j2 - j1)
            O, M = orig[i1:i2], mine[j1:j2]
            pre, post = orig[max(0, i1 - 14):i1], orig[i2:i2 + 14]
            verdict = "等长替换=错字订正 ✓" if (i2 - i1) == (j2 - j1) and (i2 - i1) == 1 \
                else ("等长替换" if (i2 - i1) == (j2 - j1) else "⚠ 增删字（越界）")
            print("\n  [%s] %s" % (tag, verdict))
            print("    原文 …%s【%s】%s…" % (pre, O, post))
            print("    抄写 …%s【%s】%s…" % (pre, M, post))
        print("\n  字符一致度 %.4f ｜ 非等长子操作 %d 处"
              % (sm.ratio(), n_ne))
        print()


if __name__ == "__main__":
    main()
