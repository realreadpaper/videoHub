#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""A100 换卡 · 唯一必改项：把工作流里的 CLIP 权重从 NVFP4 换成 INT8_CONVROT。

为什么必须改（不是优化，是硬约束）：
  · A100 = SM 8.0 Ampere，**没有 FP4 硬件**（NVFP4 要 Blackwell SM 10.0+）
  · 我们 20 份工作流的 CLIPLoader 指向
      minimax_h3/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors
    在 A100 上只能走 eager fallback，慢且不稳
  · 换成 qwen3vl_32b_minimax_h3_int8_convrot.safetensors 后走 int8 kernel，
    A100（SM≥7.5 起支持 INT8 tensor core）原生支持

不需要改的（别动）：
  · UNETLoader  → minimax_h3_fl2va_pruned_int8_convrot.safetensors  （A100 原生支持，已实测跑通 20 镜）
  · VAELoader   → video_vae_fp16 / audio_vae_fp32 / ltx conv-bf16   （A100 原生 bf16）
  · LoraLoaderBypassModelOnly → turbo LoRA bf16                      （A100 原生 bf16）
  · 分辨率 / 帧数 / prompt / seed / 节点连线                          （与硬件无关）

实现方式：**纯文本替换**，不做 json.load→dump。
  理由：dump 会重排缩进，85 处改动变成整文件 diff，无法人工复核。
  文本替换只动那一串文件名，其余字节完全不变 —— 改动可逐处 diff。

用法：
  python3 a100_patch_clip.py --dir _remote --check          # 只报告会改几处
  python3 a100_patch_clip.py --dir _remote                  # 改（自动备份 .bak）
  python3 a100_patch_clip.py --dir _remote --to bf16        # 切成 bf16 版（51.5GB，需 offload）
  python3 a100_patch_clip.py --dir _remote --restore        # 从 .bak 回滚
"""
import argparse
import glob
import os
import re
import shutil
import sys

# 目标文件名（只换文件名本体，**原有目录前缀原样保留**）
# 注意：CLIPLoader 的 clip_name 在远端必须带 `minimax_h3/` 前缀（实测缺前缀会 400
# value_not_in_list）；UNET 在根目录则不能带。这里不擅自增删前缀，只换文件名，
# 无前缀的条目会在报告里单独告警。
VARIANTS = {
    "int8": ("qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
             "27.14 GB · 40GB 显存装得下 · 走 int8 kernel（推荐）"),
    "bf16": ("qwen3vl_32b_minimax_h3_bf16.safetensors",
             "51.51 GB · 40GB 装不下需 offload · 质量最高但最慢"),
}

# 匹配「任意前缀 + qwen3vl_32b_minimax_h3_<量化>.safetensors」
# 前缀（如 minimax_h3/）单独成组，替换时原样保留
PAT = re.compile(r"(?P<pre>(?:[\w./-]*/)?)qwen3vl_32b_minimax_h3_(?P<quant>\w+)\.safetensors")

TARGET_QUANT = {"int8": "int8_convrot", "bf16": "bf16"}


def scan(paths, to):
    """返回 [(文件, 行号, 旧串, 新串, 是否缺目录前缀)]，只读不改。

    已经是目标量化的引用会被跳过（幂等 —— 重复跑不会二次改写）。
    """
    name = VARIANTS[to][0]
    hits = []
    for p in paths:
        try:
            lines = open(p, encoding="utf-8").read().splitlines()
        except Exception as e:
            print("  跳过 %s: %s" % (p, e))
            continue
        for i, ln in enumerate(lines, 1):
            for m in PAT.finditer(ln):
                if m.group("quant") == TARGET_QUANT[to]:
                    continue
                hits.append((p, i, m.group(0), m.group("pre") + name,
                             m.group("pre") == ""))
    return hits


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="_remote", help="工作流目录（递归）")
    ap.add_argument("--to", choices=list(VARIANTS), default="int8",
                    help="目标量化版本（默认 int8）")
    ap.add_argument("--check", action="store_true", help="只报告，不落盘")
    ap.add_argument("--restore", action="store_true", help="从 .bak 回滚")
    a = ap.parse_args()

    dst_name, note = VARIANTS[a.to]
    files = sorted(set(glob.glob(os.path.join(a.dir, "*.json")) +
                       glob.glob(os.path.join(a.dir, "**", "*.json"), recursive=True)))

    print("=" * 78)
    print("  A100 · CLIP 权重改写 → %s" % a.to)
    print("=" * 78)
    print("  文件本体 : %s" % dst_name)
    print("  规格     : %s" % note)
    print("  扫描范围 : %s/  (%d 份 json)" % (a.dir, len(files)))
    print("-" * 78)

    if a.restore:
        n = 0
        for p in files:
            b = p + ".bak"
            if os.path.exists(b):
                shutil.move(b, p)
                n += 1
        print("  ✔ 已从 .bak 回滚 %d 份" % n)
        return 0

    hits = scan(files, a.to)
    if not hits:
        print("  ✔ 无需改动（已经没有 nvfp4_awq 引用了）")
        return 0

    byfile = {}
    for p, ln, old, new, nopre in hits:
        byfile.setdefault(p, []).append((ln, old, new, nopre))

    nopre_hits = [h for h in hits if h[4]]
    print("  命中 %d 处，分布在 %d 份文件里：" % (len(hits), len(byfile)))
    for p in sorted(byfile):
        print("    %-58s %d 处" % (os.path.basename(p), len(byfile[p])))
    print()
    print("  抽样（前 3 处）：")
    for p, ln, old, new, _ in hits[:3]:
        print("    %s:%d" % (os.path.basename(p), ln))
        print("      - %s" % old)
        print("      + %s" % new)

    if nopre_hits:
        print()
        print("  ⚠ %d 处 clip_name 缺 `minimax_h3/` 目录前缀（实测会导致远端 400 "
              "value_not_in_list）：" % len(nopre_hits))
        for p, ln, old, _new, _ in nopre_hits[:5]:
            print("      %s:%d  %s" % (os.path.basename(p), ln, old))
        print("    这些条目本脚本不擅自补前缀（避免越权改动）；若它们会被部署，"
              "请手工补成 minimax_h3/ 开头的写法。")

    if a.check:
        print()
        print("  （--check 模式，未落盘。去掉 --check 即执行）")
        return 0

    # 落盘：文本级替换 + 备份
    changed = 0
    for p in sorted(byfile):
        src = open(p, encoding="utf-8").read()
        if not os.path.exists(p + ".bak"):
            shutil.copy2(p, p + ".bak")
        out = PAT.sub(lambda m: m.group("pre") + dst_name, src)
        if out != src:
            open(p, "w", encoding="utf-8").write(out)
            changed += 1

    print()
    print("  ✔ 已改写 %d 份（原文件备份为 *.json.bak）" % changed)

    # 复验
    left = scan(files, a.to)
    print("  ✔ 复验：残留 nvfp4_awq 引用 %d 处 %s"
          % (len(left), "（应为 0）" if not left else "← 检查一下！"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
