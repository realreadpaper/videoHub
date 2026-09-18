# -*- coding: utf-8 -*-
"""片 2 分镜数据 · 相亲这场 × 一包搞定 —— 按参考视频 100% 抄写重建

抄写口径（对齐 _lines/film2_shot_lines.txt）：
  · 台词 = 原片 whisper 逐词转写原文，逐字照抄，不增删不改写
  · 画面 = 按原片接触表逐拍重建（秋日街道 / 小餐厅 / 家用后厨 / 轮椅上的男孩）
  · 时间窗 = 原片 296.93s 均分 20 镜，每镜 14.85s（生成侧固定 15s）
  · 语音 = Edge TTS 逐字合成原文（中文），走 audio-lock 工作流驱动口型

角色锚定（写进每镜 prompt，H3 只看单镜）：
  S1 顾承舟  爸爸，宏盛集团总裁，装普通人相亲
  S2 男孩     6 岁儿子，坐轮椅
  S3 相亲女   势利，见轮椅男孩后变脸
  S4 阿姨     小餐厅老板娘，女主（22 岁）
  S5 助理     董事会来人
  SP 产品     醉锅里·鲍汁红烧酱
"""

import re

S1 = ("<Subject 1> (S1), a 32-year-old handsome East Asian man with short neat black hair, a "
      "clean-shaven face and steady, quietly worried eyes, wearing an olive-green casual jacket "
      "over a dark knit sweater and dark trousers; he stands behind a small black wheelchair")
S2 = ("<Subject 2> (S2), a cute 6-year-old East Asian boy with soft black hair and round clear "
      "eyes, wearing a cream knitted cardigan over a navy-and-white striped shirt and dark "
      "trousers, sitting in a small black wheelchair with his hands folded in his lap")
S2_STAND = ("<Subject 2> (S2), the identical cute 6-year-old East Asian boy, same soft black hair, "
            "same round clear eyes, same cream knitted cardigan over a navy-and-white striped "
            "shirt; now standing upright on his own two legs, healthy and steady")
S3 = ("<Subject 3> (S3), a 30-year-old East Asian woman with long wavy dark hair, full makeup and "
      "a sharp appraising expression, wearing an off-white tailored blazer with matching trousers, "
      "a designer handbag on her arm")
S4 = ("<Subject 4> (S4), a strikingly beautiful 22-year-old East Asian young woman with a fresh "
      "dewy youthful face, large bright almond eyes, a small straight nose, softly defined "
      "cheekbones, full natural pink lips and smooth flawless unlined porcelain skin, a tiny soft "
      "beauty mark just below her left eye, long glossy jet-black hair in a loose high bun, slim "
      "petite figure; wearing a soft sage-green knit sweater and a beige canvas apron over dark "
      "trousers, warm and completely at ease")
S5 = ("<Subject 5> (S5), a 35-year-old East Asian man in a dark navy suit with a folder in his "
      "hand and an apologetic, deferential manner")
SP = ("<Subject P> (SP), a glossy laminated stand-up sauce pouch of tall rounded doypack silhouette, "
      "vivid tomato-red metallised front panel with crisp white specular highlights along its folds "
      "and a faint crinkle across the surface, a narrow ivory header band across the very top "
      "carrying a round punched hang-hole, and a plain unadorned red label field filling the middle "
      "two thirds of the front panel - completely empty, smooth, blank and unprinted; only the bottom "
      "third carries a printed serving photograph of glossy braised pork ribs in deep red sauce on a "
      "pale dish; the pouch surface bears no lettering, no numbers, no symbols, no logo and no barcode")

# ── 禁字铁律（NO_TEXT_CLAUSE）────────────────────────────────────────────
# 背景：H3 是**临摹型**生成器。训练数据里大量带烧死字幕的短视频，它会把「字幕条 +
# 乱码字」当成画面元素画出来 —— 纯负向提示压不住（原 prompt 已写 no subtitles 仍长出字）。
# 所以本条款是「声明」不是「保证」；真正兜底的是两道机器门：
#   ① build.py 终检：任何一镜 prompt 缺本条款 → 拒绝生成（铁律，缺则报错退出）
#   ② check_no_text.py：stage1 草稿 / stage2 精修各自抽帧 OCR 验字，FAIL 不许交付
# 三处口径必须一致：本条款 ↔ check_no_text.py 判据 ↔ STORYBOARD 验收清单。
NO_TEXT_CLAUSE = (
    " no subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar "
    "across the frame, no karaoke-style highlighted characters, no on-screen text, no watermark, "
    "no logo, no timestamp, no UI overlay; never imitate or reproduce a subtitle strip or any "
    "text overlay from the source material; do not draw letterforms of any script — Chinese, "
    "Latin, digits or symbols — anywhere in the frame, especially in the lower half and along "
    "the bottom edge; any paper, document, folder, sign, screen, package or printed surface in "
    "frame is blank or shows only soft unreadable blurred marks, never legible lettering, "
    "characters, numbers or logos")
STYLE = ("cinematic 9:16 vertical, ARRI Alexa look, shallow depth of field, fine film grain, "
         "naturalistic daylight, photorealistic live-action footage," + NO_TEXT_CLAUSE)

FILM = {
    "film_title": "相亲这场 · 一包搞定（原片复刻）",
    "director_style": "都市家庭短剧质感 × 电商口播素材，秋日街景 + 暖调小餐厅后厨对照",
    "theme": "单亲爸爸推着轮椅上的儿子去相亲，相亲女见轮椅就变脸要车要房；转角小餐厅的老板娘把孩子当客人疼，"
             "顺手用一包红烧酱 + 电饭锅做出一锅硬菜；反转揭示父亲身份与孩子的腿，收尾落在「孩子最能试出善良」",
    "fps": 24,
    "target_fps": 30,
    "shot_duration_sec": 15,
    "h3_length": 362,
    "refined_frames": 361,
    "aspect_ratio": "9:16",
    "resolution_stage1": "384x672",
    "resolution_stage2": "768x1344",
    "seed": 20260919,
    "prompt_schema": "github_minimax_h3_multimodal_envelope_v2",
}

SCENE_STREET = ("a tidy modern residential street in autumn with pale stone paving, low green "
                "hedges and ginkgo trees turning yellow in soft afternoon light")
SCENE_RESTAURANT = ("a small warm neighbourhood restaurant with pale wood tables, rattan chairs, "
                    "potted plants and paper lanterns, warm afternoon light through the window")
SCENE_KITCHEN = ("a small domestic-style restaurant kitchen with white tiled walls, a pale wood "
                 "counter, a stainless gas range, a range hood and a rice cooker on the counter")

_TAIL = "\n\noverall_soundscape:\n%s\n\nnon_diegetic_music:\n%s"

# 中文场景标签 → 英文场景常量（H3 只吃英文）。让每镜 prompt 自带场景锚定，
# 避免模型凭 beats 里的零碎词猜环境。
SCENE_EN = {
    "小区门口 · 秋日白天": SCENE_STREET,
    "小餐厅门口 · 秋日白天": SCENE_RESTAURANT,
    "小餐厅后厨 · 白天": SCENE_KITCHEN,
    "小餐厅 · 傍晚": SCENE_RESTAURANT,
}
_SCENE_BLOCK = "<Scene reference — this entire shot takes place in: %s>\n\n"


# 角色锚定：H3 是「单镜生成」，每镜 prompt 必须自带出场角色的完整外貌描述。
# 否则模型只看到裸标签「S1/S2」，跨镜人脸必然漂移 —— 这就是「角色没保持一致」的根因。
_CAST_ORDER = ("SP", "S2_STAND", "S2K", "S1", "S2", "S3", "S4", "S5")
_CAST_BLOCK = ("<Character reference — every subject below keeps exactly the same face, hair, "
               "age, build and clothing in every shot of this film: %s>\n\n")


def _cast_for(text):
    out = []
    for k in _CAST_ORDER:
        if k in globals() and k not in out and \
                re.search(r"(?<![A-Za-z0-9_])%s(?![A-Za-z0-9_])" % k, text):
            out.append(k)
    # 画面里出现酱料软袋时锚定产品外观，保证跨镜产品一致
    if "SP" not in out and re.search(r"\b(pouch|packet|sachet)\b", text, re.I):
        out.append("SP")
    return out


SHOT_SEC = 15.0     # 一次生成的时长。H3 length=362 帧 @24fps = 15.0833s；
                    # prompt 时间戳按官方写法记 15.000。


def _fmt_ts(t):
    m = int(t // 60)
    return "%02d:%06.3f" % (m, t - m * 60)


def _spans(n, total=SHOT_SEC):
    """把「一次生成的 15 秒」均分成 n 段，返回 [(起秒, 止秒), ...]。

    ⚠ 澄清一个常见误解：H3 是**一次生成 15 秒**（362 帧一个 batch，见
    build_voice_workflow.py 的 FRAMES=362），prompt 里的 `[00:00.000 – 00:05.000]`
    是**描述分段**而非生成分段 —— 它只是告诉模型「这 15 秒里先后发生什么」。
    所以段数**不必等于 3**，段边界应当贴合台词/动作转折，而不是死板地切 3×5s。
    固定 5s 段正是「表情没配合上」的机制之一：情绪转折点落在段中间，prompt 没覆盖，
    模型就用一个中性表情走完 5 秒。要按台词重排段边界，用 rebuild_beats.py
    （它读干声实测的逐句时间，段数自适应）。
    """
    step = float(total) / n
    return [(i * step, min((i + 1) * step, total)) for i in range(n)]


def _prompt(beats, sound, music, cast=None, speakers=(), scene=None, spans=None):
    # 时间轴分段：默认按 beats 条数均分 15s；可传 spans（数字秒对）覆盖。
    if spans is None:
        spans = _spans(len(beats))
    ts = ["%s – %s" % (_fmt_ts(a), _fmt_ts(b)) for a, b in spans]
    if len(ts) != len(beats):
        raise ValueError("时间分段数 %d 与动作段数 %d 不一致"
                         "（旧版 zip() 会静默丢弃多余的 beats，已改为显式报错）"
                         % (len(ts), len(beats)))
    body = "\n".join("[%s] %s" % (t, b) for t, b in zip(ts, beats))
    keys = list(cast) if cast else _cast_for(" ".join(beats) + " " + sound)
    # 台词说话人必须锚定 —— 有台词就一定有他/她在画面里（哪怕 beats 只写了 he/she）
    for sp in speakers:
        if sp in globals() and sp not in keys:
            keys.append(sp)
    keys = [k for k in _CAST_ORDER if k in keys]
    pre = (_CAST_BLOCK % "; ".join(globals()[k] for k in keys)) if keys else ""
    sc = SCENE_EN.get(scene or "")
    if sc:
        pre += _SCENE_BLOCK % sc
    return "integrated_multimodal_description:\n" + pre + body + (_TAIL % (sound, music))


def _shot(no, file, framing, character, scene, dialogue, beats, sound, music, cast=None):
    return {
        "no": no, "file": file, "framing": framing, "character": character, "scene": scene,
        "dialogue": dialogue,
        "dialogue_cn": "／".join("%s：%s" % (sp, tx) for sp, tx in dialogue),
        "beats": beats, "sound": sound, "music": music,
        "prompt": _prompt(beats, sound, music, cast, [sp for sp, _ in dialogue], scene),
    }


SHOTS = [
    _shot(1, "shot01_wheelchair_talk", "中景 (MS)", "S1 + S2", "小区门口 · 秋日白天",
      [("S2", "爸爸，我又没瘸，为什么非要坐轮椅骗人？"),
       ("S1", "爸爸不是想骗人，爸爸只是想知道，谁会因为你坐轮椅就嫌弃你，谁又会把你当成真正的孩子疼。"),
       ("S2", "那他们要是都嫌弃我呢？"),
       ("S1", "那爸爸一个都不要。"),
       ("S2", "可你不是")],
      ["Medium shot in %s. S2 sits in the small black wheelchair on the paving, looking up over "
       "his shoulder; S1 stands behind the chair with both hands resting on the push handles, "
       "bending slightly toward him. Soft afternoon light through yellow ginkgo leaves."
       % SCENE_STREET,
       "Reverse over S1's shoulder onto S2, then back onto S1 as he crouches down to the boy's eye "
       "level beside the chair and speaks to him gently, one hand on the armrest.",
       "Medium close-up of S2's face: he listens, then looks down at his own folded hands and "
       "swings one foot slightly, the way a child does when he is thinking about something heavy."],
      "Quiet street ambience, a few birds, a light breeze moving the leaves, the faint tick of a "
      "wheelchair caster. No speech, no voices.",
      "Solo piano, simple and a little sad, over warm strings."),

    _shot(2, "shot02_first_meeting", "中景 (MS)", "S1 + S2 + S3", "小区门口 · 秋日白天",
      [("S2", "说要给我找个妈妈吗？"),
       ("S1", "爸爸要找的不是妈妈这个称号，是一个不会在爸爸看不见的时候让你受委屈的人。"),
       ("S3", "你怎么把孩子也带来了？还是坐轮椅的。"),
       ("S1", "他是我儿子。"),
       ("S3", "你早说你有这么大个拖累啊，你条件再好，带个坐轮椅的孩子也太掉")],
      ["S1 pushes the chair a few steps along the paving and stops under the ginkgo trees. S2 "
       "turns his head up and speaks to his father, who answers without breaking stride.",
       "S1 stops and crouches again beside the chair, straightening the boy's cardigan collar, and "
       "answers him quietly. The boy nods once, unconvinced but willing.",
       "S3 walks up the paving toward them in her off-white suit, stops two metres short, looks "
       "down at the wheelchair and back up at S1. Her polite smile switches off mid-sentence; her "
       "handbag swings as she half turns away."],
      "Footsteps on stone paving, leaves shifting, a handbag clasp. No speech, no voices.",
      "A colder string line slides under the piano."),

    _shot(3, "shot03_candy_and_turn", "中景 (MS)", "S3 + S2 + S1", "小区门口 · 秋日白天",
      [("S3", "价了吧。阿姨给你糖。"),
       ("S2", "别碰我。"),
       ("S3", "我刚做的，没假。"),
       ("S3", "你带着这种孩子出来相亲，不是找老婆，是找护工吧？"),
       ("S3", "以后我朋友问起来我怎么说？说我嫁过去就给人家当后妈？"),
       ("S3", "你赶紧让司机把孩子送走。"),
       ("S1", "不用")],
      ["Medium shot: S3 bends slightly and holds a wrapped candy out toward the wheelchair at "
       "arm's length, the way one handles something unpleasant. Her face is all performance.",
       "S2 pulls his hands back into his lap and turns his head away. S3 straightens up, retracts "
       "the candy, and her expression hardens as she looks at S1 rather than the child.",
       "Medium shot of the three of them: S3 talks with her handbag hitched up the arm, chin "
       "tilted, gesturing at the wheelchair. S1 stands behind it with both hands on the handles, "
       "face completely still, letting her finish."],
      "Street ambience, a wrapper crinkling, a handbag shifting. No speech, no voices.",
      "The strings thin out, dry and cold."),

    _shot(4, "shot04_terms", "中近景 (MCU)", "S3 + S1", "小区门口 · 秋日白天",
      [("S1", "了。"),
       ("S3", "你什么意思啊？你不是嫌他丢人吗？"),
       ("S1", "那你也不配进我的家门。"),
       ("S3", "孩子我可以接受，但婚前必须说清楚，他以后不能分你的钱。"),
       ("S1", "你还没进门就开始分财产？"),
       ("S3", "这叫现实。房子、车全写我名，工资")],
      ["Medium close-up on S1: he answers with two words, without raising his voice or moving his "
       "hands off the push handles. Bright afternoon light on his face, leaves moving behind him.",
       "Reverse on S3: she takes half a step forward, hands rising in protest, her composure "
       "cracking into open annoyance.",
       "Medium shot of the pair: S3 talks with one hand counting off points in the air; S1 stands "
       "motionless behind the wheelchair, looking at her the way one looks at weather."],
      "Street ambience, fabric moving, a heel turning on paving. No speech, no voices.",
      "A low pulse enters under the string line."),

    _shot(5, "shot05_money_talk", "中近景 (MCU)", "S3 + S1", "小区门口 · 秋日白天",
      [("S3", "卡也得交给我。孩子以后康复、上学、请保姆，这些钱都不能影响我的生活质量。"),
       ("S3", "如果他真的一辈子坐轮椅，那就更得请人照顾。我不可能给别人孩子当免费保姆，也不可能让一个坐轮椅的孩子拖累我的后半生。"),
       ("S1", "你不是来相亲的。"),
       ("S3", "那我是什么？"),
       ("S1", "你是来")],
      ["Medium close-up on S3 talking directly at S1, one hand raised with fingers extended as she "
       "lists terms. She is entirely serious; there is no embarrassment in her face at all.",
       "She keeps going, chin lifting, one finger tapping the air on each clause. S1's shoulder and "
       "the wheelchair handle sit in the soft foreground, out of focus.",
       "Close on S1: he says one flat sentence, then turns his head slightly to look at his son. "
       "S3's voice stops and her mouth stays open for a beat."],
      "Street ambience, a distant car, wind in the leaves. No speech, no voices.",
      "The strings hold one long note, very quiet."),

    _shot(6, "shot06_leaves", "中景 (MS)", "S3 + S1 + S2 + S4", "小区门口 · 秋日白天",
      [("S1", "算账的。"),
       ("S3", "现实一点，我没有错。你带着这种孩子，本来就得补偿我。"),
       ("S1", "慢点，门口的台阶。别看孩子。"),
       ("S4", "小朋友，冷不冷？坐久了腿")],
      ["S3 turns on her heel and walks away down the paving without a backward glance, handbag "
       "swinging. S1 watches her go, then puts both hands on the wheelchair handles.",
       "S1 turns the chair around and pushes it away along the paving, leaning down to say "
       "something short to the boy as they reach the step at the shopfronts.",
       "S4 appears in the doorway of a small warm restaurant, wiping her hands on her apron, and "
       "crouches down in front of the wheelchair at eye level with the boy, smiling."],
      "Heels on paving receding, then wheelchair casters rolling over stone, a shop door swinging. "
      "No speech, no voices.",
      "The piano returns, warmer, as the street empties."),

    _shot(7, "shot07_soft_pad", "中近景 (MCU)", "S4 + S2 + S1", "小餐厅门口 · 秋日白天",
      [("S4", "会不舒服吧？阿姨给你拿个软垫。"),
       ("S2", "阿姨，你不嫌我麻烦吗？"),
       ("S4", "你这么可爱，哪里麻烦了？小孩来吃饭，阿姨高兴还来不及。"),
       ("S4", "想吃什么，阿姨给你做。"),
       ("S2", "阿姨，我想吃红烧排骨。"),
       ("S1", "不用，已经很麻烦你了。"),
       ("S4", "红烧排")],
      ["Medium close-up of S4 crouched at the wheelchair, tucking a folded cushion behind the "
       "boy's back and adjusting his collar with a light, practised hand. The boy watches her face "
       "the whole time, testing her.",
       "S2 asks her something quietly and looks down at his knees; S4 laughs and shakes her head at "
       "once, then stands and holds the restaurant door open with one hand.",
       "Medium shot at the doorway: S4 gestures them in; S2 looks up at his father, who hesitates "
       "with one hand still on the push handle, then nods. Warm light spills out of the restaurant "
       "onto the paving."],
      "A shop door, cloth being tucked, a wheelchair caster turning, warm kitchen sound leaking "
      "out of the doorway. No speech, no voices.",
      "The piano turns gentle and open; light strings join."),

    _shot(8, "shot08_hinge_to_pitch", "中景 (MS)", "S4 + SP", "小餐厅后厨 · 白天",
      [("S4", "骨？又要焯水、炒糖色、看火，太费事了。"),
       ("S4", "现在做红烧排骨哪有麻烦？别再用老一套方法做红烧排骨了。"),
       ("S4", "每天上班累得骨头都快散架，回家想吃口硬菜，一想到还要在闷热厨房里切葱姜蒜，忍着油烟炒糖色，稍不注意油花四溅。")],
      ["Medium shot in %s. S4 stands behind the pale wood counter tying her apron, and answers "
       "toward the doorway the way one answers a customer - easy, cheerful, direct." % SCENE_KITCHEN,
       "She turns from the doorway to face the counter and speaks straight down the lens, both "
       "hands settling on the wood, and lifts a slim red sauce pouch into frame with one hand.",
       "Insert on the range and board: chopped ginger, garlic and scallion on a wooden board with a "
       "knife resting across it; then raw ribs tipped from a bowl into a pot of cold water with a "
       "small burst of spray. Steam and heat haze distort the edges of frame."],
      "Kitchen extractor hum, a knife set down on wood, water running, a pot set on a burner. "
      "No speech, no voices.",
      "An upbeat mid-tempo bed starts and holds, carrying the pitch."),

    _shot(9, "shot09_pain_then_promise", "中景 (MS) + 特写", "S4 + SP", "小餐厅后厨 · 白天",
      [("S4", "烫到手，吃完还得刷油腻腻的炒锅和灶台，是不是瞬间就想点外卖？"),
       ("S4", "今天我就让你看看，红烧排骨还能这么简单。只要家里有个电饭锅，饭店级别的软烂红烧排骨，闭着眼睛都能做出来。"),
       ("S4", "家里那些落灰的八角、桂皮、酱油、老抽，通")],
      ["Close on the range: dark syrup spitting in a hot wok, an arm jerking back; then a tight "
       "shot of a stainless sink stacked with scorched pans and greasy bowls, the tap still running.",
       "Medium shot: S4 speaks to camera with an open, confident face, one hand turning the red "
       "pouch over so the light slides across it. A domestic rice cooker with its lid open sits on "
       "the counter beside her.",
       "Insert on the counter: a forearm sweeps three glass jars and two bottles of soy sauce "
       "backwards off the counter edge into a crate. The wood is suddenly bare - only the pot and "
       "the red pouch remain."],
      "Extractor hum, sugar spitting in a wok, water running over a full sink, glass jars knocking "
      "into a crate. No speech, no voices.",
      "The bed keeps a steady driving measure."),

    _shot(10, "shot10_five_steps", "特写 (CU)", "SP + S4", "小餐厅后厨 · 白天",
      [("S4", "通先靠边站。排骨冷水下锅焯水，捞出来用温水洗干净，直接放进电饭锅里。"),
       ("S4", "重点来了，撕开这一包鲍汁红烧酱料直接倒进去。"),
       ("S4", "这里面是大厨调好的黄金比例，咸淡、上色、香味都配好了，根本不用你再猜「少许」到底是多少。")],
      ["Tight overhead: cleaned ribs are lifted out of a colander with both hands and lowered "
       "straight into the dry inner pot of the rice cooker, settling in a pale heap.",
       "Close on two hands tearing the top off the red pouch; the tear runs clean across the notch "
       "and the packet opens wider.",
       "Macro on the pot: a thick dark-red sauce pours from the pouch in one slow glossy ribbon "
       "over the raw ribs, coating each piece and pooling in the gaps. The sauce is heavy enough to "
       "hold its shape for a moment before it settles."],
      "Water dripping from ribs, foil tearing, thick sauce pouring and folding over raw meat. "
      "No speech, no voices.",
      "The bed holds, no flourish, letting the texture carry it."),

    _shot(11, "shot11_set_and_wait", "特写 (CU) + 中景", "SP + S4", "小餐厅后厨 · 白天",
      [("S4", "再加半碗清水，盖上盖子，按下煮饭键，搞定。"),
       ("S4", "接下来你就可以离开厨房了，不用吸油烟，不用守着火，你去洗个澡、敷个面膜、刷两集剧都行。"),
       ("S4", "等电饭锅叮的一声，直接开饭。你看这出锅的颜色，不加一滴老抽，照样红亮优")],
      ["Close: a hand tips half a bowl of clean water in around the sauced ribs; the surface rises "
       "and red streaks thread into the water. Then the stainless lid seats and rotates home and a "
       "thumb presses the cook lever down with a click; the amber lamp lights.",
       "Medium shot: S4 wipes the counter once, hangs the cloth on a rail and walks out of frame "
       "past the left edge. The camera stays on the rice cooker alone on the counter, quietly "
       "working.",
       "The lid lifts on a heavy roll of steam; inside, the ribs are deep red and glossy, the sauce "
       "reduced and thick, whole pieces holding their shape on the bone."],
      "Water poured, a lid seating with a clunk, one soft key click, steam venting, a cloth on a "
      "steel rail. No speech, no voices.",
      "The bed relaxes into something warm and unhurried."),

    _shot(12, "shot12_proof_and_ease", "特写 (CU)", "SP + S4", "小餐厅后厨 · 白天",
      [("S4", "人。排骨吸满浓郁酱汁，筷子轻轻一戳就脱骨，软烂入味，特别下饭。"),
       ("S4", "关键是吃完只用洗一个电饭锅内胆，不用刷炒锅，不用擦满是油点的灶台，简直就是懒人和上班族的厨房之光。"),
       ("S4", "而且它配料表干净，最重要的是 0 蔗糖，家里老人小孩都")],
      ["Close-up: steel chopsticks press into a rib and the meat slides clean away from the bone "
       "with almost no resistance. The bare bone comes out pale; the meat stays whole and "
       "glistening.",
       "Insert: a single rice-cooker inner pot standing alone on the clean counter beside a rack of "
       "spotless unused pans - the contrast is the point. Bright even kitchen light.",
       "Medium shot: S4 lifts the red pouch up beside her face in one hand and speaks down the lens "
       "with an easy smile, the clean empty counter behind her."],
      "Chopsticks on ceramic, a single pot set on wood, kitchen room tone. No speech, no voices.",
      "The bed keeps a light, confident lilt."),

    _shot(13, "shot13_uses_and_price", "中景 (MS) + 特写", "S4 + SP", "小餐厅后厨 · 白天",
      [("S4", "能安心吃。除了红烧排骨，拿它做红烧肉、红烧鱼、炖牛肉、炖羊肉也都可以，一包就能搞定一锅硬菜，真正的万能红烧调料。"),
       ("S4", "平时去买这么一包，少说也要七八块。今天在我们这里，直接把底价打穿，点击左下角，9 块 9 直接到")],
      ["Medium shot of the wooden counter: three finished dishes in a row - braised pork belly, "
       "braised fish, braised lamb - with S4's open palm sweeping above them left to right.",
       "Insert close-up filling the frame: the red pouch held square to camera, its blank red front "
       "panel catching the light, the ivory header band at the top and the printed serving "
       "photograph across the bottom third. No lettering anywhere on it.",
       "Medium close-up: S4 sets the pouch down, leans both hands on the counter edge and speaks "
       "straight down the lens, chin level, entirely at ease in front of a camera."],
      "Kitchen room tone, foil crinkling in a hand, a plate nudged on wood. No speech, no voices.",
      "Drive up a step, the bed gaining energy."),

    _shot(14, "shot14_bundle_close", "中景 (MS) + 特写", "S4 + SP", "小餐厅后厨 · 白天",
      [("S4", "手五包。还没完，现在拼手速下单的，我再自掏腰包多送你两包。"),
       ("S4", "也就是说 9 块 9 整整七包，直接包邮到家，折算下来，一块多钱就能解决一顿大餐的调味。"),
       ("S4", "告别满身油烟，零厨艺也能轻松做出大厨味。现货库存马上见底，赶")],
      ["Insert close-up: two extra pouches are laid down on top of the row of five on the wooden "
       "counter, and a hand fans them into a neat overlapping spread of seven.",
       "Medium shot: S4 steps back from the counter and gestures at the arranged pouches with both "
       "hands, then folds her arms with a small satisfied shrug.",
       "Medium close-up: S4 speaks straight down the lens, right index finger raised beside her "
       "shoulder, holding the closing look for a beat. Behind her the kitchen is bright and tidy."],
      "Kitchen room tone, foil pouches sliding across wood, a light hand tap on the counter. "
      "No speech, no voices.",
      "One strong final phrase, then the bed drops away cleanly."),

    _shot(15, "shot15_reveal_setup", "中景 (MS)", "S4 + S2 + S5 + S3", "小餐厅 · 傍晚",
      [("S4", "紧点击左下角头像抢单带回家。"),
       ("S2", "爸爸，好香。"),
       ("S4", "慢点吃，锅里还有。"),
       ("S5", "顾总，董事会那边已经等您半个小时了，合同需要您亲自签。"),
       ("S3", "顾总？你是宏盛集团的顾承舟？你刚才不是说你普通上")],
      ["Medium shot in %s. S4 is back at the table in her apron, serving the plate of ribs to the "
       "boy; both of them look relaxed and unguarded. The camera settles and holds on them."
       % SCENE_RESTAURANT,
       "S5 walks in from the street door in his dark suit with a folder, stops beside the table and "
       "bows slightly toward S1, speaking low. The room's warmth drops a degree.",
       "Wide shot across the restaurant: S3 appears in the doorway behind S5 with her handbag, "
       "staring at the table. S4 straightens up with the serving spoon still in her hand. Nobody "
       "moves for a beat."],
      "Restaurant room tone, a door swinging, crockery settling, an evening street outside. "
      "No speech, no voices.",
      "The warm bed cuts out; a single low string takes over."),

    _shot(16, "shot16_identity_out", "中近景 (MCU)", "S1 + S2 + S3 + S4", "小餐厅 · 傍晚",
      [("S3", "班吗？"),
       ("S1", "我从来没说过我普通，是你们只看我穿的普通。"),
       ("S4", "顾总，刚才是误会，我不是嫌孩子，我是怕他不舒服。"),
       ("S3", "对啊，我也是替你考虑，毕竟孩子以后需要规划。"),
       ("S2", "不用你们规划，我腿没事。是爸爸想看看，谁真心喜欢我。"),
       ("S1", "我儿子腿")],
      ["Medium close-up on S1 at the table: he answers without heat, one hand resting on the table "
       "edge, and does not look at either of the women.",
       "Medium shot: S4 and S3 both step in toward the table at the same time, hands raised in "
       "explanation, voices overlapping, polite faces working hard. S1 simply reaches over and "
       "straightens the boy's sleeve.",
       "The boy puts both hands flat on the arms of the wheelchair, pushes himself up and stands "
       "on his own two legs. He takes one steady step and turns to look at S4. Hold on his face, "
       "clear and unafraid."],
      "Restaurant room tone, chair legs on wood, a wheelchair frame creaking, then a sudden "
      "stillness. No speech, no voices.",
      "Tense held strings, one soft accent as the boy stands.",
      cast=["S1", "S2_STAND", "S3", "S4"]),

    _shot(17, "shot17_accusation", "中近景 (MCU)", "S1 + S3 + S2 + S4", "小餐厅 · 傍晚",
      [("S1", "没问题，有问题的是你们的人品。"),
       ("S3", "顾总，我其实也很喜欢孩子，我也可以学着照顾他。"),
       ("S1", "晚了。你们刚才嫌弃他的样子，他都记得。"),
       ("S4", "那你坐了一上午，腿麻吗？"),
       ("S2", "阿姨，你不怪我骗你吗？"),
       ("S4", "能走是好事。可就算你真的坐轮")],
      ["Medium close-up on S1: he stands, buttons his olive jacket and delivers the line flat and "
       "finished. Then he looks down at the wheelchair - now empty - beside the table.",
       "Medium shot: S3 steps toward the table with both hands out, smile carefully rebuilt. S1 "
       "does not turn to her at all; he picks up the boy's cardigan off the chair back and folds it.",
       "S4 walks around the table, crouches beside the standing boy and puts one hand on his knee "
       "without hesitation, checking him the way she checked him at the door. The boy looks up at "
       "her, guarded, and asks his question."],
      "Restaurant room tone, a chair moved, quiet footsteps on wood. No speech, no voices.",
      "The strings loosen; the piano comes back underneath."),

    _shot(18, "shot18_forgiveness", "中近景 (MCU)", "S4 + S2 + S1", "小餐厅 · 傍晚",
      [("S4", "椅，阿姨也不会嫌你。"),
       ("S1", "你知道我是谁，以后不生气吗？"),
       ("S4", "生气。你们试探我，但不生孩子的气。他只是想知道，以后会不会有人真的疼他。"),
       ("S1", "今天是我做的不对，不该让孩子陪我演这场戏。可我更怕有一天，把他交给一个表面温柔、背后")],
      ["Medium close-up of S4 still crouched at the boy's side: she answers him directly, one hand "
       "still on his knee, entirely matter-of-fact. The boy's shoulders come down a notch.",
       "S1 stands a little apart with the folded cardigan over his arm and speaks toward S4; for "
       "the first time his expression is not controlled but tired and honest.",
       "Back onto S4: she stands up slowly and faces S1 across the table, chin up, not softening. "
       "The boy stays between them, looking from one to the other."],
      "Restaurant room tone, apron fabric, a table settling, an evening street beyond the window. "
      "No speech, no voices.",
      "Warm strings return under the piano, low and steady."),

    _shot(19, "shot19_moral", "中景 (MS)", "S1 + S2 + S4", "小餐厅 · 傍晚",
      [("S1", "嫌弃他的人。"),
       ("S2", "阿姨，那你会疼我吗？"),
       ("S4", "会。小孩不是负担，是应该被好好照顾的人。"),
       ("S1", "今天我看清了，有人看见轮椅只觉得丢人，有人看见孩子只想分财产，只有你先问他冷不冷、饿不饿。"),
       ("S4", "我不懂你们有钱人的规矩，我只知道孩子进了我的店，就得吃上一口")],
      ["Medium shot: S1 speaks across the table with the folded cardigan over his arm; his voice is "
       "low and he does not perform it. S4 listens with her arms folded, absolutely still.",
       "The boy looks up from the table at S4 and asks his question plainly. S4 crouches back to "
       "his eye level and answers at once, without hesitation.",
       "Warm wide shot: S1 stands, the boy sits back down at the table with the plate of ribs in "
       "front of him, and S4 stands between them with one hand on the back of the boy's chair. The "
       "evening light through the window has gone gold."],
      "Restaurant room tone, a serving spoon on crockery, quiet warmth in the room. No speech, "
      "no voices.",
      "The theme opens out, warm and full."),

    _shot(20, "shot20_closing", "中景 (MS) + 特写", "S1 + S2 + S4", "小餐厅 · 傍晚",
      [("S4", "热饭。"),
       ("S2", "爸爸，我喜欢这个阿姨。"),
       ("S1", "爸爸也喜欢。"),
       ("S1", "屏幕前的家人们，钱能试出贪心，落魄能试出真心，孩子最能试出一个人骨子里的善良。"),
       ("S1", "真正能走进一个家的，不是最会算条件的人，而是在孩子最需要温暖的时候，愿意给他一碗热饭的人。你们说对吗？")],
      ["Medium shot at the table: the boy says it without looking up from his plate; S1 answers "
       "him from the other side of the table, and for the first time all evening he smiles. S4, "
       "carrying a tray past, hears them and keeps walking.",
       "S1 turns from the table to face the camera position. The restaurant, the boy and S4 fall "
       "softly out of focus behind him; the plate of ribs on the table stays bright in the "
       "foreground.",
       "Close-up on S1's face: calm, open, no performance left in it. He speaks straight down the "
       "lens, unhurried, and holds the look to the last frame."],
      "Warm restaurant room tone, a tray set down, quiet evening street outside. No speech, no voices.",
      "The theme resolves fully and fades warm into silence."),
]

assert len(SHOTS) == 20, len(SHOTS)
