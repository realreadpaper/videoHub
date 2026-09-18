#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""探测 H3 关键节点的真实输入定义（消除 widget / slot 索引的不确定性）。
为什么需要
----------
`build_voice_workflow.py` 往 `MiniMaxH3AudioConditioningT8` 的 `first_frame` / `last_frame` /
`ref_images` 等槽接输入时，slot 号是按模板 JSON 的 inputs 数组顺序推出来的；
而节点内部的 **widget 顺序**（widgets_values 各位置到底对应哪个参数）只能靠猜。
一旦节点版本升级、参数增删，猜测就会静默错位 —— 生成出来的是错参数、却不会报错。

本脚本直接读 ComfyUI 的 `/object_info`，把 required / optional 的**真实顺序**打出来，
并可用 `--dump-slots` 落一份 `h3_slots.json` 给生成器消费（名字 → 索引 + 类型）。

用法（远端实例恢复后在远端跑，或本地有 ComfyUI 时本地跑）
------------------------------------------------------
  python3 probe_h3_nodes.py                              # 打印真实顺序
  python3 probe_h3_nodes.py --dump-slots h3_slots.json    # 额外落一份槽位映射表
  python3 probe_h3_nodes.py --url http://127.0.0.1:8188
"""
import argparse
import json
import os
import sys
import urllib.request

# 节点定义里的「连接槽」顺序 —— 即前端 inputs 数组顺序（length 这类
# 既可 widget 又可连线；只要被连上就会出现在 inputs 里）。
# 生成器在没有 h3_slots.json 时会回退到这份表，所以它是**必须被实测校正**的。
SLOT_FALLBACK = [
    "clip", "video_vae", "audio_vae", "length", "drive_audio", "final_audio",
    "first_frame", "last_frame",
    "ref_images", "ref_videos", "ref_video_audios", "ref_audios",
]

NODES = [
    "MiniMaxH3AudioConditioningT8",
    "MiniMaxH3AudioWindowT8",
    "MiniMaxH3AVDecodeT8",
    "MiniMaxH3DualClockSamplerT8",
    "MiniMaxH3OutputTrimT8",
    "MiniMaxH3PreflightT8",
    "MiniMaxH3AudioLatentControlT8",
    "LoadImage",
]


def get(url, timeout=20):
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fmt(v):
    if isinstance(v, list) and v:
        t = v[0]
        if isinstance(t, list):
            return "ENUM%s" % t[:8]
        return str(t)
    return str(v)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://127.0.0.1:8188")
    ap.add_argument("--dump-slots", default=None,
                    help="把 input 槽位映射写到该路径（默认 h3_slots.json，传 '' 关闭）")
    ap.add_argument("--template", default=None,
                    help="UI 工作流 JSON：读其 conditioning 节点的 inputs 数组作槽序权威基底")
    a = ap.parse_args()
    base = a.url.rstrip("/")

    try:
        get(base + "/system_stats", timeout=8)
    except Exception as e:
        sys.exit("✘ 连不上 ComfyUI %s：%s\n  （实例没起来 / 端口未转发时属正常，等实例恢复再跑）"
                 % (base, e))

    # ★ 模板基底：ComfyUI 前端序列化出的 inputs 数组才是槽序的权威来源。
    #   见下方 order 计算处的详细说明。
    COND = "MiniMaxH3AudioConditioningT8"
    template_order = []
    if a.template and os.path.isfile(a.template):
        try:
            td = json.load(open(a.template, encoding="utf-8"))
            for node in td.get("nodes", []):
                if node.get("type") == COND:
                    template_order = [i.get("name") for i in (node.get("inputs") or [])]
                    break
            if template_order:
                print("✓ 模板基底 %s" % a.template)
                print("  %s" % template_order)
            else:
                print("⚠ 模板里没找到 %s 节点" % COND)
        except Exception as e:
            print("⚠ 模板读取失败：%s" % e)
    elif a.template:
        print("⚠ 模板不存在：%s" % a.template)

    slotmap = {}
    for n in NODES:
        try:
            info = get("%s/object_info/%s" % (base, n))[n]
        except Exception as e:
            print("=" * 72)
            print("✘ %-34s 取不到：%s" % (n, e))
            continue
        inp = info.get("input", {})
        req = inp.get("required", {}) or {}
        opt = inp.get("optional", {}) or {}
        print("=" * 72)
        print(n)
        print("  required（顺序 = widget/link 前台顺序）:")
        for i, (k, v) in enumerate(req.items()):
            print("     [%d] %-26s %s" % (i, k, fmt(v)))
        if opt:
            print("  optional:")
            for i, (k, v) in enumerate(opt.items()):
                print("     [%d] %-26s %s" % (i, k, fmt(v)))
        print("  outputs:", info.get("output"), info.get("output_name"))

        # 槽位映射：required 里「类型不是基础标量」的视为连接槽，加上全部 optional
        order = []
        scalar = {"INT", "FLOAT", "STRING", "BOOLEAN", "COMBO"}
        req_link = [k for k, v in req.items() if fmt(v).split("ENUM")[0] not in scalar]
        opt_names = list(opt.keys())

        # ★ 关键修正（2026-09-17，实测校正）：
        # 可连线的 required 标量（如 `length`，INT 但被从上游接进来）在前端序列化出的
        # inputs 数组里**仍位于 required 段内**（clip/video_vae/audio_vae 之后），
        # 不是被追加到末尾。旧算法一律当 widget 追加末尾，会让后续 optional 槽
        # 全部往前挤：ref_images 从正确的 8 算成 7，first_frame 从 6 算成 5 …
        # 后果是**接线错位但不报任何错**，参考图/首帧静默失效。
        # 正确做法：以模板 JSON 的 inputs 数组为基底（它由前端写出，天然正确），
        # 再把模板尚未包含的 optional 槽按定义顺序追加。
        if n == COND and template_order:
            tbase = [k for k in template_order if k in req or k in opt]
            order_names = tbase + opt_names
        else:
            order_names = req_link + opt_names
        seen, uniq = set(), []
        for k in order_names:
            if k not in seen:
                seen.add(k)
                uniq.append(k)
        for k in uniq:
            kind = "required" if k in req else "optional"
            t = fmt(req[k] if k in req else opt[k]).split("ENUM")[0]
            order.append({"name": k, "type": t, "kind": kind})
        # 仍未登记的 required 标量（不被连线、纯 widget）也记一笔，便于按名字定位
        for k, v in req.items():
            if not any(x["name"] == k for x in order):
                order.append({"name": k, "type": fmt(v), "kind": "required-scalar"})
        slotmap[n] = order
        # widget 顺序（前端 widgets_values 各位置）
        wid = [k for k, v in req.items()]
        print("  widget 顺序:", wid)

    out = a.dump_slots
    if out is None:
        out = "h3_slots.json"
    if out:
        cond = slotmap.get("MiniMaxH3AudioConditioningT8") or []
        names = [x["name"] for x in cond]
        payload = {
            "_note": "由 probe_h3_nodes.py 从 /object_info 导出；生成器优先读它，缺失则回退 SLOT_FALLBACK",
            "source": base,
            "h3_slots": slotmap,
            "cond_slot_order": names,
            "cond_slot_index": {n: i for i, n in enumerate(names)},
        }
        p = os.path.abspath(out)
        json.dump(payload, open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print("=" * 72)
        print("✓ 槽位映射已写出: %s" % p)
        print("  conditioning 槽顺序: %s" % names)
        # 与回退表对照，明确提示差异
        diff = [(i, x) for i, x in enumerate(SLOT_FALLBACK) if i >= len(names) or names[i] != x]
        if diff:
            print("  ⚠ 与生成器回退表不一致，务必让 build_voice_workflow.py 读这份 json:")
            for i, x in diff[:8]:
                got = names[i] if i < len(names) else "(无)"
                print("     [%d] 回退=%s  实际=%s" % (i, x, got))
        else:
            print("  ✔ 与生成器回退表完全一致，无需改动")


if __name__ == "__main__":
    main()
