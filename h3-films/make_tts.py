#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把分镜里的原文台词合成成可驱动口型的中文干声（100% 抄写）。

v3（2026-09-16 深夜）关键修正 —— 实测发现两个致命问题：
  1) edge-tts 的 rate 在 +50% 处封顶：+50% 与 +100%/+200% 时长完全一致，
     所以 v2 里「迭代加速到 +90%/+150%」是无效空转，白跑还听感发飘；
  2) 每句 TTS 产物的**首尾都垫着 0.4–0.9s 静音**：
     例「束一半了。」总长 1.872s，真实语音只有 0.81s，尾部 0.88s 全是静音。
     8 句一镜就白扔 5–7s —— 这才是「40 镜里 38 镜超窗」的真根因。

v3 对策：
  A) 每句合成后做**首尾静音裁剪**（silencedetect 定位语音区间 → atrim）；
  B) 裁剪后按实测时长排布，句间留白均分（0.06–0.75s）；
  C) 若裁剪后仍塞不下，用 ffmpeg **atempo** 变速兜底（不受 edge-tts 限制），
     数学上保证 end ≤ 窗长，绝不与下一镜重叠。
  语速默认 +0%（自然），听感比 v2 自然得多。

产物（每镜一份，供远端 audio-lock 工作流直接 LoadAudio）：
  _tts/<film>/sNN_<i>.mp3        逐句原始合成（留档）
  _tts/<film>/shotNN_dry.wav     15.08s 干声（32kHz 立体声）
  _tts/<film>/shotNN_lines.json  时间定位表（含实测时长）

用法（必须用装了 edge-tts 的解释器）：
  .../envs/default/bin/python make_tts.py
  .../envs/default/bin/python make_tts.py --film film1 --shots 6
"""
import argparse
import asyncio
import importlib.util
import json
import os
import re
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
TTS = os.path.join(ROOT, "_tts")
SR = 32000                 # 与远端 audio VAE / 工作流一致
DUR = 15.0833              # 362 帧 / 24fps
LEAD = 0.20                # 镜首留白
TAIL = 0.26                # 镜尾留白
MIN_GAP = 0.06             # 句间最小留白
MAX_GAP = 0.75             # 句间最大留白（再多就靠尾部静音吸收）
RATE_MAX_PCT = 50          # edge-tts 语速硬上限（实测 +50% 即封顶）
SIL_DB = -45               # 静音判定阈值（dB）
PAD_S, PAD_E = 0.03, 0.06  # 裁剪时保留的首尾呼吸

# 音色：按片定义（S1 在片1 是 65 岁董事长，在片2 是 32 岁总裁）
VOICES = {
    "film1": {
        "S1": "zh-CN-YunjianNeural",   # 顾董 · 沉稳老年男声
        "S2": "zh-CN-XiaoxiaoNeural",  # 林晚晴 · 年轻女声
        "S3": "zh-CN-YunxiNeural",     # 男面试者
        "S4": "zh-CN-XiaoyiNeural",    # 白西装女
        "S5": "zh-CN-YunyangNeural",   # 助理
    },
    "film2": {
        "S1": "zh-CN-YunxiNeural",     # 顾承舟 · 青年男声
        "S2": "zh-CN-YunxiaNeural",    # 男孩 · 童声
        "S3": "zh-CN-XiaoyiNeural",    # 相亲女
        "S4": "zh-CN-XiaoxiaoNeural",  # 阿姨 · 年轻女声
        "S5": "zh-CN-YunyangNeural",   # 助理
    },
}
DEFAULT_VOICE = "zh-CN-XiaoxiaoNeural"


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def probe(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", path], capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except Exception:
        return 0.0


async def _synth(text, voice, out, rate, tries=4):
    """合成单句。edge-tts 走 websocket，偶发 NoAudioReceived / 连接重置，
    必须重试——否则 40 镜批跑会在最后一镜崩掉整条链（实测碰到过）。"""
    import edge_tts
    last = None
    for k in range(tries):
        try:
            if os.path.exists(out):
                os.remove(out)
            await edge_tts.Communicate(text, voice, rate=rate).save(out)
            if os.path.getsize(out) > 512:      # 空壳/半截文件也算失败
                return
            raise RuntimeError("产物过小：%d 字节" % os.path.getsize(out))
        except Exception as e:                   # noqa: BLE001
            last = e
            await asyncio.sleep(1.5 * (k + 1))   # 退避 1.5 / 3 / 4.5s
    raise RuntimeError("edge-tts 连续 %d 次失败：%s" % (tries, last))


def synth_all(rows, rate, outdir, no, vmap):
    """把每句合成到 sNN_i.mp3，回写 mp3 / voice 字段"""
    async def run():
        for i, ln in enumerate(rows):
            voice = vmap.get(ln["speaker"], DEFAULT_VOICE)
            mp3 = os.path.join(outdir, "s%02d_%d.mp3" % (no, i))
            await _synth(ln["text"], voice, mp3, rate)
            ln["mp3"] = os.path.basename(mp3)
            ln["voice"] = voice
    asyncio.run(run())


def silence_span(path):
    """返回 (语音起点, 语音终点, 总长)。用 silencedetect 定位首尾静音。"""
    r = subprocess.run(["ffmpeg", "-v", "info", "-i", path, "-af",
                        "silencedetect=noise=%ddB:d=0.05" % SIL_DB, "-f", "null", "-"],
                       capture_output=True, text=True)
    log = r.stderr
    dur = probe(path)
    starts = [float(x) for x in re.findall(r"silence_start:\s*(-?[\d.]+)", log)]
    ends = [float(x) for x in re.findall(r"silence_end:\s*(-?[\d.]+)", log)]
    s, e = 0.0, dur
    # 首段静音：silence_start≈0，其配对 silence_end 即语音起点
    if starts and ends and starts[0] < 0.03 and ends[0] > starts[0]:
        s = ends[0]
    # 尾段静音：最后一个 silence_end≈文件末尾，其配对 silence_start 即语音终点
    if starts and ends and abs(ends[-1] - dur) < 0.08 and starts[-1] > s:
        e = starts[-1]
    if e <= s + 0.05:                       # 全静音/异常 → 不裁
        return 0.0, dur, dur
    return s, e, dur


def trim_clip(src, dst):
    """裁掉首尾静音，输出 SR 立体声 wav，返回时长"""
    s, e, dur = silence_span(src)
    s = max(0.0, s - PAD_S)
    e = min(dur, e + PAD_E)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-af",
           "atrim=start=%.4f:end=%.4f,asetpts=N/SR/TB,"
           "aformat=channel_layouts=stereo,aresample=%d" % (s, e, SR),
           "-c:a", "pcm_s16le", "-ar", str(SR), dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("trim 失败: " + r.stderr[-300:])
    return probe(dst)


def atempo_clip(src, dst, f):
    """atempo 变速（不改音高），f>1 加速。ffmpeg 单次 atempo 限 0.5–2.0，超限则级联。"""
    chain, g = [], float(f)
    while g > 2.0:
        chain.append("atempo=2.0"); g /= 2.0
    while g < 0.5:
        chain.append("atempo=0.5"); g /= 0.5
    chain.append("atempo=%.5f" % g)
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", src, "-af", ",".join(chain),
           "-c:a", "pcm_s16le", "-ar", str(SR), dst]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("atempo 失败: " + r.stderr[-300:])
    return probe(dst)


def assemble(rows, clipdir, out_wav):
    """把逐句 wav 按时间定位混成 15.08s 立体声干声"""
    inputs = ["-f", "lavfi", "-i", "anullsrc=r=%d:cl=stereo:d=%.4f" % (SR, DUR)]
    flt, mix = [], ["[0:a]"]
    for i, r in enumerate(rows):
        inputs += ["-i", os.path.join(clipdir, r["clip"])]
        d = int(round(r["t"] * 1000))
        flt.append("[%d:a]aresample=%d,aformat=channel_layouts=stereo,adelay=%d|%d[v%d]"
                   % (i + 1, SR, d, d, i))
        mix.append("[v%d]" % i)
    flt.append("%samix=inputs=%d:duration=first:normalize=0[out]" % ("".join(mix), len(rows) + 1))
    cmd = (["ffmpeg", "-v", "error", "-y"] + inputs +
           ["-filter_complex", ";".join(flt), "-map", "[out]",
            "-c:a", "pcm_s16le", "-ar", str(SR), "-t", "%.4f" % DUR, out_wav])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("ffmpeg 失败: " + r.stderr[-400:])


def do_shot(film, shot, rate_pct=0):
    outdir = os.path.join(TTS, film)
    os.makedirs(outdir, exist_ok=True)
    vmap = VOICES.get(film, {})
    rows = [{"speaker": sp, "text": tx} for sp, tx in shot["dialogue"]]
    n = len(rows)
    rate = "+%d%%" % min(rate_pct, RATE_MAX_PCT)

    # 1) 自然语速合成
    synth_all(rows, rate, outdir, shot["no"], vmap)

    tmp = tempfile.mkdtemp(prefix="tts_%s_%02d_" % (film, shot["no"]))
    try:
        # 2) 逐句裁首尾静音
        durs = []
        for i, r in enumerate(rows):
            clip = "f%02d.wav" % i
            durs.append(trim_clip(os.path.join(outdir, r["mp3"]), os.path.join(tmp, clip)))
            r["clip"] = clip

        # 3) 兜底变速：裁剪后仍塞不下才动 atempo（数学保证不超窗）
        span = DUR - LEAD - TAIL
        floor = span - MIN_GAP * max(n - 1, 0)
        total = sum(durs)
        tempo = 1.0
        if total > floor:
            tempo = total / max(floor, 1.0)
            for i, r in enumerate(rows):
                src = os.path.join(tmp, r["clip"])
                out = "a%02d.wav" % i
                durs[i] = atempo_clip(src, os.path.join(tmp, out), tempo)
                r["clip"] = out
            total = sum(durs)

        # 4) 排布：句间留白均分，落在 [MIN_GAP, MAX_GAP]
        if n > 1:
            gap = min(max((span - total) / (n - 1), MIN_GAP), MAX_GAP)
        else:
            gap = 0.0
        t = LEAD
        for i, r in enumerate(rows):
            r["t"] = round(t, 3)
            r["dur"] = round(durs[i], 3)
            t += durs[i] + gap
        end = max((r["t"] + r["dur"] for r in rows), default=0.0)

        assemble(rows, tmp, os.path.join(outdir, "shot%02d_dry.wav" % shot["no"]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    json.dump(rows, open(os.path.join(outdir, "shot%02d_lines.json" % shot["no"]), "w",
                         encoding="utf-8"), ensure_ascii=False, indent=1)
    return rate, end, n, tempo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--film", default="all", choices=["all", "film1", "film2"])
    ap.add_argument("--shots", nargs="*", type=int, default=None)
    ap.add_argument("--rate", type=int, default=0, help="edge-tts 语速%%（≤50 有效）")
    a = ap.parse_args()

    films = [("film1", "p1_data"), ("film2", "p2_data")]
    if a.film != "all":
        films = [f for f in films if f[0] == a.film]

    over = []; fail = []
    for tag, mod in films:
        m = load(mod)
        shots = m.SHOTS
        if a.shots:
            shots = [s for s in shots if s["no"] in a.shots]
        print("=" * 86)
        print("%s · %s  共 %d 镜" % (tag, m.FILM["film_title"], len(shots)))
        for s in shots:
            try:
                rate, end, n, tempo = do_shot(tag, s, rate_pct=a.rate)
            except Exception as e:                       # noqa: BLE001
                # 单镜失败不拖垮整批：记录后继续，跑完统一重跑这些镜
                fail.append((tag, s["no"]))
                print("  镜%-3d %-24s ✘ 合成失败：%s（稍后单独重跑）" % (s["no"], s["file"], e))
                continue
            flag = "" if end <= DUR - 0.05 else "  ⚠ 超窗"
            if flag:
                over.append((tag, s["no"], round(end, 2)))
            tp = "tempo×%.3f" % tempo if tempo > 1.0001 else "未变速"
            print("  镜%-3d %-24s %2d句 | 语速%-5s | %-11s | 语音结束 %5.2fs / 15.08s%s"
                  % (s["no"], s["file"], n, rate, tp, end, flag))
    print("\n干声轨 -> %s/<film>/shotNN_dry.wav" % TTS)
    if over:
        print("⚠ 仍超窗 %d 镜：%s" % (len(over), over))
    else:
        print("✔ 全部落在 15.0833s 窗内")
    if fail:
        print("✘ 合成失败 %d 镜（需重跑）：%s" % (len(fail), fail))


if __name__ == "__main__":
    main()
