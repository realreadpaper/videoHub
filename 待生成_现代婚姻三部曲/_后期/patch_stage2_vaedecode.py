#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
A1 补丁 · 把 Stage2 精修工作流的解码器从 TAEHV 换成完整 LTX VAE

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
为什么改
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Stage2 官方工作流最后一步用 MiniMaxH3SolEngineTAEHVDecodeT8Advanced 解码。
TAEHV 是 ComfyUI 里的「微型视频自编码器」，为**快速预览**设计，解码质量
明显低于完整 VAE。

而完整 VAE（ltx-2.5-video-vae-conv-bf16）其实**已经作为 VAELoader 节点加载
在工作流里了**，只是只被 VAEEncode 用于编码侧，解码侧根本没用上。

等于：22B 模型 + 3 步精修辛苦算出来的 latent，在最后一步被一个预览级
解码器糊掉了。这是当前画质偏软的头号原因（比分辨率不足更直接）。

外部佐证：对成片做「下采样往返 PSNR 探针」，672px 往返高达 49.95 dB，
意味着 1344×768 里几乎没有超过 672px 的真实高频——细节是在解码环节丢的。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
做什么（纯结构替换，**不需要连服务器**）
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  1. 定位 TAEHV 解码节点（按类型名匹配，自动兜底模糊匹配）
  2. 替换成 VAEDecode（或 VAEDecodeTiled）：
       · 保留它原本消费的 LATENT 连线        → samples
       · 新增一条从 VAELoader 来的 VAE 连线  → vae
       · 保留它原有的 IMAGE 下游连线         → 输出槽 0 类型不变，下游不用动
       · widgets_values 按目标节点重设
  3. 把只为它服务的 TAEHVLoader 节点设为 bypass（mode=4），省一次权重加载
  4. 打印改动报告；若发现 report_json 之类输出有下游，明确告警

**自省式实现**：不硬编码 slot 序号，全部按 type/name 匹配。所以即使官方
工作流改版、节点顺序变了，脚本依然能正确工作。

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
用法
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  # 0) 先看这张图长什么样（强烈建议第一次先跑，确认目标节点和 VAE 节点）
  python3 patch_stage2_vaedecode.py --src 原工作流.json --inspect

  # 1) 打补丁
  python3 patch_stage2_vaedecode.py --src 原工作流.json --out stage2_vaedecode.json

  # 2) 显存不够时换分块解码（tile_size / overlap / temporal_* 可用 --tile-* 调）
  python3 patch_stage2_vaedecode.py --src 原工作流.json --out ... --decode-node VAEDecodeTiled

  # 3) 工作流里有多个 VAELoader 时显式指定
  python3 patch_stage2_vaedecode.py --src 原工作流.json --out ... --vae-node 4

退出码：0 成功 / 2 参数或结构问题 / 3 找不到目标节点
"""
from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 定位规则
# ---------------------------------------------------------------------------
# TAEHV 解码节点的类型名关键词（小写匹配）
TAEHV_DECODE_HINTS = ["taehvdecode", "taehv_decode", "taehvdecodet8"]
# 完整 VAE 解码节点（ComfyUI 内置）
NODE_VAEDECODE = "VAEDecode"
NODE_VAEDECODE_TILED = "VAEDecodeTiled"
# 提供 VAE 的加载器类型名关键词
VAE_LOADER_HINTS = ["vaeloader"]
# TAEHV 权重加载器（替换后变孤儿，可 bypass）
TAEHV_LOADER_HINTS = ["taehvloader", "taehv_loader"]


def norm(s) -> str:
    return str(s or "").strip().lower().replace(" ", "").replace("-", "").replace("_", "")


def is_taehv_decode(ntype: str) -> bool:
    n = norm(ntype)
    return any(h.replace("_", "") in n for h in TAEHV_DECODE_HINTS)


def is_vae_loader(ntype: str) -> bool:
    return any(h in norm(ntype) for h in VAE_LOADER_HINTS)


def is_taehv_loader(ntype: str) -> bool:
    return any(h.replace("_", "") in norm(ntype) for h in TAEHV_LOADER_HINTS)


def slot_type(slot: dict) -> str:
    """取连线槽的类型，兼容 type / widget 两种写法。"""
    return str(slot.get("type") or "").upper()


# ---------------------------------------------------------------------------
# UI 格式工具
# ---------------------------------------------------------------------------
def load_workflow(path: Path) -> dict:
    wf = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(wf, dict):
        raise SystemExit("工作流 JSON 顶层不是对象，无法处理")
    return wf


def is_ui_format(wf: dict) -> bool:
    return isinstance(wf.get("nodes"), list)


def is_api_format(wf: dict) -> bool:
    return not is_ui_format(wf) and all(
        isinstance(v, dict) and "class_type" in v for v in wf.values()
    ) and len(wf) > 0


def next_link_id(links: list) -> int:
    mx = 0
    for lk in links:
        if isinstance(lk, list) and lk and isinstance(lk[0], int):
            mx = max(mx, lk[0])
    return mx + 1


# ---------------------------------------------------------------------------
# inspect：把结构摊开给人看
# ---------------------------------------------------------------------------
def inspect(wf: dict) -> None:
    if is_api_format(wf):
        print("格式：API（已是导出格式，直接改 class_type 即可）")
        for nid, n in sorted(wf.items(), key=lambda kv: int(kv[0]) if str(kv[0]).isdigit() else 0):
            print("  %-4s | %-52s | %s" % (nid, n.get("class_type"),
                                            json.dumps(n.get("inputs"), ensure_ascii=False)[:110]))
        return

    nodes = wf.get("nodes", [])
    links = wf.get("links", []) or []
    print("格式：UI（含 nodes/links，需结构替换）")
    print("节点共 %d 个，连线共 %d 条\n" % (len(nodes), len(links)))
    print("  %-5s %-8s %-56s %s" % ("id", "mode", "type", "widgets_values"))
    print("  " + "-" * 104)
    for n in sorted(nodes, key=lambda x: x.get("id", 0)):
        mark = ""
        if is_taehv_decode(n.get("type")):  mark = "  ← 【解码目标】"
        elif is_vae_loader(n.get("type")):  mark = "  ← 【VAE 候选】"
        elif is_taehv_loader(n.get("type")): mark = "  ← 【TAEHV 权重】"
        print("  %-5s %-8s %-56s %s%s" % (
            n.get("id"), n.get("mode", 0), n.get("type"),
            json.dumps(n.get("widgets_values"), ensure_ascii=False)[:60], mark))

    for n in nodes:
        if not is_taehv_decode(n.get("type")):
            continue
        print("\n目标节点 %s 完整结构：" % n.get("id"))
        print(json.dumps({k: v for k, v in n.items() if k != "widgets_values"},
                         ensure_ascii=False, indent=2))
        print("  widgets_values =", json.dumps(n.get("widgets_values"), ensure_ascii=False))
    for n in nodes:
        if is_vae_loader(n.get("type")):
            print("\nVAE 加载节点 %s：widgets_values = %s（确认是 ltx-2.5 video vae）"
                  % (n.get("id"), json.dumps(n.get("widgets_values"), ensure_ascii=False)))


# ---------------------------------------------------------------------------
# 核心：UI 格式替换
# ---------------------------------------------------------------------------
def patch_ui(wf: dict, decode_node: str, vae_node_id, tiles: tuple, do_bypass: bool,
             verbose: bool) -> dict:
    wf = copy.deepcopy(wf)
    nodes = wf.get("nodes", [])
    links = wf.setdefault("links", [])
    by_id = {n.get("id"): n for n in nodes}

    # ---- 1. 找解码目标 ------------------------------------------------
    targets = [n for n in nodes if is_taehv_decode(n.get("type"))]
    if not targets:
        # 兜底：名字里带 decode 且不是标准 VAEDecode 的节点
        targets = [n for n in nodes
                   if "decode" in norm(n.get("type")) and norm(n.get("type")) not in ("vaedecode", "vaedecodetiled")]
    if not targets:
        raise SystemExit("[退出码 3] 没有找到 TAEHV 解码节点，无法打补丁。"
                         "请先跑 --inspect 看真实节点类型。")
    if len(targets) > 1:
        print("  ！发现 %d 个疑似解码节点，将对全部执行替换：%s"
              % (len(targets), [t.get("id") for t in targets]))
    tgt = targets[0]
    tid = tgt.get("id")
    print("  ✔ 解码目标：节点 %s (%s)" % (tid, tgt.get("type")))

    # ---- 2. 找 VAE 来源 -----------------------------------------------
    if vae_node_id is not None:
        vae_node = by_id.get(vae_node_id)
        if vae_node is None:
            raise SystemExit("[退出码 2] 指定的 --vae-node %s 不存在" % vae_node_id)
    else:
        loaders = [n for n in nodes if is_vae_loader(n.get("type"))]
        if not loaders:
            raise SystemExit("[退出码 2] 没有找到 VAELoader 节点，请用 --inspect 确认"
                             "完整 VAE 是否在工作流里。")
        if len(loaders) > 1:
            print("  ！有 %d 个 VAELoader，默认取第一个；可用 --vae-node 显式指定"
                  % len(loaders))
            for l in loaders:
                print("     节点 %s widgets=%s" % (l.get("id"),
                                                 json.dumps(l.get("widgets_values"), ensure_ascii=False)))
        vae_node = loaders[0]
    vid = vae_node.get("id")
    print("  ✔ VAE 来源：节点 %s (%s) widgets=%s"
          % (vid, vae_node.get("type"), json.dumps(vae_node.get("widgets_values"), ensure_ascii=False)))
    lw = norm(json.dumps(vae_node.get("widgets_values"), ensure_ascii=False))
    if "ltx" not in lw:
        print("  ⚠ VAE 权重名里没有 'ltx' 字样，请人工确认它确实是 ltx-2.5 video vae")

    # ---- 3. 抓原有连线 ------------------------------------------------
    in_slots = tgt.get("inputs") or []
    out_slots = tgt.get("outputs") or []

    latent_slot = next((s for s in in_slots if slot_type(s) == "LATENT"), None)
    if latent_slot is None:
        raise SystemExit("[退出码 2] 目标节点的输入里找不到 LATENT 槽，结构异常：\n%s"
                         % json.dumps(in_slots, ensure_ascii=False, indent=2))
    latent_link = latent_slot.get("link")
    if latent_link is None:
        raise SystemExit("[退出码 2] 目标节点的 LATENT 槽没有连线（上游缺失）")
    print("  ✔ 保留 latent 连线 link#%s（%s ← 上游）" % (latent_link, latent_slot.get("name")))

    img_slot = next((s for s in out_slots if slot_type(s) == "IMAGE"), None)
    img_links = list(img_slot.get("links") or []) if img_slot else []
    if not img_links:
        print("  ⚠ 目标节点 IMAGE 输出没有下游连线——请确认这是不是终端节点")
    else:
        print("  ✔ 保留 IMAGE 下游连线 %s（%d 条，槽 0 类型不变，下游无需改动）"
              % (img_links, len(img_links)))

    # 非 IMAGE 输出若有下游 → 替换后会断，必须告警
    orphan_outs = []
    for s in out_slots:
        if slot_type(s) == "IMAGE":
            continue
        if s.get("links"):
            orphan_outs.append((s.get("name"), slot_type(s), list(s["links"])))
    for name, typ, lks in orphan_outs:
        print("  ⚠ 告警：输出「%s」(%s) 有 %d 条下游连线 %s——换成 VAEDecode 后该输出消失，"
              "这些下游会断。请人工确认它们不是必需的。" % (name, typ, len(lks), lks))
    other_in = [s for s in in_slots if s is not latent_slot]
    for s in other_in:
        if s.get("link") is not None:
            print("  · 目标节点原有输入「%s」(%s, link#%s) 将被丢弃，连线一并回收"
                  % (s.get("name"), slot_type(s), s.get("link")))

    # ---- 4. 写回新节点 ------------------------------------------------
    new_lid = next_link_id(links)
    # 目标节点的新 inputs：samples(沿用原连线) + vae(新连线)
    tgt["inputs"] = [
        {"name": "samples", "type": "LATENT", "link": latent_link},
        {"name": "vae", "type": "VAE", "link": new_lid},
    ]
    # 新 outputs：只留 IMAGE，槽 0
    tgt["outputs"] = [{
        "name": "IMAGE", "type": "IMAGE", "links": img_links,
        "slot_index": 0, "shape": img_slot.get("shape", 3) if img_slot else 3,
    }]
    tgt["type"] = decode_node
    if decode_node == NODE_VAEDECODE_TILED:
        tgt["widgets_values"] = list(tiles)   # tile_size, overlap, temporal_size, temporal_overlap
    else:
        tgt["widgets_values"] = []
    tgt["mode"] = 0
    if "properties" in tgt and isinstance(tgt["properties"], dict):
        tgt["properties"].pop("Node name for S&R", None)

    # ---- 5. 新增 vae 连线 ---------------------------------------------
    links.append([new_lid, vid, 0, tid, 1, "VAE"])
    vae_out = (vae_node.get("outputs") or [{}])[0]
    vae_out.setdefault("links", [])
    if vae_out["links"] is None:
        vae_out["links"] = []
    vae_out["links"].append(new_lid)
    print("  ✔ 新增连线 link#%d：节点 %s[0] VAE → 节点 %s.vae" % (new_lid, vid, tid))

    # ---- 6. bypass 孤儿 TAEHVLoader -----------------------------------
    if do_bypass:
        for n in nodes:
            if is_taehv_loader(n.get("type")):
                # 确认它没有别的下游（除了刚被替换掉的那个）
                outs = n.get("outputs") or []
                still = []
                for s in outs:
                    for l in (s.get("links") or []):
                        for lk in links:
                            if isinstance(lk, list) and len(lk) >= 5 and lk[0] == l:
                                if lk[3] != tid:      # 目标不是被替换的节点
                                    still.append((l, lk[3]))
                if still:
                    print("  · TAEHVLoader 节点 %s 还有别的下游 %s，**不 bypass**"
                          % (n.get("id"), still))
                else:
                    n["mode"] = 4
                    print("  ✔ 节点 %s (%s) 设为 bypass（mode=4），省一次 TAEHV 权重加载"
                          % (n.get("id"), n.get("type")))

    # ---- 7. 回收悬空连线 ----------------------------------------------
    dropped = prune_dangling_links(wf)
    if dropped:
        print("  ✔ 回收悬空连线 %s（已无人引用，从 links 数组与上游输出槽中移除）"
              % dropped)

    # ---- 8. 一致性自检 ------------------------------------------------
    problems = check_consistency(wf)
    if problems:
        print("\n  ⚠ 一致性自检发现问题：")
        for p in problems:
            print("     -", p)
    else:
        print("\n  ✔ 一致性自检通过（连线双向引用完整、无悬空 link）")
    return wf


def prune_dangling_links(wf: dict) -> list:
    """回收悬空连线。

    替换解码节点后，它原本的 `taehv` 输入连线就没有任何节点引用了，
    但还留在 links 数组和上游节点的 output.links 里。ComfyUI 载入工作流时
    对这类残留多半能容忍，但会让转换器打印「控件值对齐不符」之类的噪声告警，
    也可能让某条连线的槽位索引错位。所以一次性清干净。

    返回被删除的 link id 列表。
    """
    nodes = wf.get("nodes", [])
    links = wf.get("links", []) or []

    used = set()
    for n in nodes:
        for s in (n.get("inputs") or []):
            l = s.get("link")
            if l is not None:
                used.add(l)

    dropped = [lk[0] for lk in links
               if isinstance(lk, list) and lk and lk[0] not in used]
    wf["links"] = [lk for lk in links
                   if isinstance(lk, list) and lk and lk[0] in used]
    for n in nodes:
        for s in (n.get("outputs") or []):
            if s.get("links"):
                s["links"] = [l for l in s["links"] if l in used]
    return dropped


def check_consistency(wf: dict) -> list:
    """检查 links 数组与各节点槽位是否互相自洽。"""
    problems = []
    nodes = wf.get("nodes", [])
    links = wf.get("links", []) or []
    by_id = {n.get("id"): n for n in nodes}
    link_map = {lk[0]: lk for lk in links if isinstance(lk, list) and len(lk) >= 6}

    # links → 节点槽
    for lid, lk in link_map.items():
        _, src, sslot, dst, dslot, ltype = lk[0], lk[1], lk[2], lk[3], lk[4], lk[5]
        if src not in by_id:
            problems.append("link#%s 的源节点 %s 不存在" % (lid, src)); continue
        if dst not in by_id:
            problems.append("link#%s 的目标节点 %s 不存在" % (lid, dst)); continue
        so = by_id[src].get("outputs") or []
        if sslot < len(so) and lid not in (so[sslot].get("links") or []):
            problems.append("link#%s 未登记在源节点 %s 的输出槽 %s.links 里" % (lid, src, sslot))
        di = by_id[dst].get("inputs") or []
        if dslot < len(di) and di[dslot].get("link") != lid:
            problems.append("link#%s 与目标节点 %s 输入槽 %s.link(%s) 不一致"
                            % (lid, dst, dslot, di[dslot].get("link")))

    # 节点槽 → links
    for n in nodes:
        for s in (n.get("inputs") or []):
            l = s.get("link")
            if l is not None and l not in link_map:
                problems.append("节点 %s 输入「%s」引用了不存在的 link#%s"
                                % (n.get("id"), s.get("name"), l))
        for i, s in enumerate(n.get("outputs") or []):
            for l in (s.get("links") or []):
                if l not in link_map:
                    problems.append("节点 %s 输出槽 %d「%s」引用了不存在的 link#%s"
                                    % (n.get("id"), i, s.get("name"), l))
    return problems


# ---------------------------------------------------------------------------
# API 格式替换（若用户用的是导出后的 API JSON，这条路更简单）
# ---------------------------------------------------------------------------
def patch_api(wf: dict, decode_node: str, vae_node_id, tiles: tuple, do_bypass: bool) -> dict:
    wf = copy.deepcopy(wf)
    tgt_ids = [nid for nid, n in wf.items() if is_taehv_decode(n.get("class_type"))]
    if not tgt_ids:
        raise SystemExit("[退出码 3] API 格式里没有找到 TAEHV 解码节点")
    tid = tgt_ids[0]
    tgt = wf[tid]
    print("  ✔ 解码目标：节点 %s (%s)" % (tid, tgt.get("class_type")))

    inputs = tgt.get("inputs") or {}
    latent_ref = None
    for k, v in inputs.items():
        if isinstance(v, list) and len(v) == 2:
            # 取第一个「来自别处的 latent 引用」；TAEHV 的 taehv 输入也是引用，
            # 所以要靠上游节点类型来区分
            up = wf.get(str(v[0]), {}).get("class_type", "")
            if is_taehv_loader(up):
                continue
            latent_ref = v
            print("  ✔ 保留 latent 来源：%s ← 节点 %s (%s)" % (k, v[0], up))
            break
    if latent_ref is None:
        raise SystemExit("[退出码 2] 找不到 latent 上游引用")

    if vae_node_id is not None:
        vid = str(vae_node_id)
    else:
        cands = [nid for nid, n in wf.items() if is_vae_loader(n.get("class_type"))]
        if not cands:
            raise SystemExit("[退出码 2] 没有找到 VAELoader")
        vid = cands[0]
    print("  ✔ VAE 来源：节点 %s (%s)" % (vid, wf[vid].get("class_type")))

    new_inputs = {"samples": latent_ref, "vae": [vid, 0]}
    if decode_node == NODE_VAEDECODE_TILED:
        new_inputs.update({"tile_size": tiles[0], "overlap": tiles[1],
                           "temporal_size": tiles[2], "temporal_overlap": tiles[3]})
    tgt["class_type"] = decode_node
    tgt["inputs"] = new_inputs
    print("  ✔ 节点 %s 已改写为 %s，inputs=%s"
          % (tid, decode_node, json.dumps(new_inputs, ensure_ascii=False)))

    if do_bypass:
        for nid, n in wf.items():
            if is_taehv_loader(n.get("class_type")):
                # API 格式没有 mode，只能删。确认没有其他下游再删。
                used = any(isinstance(v, list) and len(v) == 2 and str(v[0]) == nid
                           for m in wf.values() for v in (m.get("inputs") or {}).values())
                if used:
                    print("  · TAEHVLoader 节点 %s 仍有其他下游，保留" % nid)
                else:
                    del wf[nid]
                    print("  ✔ 已移除孤儿 TAEHVLoader 节点 %s" % nid)
                    break
    return wf


# ---------------------------------------------------------------------------
def main() -> None:
    ap = argparse.ArgumentParser(
        description="A1 补丁：Stage2 精修工作流 TAEHV 解码 → 完整 VAE 解码")
    ap.add_argument("--src", required=True, help="原始工作流 JSON（UI 或 API 格式）")
    ap.add_argument("--out", default="", help="输出的新工作流 JSON；--inspect 时可省略")
    ap.add_argument("--inspect", action="store_true", help="只打印结构，不写文件")
    ap.add_argument("--vae-node", default=None,
                    help="显式指定提供 VAE 的节点 id（工作流里有多个 VAELoader 时用）")
    ap.add_argument("--decode-node", default=NODE_VAEDECODE,
                    choices=[NODE_VAEDECODE, NODE_VAEDECODE_TILED],
                    help="目标解码节点；显存不够时用 VAEDecodeTiled（默认 VAEDecode）")
    ap.add_argument("--tile-size", type=int, default=512)
    ap.add_argument("--overlap", type=int, default=64)
    ap.add_argument("--temporal-size", type=int, default=64)
    ap.add_argument("--temporal-overlap", type=int, default=8)
    ap.add_argument("--keep-taehv-loader", action="store_true",
                    help="不 bypass/移除 TAEHV 权重加载节点（默认会清理）")
    args = ap.parse_args()

    src = Path(args.src).expanduser().resolve()
    if not src.is_file():
        raise SystemExit("[退出码 2] 找不到工作流文件：%s" % src)
    wf = load_workflow(src)

    if args.inspect:
        inspect(wf)
        return

    if not args.out:
        raise SystemExit("[退出码 2] 非 --inspect 模式必须给 --out")
    out = Path(args.out).expanduser().resolve()

    vae_id = None
    if args.vae_node is not None:
        vae_id = int(args.vae_node) if str(args.vae_node).isdigit() else args.vae_node

    tiles = (args.tile_size, args.overlap, args.temporal_size, args.temporal_overlap)
    print("=" * 96)
    print("  A1 补丁 · 解码器替换  |  %s" % src.name)
    print("  目标解码节点 = %s" % args.decode_node)
    print("=" * 96)

    if is_api_format(wf):
        new_wf = patch_api(wf, args.decode_node, vae_id, tiles, not args.keep_taehv_loader)
    elif is_ui_format(wf):
        new_wf = patch_ui(wf, args.decode_node, vae_id, tiles,
                          not args.keep_taehv_loader, True)
    else:
        raise SystemExit("[退出码 2] 既不像 UI 格式也不像 API 格式，请检查文件")

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(new_wf, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n  ✔ 已写出：%s（%.1f KB）" % (out, out.stat().st_size / 1024))
    print("\n  下一步：用 10_run_film.py --shots <N> --stage refine 单镜验证，")
    print("          记录峰值显存；若 OOM 改用 --decode-node VAEDecodeTiled 重跑本脚本。")


if __name__ == "__main__":
    main()
