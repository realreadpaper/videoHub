#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把逐句 TTS 组装成「整镜干声轨」——H3 lock_source 的输入。

为什么需要：lock_source 是把一段**与镜头等长的音频**作为驱动源，H3 按它的
时序生成口型与画面，并把这段音频原样混进成片。所以要先把零散台词摆到
prompt 时间线上（台词所在切片的时刻），其余补静音。

产物：_tts/<tag>/shotNN_dry.wav  （32kHz stereo，长度 = 镜头时长 15.083s）

用法：
  python3 assemble_dry.py                 # 两片全量（已存在的会重做）
  python3 assemble_dry.py --film film1 --shots 5
"""
import argparse, glob, json, os, subprocess


ROOT = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(ROOT, "_tts")
SR = 32000
DUR = 362 / 24.0        # 15.0833s，与 h3_length 一致


def assemble(tag, no, lines):
    d = os.path.join(TTS, tag)
    out = os.path.join(d, "shot%02d_dry.wav" % no)
    inputs = ["-f", "lavfi", "-i", "anullsrc=r=%d:cl=stereo:d=%.4f" % (SR, DUR)]
    flt, mix_in = [], ["[0:a]"]
    for i, ln in enumerate(lines):
        inputs += ["-i", os.path.join(d, ln["mp3"])]
        delay = int(round(ln["t"] * 1000))
        flt.append("[%d:a]aresample=%d,aformat=channel_layouts=stereo,"
                   "adelay=%d|%d[v%d]" % (i + 1, SR, delay, delay, i))
        mix_in.append("[v%d]" % i)
    n = len(lines) + 1
    flt.append("%samix=inputs=%d:duration=first:normalize=0[out]" % ("".join(mix_in), n))
    cmd = ["ffmpeg", "-v", "error", "-y"] + inputs + [
        "-filter_complex", ";".join(flt), "-map", "[out]",
        "-c:a", "pcm_s16le", "-ar", str(SR), "-t", "%.4f" % DUR, out]
    subprocess.run(cmd, check=True)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="both", choices=["both", "film1", "film2"])
    ap.add_argument("--shots", nargs="*", type=int)
    a = ap.parse_args()

    tags = ["film1", "film2"] if a.film == "both" else [a.film]
    made = 0
    for tag in tags:
        for jf in sorted(glob.glob(os.path.join(TTS, tag, "shot*_lines.json"))):
            no = int(os.path.basename(jf)[4:6])
            if a.shots and no not in a.shots:
                continue
            lines = json.load(open(jf, encoding="utf-8"))
            out = assemble(tag, no, lines)
            made += 1
            print("  %s 镜%-3d %d 句 -> %s" % (tag, no, len(lines), os.path.basename(out)))
    print("\n干声轨 %d 条 -> %s" % (made, TTS))


if __name__ == "__main__":
    main()
