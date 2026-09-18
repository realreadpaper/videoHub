#!/usr/bin/env python3
"""wf_summary.py — 解析 ComfyUI 工作流：节点类型分布 + 外部文件引用 + 模型引用"""
import json
import sys
from collections import Counter

EXT = (".wav", ".mp3", ".flac", ".jpg", ".jpeg", ".png", ".webp",
       ".mp4", ".mov", ".safetensors", ".ckpt", ".pt", ".json")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if not path:
        print("用法: wf_summary.py <workflow.json>")
        return 1
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    nodes = data.get("prompt", data)

    print("文件: %s" % path)
    print("节点数: %d" % len(nodes))

    print("\n--- 节点类型分布 ---")
    counter = Counter(v.get("class_type") for v in nodes.values())
    for cls, num in counter.most_common():
        print("  %3d  %s" % (num, cls))

    print("\n--- 外部文件引用 ---")
    found = False
    for nid in sorted(nodes, key=lambda x: int(x) if str(x).isdigit() else 0):
        node = nodes[nid]
        for key, val in (node.get("inputs") or {}).items():
            if isinstance(val, str) and val.lower().endswith(EXT):
                print("  [%s] %s.%s = %r" % (nid, node.get("class_type"), key, val))
                found = True
    if not found:
        print("  （无字符串形式的文件引用）")

    print("\n--- 关键节点（模型加载 / 采样 / 输出）---")
    KEYS = ("Loader", "Load", "Sampler", "Save", "Decode", "Encode", "Audio", "MiniMax", "Latent")
    for nid in sorted(nodes, key=lambda x: int(x) if str(x).isdigit() else 0):
        node = nodes[nid]
        cls = node.get("class_type") or ""
        if any(k in cls for k in KEYS):
            ins = node.get("inputs") or {}
            brief = {k: v for k, v in ins.items() if not isinstance(v, list)}
            print("  [%s] %s  %s" % (nid, cls, json.dumps(brief, ensure_ascii=False)[:180]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
