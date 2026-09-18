#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""batch_s2.py — Stage2 精修 20 镜批处理驱动（阶段化 + 断点续跑）

设计要点（对应 A100_20镜全流程方案.html）
----------------------------------------
· **批处理而非逐镜冷启**：20 镜在同一 ComfyUI 进程里连续提交，模型只在首镜付一次
  装载成本，之后全是热态（实测 75.2 s/镜 vs 冷启 270 s/镜）。
· **断点续跑**：输出已存在即跳过，中断后重跑不会重做工。
· **阶段边界释放**：--free-before 在开跑前调 /free 卸载上一阶段的模型，
  避免 S1 的 52 GB 权重与 S2 的 37 GB 权重在 62 GB 内存里互相淘汰（那会导致
  权重退化成从磁盘读，比 PCIe 慢约 20 倍）。
· **演练优先**：默认只打印计划，加 --go 才真正提交。

用法
----
  python3 batch_s2.py --list                     # 看哪些镜缺草稿 / 缺成片
  python3 batch_s2.py --shots 13,15              # 演练：只跑 13、15
  python3 batch_s2.py --shots 1-20 --free-before # 演练全部 + 先释放
  python3 batch_s2.py --shots 1-20 --go          # 真跑

  # 草稿放在别处 / 尺寸不同
  python3 batch_s2.py --shots 1-20 --go \
      --drafts-dir /workspace/ComfyUI/input/drafts \
      --out-prefix MiniMaxH3/film1-refined \
      --width 768 --height 1344
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = "/workspace/films/film1-office/manifest.json"
COMFY = "/workspace/ComfyUI"
INPUT_DIR = COMFY + "/input"
OUTPUT_DIR = COMFY + "/output"
API = "http://127.0.0.1:8188"
BASE_SEED = 20260918  # manifest 的 seed，逐镜 +镜号 以错开


def parse_shots(spec, all_shots):
    if not spec or spec == "all":
        return list(all_shots)
    out = []
    for part in spec.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            out.extend(range(int(a), int(b) + 1))
        elif part:
            out.append(int(part))
    return [n for n in out if n in all_shots]


def http_post(url, payload, timeout=60):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def free_vram():
    """卸载全部模型 + 释放缓存。

    ★ 坑：`POST /free` 返回的是**空 body**（server.py 里就一句
    `return web.Response(status=200)`）。写 `json.loads(resp.read())` 会抛
    JSONDecodeError，被 except 吞掉后打印"失败（不致命）"——**看起来调用过了，
    实际请求已经发出并且生效了**，但日志会误导人去排查一个不存在的问题。
    这里不解析响应体，只在 HTTP 层报错时才认为是真失败。
    """
    try:
        req = urllib.request.Request(
            API + "/free",
            data=json.dumps({"unload_models": True, "free_memory": True}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()  # 空 body，不解析
        print("[i] 已请求 /free（卸载全部模型 + 释放缓存）")
        time.sleep(5)
    except Exception as e:  # noqa: BLE001
        print("[!] /free 请求失败（不致命）：%r" % (e,))


def output_exists(prefix, shot):
    """ComfyUI 的 SaveVideo 会写成 <prefix>_00001_.mp4"""
    sub = os.path.dirname(prefix)
    base = os.path.basename(prefix)
    d = os.path.join(OUTPUT_DIR, sub)
    if not os.path.isdir(d):
        return False
    return any(f.startswith(base + "_") and f.endswith(".mp4")
               for f in os.listdir(d))


def run_one(shot, draft_rel, prompt, seed, prefix, w, h, timeout,
            preset=None, guide=None, guide_frame=0, guide_strength=1.0):
    """生成 API JSON 并提交，返回 (ok, seconds, 输出文件)。"""
    api_json = os.path.join(HERE, "api_s%02d.json" % shot)
    pf = "/tmp/_p%02d.txt" % shot
    with open(pf, "w", encoding="utf-8") as f:
        f.write(prompt)

    cmd = [sys.executable, os.path.join(HERE, "s2_adapt.py"),
           "--template", os.path.join(HERE, "s2_template.json"),
           "--shot", str(shot), "--draft", draft_rel, "--prompt-file", pf,
           "--seed", str(seed), "--prefix", prefix,
           "--width", str(w), "--height", str(h),
           "--out", api_json]
    if preset:
        cmd += ["--preset", preset]
    if guide:
        cmd += ["--guide", guide, "--guide-frame", str(guide_frame),
                "--guide-strength", str(guide_strength)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        return False, 0.0, "s2_adapt 失败: " + (r.stderr or r.stdout)[-300:]

    t0 = time.time()
    r = subprocess.run([sys.executable, os.path.join(HERE, "submit_api.py"),
                        api_json, "--poll", "15", "--timeout", str(timeout)],
                       capture_output=True, text=True)
    el = time.time() - t0
    out = (r.stdout or "") + (r.stderr or "")
    ok = r.returncode == 0
    tail = ""
    m = re.search(r"用时 ([\d.]+) s\s+status=(\w+)", out)
    if m:
        tail = "status=%s" % m.group(2)
    if not ok:
        tail = out.strip().splitlines()[-1][:200] if out.strip() else "无输出"
    return ok, el, tail


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shots", default="all")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--go", action="store_true", help="真正提交（默认只演练）")
    ap.add_argument("--free-before", action="store_true",
                    help="开跑前调 /free 释放上一阶段模型")
    ap.add_argument("--manifest", default=MANIFEST)
    ap.add_argument("--drafts-dir", default=INPUT_DIR + "/drafts")
    ap.add_argument("--out-prefix", default="MiniMaxH3/film1-refined")
    ap.add_argument("--width", type=int, default=768)
    ap.add_argument("--height", type=int, default=1344)
    ap.add_argument("--timeout", type=int, default=3600)
    ap.add_argument("--force", action="store_true", help="已有成片也重跑")
    ap.add_argument("--preset", choices=("official", "identity"), default="identity",
                    help="精修强度：identity=低Sigma保脸(默认,主体/文字保真) / official=官方满强度")
    ap.add_argument("--guide", help="全局参考图引导（相对 ComfyUI/input）")
    ap.add_argument("--guide-frame", type=int, default=0)
    ap.add_argument("--guide-strength", type=float, default=1.0)
    a = ap.parse_args()

    man = json.load(open(a.manifest, encoding="utf-8"))
    shots = {s["no"]: s for s in man["shots"]}
    todo = parse_shots(a.shots, shots.keys())

    # ---- 计划 ----
    plan = []
    for n in todo:
        s = shots.get(n)
        if not s:
            continue
        draft_abs = os.path.join(a.drafts_dir, "s%02d.mp4" % n)
        prefix = "%s/s%02d" % (a.out_prefix, n)
        has_draft = os.path.isfile(draft_abs)
        has_out = output_exists(prefix, n)
        plan.append((n, has_draft, has_out, s.get("ref"), s.get("anchored")))

    print("[i] 精修预设: %s%s" % (
        a.preset,
        "  + 参考图引导 %s@frame%d strength%s" % (a.guide, a.guide_frame, a.guide_strength)
        if a.guide else ""))
    print("镜  | 草稿 | 成片 | ref  | anchor | 状态")
    print("-" * 58)
    runnable = []
    for n, hd, ho, ref, anc in plan:
        if not hd:
            st = "缺草稿（先跑 S1）"
        elif ho and not a.force:
            st = "已完成（跳过）"
        else:
            st = "待跑"
            runnable.append(n)
        print("%3d | %-4s | %-4s | %-4s | %-6s | %s"
              % (n, "有" if hd else "-", "有" if ho else "-", ref, anc, st))

    print("\n可跑 %d 镜，跳过 %d 镜，缺草稿 %d 镜"
          % (len(runnable), len(plan) - len(runnable) - sum(1 for p in plan if not p[1]),
             sum(1 for p in plan if not p[1])))

    if a.list or not a.go:
        if not a.go:
            print("\n[i] 演练模式。加 --go 真正提交。")
        return 0
    if not runnable:
        print("[i] 无可跑镜。")
        return 0

    if a.free_before:
        free_vram()

    # ---- 执行 ----
    t_start = time.time()
    done, failed = [], []
    for i, n in enumerate(runnable, 1):
        s = shots[n]
        draft_rel = "drafts/s%02d.mp4" % n
        prefix = "%s/s%02d" % (a.out_prefix, n)
        seed = BASE_SEED + n
        print("\n[%d/%d] shot%02d  seed=%d  %dx%d  ref=%s"
              % (i, len(runnable), n, seed, a.width, a.height, s.get("ref")))
        ok, el, msg = run_one(n, draft_rel, s["prompt"], seed, prefix,
                              a.width, a.height, a.timeout,
                              preset=a.preset, guide=a.guide,
                              guide_frame=a.guide_frame,
                              guide_strength=a.guide_strength)
        if ok:
            done.append((n, el))
            print("   ✓ %.1f s  %s" % (el, msg))
        else:
            failed.append((n, msg))
            print("   ✗ %.1f s  %s" % (el, msg))

    # ---- 汇总 ----
    total = time.time() - t_start
    print("\n" + "=" * 58)
    print("完成 %d 镜，失败 %d 镜，总耗时 %.1f min" % (len(done), len(failed), total / 60))
    if done:
        times = [t for _, t in done]
        print("单镜：min %.1f s / 中位 %.1f s / max %.1f s"
              % (min(times), sorted(times)[len(times) // 2], max(times)))
        if len(times) > 1:
            print("首镜（含冷加载）%.1f s，其余中位 %.1f s"
                  % (times[0], sorted(times[1:])[len(times[1:]) // 2]))
    for n, msg in failed:
        print("  失败 shot%02d: %s" % (n, msg))
    return 0 if not failed else 2


if __name__ == "__main__":
    sys.exit(main())
