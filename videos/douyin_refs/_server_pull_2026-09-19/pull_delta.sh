#!/usr/bin/env bash
# 增量补拉：抓取「MANIFEST 快照之后」服务器上新增/变更的文件
# 做法：在服务器重新生成一份清单，与本机 MANIFEST.tsv 取差集，只传差集文件。
# 用法: bash pull_delta.sh            （只列差异）
#       bash pull_delta.sh --pull     （列出并拉取）
set -uo pipefail

DEST="/Users/jianglong/Desktop/videoHub/videos/douyin_refs/_server_pull_2026-09-19"
HOST="kehu"
TREES="ComfyUI/output ComfyUI/input logs dy_key dy4 trilogy"

cd "$DEST" || exit 1

echo "===== 增量比对 $(date '+%H:%M:%S') ====="
ssh -o ConnectTimeout=20 "$HOST" \
  "/workspace/venv/bin/python3 - /workspace/_pull_2026-09-19/MANIFEST_NEW.tsv $TREES" \
  < "$DEST/make_pull_manifest.py" > /dev/null 2>&1

scp -q "$HOST:/workspace/_pull_2026-09-19/MANIFEST_NEW.tsv" "$DEST/.MANIFEST_NEW.tsv" || exit 1

# 差集：新增或 md5 变了的文件（按第三列路径比对）
awk -F'\t' '!/^#/ {print $3"\t"$1}' MANIFEST.tsv     | sort > /tmp/_old.txt
awk -F'\t' '!/^#/ {print $3"\t"$1}' .MANIFEST_NEW.tsv | sort > /tmp/_new.txt

comm -13 /tmp/_old.txt /tmp/_new.txt > /tmp/_delta.txt
N=$(wc -l < /tmp/_delta.txt | tr -d ' ')
echo "快照外新增/变更文件: $N 个"
if [ "$N" -gt 0 ]; then
  head -20 /tmp/_delta.txt | awk -F'\t' '{print "  + "$1}'
  [ "$N" -gt 20 ] && echo "  ...（共 $N 个）"
fi

if [ "${1:-}" != "--pull" ] || [ "$N" -eq 0 ]; then
  echo "（未拉取；加 --pull 参数即可下载）"
  exit 0
fi

cut -f1 /tmp/_delta.txt > /tmp/_delta_paths.txt
echo "--- 开始拉取 ---"
if ssh -o ConnectTimeout=20 "$HOST" "cd /workspace && tar -cf - -T -" < /tmp/_delta_paths.txt | tar -xf -; then
  echo "--- 完成 $(date '+%H:%M:%S') ---"
  # 把增量并入主清单，保持单一校验基准。
  # 注意：同一路径若 md5 变了，必须以新记录为准 —— 否则校验时会同时看到新旧两条，
  # 旧的那条会永远报「md5 不符」。所以按路径去重、新清单优先。
  awk -F'\t' '!/^#/ && NF==3 {print $3"\t"$0}' .MANIFEST_NEW.tsv | sort -k1,1 > /tmp/_n.txt
  awk -F'\t' '!/^#/ && NF==3 {print $3"\t"$0}' MANIFEST.tsv      | sort -k1,1 > /tmp/_o.txt
  # awk 外连接：新清单优先，旧清单补缺
  awk -F'\t' '
    NR==FNR { seen[$1]=1; print $1"\t"$2"\t"$3"\t"$4; next }
    !($1 in seen) { print $1"\t"$2"\t"$3"\t"$4 }
  ' /tmp/_n.txt /tmp/_o.txt | cut -f2- | sort -t$'\t' -k3,3 > /tmp/_merged.txt
  {
    echo "# videoHub server pull manifest (含增量，合并于 $(date '+%Y-%m-%d %H:%M:%S'))"
    echo "# md5	bytes	relpath"
    cat /tmp/_merged.txt
  } > MANIFEST.tsv
  rm -f .MANIFEST_NEW.tsv
  echo "MANIFEST.tsv 已更新，合并后 $(grep -vc '^#' MANIFEST.tsv) 条"
else
  echo "!!! 拉取失败，可重跑"
fi
