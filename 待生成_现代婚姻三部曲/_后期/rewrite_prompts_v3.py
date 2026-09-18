#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rewrite_prompts_v3.py —— 把三段式「到点切镜头」prompt 改写成「单镜连续运镜」prompt

背景（实测证据）
----------------
01《三十八万八》用 v2 信封式 prompt（三段 `[00:00–05] [05–10] [10–15]`，每段以
`At 00:05.000,` 开头引入新视角/新主体）生成的成片，镜内硬切实测：

    镜01: 2 处 (8.79s MAE=54.2, 12.12s MAE=72.2)
    镜02: 1 处 (12.12s MAE=56.2)
    镜03: 2 处 (9.29s MAE=62.4, 12.29s MAE=34.3)

对照旧版单段连续 prompt 的 shot01：零尖峰、最大帧差仅 9.20、运动平滑递减。
⇒ 硬切是 prompt 写法造成的，不是模型能力上限。

改写原则（最小改动，内容一律不动）
----------------------------------
1. 开头加「单一不中断长镜头」锁定语，并显式禁止 cut / shot change / montage
2. 删掉每段的 `At 00:XX.XXX,` 时间戳前缀（它等价于告诉模型「这里换拍」）
3. 段落衔接改为「同一镜头延续」的运镜描述，而不是引入新视角
4. 视角突变（如 手→脸→手）改写成镜头内的一次性运动（tilt / pan）自然揭示
5. 主体在首段就「已在画面内」交代清楚，避免中途凭空出现
6. 删除一切「要求画面显示可读文字」的诉求（模型渲染汉字/英文必乱码）
7. 保留 <Subject N> 主体标记、<d>[Chinese] "…"</d> 对白标签、时间轴三段结构、
   overall_soundscape / non_diegetic_music 块 —— 一字不动

用法
----
  python3 rewrite_prompts_v3.py                      # 生成 manifest_v3.json
  python3 rewrite_prompts_v3.py --src manifest.json --out manifest_v3.json
  python3 rewrite_prompts_v3.py --diff               # 只打印逐镜改写摘要
"""

import argparse
import json
import os
import re
import sys

# =====================================================================
# 锁定语：放在 integrated_multimodal_description 正文最前
# =====================================================================
LOCK = ("A single continuous unbroken 15-second take — one sustained camera move, "
        "no cuts, no shot changes, no montage, no scene transitions. Every event below "
        "happens inside this one uninterrupted shot, revealed only through camera motion "
        "and the subjects' own movement.")

TAIL = ("cinematic 16:9 widescreen, ARRI Alexa look, shallow depth of field, fine film grain, "
        "naturalistic lighting, photorealistic, no subtitles, no captions, no on-screen text, "
        "no watermark, no logo.")

# =====================================================================
# 8 镜修正版 integrated_multimodal_description 正文（不含 LOCK 与 TAIL）
# =====================================================================
BODY = {}

# ---------------------------------------------------------------- 镜01
BODY[1] = """[00:00.000 – 00:05.000] Medium close-up. The camera retreats slowly and steadily, moving backward ahead of the climbing subject up a narrow cramped peeling concrete stairwell of a 1990s urban village tenement building, keeping <Subject 1> (S1) centred in frame the whole time. <Subject 1> (S1), a 30-year-old lean East Asian groom named A-XING, slightly messy black parted hair, sweating forehead, tired eyes with stubborn pride, wearing a cheap ill-fitting rented black polyester wedding suit, a crooked bright red polyester necktie, and a gaudy plastic red rose pinned to his lapel, climbs toward the camera clutching a bouquet of slightly wilted red roses, sweat dripping down his temple, smiling with forced nervous optimism. Already inside the same frame two steps behind and below him walks <Subject 2> (S2), a 65-year-old frail stooped East Asian elderly father in a faded navy blue zip-up windbreaker over a worn knitted sweater, a red velvet pouch held against his chest with trembling fingers.
[00:05.000 – 00:10.000] The camera keeps retreating at the same slow steady pace, never breaking the move. <Subject 1> (S1) slows on a concrete step, turns his head back over his shoulder toward his father, and says with a reassuring strained grin: <d>[Chinese] "爸，等会儿进去你别紧张，一切有我。"</d>
[00:10.000 – 00:15.000] Still inside the very same continuous shot, the camera eases to a stop and drifts gently sideways and down, settling on <Subject 2> (S2) as he nods hesitantly and clutches the red velvet pouch tighter, his son watching him from the edge of frame. Dusty midday sunbeams slice through the barred window."""

# ---------------------------------------------------------------- 镜02
BODY[2] = """[00:00.000 – 00:05.000] Close-up on a heavy rust-spotted security steel door decorated with a faded red Double Happiness paper-cut, held in one steady framing throughout. <Subject 1> (S1), in his rented black suit with crooked red tie and plastic red rose on the lapel, stands squarely inside the frame, knocking enthusiastically on the metal door with a red envelope in his other hand, grinning with anticipation.
[00:05.000 – 00:10.000] The camera holds, then inches in as <Subject 1> (S1) knocks again with eager knuckles and shouts loudly: <d>[Chinese] "大喜的日子，开开门啦，大舅哥！"</d> The metal peephole clicks open, and a folded slip of paper is pushed out through the door crack, fluttering slightly in the draught.
[00:10.000 – 00:15.000] Without any break in the shot, the camera continues its slow push-in and drifts down to settle on the slip of paper held between the door and its frame, its surface covered edge to edge in hasty black marker strokes, the paper trembling as unseen fingers release it. <Subject 1> (S1)'s beaming wedding smile freezes into a stiff, bewildered grimace, sweat trickling down his jawline, his hand slowly lowering the red envelope as he stares at the slip."""

# ---------------------------------------------------------------- 镜03
BODY[3] = """[00:00.000 – 00:05.000] Medium shot inside a stuffy bridal bedroom decorated with gaudy pink balloons. The camera pans right in one smooth uninterrupted arc across the room, starting on the red satin bedspread where <Subject 4> (S4), a 28-year-old East Asian bride with heavy wedding makeup and a tiered white lace veil, sits completely passive and numb, her manicured thumb robotically swiping a glowing smartphone screen under her veil. The pan continues left to right and comes to rest on <Subject 3> (S3), a 55-year-old sharp-eyed East Asian mother-in-law in an opulent gaudy crimson and gold embroidered qipao dress, who is already standing in the room with arms crossed, glaring toward the bedroom door.
[00:05.000 – 00:10.000] The camera stops on <Subject 3> (S3) and holds her in frame as she uncrosses her arms and jabs a sharp index finger toward the bedroom door, saying in an aggressive, domineering voice: <d>[Chinese] "不拿出这三十八万八，我家静静绝不下轿！"</d>
[00:10.000 – 00:15.000] The same single shot continues, the camera settling a little lower and holding both women in the same framing — <Subject 3> (S3)'s oppressive glare filling the foreground while, deeper in the frame and still softly out of focus, <Subject 4> (S4) remains utterly unresponsive, chewing gum without looking up. A ceiling fan rotates slowly overhead throughout."""

# ---------------------------------------------------------------- 镜04
BODY[4] = """[00:00.000 – 00:05.000] Top-down macro close-up, the camera drifting in a slow continuous push. The calloused, trembling hands of <Subject 2> (S2) carefully unzip an inner chest pocket of a worn navy blue windbreaker and unfold a faded cotton handkerchief stained with old tea. Already visible at the top edge of the same frame is the lower half of <Subject 2> (S2)'s face and his collarbone, so that the whole action stays inside one framing.
[00:05.000 – 00:10.000] Without cutting, the camera tilts smoothly upward off the hands and travels up to <Subject 2> (S2)'s weathered, tear-rimmed eyes, holding him as his chin quivers with deep humility and he stammers in a pleading voice: <d>[Chinese] "亲家母，我这还有张两万的存折……你看行不行？"</d>
[00:10.000 – 00:15.000] The same unbroken shot continues as the camera tilts gently back down the way it came, returning to the trembling hands as they present three dog-eared bank passbooks, their paper edges frayed from decades of labor, while <Subject 2> (S2)'s bowed grey head stays visible at the top of the frame. Harsh fluorescent light glints on his white temple hair."""

# ---------------------------------------------------------------- 镜05
BODY[5] = """[00:00.000 – 00:04.500] Tight close-up, one continuous hand-held shot with a subtle shake, locked on <Subject 1> (S1)'s face. He stares down at something just below the lens, his clenched jaw twitching violently, veins bulging on his neck, tears welling in his red eyes as deep grief shifts into Stephen Chow-style absurd manic realization.
[00:04.500 – 00:10.000] The same shot continues without a break as the camera pushes in a little closer on his face. <Subject 1> (S1) bursts into three exaggerated, bitter laughs, tears spilling onto his smiling cheeks, then his shoulders drop and he roars with defiant fury: <d>[Chinese] "哈！哈哈哈！这婚，谁爱结谁结！"</d>
[00:10.000 – 00:15.000] Still inside the very same take, the camera widens its framing slightly and drifts down from his face to his chest as <Subject 1> (S1) reaches up with both hands, tears the plastic red rose off his suit lapel and hurls it down onto the linoleum floor, then turns his body resolutely toward the door, his face staying inside the frame the entire time."""

# ---------------------------------------------------------------- 镜06
BODY[6] = """[00:00.000 – 00:05.000] Wide dynamic tracking shot, the camera flying backward ahead of the running subjects down a narrow tenement alley. <Subject 1> (S1), jacket unbuttoned and tie loosened, firmly grasps the arm of <Subject 2> (S2) and pulls him along, the two of them brushing past stunned bridesmaids and relatives who stand frozen like statues on either side.
[00:05.000 – 00:10.000] The camera keeps retreating at running pace, never cutting, as <Subject 1> (S1) reaches the door of a dusty vintage white 2005 sedan parked at the mouth of the alley, wrenches it open, bundles <Subject 2> (S2) into the passenger seat, straightens up and yells at the sky with exhilaration: <d>[Chinese] "走！爸，我带你去看真正的海！"</d>
[00:10.000 – 00:15.000] In the same uninterrupted move the camera swings in a single smooth arc around the front of the car as <Subject 1> (S1) dives into the driver's seat and slams the door, the engine catching, the white sedan lurching forward, its tires spinning over red firecracker paper as it swings round and accelerates away down the alley, the camera holding on the departing car."""

# ---------------------------------------------------------------- 镜07
BODY[7] = """[00:00.000 – 00:05.000] Medium shot inside the cabin of a moving white sedan, the camera mounted low on the dashboard with subtle road vibration, framing both front seats. Golden afternoon sunlight floods through fully rolled-down windows, a ferocious headwind whipping <Subject 1> (S1)'s black hair and tossing his red necktie over his shoulder, while <Subject 2> (S2) sits beside him in the passenger seat, quietly watching the road ahead.
[00:05.000 – 00:10.000] The camera holds the same two-shot without cutting as <Subject 1> (S1) grips the worn steering wheel with one hand, throws his head back laughing with untamed liberation, and hollers into the wind: <d>[Chinese] "爸，三十八万八省下来，够咱们加满一千箱油！"</d>
[00:10.000 – 00:15.000] Still one unbroken shot, the camera pans gently across the dashboard from the driver to the passenger side and settles on <Subject 2> (S2), whose wrinkled face slowly softens from bewilderment into a relieved, peaceful smile while an old cassette tape spins in the dashboard deck between them."""

# ---------------------------------------------------------------- 镜08
BODY[8] = """[00:00.000 – 00:05.000] Medium long shot on an elevated plateau roadside overlook at sunset, the camera fully static at first. A majestic snow-capped mountain range is bathed in blazing orange-magenta twilight glow. A dusty white sedan is parked on gravel in the frame; <Subject 1> (S1) and <Subject 2> (S2) lean shoulder-to-shoulder against its warm hood, both already in frame together.
[00:05.000 – 00:10.000] Without any cut, the camera begins an extremely slow push in as <Subject 2> (S2) uses calloused thumbs to peel a bright juicy orange, offering a fresh crescent slice up toward his son's lips and murmuring tenderly: <d>[Chinese] "甜不甜？"</d>
[00:10.000 – 00:15.000] The same single shot continues, the camera slowly pulling back out to widen the framing as <Subject 1> (S1) bites into the orange slice and a silent tear rolls down his grinning cheek while he whispers softly: <d>[Chinese] "甜透了，爸。"</d> The camera keeps drawing back until the two figures become a small warm silhouette against the deep glowing dusk, holding there without any transition to black."""

SOUND_PREFIX = "overall_soundscape:"
MUSIC_PREFIX = "non_diegetic_music:"


def split_prompt(p):
    """拆出 (区块头, 正文, soundscape块, music块)。区块头指 `integrated_multimodal_description:`。"""
    i = p.index(SOUND_PREFIX)
    j = p.index(MUSIC_PREFIX)
    head_part = p[:i]
    sound = p[i:j].rstrip()
    music = p[j:].rstrip()
    # head_part 形如 "integrated_multimodal_description:\n<正文>\n\n"
    m = re.match(r"\s*([a-z_]+:)\s*\n", head_part)
    header = m.group(1) if m else "integrated_multimodal_description:"
    return header, sound, music


def build(orig_prompt, no):
    header, sound, music = split_prompt(orig_prompt)
    body = BODY[no].strip()
    return "%s\n%s\n\n%s\n\n%s" % (header, LOCK, body, sound + "\n\n" + music)


def check(old, new, no):
    """断言：主体标记 / 对白标签 / 时间轴段数 / 环境音 / 配乐 均未变。"""
    problems = []
    # 主体标记：只校验「编号集合」不变（首次出现的人数），允许正文多提几次
    # —— v3 有意在首段就交代人物已入画，避免中途凭空出现造成硬切
    soc = set(re.findall(r"<Subject\s*(\d)>", old))
    snc = set(re.findall(r"<Subject\s*(\d)>", new))
    if soc != snc:
        problems.append("主体标记集合不一致\n     旧 %s\n     新 %s" % (sorted(soc), sorted(snc)))
    for tag, pat in [("对白标签", r"<d>.*?</d>"),
                     ("时间轴段", r"\[(\d\d:\d\d\.\d+)\s*[–-]\s*(\d\d:\d\d\.\d+)\]")]:
        a = sorted(re.findall(pat, old, re.S))
        b = sorted(re.findall(pat, new, re.S))
        if a != b:
            problems.append("%s 不一致\n     旧 %s\n     新 %s" % (tag, a, b))
    for name, prefix in [("环境音", SOUND_PREFIX), ("配乐", MUSIC_PREFIX)]:
        a = old[old.index(prefix):].strip()
        b = new[new.index(prefix):].strip()
        if a != b:
            problems.append("%s 块被改动" % name)
    # 残留的到点切换词
    for kw in ["At 00:", "suddenly", "instantly", "abrupt", "cut to", "cuts to"]:
        if kw.lower() in new.lower():
            problems.append("新 prompt 仍含切换词「%s」" % kw)
    # 残留的画面文字诉求
    for kw in ["reading \"", "characters reading", "written on", "displaying bold"]:
        if kw.lower() in new.lower():
            problems.append("新 prompt 仍含画面文字诉求「%s」" % kw)
    return problems


def main():
    ap = argparse.ArgumentParser(description="v2 三段式 prompt → v3 单镜连续运镜 prompt")
    here = os.path.dirname(os.path.abspath(__file__))
    default_src = os.path.join(os.path.dirname(here), "01_周星驰_三十八万八", "manifest.json")
    ap.add_argument("--src", default=default_src)
    ap.add_argument("--out", default=None, help="默认写到 manifest_v3.json")
    ap.add_argument("--diff", action="store_true", help="只打印摘要，不写文件")
    a = ap.parse_args()

    if not os.path.exists(a.src):
        print("✘ 找不到 %s" % a.src); return 1
    m = json.load(open(a.src, encoding="utf-8"))
    out_path = a.out or os.path.join(os.path.dirname(a.src), "manifest_v3.json")

    print("=" * 92)
    print("v3 单镜连续运镜 prompt 改写 · %s" % os.path.basename(a.src))
    print("=" * 92)

    all_problems = []
    for s in m["shots"]:
        no = s["no"]
        if no not in BODY:
            print("  ⚠ 镜%02d 无改写模板，跳过" % no); continue
        old = s["prompt"]
        new = build(old, no)
        probs = check(old, new, no)
        flag = "✔" if not probs else "✘"
        print("  %s 镜%02d | %4d → %4d 字符 | 时间轴 %d 段 | 主体 %s" % (
            flag, no, len(old), len(new),
            len(re.findall(r"\[\d\d:\d\d\.\d+", new)),
            sorted(set(re.findall(r"<Subject\s*(\d)>", new)))))
        for p in probs:
            print("        ✘ %s" % p)
        all_problems += probs
        s["prompt"] = new

    print("-" * 92)
    if all_problems:
        print("✘ 共 %d 项自检未通过，不写文件" % len(all_problems))
        return 1
    print("✔ 全部 %d 镜自检通过" % len(BODY))
    if a.diff:
        print("  (--diff 模式，未写文件)")
        return 0
    json.dump(m, open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print("✔ 已写出 %s" % out_path)
    print()
    print("上机用法（远端工程目录内）：")
    print("  cp manifest.json manifest_v2_backup.json")
    print("  cp manifest_v3.json manifest.json")
    print("  # 清掉 v2 的草稿与成片，避免读到旧产物")
    print("  /workspace/venv/bin/python 10_run_film.py --shots 1-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
