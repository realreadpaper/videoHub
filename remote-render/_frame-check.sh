#!/usr/bin/env bash
# 帧数校验：确认远端 ffmpeg 能精确产出 hypit 计划的帧数
# 背景：ffmpeg 7.0.2 在同样 filter 下只产出 2356/2826 帧，触发 hypit 断言
#       "Normalized visual frame shape differs from its plan"
cd /tmp || exit 1

FILTER='setpts=PTS-STARTPTS,fps=fps=30/1:round=near:start_time=0:eof_action=round,trim=start_frame=0:end_frame=2826,setpts=N*(1)/(30*TB),scale=trunc(iw*max(sar\,1)/2)*2:trunc(ih*max(1/sar\,1)/2)*2,setsar=1'

rm -f visual.mp4
ffmpeg -y -autorotate \
  -i /work/productions/ad-clone/assets/ad-segment.mp4 \
  -map 0:0 -an -vf "$FILTER" \
  -frames:v 2826 -fps_mode cfr \
  -c:v libx264 -preset veryfast -pix_fmt yuv420p -movflags +faststart \
  visual.mp4 > ff.log 2>&1

GOT=$(ffprobe -v error -select_streams v:0 -count_frames \
  -show_entries stream=nb_read_frames -of csv=p=0 visual.mp4)

echo "ffmpeg : $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
echo "plan   : 2826 帧"
echo "actual : ${GOT} 帧"

if [ "${GOT}" = "2826" ]; then
  echo "RESULT : PASS"
  exit 0
fi
echo "RESULT : FAIL"
exit 1
