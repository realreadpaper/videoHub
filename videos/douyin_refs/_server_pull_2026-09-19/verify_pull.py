#!/usr/bin/env python3
"""按服务器端 MANIFEST.tsv 逐文件校验本机回传结果。

用法: python3 verify_pull.py [回传根目录] [清单文件]
判据: 文件存在 且 字节数一致 且 md5 一致 —— 三者全中才算通过。
"""
import hashlib, os, sys, time, collections

ROOT = sys.argv[1] if len(sys.argv) > 1 else "."
MAN = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, "MANIFEST.tsv")

def md5_of(p, chunk=1 << 20):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(chunk), b""):
            h.update(b)
    return h.hexdigest()

rows = []
with open(MAN, encoding="utf-8") as f:
    for ln in f:
        if ln.startswith("#") or not ln.strip():
            continue
        parts = ln.rstrip("\n").split("\t")
        if len(parts) != 3:
            continue
        rows.append((parts[0], int(parts[1]), parts[2]))

ok = missing = size_bad = hash_bad = err = 0
problems = []
per_tree = collections.defaultdict(lambda: [0, 0, 0])  # ok, bad, bytes
t0 = time.time()

for want_md5, want_sz, rel in rows:
    p = os.path.join(ROOT, rel)
    tree = rel.split("/")[0] + "/" + (rel.split("/")[1] if rel.count("/") > 0 else "")
    if not os.path.isfile(p):
        missing += 1
        problems.append(("缺失", rel, ""))
        per_tree[tree][1] += 1
        continue
    got_sz = os.path.getsize(p)
    if got_sz != want_sz:
        size_bad += 1
        problems.append(("字节数不符", rel, f"本地 {got_sz} vs 服务器 {want_sz}"))
        per_tree[tree][1] += 1
        continue
    try:
        got_md5 = md5_of(p)
    except OSError as e:
        err += 1
        problems.append(("读取失败", rel, str(e)))
        per_tree[tree][1] += 1
        continue
    if got_md5 != want_md5:
        hash_bad += 1
        problems.append(("md5 不符", rel, f"{got_md5[:12]} vs {want_md5[:12]}"))
        per_tree[tree][1] += 1
        continue
    ok += 1
    per_tree[tree][0] += 1
    per_tree[tree][2] += want_sz

print(f"清单条目: {len(rows)}   耗时 {time.time()-t0:.1f}s")
print(f"通过 {ok}   缺失 {missing}   字节数不符 {size_bad}   md5 不符 {hash_bad}   读错 {err}")
print()
print(f"{'子树':<26}{'通过':>7}{'异常':>7}{'体积':>12}")
for t in sorted(per_tree):
    o, b, s = per_tree[t]
    print(f"{t:<26}{o:>7}{b:>7}{s/1048576:>10.1f} MB")

if problems:
    print(f"\n异常明细（前 30 条，共 {len(problems)}）:")
    for kind, rel, extra in problems[:30]:
        print(f"  [{kind}] {rel}  {extra}")
    sys.exit(1)
print("\n全部一致：0 漏拉 / 0 损坏")
