#!/bin/bash
set -u
URL='https://huggingface.co/WarmBloodAban/Minimax-h3_Singularity/resolve/main/Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors'
TARGET_DIR='/workspace/ComfyUI/models/diffusion_models'
TARGET_FILE='Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors'
LOG='/workspace/dl/dl_singularity.log'

mkdir -p "$TARGET_DIR"
cd "$TARGET_DIR"

echo "[$(date +%T)] Starting download $TARGET_FILE ..." | tee -a "$LOG"

aria2c -c -x 8 -s 8 -k 1M \
       --file-allocation=none \
       --summary-interval=5 \
       -o "$TARGET_FILE" \
       "$URL" >> "$LOG" 2>&1

EXIT_CODE=$?
if [ $EXIT_CODE -eq 0 ]; then
    echo "[$(date +%T)] Download complete! Size: $(du -h "$TARGET_FILE" | cut -f1)" | tee -a "$LOG"
else
    echo "[$(date +%T)] Download failed with code $EXIT_CODE" | tee -a "$LOG"
fi
exit $EXIT_CODE
