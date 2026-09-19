#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
骨架镜台词 TTS 管线（阿里云百炼 sambert）
台词全部取自原片拆解产物（transcript / shots_dialogue.md / segments.md），只修 ASR 错字与数字读法，不改写剧情。
输出：voice/<key>.wav  16 kHz mono，静音补齐到 14.750 s（= 镜头时长），供 H3 原声锁驱动口型。
"""
import os
import json
import subprocess
import wave

import dashscope
from dashscope.audio.tts import SpeechSynthesizer

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "voice")
TARGET = 14.750

# 音色分配：不同角色尽量不同 voice（百炼 sambert 系列）
V_MALE_YOUNG = "sambert-zhichu-v1"      # 小周 / 小伙子（青年男）
V_MALE_OLD = "sambert-zhichu-v1"        # 老赵 / 老王（中老年男）
V_FEMALE = "sambert-zhichu-v1"          # 莫姨 / 小优 / 女总裁 / 楠奶

# (key, 台词, 音色, 语速)  —— 台词一律来自原片拆解
LINES = [
    # ---------------- 片1 被抛弃男孩报恩 ----------------
    ("dy1_s01_open_kick", "爸爸不要我了，妈妈也不要我，我明天能去哪儿？", "young", 1.0),
    ("dy1_s02_takein", "先进来，我给你擦擦，疼不疼？忍一下，马上就好。", "old", 0.95),
    ("dy1_s03_firstbowl", "叔，这肉真好吃。", "young", 0.95),
    ("dy1_s04_stay", "叔，我能留在这儿给你帮工吗？洗碗、切菜、擦灶台，什么活都行。", "young", 1.05),
    ("dy1_s05_recipe", "这包酱是咱店里的招牌，红烧肉、红烧排骨、红烧鱼，放这个就不用再加别的调料了。", "old", 1.0),
    ("dy1_s06_farewell", "出去闯吧，酱带上，想家的时候就炖个肉，跟你叔做的一个味儿。", "old", 0.95),
    ("dy1_s07_return", "叔，我回来看你了。", "young", 0.95),
    ("dy1_s08_samesauce", "现在我的店，一直用的就是同一款酱。", "young", 1.0),
    ("dy1_s09_offer", "您去了不用干活，就在后厨坐镇就行。", "young", 1.0),
    ("dy1_s10_gate", "那您当年把我从后门口接进来，现在就换我接您走。", "young", 0.95),
    # ---------------- 片2 被误解的继母 ----------------
    ("dy2_s01_open", "小优，地拖完了，把我和你爸的衬衫也洗了，领口记得用手好好搓一搓。", "female", 1.05),
    ("dy2_s02_birthday", "爸，今天是我十八岁生日，我什么礼物都不要，就想吃小时候咱们总去的老巷子饭店，吃一口曹阿姨做的红烧肉。", "female", 1.05),
    ("dy2_s03_snatch", "老王，你干什么？谁允许你给他钱的？", "female", 1.1),
    ("dy2_s04_callmom", "喂，妈妈，今天是我生日，你能带我出去吃顿曹阿姨烧的红烧肉吗？", "female", 1.0),
    ("dy2_s05_beg", "曹阿姨，今天孩子十八岁，她就想吃您做的红烧肉，我想跟您学这道菜，亲手给她做一份，求您成全。", "female", 1.05),
    ("dy2_s06_truth", "今天她成年了，我就想亲手做一顿她记忆里的味道，哪怕她只肯吃一口，我也心满意足了。", "female", 0.95),
    ("dy2_s07_cook", "你看这肉一定要选五花三层的，冷水下锅加料酒焯透，不用加一滴油，也不用炒糖色。", "female", 1.05),
    ("dy2_s08_taste", "哇塞，这肉Q弹入口，肥而不腻，瘦而不柴。", "old", 1.1),
    ("dy2_s09_price", "这料包不贵，一包才一块多钱，比买瓶酱油都便宜。", "female", 1.05),
    ("dy2_s10_hug", "谢谢妈妈。", "female", 0.9),
    # ---------------- 片3 女总裁挑食女儿 ----------------
    ("dy3_s01_open", "三个月九个厨师，我女儿瘦了四斤。", "female", 1.1),
    ("dy3_s02_meet", "你做的饭也这么好吃吗？", "female", 1.05),
    ("dy3_s03_interview", "他是救我的哥哥，你们不许欺负他。", "female", 1.15),
    ("dy3_s04_fury", "你查了九个厨师的身份，我女儿瘦了四斤，还有什么要查的？", "female", 1.15),
    ("dy3_s05_asktaste", "她平时最不想吃什么？半年了，加到碗里也不动。", "female", 1.05),
    ("dy3_s06_mock", "就这，倒一包现成的酱，就叫做菜？", "old", 1.1),
    ("dy3_s07_cook", "不放油，不放盐，连料酒都不搁，一包酱倒进去就等着。", "young", 1.05),
    ("dy3_s08_eat", "嗯，好吃，好好吃。", "female", 1.0),
    ("dy3_s09_buy", "九块九七包，一包才一块多钱，比去菜市场买瓶酱油都便宜。", "young", 1.1),
    ("dy3_s10_promise", "你负责吃饭，我负责做饭，拉钩，一百年不许变。", "female", 1.0),
]

VOICE_MAP = {"young": V_MALE_YOUNG, "old": V_MALE_OLD, "female": V_FEMALE}


def synth(text, model):
    r = SpeechSynthesizer.call(model=model, text=text, sample_rate=16000, format="wav")
    data = r.get_audio_data()
    if not data:
        raise RuntimeError("empty audio: %s" % r)
    return data


def duration(path):
    with wave.open(path) as w:
        return w.getnframes() / float(w.getframerate())


def main():
    os.makedirs(OUT, exist_ok=True)
    key = open(os.path.expanduser("~/.workbuddy/secrets/dashscope.key")).read().strip()
    dashscope.api_key = key
    meta = {}
    for k, text, vk, rate in LINES:
        dst = os.path.join(OUT, k + ".wav")
        raw = os.path.join(OUT, "_raw_" + k + ".wav")
        if os.path.exists(dst):
            print("[skip]", k)
            meta[k] = {"text": text, "dur": round(duration(dst), 2)}
            continue
        data = synth(text, VOICE_MAP[vk])
        open(raw, "wb").write(data)
        d = duration(raw)
        # 语速（atempo 保持音高）
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw,
                        "-filter:a", "atempo=%.3f" % rate, "-ar", "16000", "-ac", "1", raw + ".r.wav"],
                       check=True)
        d2 = duration(raw + ".r.wav")
        pad = max(0.0, TARGET - d2)
        # 干声前置（前 0.6s 留环境噪底），其余静音补齐到镜头时长
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw + ".r.wav",
                        "-filter:a", "adelay=600|600,apad", "-t", "%.3f" % TARGET,
                        "-ar", "16000", "-ac", "1", dst], check=True)
        os.remove(raw + ".r.wav")
        os.remove(raw)
        meta[k] = {"text": text, "voice": VOICE_MAP[vk], "raw_dur": round(d2, 2), "pad": round(pad, 2)}
        print("[tts] %-22s %5.2fs -> %s" % (k, d2, dst))
    json.dump(meta, open(os.path.join(OUT, "_meta.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[done] %d wav -> %s" % (len(LINES), OUT))


if __name__ == "__main__":
    main()
