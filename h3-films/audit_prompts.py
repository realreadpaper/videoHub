#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量禁字幕审查 · 两片 146 镜 v2 prompt（manifest_v2.json）

七道检查（打到 stdout）：
  1 禁字铁律存在（no subtitles + do not draw letterforms）
  2 条款版本正确：ref2va=实物印刷豁免版 / t2va=严格版
  3 无「引号包中文」（已知会触发 H3 烧字幕的写法）
  4 无 <d> 台词标签
  5 <Picture 1> 仅出现在 ref2va 镜（认领与接线一致）
  6 prompt 内无中文字符（台词走 audio-lock，中文进 prompt 有烧字幕风险）
  7 单段连续 take（一个 [00:00 起始段）
"""
import json, re
from pathlib import Path

H3 = "/Users/hejianglong/Desktop/videoHub/h3-films"
FILES = {
    "film1": "/Users/hejianglong/Desktop/videoHub/h3-films/film1-office/manifest_v2.json",
    "film2": "/Users/hejianglong/Desktop/videoHub/h3-films/film2-blinddate/manifest_v2.json",
}
CJK = re.compile(r"[\u4e00-\u9fff]")
QUOTED_CN = re.compile(r'["“”‘’][^"“”‘’]{0,4}[\u4e00-\u9fff]|[\u4e00-\u9fff][^"“”‘’]{0,4}["“”‘’]')


def audit(film):
    d = json.loads(Path(FILES[film]).read_text(encoding="utf-8"))
    bad = {k: [] for k in ("条款缺失", "版本错配", "引号包中文", "d标签", "认领错配", "中文入prompt", "多段结构")}
    for s in d["shots"]:
        p, no, task = s["prompt"], s["no"], s["task_type"]
        if "no subtitles" not in p or "do not draw letterforms" not in p \
                and "do not add any floating or superimposed" not in p:
            bad["条款缺失"].append(no)
        anchored = "physically part of an object's own surface" in p
        strict = "package or printed surface in frame is blank" in p
        if task == "ref2va" and not anchored:
            bad["版本错配"].append((no, "ref2va 应为豁免版"))
        if task == "t2va" and not strict:
            bad["版本错配"].append((no, "t2va 应为严格版"))
        if QUOTED_CN.search(p):
            bad["引号包中文"].append(no)
        if "<d>" in p or "<d " in p:
            bad["d标签"].append(no)
        if ("<Picture 1>" in p) != (task == "ref2va"):
            bad["认领错配"].append(no)
        if CJK.search(p):
            bad["中文入prompt"].append(no)
        if p.count("[00:00.000") != 1:
            bad["多段结构"].append(no)
    total = len(d["shots"])
    issues = sum(len(v) for v in bad.values())
    print("[%s] %d 镜审查：%s" % (film, total, "全部通过 ✅" if not issues else "发现 %d 处问题 ⚠" % issues))
    for k, v in bad.items():
        if v:
            print("   %s: %s" % (k, v))
    return issues


if __name__ == "__main__":
    counts = {f: len(json.loads(Path(FILES[f]).read_text(encoding="utf-8"))["shots"]) for f in FILES}
    n = sum(audit(f) for f in FILES)
    print("合计：两片 %d 镜禁字幕审查%s" % (sum(counts.values()),
                                          "全部通过" if n == 0 else "共 %d 处需修" % n))
