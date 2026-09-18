#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
patch_stage2_steps.py —— 把 Stage2 精修的「3 步」改成任意步数（官方支持的手动路线）

背景
----
LTX-2.5 Stage2 的步数**不是参数，是硬编码**：
  h3_t8/sol_engine_h3_super_advanced.py:16
      OFFICIAL_STAGE2_SIGMAS = (0.909375, 0.725, 0.421875, 0.0)
节点 `MiniMaxH3SolEngineLTXRefinerSetupT8Advanced` 只有 6 个输入
（model/enabled/attention_backend/min_tokens/kernel_precision/verbose），
它把 sampler 和 sigmas 一起输出给 SamplerCustomAdvanced —— 没有「步数」这个旋钮。

官方给的手动入口在同族的 Identity 节点：
  MiniMaxH3SolEngineLTXIdentityRefinerSetupT8Advanced
    inputs: enabled / schedule_mode(identity_preserve_0p5 | manual_exp)
            / manual_sigmas(逗号分隔字符串) / attention_backend / min_tokens
            / kernel_precision / verbose
    outputs: model / sampler / sigmas / refiner_lora_strength / report_json  ← 与原节点逐位一致

**两个节点输出顺序完全相同**，所以换类型后原来的 5 条连线（model→14、sampler→16[2]、
sigmas→16[3] 等）全部原样保留，零改线。

⚠️ 已知代价（源码明说，不是我推测）
  · Identity 节点的注意力后端只有 `dense_reference` 和
    `auto_sol_attn_conservative_exp`。后者用**常数 tau=1.0**，
    不能把自定义 sigma 映射到官方的 per-step tau 递进 (1.0/1.25/1.5)。
  · 该节点带 is_experimental=True，报告里 official_stage2_parity=False。
  · 蒸馏 LoRA（ltx-2.5-22b-distilled-lora-450，strength 0.8）是按官方 3 个噪声
    水平训练的；插入中间 sigma 属于分布外（OOD），结果好坏必须实测，不能推演。

本脚本只做一件事：把节点换成 Identity 并写入指定 sigmas。
**不修改官方原文件**，只写新文件；删掉新文件即完全回退。

用法
----
  # 看当前结构（只读，不改任何东西）
  python3 patch_stage2_steps.py --src stage2_vaedecode.json --inspect

  # 生成 3 步对照组（等价官方调度）
  python3 patch_stage2_steps.py --src stage2_vaedecode.json \
      --sigmas "0.909375, 0.725, 0.421875, 0" \
      --out stage2_ctl_3step.json

  # 生成 8 步组
  python3 patch_stage2_steps.py --src stage2_vaedecode.json \
      --sigmas "0.909375, 0.847917, 0.786458, 0.725, 0.623958, 0.522917, 0.421875, 0.210938, 0" \
      --out stage2_exp_8step.json

  # 想换成稠密注意力（消除稀疏近似误差，但更慢）
  ... --backend dense_reference
"""
from __future__ import annotations

import argparse
import json
import math
import sys

SRC_CLS = "MiniMaxH3SolEngineLTXRefinerSetupT8Advanced"
DST_CLS = "MiniMaxH3SolEngineLTXIdentityRefinerSetupT8Advanced"

# Identity 节点 widgets 顺序（= schema 里非连线输入的顺序）
W_ENABLED, W_MODE, W_SIGMAS, W_BACKEND, W_MINTOK, W_PREC, W_VERBOSE = range(7)

BACKENDS = ("dense_reference", "auto_sol_attn_conservative_exp")


# ---------------------------------------------------------------- 数据校验
def parse_sigmas(text: str) -> list[float]:
    """解析并严格校验 sigma 串，规则与官方 _parse_manual_stage2_sigmas 一致。"""
    raw = [p.strip() for p in str(text).replace(";", ",").split(",")]
    raw = [p for p in raw if p != ""]
    if len(raw) < 2:
        raise ValueError("sigma 至少要有 2 个数（1 步）")
    vals: list[float] = []
    for p in raw:
        try:
            vals.append(float(p))
        except ValueError:
            raise ValueError("不是合法数字: %r" % p)
    if not all(math.isfinite(v) for v in vals):
        raise ValueError("含非有限值")
    if vals[0] <= 0.0 or vals[0] > 1.0 or any(v < 0.0 or v > 1.0 for v in vals):
        raise ValueError("sigma 必须落在 (0, 1]，且不得为负")
    for a, b in zip(vals, vals[1:]):
        if a <= b:
            raise ValueError("sigma 必须严格递减，问题出现在 %.6f -> %.6f" % (a, b))
    if not math.isclose(vals[-1], 0.0, rel_tol=0.0, abs_tol=1e-8):
        raise ValueError("最后一个 sigma 必须是 0")
    return vals


def sigma_report(vals: list[float]) -> str:
    nfe = len(vals) - 1
    gaps = ["%.6f" % (a - b) for a, b in zip(vals, vals[1:])]
    return ("  sigma 序列 (%d 个节点 / NFE=%d)\n" % (len(vals), nfe)
            + "    " + "  ".join("%.6f" % v for v in vals) + "\n"
            + "    相邻间隔: " + "  ".join(gaps) + "\n"
            + "    入口 sigma %.6f  终止 sigma %.6f" % (vals[0], vals[-1]))


# ---------------------------------------------------------------- 定位节点
def find_setup_node(wf: dict):
    nodes = wf.get("nodes") if isinstance(wf, dict) else None
    if not isinstance(nodes, list):
        return None, "不是 UI 格式工作流（缺 nodes 数组）"
    hits = [n for n in nodes
            if n.get("type") in (SRC_CLS, DST_CLS)]
    if not hits:
        return None, "找不到精修设置节点（%s / %s）" % (SRC_CLS, DST_CLS)
    if len(hits) > 1:
        return None, "找到 %d 个精修设置节点，无法确定改哪个：%s" % (
            len(hits), [n.get("id") for n in hits])
    return hits[0], None


def node_links(node: dict) -> dict:
    """记录每个输出槽的连线号，用于事后核对连线未被破坏。"""
    out = {}
    for i, s in enumerate(node.get("outputs") or []):
        out[i] = (s.get("name"), s.get("type"), tuple(s.get("links") or ()))
    return out


# ---------------------------------------------------------------- 主流程
def inspect(wf: dict) -> int:
    node, err = find_setup_node(wf)
    if err:
        print("✘ " + err)
        return 2
    print("找到精修设置节点：node id=%s" % node.get("id"))
    print("  当前类型      : %s" % node.get("type"))
    print("  widgets_values: %s" % json.dumps(node.get("widgets_values"), ensure_ascii=False))
    print("  inputs        : %s" % json.dumps(
        [{"name": s.get("name"), "type": s.get("type"), "link": s.get("link")}
         for s in (node.get("inputs") or [])], ensure_ascii=False))
    print("  outputs:")
    for i, (name, typ, links) in node_links(node).items():
        print("     [%d] %-24s %-8s links=%s" % (i, name, typ, list(links)))
    print()
    print("  → Identity 节点需要 7 个 widget：enabled / schedule_mode / manual_sigmas /")
    print("    attention_backend / min_tokens / kernel_precision / verbose")
    print("  → 两个节点的 5 个输出逐位一致，换类型后连线应当完全不变")
    return 0


def patch(wf: dict, sigmas: str, backend: str) -> int:
    vals = parse_sigmas(sigmas)
    if backend not in BACKENDS:
        print("✘ 不支持的后端 %r，只能是 %s" % (backend, " / ".join(BACKENDS)))
        return 2

    node, err = find_setup_node(wf)
    if err:
        print("✘ " + err)
        return 2
    nid = node.get("id")
    before = node_links(node)
    was = node.get("type")

    # ---- 1. 断言输出结构符合预期（换类型的安全性前提）--------------------
    expect = [("model", "MODEL"), ("sampler", "SAMPLER"), ("sigmas", "SIGMAS"),
              ("refiner_lora_strength", "FLOAT"), ("report_json", "STRING")]
    got = [(v[0], v[1]) for v in before.values()]
    if got != expect:
        print("✘ 节点输出结构与预期不符，拒绝修改（避免连线错位）")
        print("   实际: %s" % got)
        print("   预期: %s" % expect)
        return 3

    # ---- 2. 记录原 widget 值（用于打印差异，便于回退）--------------------
    old_wv = list(node.get("widgets_values") or [])

    # ---- 3. 换类型 + 写 widgets -----------------------------------------
    node["type"] = DST_CLS
    new_wv = [None] * 7
    new_wv[W_ENABLED] = True
    new_wv[W_MODE] = "manual_exp"
    new_wv[W_SIGMAS] = ", ".join("%g" % v for v in vals)
    new_wv[W_BACKEND] = backend
    new_wv[W_MINTOK] = 4096
    new_wv[W_PREC] = "bf16_official"
    new_wv[W_VERBOSE] = False
    node["widgets_values"] = new_wv

    # ---- 4. inputs 只保留 model 连线（原节点就只有它）--------------------
    keep = [s for s in (node.get("inputs") or []) if s.get("name") == "model"]
    dropped = [s.get("name") for s in (node.get("inputs") or []) if s.get("name") != "model"]
    node["inputs"] = keep

    # ---- 5. 自检 --------------------------------------------------------
    problems = []
    if node.get("type") != DST_CLS:
        problems.append("类型未替换")
    if len(node.get("widgets_values") or []) != 7:
        problems.append("widgets_values 长度不是 7")
    after = node_links(node)
    if before != after:
        problems.append("输出槽或连线号被改动")
    if not any(s.get("name") == "model" and s.get("link") is not None
               for s in node.get("inputs") or []):
        problems.append("model 连线丢失")
    # 全图悬空 link 检查
    all_ids = set()
    for n in wf.get("nodes", []):
        for s in (n.get("outputs") or []):
            all_ids.update(s.get("links") or ())
    dangling = sorted({l[0] for l in (wf.get("links") or [])} - all_ids)
    if dangling:
        problems.append("存在悬空 link: %s" % dangling)

    print("═" * 78)
    print("Stage2 步数补丁")
    print("═" * 78)
    print("节点 id        : %s" % nid)
    print("类型           : %s" % was)
    print("            -> : %s" % node["type"])
    print("原 widgets     : %s" % json.dumps(old_wv, ensure_ascii=False))
    print("新 widgets     : %s" % json.dumps(new_wv, ensure_ascii=False))
    print("保留的连线输入 : %s" % [s.get("name") for s in keep])
    if dropped:
        print("丢弃的连线输入 : %s  （Identity 节点无此输入，原本也未接线）" % dropped)
    print()
    print(sigma_report(vals))
    print()
    print("注意力后端     : %s" % backend)
    if backend == "auto_sol_attn_conservative_exp":
        print("                 ⚠ 常数 tau=1.0，不再是官方 per-step tau 递进 1.0/1.25/1.5")
    else:
        print("                 ⚠ 稠密注意力：消除稀疏近似误差，但更慢")
    print("官方 3 步调度  : 0.909375 / 0.725 / 0.421875 / 0")
    print("蒸馏 LoRA     : 仍为 strength 0.8（两节点均用 OFFICIAL_REFINER_LORA_STRENGTH）")
    print()
    if problems:
        print("✘ 自检未通过：")
        for p in problems:
            print("    · %s" % p)
        return 3
    print("✔ 自检通过：类型已换、5 个输出槽与全部连线号未变、无悬空 link")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(
        description="把 Stage2 精修的 3 步调度改成手动 sigma 列表（Identity 节点路线）")
    ap.add_argument("--src", required=True, help="输入工作流（UI 格式 json）")
    ap.add_argument("--out", help="输出工作流路径")
    ap.add_argument("--sigmas", help="逗号分隔、严格递减、以 0 结尾的 sigma 列表")
    ap.add_argument("--backend", default="auto_sol_attn_conservative_exp",
                    choices=list(BACKENDS))
    ap.add_argument("--inspect", action="store_true", help="只查看结构，不修改")
    a = ap.parse_args()

    with open(a.src, encoding="utf-8") as f:
        wf = json.load(f)

    if a.inspect:
        return inspect(wf)
    if not a.sigmas or not a.out:
        ap.error("非 --inspect 模式必须同时给 --sigmas 和 --out")

    try:
        rc = patch(wf, a.sigmas, a.backend)
    except ValueError as e:
        print("✘ sigma 不合法：%s" % e)
        print("\n未写出文件。")
        return 2
    if rc != 0:
        print("\n未写出文件。")
        return rc
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(wf, f, ensure_ascii=False, indent=2)
    print("\n✔ 已写出: %s" % a.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
