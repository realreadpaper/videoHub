#!/usr/bin/env bash
# 把两部片的分镜投送到远端 4090，建成可直接投产的 H3 工程。
#
#   export SSHPASS='远端密码'
#   bash deploy.sh [host] [port]        # 默认 root@117.50.188.156 23
#
# 做四件事：生成 spec -> 投送 patch_film.py 与 manifest -> 远端建工程 -> 逐项验证
set -euo pipefail
cd "$(dirname "$0")"

HOST="${1:-root@117.50.188.156}"
PORT="${2:-23}"
: "${SSHPASS:?请先 export SSHPASS=远端密码}"

PY=/Users/hejianglong/.workbuddy/binaries/python/versions/3.13.12/bin/python3
STAGE="$(mktemp -d)"
trap 'rm -rf "$STAGE"' EXIT

echo "== 1/5 生成 spec =="
"$PY" - "$STAGE/spec.json" <<'PYEOF'
import json, os, sys
specs = []
for slug, d in [("douyin-office", "film1-office"),
                ("douyin-blinddate", "film2-blinddate")]:
    m = json.load(open(os.path.join(d, "manifest.json"), encoding="utf-8"))
    specs.append({
        "slug": slug,
        "seed": m["seed"],
        "title": m["film_title"],
        "outname": m["film_title"].replace(" · ", "_") + "_全片.mp4",
    })
    print("   %-18s seed=%d  %s" % (slug, m["seed"], m["film_title"]))
json.dump(specs, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=2)
PYEOF

SSH="sshpass -e ssh -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 $HOST"
SCP="sshpass -e scp -P $PORT -o StrictHostKeyChecking=no"

echo "== 2/5 投送文件 =="
$SSH "mkdir -p /tmp/h3dep"
$SCP patch_film.py "$HOST:/tmp/h3dep/patch_film.py"
$SCP "$STAGE/spec.json" "$HOST:/tmp/h3dep/spec.json"
$SCP film1-office/manifest.json "$HOST:/tmp/h3dep/manifest-office.json"
$SCP film2-blinddate/manifest.json "$HOST:/tmp/h3dep/manifest-blinddate.json"
echo "   patch_film.py + spec.json + 2 份 manifest"

echo "== 3/5 远端建工程 =="
$SSH '/workspace/venv/bin/python /tmp/h3dep/patch_film.py /tmp/h3dep/spec.json'

echo "== 4/5 落位 manifest =="
$SSH '
set -e
cp /tmp/h3dep/manifest-office.json    /workspace/films/douyin-office/manifest.json
cp /tmp/h3dep/manifest-blinddate.json /workspace/films/douyin-blinddate/manifest.json
for s in douyin-office douyin-blinddate; do
  printf "   %-18s manifest %s 字节\n" "$s" "$(stat -c %s /workspace/films/$s/manifest.json)"
done'

echo "== 5/5 验证（--list 读 manifest 前 4 镜）=="
$SSH '
for s in douyin-office douyin-blinddate; do
  echo "--- $s ---"
  cd /workspace/films/$s
  /workspace/venv/bin/python 10_run_film.py --list 2>&1 | head -4
  echo "   ..."
done'

echo
echo "投送完成。下一步（远端执行，先跑一镜验竖版构图）："
echo "  cd /workspace/films/douyin-office && /workspace/venv/bin/python 10_run_film.py --shots 1 --stage both"
