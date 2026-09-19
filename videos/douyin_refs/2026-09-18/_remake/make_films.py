#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三片复刻骨架成片 —— 拼接 + 外挂字幕
输入：out/skel/ 下的逐镜 mp4（14.750s/354帧，768x1344），缺镜自动跳过并在清单标注
输出：成片/01_被抛弃男孩报恩_复刻骨架.mp4 + 同名 .srt（绝对时间 = Σ前序镜实际时长）
"""
import os
import subprocess
import json

HERE = os.path.dirname(os.path.abspath(__file__))
SKEL = os.path.join(HERE, "out", "skel")
OUTDIR = os.path.join(HERE, "成片")
VOICE_META = os.path.join(HERE, "voice", "_meta.json")

# 每片成片顺序：(镜 key, 台词 or None)
FILMS = {
    "01_被抛弃男孩报恩": [
        ("dy1_s01_open_kick", "爸爸不要我了，妈妈也不要我，我明天能去哪儿？"),
        ("dy1_s02_takein", "先进来，我给你擦擦，疼不疼？忍一下，马上就好。"),
        ("p3_dy1_pour3", None),
        ("dy1_s03_firstbowl", "叔，这肉真好吃。"),
        ("dy1_s04_stay", "叔，我能留在这儿给你帮工吗？洗碗、切菜、擦灶台，什么活都行。"),
        ("dy1_s05_recipe", "这包酱是咱店里的招牌，红烧肉、红烧排骨、红烧鱼，放这个就不用再加别的调料了。"),
        ("dy1_s06_farewell", "出去闯吧，酱带上，想家的时候就炖个肉，跟你叔做的一个味儿。"),
        ("dy1_s07_return", "叔，我回来看你了。"),
        ("dy1_s08_samesauce", "现在我的店，一直用的就是同一款酱。"),
        ("dy1_s09_offer", "您去了不用干活，就在后厨坐镇就行。"),
        ("dy1_s10_gate", "那您当年把我从后门口接进来，现在就换我接您走。"),
    ],
    "02_被误解的继母": [
        ("dy2_s01_open", "小优，地拖完了，把我和你爸的衬衫也洗了，领口记得用手好好搓一搓。"),
        ("dy2_s02_birthday", "爸，今天是我十八岁生日，我什么礼物都不要，就想吃一口曹阿姨做的红烧肉。"),
        ("dy2_s03_snatch", "老王，你干什么？谁允许你给他钱的？"),
        ("dy2_s04_callmom", "喂，妈妈，今天是我生日，你能带我出去吃顿曹阿姨烧的红烧肉吗？"),
        ("dy2_s05_beg", "我想跟您学这道菜，亲手给她做一份，求您成全。"),
        ("dy2_s06_truth", "哪怕她只肯吃一口，我也心满意足了。"),
        ("dy2_s07_cook", "不用加一滴油，也不用炒糖色。"),
        ("p3_dy2_hero3", None),
        ("dy2_s08_taste", "哇塞，这肉Q弹入口，肥而不腻，瘦而不柴。"),
        ("dy2_s09_price", "这料包不贵，一包才一块多钱，比买瓶酱油都便宜。"),
        ("dy2_s10_hug", "谢谢妈妈。"),
    ],
    "03_女总裁挑食女儿": [
        ("dy3_s01_open", "三个月九个厨师，我女儿瘦了四斤。"),
        ("dy3_s02_meet", "你做的饭也这么好吃吗？"),
        ("dy3_s03_interview", "他是救我的哥哥，你们不许欺负他。"),
        ("dy3_s04_fury", "你查了九个厨师的身份，我女儿瘦了四斤，还有什么要查的？"),
        ("dy3_s05_asktaste", "她平时最不想吃什么？半年了，加到碗里也不动。"),
        ("dy3_s06_mock", "就这，倒一包现成的酱，就叫做菜？"),
        ("dy3_s07_cook", "不放油，不放盐，连料酒都不搁，一包酱倒进去就等着。"),
        ("dy3_s08_eat", "嗯，好吃，好好吃。"),
        ("p3_dy3_handhero3", None),
        ("dy3_s09_buy", "九块九七包，一包才一块多钱，比买瓶酱油都便宜。"),
        ("dy3_s10_promise", "你负责吃饭，我负责做饭，拉钩，一百年不许变。"),
    ],
}


def dur(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", path], capture_output=True, text=True)
    return float(r.stdout.strip())


def ts(sec):
    ms = int(round(sec * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def find_clip(key):
    for cand in ("%s.mp4" % key, "%s_00001_.mp4", "%s_00002_.mp4", "%s_00003_.mp4"):
        p = os.path.join(SKEL, key, cand) if os.path.isdir(os.path.join(SKEL, key)) else os.path.join(SKEL, cand)
        if os.path.exists(p):
            return p
    # 兼容 dy_skel 拉回时的命名（key_00001_.mp4 -> key_v1.mp4 等）
    for f in os.listdir(SKEL):
        if f.startswith(key):
            return os.path.join(SKEL, f)
    return None


def main():
    os.makedirs(OUTDIR, exist_ok=True)
    report = {}
    for film, shots in FILMS.items():
        lines, srt, t = [], [], 0.0
        for key, line in shots:
            clip = find_clip(key)
            if not clip:
                lines.append((key, None, "MISSING"))
                continue
            d = dur(clip)
            lines.append((key, clip, "%.2fs" % d))
            if line:
                srt.append((t + 0.6, t + min(d - 0.2, 0.6 + 6.0), line))
            t += d
        # concat
        lst = os.path.join(OUTDIR, "_%s.txt" % film)
        with open(lst, "w") as f:
            for key, clip, _ in lines:
                if clip:
                    f.write("file '%s'\n" % clip)
        used = [c for _, c, _ in lines if c]
        out = os.path.join(OUTDIR, "%s_复刻骨架.mp4" % film)
        if len(used) >= 2:
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                            "-i", lst, "-c", "copy", out], check=True)
        elif len(used) == 1:
            subprocess.run(["cp", used[0], out], check=True)
        # srt
        srtp = os.path.splitext(out)[0] + ".srt"
        with open(srtp, "w", encoding="utf-8") as f:
            for i, (a, b, line) in enumerate(srt, 1):
                f.write("%d\n%s --> %s\n%s\n\n" % (i, ts(a), ts(b), line))
        os.remove(lst)
        missing = [k for k, c, _ in lines if not c]
        report[film] = {"clips": len(used), "missing": missing, "total": round(t, 2), "out": out}
        print("[film] %s: %d 镜 %.1fs 缺:%s" % (film, len(used), t, missing or "无"))
    json.dump(report, open(os.path.join(OUTDIR, "_report.json"), "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
