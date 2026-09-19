#!/usr/bin/env python3
"""从回传日志里抽取「每镜 GPU 耗时」，按批次/日志聚合成分析表。

覆盖的日志格式（本工程 2026-09 实跑产出）:
  [HH:MM:SS][A] -> dy1_s088
  [✓] 用时 180.2 s  status=success completed=True
     节点#12 → {"images": [{"filename": "dy1_s088_00001_.mp4",
                            "subfolder": "dy_six", ...}], "animated": [true]}
  [✗] 用时  70.1 s  status=error completed=False   ← 失败镜同样计入统计（很重要）

用法:
  python3 analyze_logs.py <根目录> [--json 输出.json] [--md 输出.md]
"""
import json, os, re, statistics as st, sys, collections

RE_SHOT = re.compile(r"(?:->|done)\s+([A-Za-z0-9_]+)\s*$")
RE_TIME = re.compile(r"用时\s+([\d.]+)\s*s\s+status=(\w+)")
RE_OK = re.compile(r"\[(?:[A-Z0-9]+)\]\s+OK\s+([A-Za-z0-9_]+)\s+(\d+)s")
RE_SUB = re.compile(r'"subfolder":\s*"([^"]+)"')


def parse_file(path):
    """返回 [(shot, seconds, status, batch|None)]"""
    out = []
    cur_shot = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.rstrip("\n")
            m = RE_OK.search(line)
            if m:
                # 形如 [A] OK dy1_s003  110s —— 这是权威落账行，覆盖本镜
                shot, sec = m.group(1), int(m.group(2))
                for r in reversed(out):
                    if r[0] == shot:
                        break
                out.append((shot, sec, "success", None))
                continue
            m = RE_TIME.search(line)
            if m:
                sec, status = float(m.group(1)), m.group(2)
                out.append((cur_shot or "?", sec, status, None))
                continue
            m = RE_SUB.search(line)
            if m and out:
                s, sec, status, _ = out[-1]
                out[-1] = (s, sec, status, m.group(1))
                continue
            m = RE_SHOT.search(line)
            if m:
                cur_shot = m.group(1)
    return out


def main():
    root = sys.argv[1] if len(sys.argv) > 1 else "."
    rows = []          # (logfile, shot, sec, status, batch)
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in sorted(filenames):
            if not fn.endswith(".log"):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.getsize(p) == 0:
                continue
            rel = os.path.relpath(p, root)
            for shot, sec, status, batch in parse_file(p):
                rows.append((rel, shot, sec, status, batch or "?"))

    if not rows:
        print("未解析到任何计时行，请检查日志格式。")
        return

    by_batch = collections.defaultdict(list)
    for rel, shot, sec, status, batch in rows:
        by_batch[batch].append((shot, sec, status))

    print(f"解析到 {len(rows)} 条计时记录，来自 {len({r[0] for r in rows})} 个日志，"
          f"{len(by_batch)} 个批次\n")
    print(f"{'批次':<16}{'镜数':>5}{'成功':>5}{'失败':>5}{'中位s':>9}{'均值s':>9}{'最短':>7}{'最长':>7}{'总机时s':>10}")
    print("-" * 74)
    summary = {}
    for b in sorted(by_batch):
        items = by_batch[b]
        ok = [x for x in items if x[2] == "success"]
        bad = [x for x in items if x[2] != "success"]
        v = [x[1] for x in ok] or [x[1] for x in items]
        summary[b] = {
            "shots": len(items), "ok": len(ok), "fail": len(bad),
            "median_s": round(st.median(v), 1), "mean_s": round(st.mean(v), 1),
            "min_s": min(v), "max_s": max(v), "total_s": round(sum(x[1] for x in items), 1),
        }
        print(f"{b:<16}{len(items):>5}{len(ok):>5}{len(bad):>5}"
              f"{st.median(v):>9.1f}{st.mean(v):>9.1f}{min(v):>7.1f}{max(v):>7.1f}"
              f"{sum(x[1] for x in items):>10.1f}")

    args = sys.argv[2:]
    if "--json" in args:
        p = args[args.index("--json") + 1]
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"by_batch": summary,
                       "rows": [{"log": r[0], "shot": r[1], "sec": r[2],
                                 "status": r[3], "batch": r[4]} for r in rows]},
                      f, ensure_ascii=False, indent=1)
        print(f"\nJSON 写出: {p}")
    if "--md" in args:
        p = args[args.index("--md") + 1]
        with open(p, "w", encoding="utf-8") as f:
            f.write("| 批次 | 镜数 | 成功 | 失败 | 中位 s | 均值 s | 最短 s | 最长 s | 总机时 s |\n")
            f.write("|---|---|---|---|---|---|---|---|---|\n")
            for b, s in sorted(summary.items()):
                f.write(f"| `{b}` | {s['shots']} | {s['ok']} | {s['fail']} | {s['median_s']} | "
                        f"{s['mean_s']} | {s['min_s']} | {s['max_s']} | {s['total_s']} |\n")
        print(f"Markdown 写出: {p}")


if __name__ == "__main__":
    main()
