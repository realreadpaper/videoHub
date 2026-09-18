#!/usr/bin/env python3
"""ui_dump.py — 打印 UI 格式工作流每个节点的类型 / 输入槽 / widgets / 输出"""
import json
import sys


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    nodes = data["nodes"]
    links = {l[0]: l for l in data.get("links", [])}  # link_id -> [id, src, src_slot, dst, dst_slot, type]

    print("节点数: %d  links: %d\n" % (len(nodes), len(links)))
    for n in nodes:
        print("[%s] %s   (mode=%s)" % (n.get("id"), n.get("type"), n.get("mode", 0)))
        for inp in (n.get("inputs") or []):
            lid = inp.get("link")
            if lid is not None and lid in links:
                l = links[lid]
                src = "%s.%s" % (l[1], l[2])
            else:
                src = "-"
            print("    in  %-22s type=%-14s <- %s" % (inp.get("name"), inp.get("type"), src))
        if n.get("widgets_values") is not None:
            print("    widgets = %s" % json.dumps(n["widgets_values"], ensure_ascii=False)[:300])
        for out in (n.get("outputs") or []):
            tgts = out.get("links") or []
            print("    out %-22s type=%-14s -> %s" % (out.get("name"), out.get("type"), tgts))
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
