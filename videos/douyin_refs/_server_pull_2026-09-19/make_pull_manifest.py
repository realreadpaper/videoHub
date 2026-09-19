#!/usr/bin/env python3
"""为「回传本机」的资产集生成带 md5 的清单。

用法: python3 make_pull_manifest.py <输出文件> <目录1> [目录2 ...]
输出格式（TSV）: md5 <TAB> bytes <TAB> 相对路径(<ROOT>)
ROOT = /workspace
"""
import hashlib, os, sys, json, time

ROOT = "/workspace"
TREES = sys.argv[2:]
OUT = sys.argv[1]

def md5_of(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()

rows = []
t0 = time.time()
total = 0
for tree in TREES:
    abs_tree = os.path.join(ROOT, tree)
    if not os.path.isdir(abs_tree):
        print(f"[跳过] 不存在: {abs_tree}", file=sys.stderr)
        continue
    for dirpath, dirnames, filenames in os.walk(abs_tree):
        dirnames.sort()
        for fn in sorted(filenames):
            if fn == ".DS_Store" or fn.startswith("._"):
                continue
            p = os.path.join(dirpath, fn)
            if os.path.islink(p) or not os.path.isfile(p):
                continue
            try:
                sz = os.path.getsize(p)
                m = md5_of(p)
            except OSError as e:
                print(f"[读失败] {p}: {e}", file=sys.stderr)
                continue
            rows.append((m, sz, os.path.relpath(p, ROOT)))
            total += sz

with open(OUT, "w", encoding="utf-8") as f:
    f.write(f"# videoHub server pull manifest\n")
    f.write(f"# generated: {time.strftime('%Y-%m-%d %H:%M:%S %Z')}\n")
    f.write(f"# host: {os.uname().nodename}\n")
    f.write(f"# trees: {' '.join(TREES)}\n")
    f.write(f"# files: {len(rows)}  bytes: {total}\n")
    f.write("# md5\tbytes\trelpath\n")
    for m, sz, rel in rows:
        f.write(f"{m}\t{sz}\t{rel}\n")

print(f"清单写出: {OUT}")
print(f"文件 {len(rows)} 个, 合计 {total/1048576:.1f} MB, 耗时 {time.time()-t0:.1f}s")
