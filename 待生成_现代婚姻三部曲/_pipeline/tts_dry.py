#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""中文台词 -> 干声 wav（24kHz mono 16bit），静音 pad 到镜长。零台词镜出纯静音。"""
import json, os, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT  = os.path.join(ROOT, "_pipeline", "tts_dry")
EDGE = "/Users/hejianglong/.workbuddy/binaries/python/envs/default/bin/edge-tts"
FF   = "ffmpeg"
DIRS = {
    "01_周星驰_三十八万八": "f1",
    "02_姜文_老子不娶了": "f2",
    "03_奉俊昊_加名之夜": "f3",
}
# 音色：按角色性别/气质分配（edge-tts 免费，无 key）
VOICE = {
    "f1": "zh-CN-XiaoxiaoNeural",   # 女儿：清亮女声
    "f2": "zh-CN-YunjianNeural",    # 姜文式：粗粝男声
    "f3": "zh-CN-YunxiNeural",      # 男主：平实男声
}
FEMALE_F3 = {2, 3, 4}              # 片3 这几镜是丈母娘/妻子台词 -> 女声

def synth(text, voice, mp3):
    subprocess.run([EDGE, "--voice", voice, "--text", text,
                    "--write-media", mp3], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def pad_to(src, dur, wav):
    if src:   # 有干声：pad 静音到镜长
        cmd = [FF, "-y", "-i", src, "-af",
               "apad=whole_dur=%.3f" % dur, "-t", "%.3f" % dur,
               "-ar", "24000", "-ac", "1", "-c:a", "pcm_s16le", wav]
    else:     # 零台词：纯静音
        cmd = [FF, "-y", "-f", "lavfi", "-i",
               "anullsrc=r=24000:cl=mono", "-t", "%.3f" % dur,
               "-c:a", "pcm_s16le", wav]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

def main():
    os.makedirs(OUT, exist_ok=True)
    n_ok = n_sil = 0
    for d, fk in DIRS.items():
        man = json.load(open(os.path.join(ROOT, d, "manifest.json"), encoding="utf-8"))
        for s in man["shots"]:
            no, dur = s["no"], s["h3_length"] / 24.0
            wav = os.path.join(OUT, "%s_s%02d_dry.wav" % (fk, no))
            txt = (s.get("dialogue_cn") or "").strip()
            voice = VOICE[fk]
            if fk == "f3" and no in FEMALE_F3:
                voice = "zh-CN-XiaoyiNeural"
            if txt:
                mp3 = wav.replace(".wav", ".mp3")
                synth(txt, voice, mp3)
                pad_to(mp3, dur, wav); os.remove(mp3); n_ok += 1
                print("  %s 镜%02d  %.3fs  %-14s %s" % (fk, no, dur, voice, txt[:26]))
            else:
                pad_to(None, dur, wav); n_sil += 1
                print("  %s 镜%02d  %.3fs  [静音·无台词]" % (fk, no, dur))
            s["audio_file"] = "tts_dry/trilogy/%s_s%02d_dry.wav" % (fk, no)
        json.dump(man, open(os.path.join(ROOT, d, "manifest.json"), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
    print("\n干声 %d 条 + 静音 %d 条 -> %s" % (n_ok, n_sil, OUT))

main()
