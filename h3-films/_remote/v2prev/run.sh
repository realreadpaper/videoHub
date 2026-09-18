#!/bin/bash
# v2 关键分镜预览 · 三段五步（权重驻留序：fl2va 草稿×2 → ref2va 直出×1 → LTX 精修×2）
set -x
cd /root/v2prev
S="python3 /root/s2/submit_api.py"
OUT=/workspace/ComfyUI/output/MiniMaxH3/v2prev
IN=/workspace/ComfyUI/input

echo "== [1/5] T2V 草稿 f2s03 (384) =="
$S d_f2s03.json || exit 1
echo "== [2/5] T2V 草稿 f1s01 (384, fl2va 热跑) =="
$S d_f1s01.json || exit 1
echo "== [3/5] Ref2VA 直出 768 f2s35 (产品镜, ref2va 权重切换) =="
$S x_f2s35.json || exit 1

echo "== 草稿归位供精修输入 =="
cp $OUT/f2s03_draft_*.mp4 $IN/drafts/v2prev/f2s03_draft.mp4
cp $OUT/f1s01_draft_*.mp4 $IN/drafts/v2prev/f1s01_draft.mp4

echo "== [4/5] LTX 精修 f2s03 (768, LTX 权重切换) =="
$S r_f2s03.json || exit 1
echo "== [5/5] LTX 精修 f1s01 (768, 热跑) =="
$S r_f1s01.json || exit 1
echo "== ALL DONE =="
ls -la $OUT/
