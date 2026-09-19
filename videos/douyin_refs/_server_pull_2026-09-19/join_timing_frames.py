#!/usr/bin/env python3
"""把「实测每镜耗时」与「工作流帧数」按镜号对上，检验成本模型。

数据源：
  timing.json  ← analyze_logs.py 从回传日志抽取的实测耗时
  wf 目录      ← 本机 373 个全量工作流（含 scene_duration_seconds → 帧数）

输出：散点（帧数, 实测秒）与最小二乘拟合，检验 T ∝ N 是否成立。
"""
import json, os, re, glob, statistics as st, sys

PULL = "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/_server_pull_2026-09-19"
WF_DIRS = [
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_full",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_skel",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_v3full",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_six",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_six2",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-18/_remake/wf_six3",
    "/Users/jianglong/Desktop/videoHub/videos/douyin_refs/2026-09-19/_remake/wf",
]

# 1) 建 (镜名) -> (帧数, 步数) 索引
fmap = {}
for d in WF_DIRS:
    for p in glob.glob(os.path.join(d, "*.json")):
        try:
            w = json.load(open(p))
        except Exception:
            continue
        if not isinstance(w, dict):
            continue          # UI 格式（nodes 数组）不是 API 格式，本工程用的是后者
        dur = steps = None
        for k, v in w.items():
            if not isinstance(v, dict):
                continue
            ct = v.get("class_type", "")
            ins = v.get("inputs", {}) or {}
            if ct == "MiniMaxH3AudioWindowT8":
                s = ins.get("scene_duration_seconds")
                if isinstance(s, (int, float)):
                    dur = s
            if ct == "MiniMaxH3DualClockSamplerT8":
                s = ins.get("steps")
                if isinstance(s, int):
                    steps = s
        if dur is None:
            continue
        name = os.path.basename(p)[len("wf_"):-len(".json")] if os.path.basename(p).startswith("wf_") else None
        if name and name not in fmap:
            fmap[name] = (round(dur * 24), steps, os.path.basename(d))

# 2) 读实测
tim = json.load(open(os.path.join(PULL, "timing.json")))
rows = []
unmatched = []
for r in tim["rows"]:
    key = r["shot"]
    if key in fmap:
        N, steps, src = fmap[key]
        rows.append((key, N, steps, r["sec"], r["status"], r["batch"]))
    else:
        unmatched.append((key, r["sec"], r["status"]))

print(f"工作流索引: {len(fmap)} 个镜")
print(f"实测记录: {len(tim['rows'])} 条，其中对得上帧数的 {len(rows)} 条\n")

# 3) 只保留成功且步数已知的
ok = [x for x in rows if x[4] == "success" and x[2]]
print(f"成功且步数已知: {len(ok)} 条\n")
print(f"{'镜号':<18}{'帧':>5}{'步':>4}{'实测s':>9}{'批次':>18}")
for k, N, s, sec, stt, b in sorted(ok, key=lambda x: x[1]):
    print(f"{k:<18}{N:>5}{s:>4}{sec:>9.1f}{b:>18}")

# 4) 拟合：分步数分组，看 T/N 是否随 N 变化
print("\n=== 每组：T/N（每帧每秒）===")
grp = {}
for k, N, s, sec, stt, b in ok:
    grp.setdefault(s, []).append((N, sec))
for s in sorted(grp):
    vals = grp[s]
    print(f"\n{s} 步：")
    for N, sec in sorted(vals):
        print(f"   N={N:<4} T={sec:<8.1f} T/N={sec/N:.3f}")
    if len(vals) >= 2:
        Ns = [v[0] for v in vals]; Ts = [v[1] for v in vals]
        n = len(Ns); sx = sum(Ns); sy = sum(Ts)
        sxx = sum(x*x for x in Ns); sxy = sum(x*y for x, y in zip(Ns, Ts))
        b1 = (n*sxy - sx*sy) / (n*sxx - sx*sx)
        b0 = (sy - b1*sx) / n
        print(f"   拟合 T = {b0:.2f} + {b1:.4f}·N   (T/N 从 {Ts[0]/Ns[0]:.3f} 到 {Ts[-1]/Ns[-1]:.3f})")

if unmatched:
    print(f"\n未能对上帧数的实测记录 {len(unmatched)} 条（前 10）:")
    for k, sec, stt in unmatched[:10]:
        print(f"   {k:<18}{sec:>9.1f}s  {stt}")
