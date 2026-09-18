# -*- coding: utf-8 -*-
"""片 1 分镜数据 · 良心面试 × 食堂红烧 —— 按参考视频 100% 抄写重建

抄写口径（对齐 _lines/film1_shot_lines.txt）：
  · 台词 = 原片 whisper 逐词转写原文，逐字照抄，不增删不改写
  · 画面 = 按原片接触表逐拍重建（白天 / 公司后门 / 顾董坐轮椅 / 真人演员 / 真实食堂后厨）
  · 时间窗 = 原片 286.13s 均分 20 镜，每镜 14.31s（生成侧固定 15s）
  · 语音 = Edge TTS 逐字合成原文（中文），走 audio-lock 工作流驱动口型，不依赖模型自己说话

角色锚定（写进每镜 prompt，H3 只看单镜）：
  S1 顾怀山  董事长，坐轮椅装落魄老人测试面试者
  S2 林晚晴  面试者，女主（20 岁）
  S2K 林晚晴 换后厨装（浅蓝衬衫 + 米色围裙）
  S3 男面试者 竞争者，冷漠
  S4 白西装女 竞争者，傲慢
  S5 助理
  SP 产品    醉锅里·鲍汁红烧酱（外观取自参考视频抽帧，见 _product/PRODUCT.md）
"""

import re

S1 = ("<Subject 1> (S1), a dignified 65-year-old East Asian man with thick silver-white hair "
      "combed back, deep laugh lines, calm penetrating eyes and a neatly shaved jaw, wearing a "
      "charcoal-grey wool jacket over a dark grey knit sweater and plain dark trousers; he sits in "
      "a black manual wheelchair with chrome hand-rims")
S2 = ("<Subject 2> (S2), a strikingly beautiful 20-year-old East Asian young woman with a fresh "
      "dewy youthful face, large bright almond eyes, a small straight nose, softly defined "
      "cheekbones, full natural pink lips and smooth flawless unlined porcelain skin, a tiny soft "
      "beauty mark just below her left eye, long glossy jet-black hair pulled into a high loose bun "
      "with a few strands framing her face, slim petite figure; wearing a crisp white shirt under a "
      "tailored black blazer with matching black trousers, a slim leather document folder in her arm")
S2K = ("<Subject 2> (S2), the identical strikingly beautiful 20-year-old East Asian young woman, "
       "same fresh dewy youthful face, same large bright almond eyes, same tiny beauty mark below "
       "her left eye, same glossy jet-black hair now in a high loose bun; now wearing a pale blue "
       "cotton shirt with the sleeves rolled to the elbow and a soft beige apron over black "
       "trousers, standing behind a stainless prep counter")
S3 = ("<Subject 3> (S3), a 27-year-old East Asian man with short neat black hair and a "
      "self-assured manner, wearing a light grey slim-fit suit and a white shirt with no tie, a "
      "black portfolio under his arm")
S4 = ("<Subject 4> (S4), a 30-year-old East Asian woman with shoulder-length dark-brown hair, sharp "
      "eyeliner and a cold appraising expression, wearing an immaculate white trouser suit and nude "
      "heels, a slim folder pressed against her chest")
S5 = ("<Subject 5> (S5), a 35-year-old East Asian man in a dark navy uniform jacket and matching "
      "trousers, standing attentively beside the wheelchair")
SP = ("<Subject P> (SP), a glossy laminated stand-up sauce pouch of tall rounded doypack silhouette, "
      "vivid tomato-red metallised front panel with crisp white specular highlights along its folds "
      "and a faint crinkle across the surface, a narrow ivory header band across the very top "
      "carrying a round punched hang-hole, and a plain unadorned red label field filling the middle "
      "two thirds of the front panel - completely empty, smooth, blank and unprinted; only the bottom "
      "third carries a printed serving photograph of glossy braised pork ribs in deep red sauce on a "
      "pale dish; the pouch surface bears no lettering, no numbers, no symbols, no logo and no barcode")

# ── 首帧锚定版产品锚定（SP_ANCHORED）──────────────────────────────────────
# 走 FL2VA 首帧锚定（先用 make_first_frame.py 把真产品图合进关键帧）时用这一版。
# 官方 FLF2V 提示词规范明确：端点图像已经回答了「呈现什么内容」，提示词只需说明
# 中间「如何运动」，**不要重复描述视觉细节，否则会与固定帧产生冲突**。
# 所以这里不再说「红区空白、无字」，只声明「维持首帧那张已印刷的包装面」。
SP_ANCHORED = (
    "<Subject P> (SP), the same glossy laminated stand-up sauce pouch of tall rounded doypack "
    "silhouette, vivid tomato-red metallised front panel with crisp white specular highlights "
    "along its folds and a faint crinkle across the surface, a narrow ivory header band across "
    "the very top carrying a round punched hang-hole - the pouch's front panel carries its own "
    "printed packaging artwork, exactly as it appears in the opening frame; keep that printed "
    "surface identical, unchanged and physically part of the film throughout the shot")

# ── 参考图锚定版（Ref2VA）────────────────────────────────────────────
# 与首帧锚定的**本质区别**（决定它为什么更有用）：
#   FL2VA 关键帧 = 占**真实帧位**（第 0 帧 / 末帧），且必须与目标画布同比例
#                → 产品只在镜头中段出现时**根本用不了**（镜15 就是这种）；
#   Ref2VA 参考图 = **不占帧位**、可用自身分辨率，只「引导身份/外观」而不成为某一帧
#                → 产品出现在**任意时段**都能锁，最多 9 图 / 3 视频 / 3 音频。
# 官方 R2V 提示词规范要求：必须说明参考图与目标画面的关系；产品外观交给
# <Picture 1>，**不要重复描写视觉细节**（重复描述会与参考图打架，反而拉低一致性）。
#
# ★ 标签规范：H3 的媒体标签是 <Picture N> / <Video N> / <Audio N>，编号必须与
#   实际接线顺序一致（节点的 strict_prompt_tags=true 会校验）。原 prompt 里那套
#   <Subject N> 不是 H3 媒体标签，只是普通文本 —— 所以它从来没能真正锚定过任何图。
SP_REF = (
    "<Picture 1> is the authoritative reference for the product SP: a glossy laminated stand-up "
    "sauce pouch of tall rounded doypack silhouette with a vivid tomato-red metallised front "
    "panel and a narrow ivory header band carrying a round punched hang-hole. Whenever the pouch "
    "is on screen, keep its identity, silhouette, proportions, colour, material and its own "
    "printed packaging design exactly as shown in <Picture 1> - do not invent, restyle, re-letter "
    "or recolour the packaging, and do not replace it with a different bag or a box")

_REF_NOTE = ("The supplied <Picture 1> reference fixes what the product is and how its packaging "
             "looks; the description below only covers staging, action, camera and timing. Do not "
             "re-describe or re-draw the packaging design beyond what <Picture 1> already shows.\n\n")

# ── 禁字铁律（NO_TEXT_CLAUSE）────────────────────────────────────────────
# 背景：H3 是**临摹型**生成器。训练数据里大量带烧死字幕的短视频，它会把「字幕条 +
# 乱码字」当成画面元素画出来 —— 实测镜3 t≈38s、镜12 t≈173s 出现成行乱码字，而
# 原 prompt 里**已经写了** no subtitles / no captions，说明纯负向提示压不住。
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
# ★ 首帧锚定版（NO_TEXT_CLAUSE_ANCHORED）—— 只给走 FL2VA 锚定的产品镜用
# 为什么必须单开一版：严格版的最后一句要求「画面里任何纸张/文件/招牌/屏幕/**包装**/
# 印刷面都必须是空白或只有不可读的模糊痕迹」，还写了 no logo。可产品镜的首帧里
# **袋面本来就有真包装印刷** —— 两者直接打架，模型要么抹掉印刷（回到空壳），
# 要么画出混乱的字。所以锚定版把这两条「实物固有印刷」的豁免掉，
# 其余禁叠加层的条款**一字不动**全保留（那才是乱码字幕的真来源）：
#   禁的仍是「叠加在画面上的文字」——字幕条/标题/角标/卡拉OK/水印/时间码/UI；
#   允许的只是「物体自己表面的印刷」，且要求它平、哑光、略虚，不许比实物更亮更粗。
NO_TEXT_CLAUSE_ANCHORED = (
    " no subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar "
    "across the frame, no karaoke-style highlighted characters, no on-screen text overlay, "
    "no watermark, no timestamp, no UI overlay; never imitate or reproduce a subtitle strip or "
    "any text overlay from the source material; do not add any floating or superimposed "
    "lettering of any script - Chinese, Latin, digits or symbols - anywhere in the frame, "
    "especially in the lower half and along the bottom edge; the only lettering allowed is the "
    "printing that is physically part of an object's own surface, and it must stay flat, matte, "
    "slightly out of focus and exactly as it appears in the supplied reference image - never "
    "sharpened, never glowing, never larger, bolder or more legible than the physical print")
_STYLE_HEAD = ("cinematic 9:16 vertical, ARRI Alexa look, shallow depth of field, fine film grain, "
               "naturalistic daylight, photorealistic live-action footage,")
STYLE = _STYLE_HEAD + NO_TEXT_CLAUSE
STYLE_ANCHORED = _STYLE_HEAD + NO_TEXT_CLAUSE_ANCHORED
# 参考图（Ref2VA）与关键帧（FL2VA）共用同一版禁字条款：两者都豁免「实物自带印刷」，
# 都仍严禁任何叠加层文字。措辞已泛化成 "supplied reference image" 以同时覆盖两种来源。
STYLE_REF = STYLE_ANCHORED

FILM = {
    "film_title": "良心面试 · 食堂红烧（原片复刻）",
    "director_style": "都市职场短剧质感 × 电商口播素材，冷调写字楼后门 + 暖调食堂后厨对照",
    "theme": "食品集团董事长坐轮椅在后门假摔测试三位面试者；唯一扶人、分饭的姑娘通过人品关，"
             "进入后厨用电饭锅 + 一包红烧酱现场做菜，完成省事类口播带货，收尾「良心不能没有」",
    "fps": 24,
    "target_fps": 30,
    "shot_duration_sec": 15,
    "h3_length": 362,
    "refined_frames": 361,
    "aspect_ratio": "9:16",
    "resolution_stage1": "384x672",
    "resolution_stage2": "768x1344",
    "seed": 20260918,
    "prompt_schema": "github_minimax_h3_multimodal_envelope_v2",
}

SCENE_OFFICE = ("the rear service gate of a modern food-group office building in flat daylight: "
                "beige rendered concrete walls, a grey steel roller shutter, a covered walkway")
SCENE_HALL = ("a bright modern corporate lobby or corridor with pale marble floors, a long "
              "reception counter and a wall of frosted glass")
SCENE_ROOM = ("a bright corporate meeting room with a long pale wood table, black leather chairs "
              "and a frosted glass wall")
SCENE_KITCHEN = ("a professional canteen kitchen: stainless-steel counters, a wide gas range, an "
                 "extractor hood, white tiled walls and bright overhead lights, a rice cooker on "
                 "the counter")

_TAIL = "\n\noverall_soundscape:\n%s\n\nnon_diegetic_music:\n%s"

# 中文场景标签 → 英文场景常量（H3 只吃英文）。让每镜 prompt 自带场景锚定，
# 否则模型只凭 beats 里的零碎词猜环境（实测镜05 该是「后门」却被画成正门台阶）。
SCENE_EN = {
    "公司后门 · 白天": SCENE_OFFICE,
    "公司大堂 · 白天": SCENE_HALL,
    "公司大堂走廊 · 白天": SCENE_HALL,
    "公司会议室 · 白天": SCENE_ROOM,
    "食堂后厨 · 白天": SCENE_KITCHEN,
    "大堂 → 食堂后厨 · 白天": SCENE_KITCHEN,
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


_ANCHOR_NOTE = ("Start exactly from the supplied first frame; preserve its composition, framing, "
                "lighting, colour and the pouch's printed front panel. Animate only the motion "
                "described below; do not restage the opening.\n\n")


def _prompt(beats, sound, music, cast=None, speakers=(), scene=None, spans=None, anchored=False,
            ref=False):
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
    # 产品锚定的三种口径（互斥，优先级 ref > anchored > 严格版）：
    #   ref      → SP_REF    参考图（Ref2VA），产品可出现在任意时段
    #   anchored → SP_ANCHORED 首帧/尾帧关键帧（FL2VA），只能锁两端帧
    #   都不设   → SP        严格版（袋面必须空白）—— 纯 T2VA 现状
    pre = (_CAST_BLOCK % "; ".join(
        globals()["SP_REF" if (ref and k == "SP")
                 else "SP_ANCHORED" if (anchored and k == "SP") else k] for k in keys)) if keys else ""
    sc = SCENE_EN.get(scene or "")
    if sc:
        pre += _SCENE_BLOCK % sc
    if ref:
        pre += _REF_NOTE
    elif anchored:
        pre += _ANCHOR_NOTE
    return "integrated_multimodal_description:\n" + pre + body + (_TAIL % (sound, music))


def _shot(no, file, framing, character, scene, dialogue, beats, sound, music, cast=None,
          anchored=False, ref=False):
    return {
        "no": no, "file": file, "framing": framing, "character": character, "scene": scene,
        "dialogue": dialogue,
        "dialogue_cn": "／".join("%s：%s" % (sp, tx) for sp, tx in dialogue),
        "beats": beats, "sound": sound, "music": music,
        # anchored=True → 走 FL2VA 首帧锚定重跑（build.py 自动换 STYLE_ANCHORED）
        "anchored": bool(anchored),
        # ref=True → 走 Ref2VA 参考图重跑（build.py 自动换 STYLE_REF，prompt 用 <Picture 1>）
        "ref": bool(ref),
        "prompt": _prompt(beats, sound, music, cast, [sp for sp, _ in dialogue], scene,
                          anchored=anchored, ref=ref),
    }


SHOTS = [
    _shot(1, "shot01_backdoor_fall", "全景 (WS)", "S1 + S5", "公司后门 · 白天",
      [("S1", "有没有人啊，扶我一把。"),
       ("S5", "顾董您慢点，别真摔着。"),
       ("S1", "别出来，今天来面试的人都从这后门进，我就看看他们见到一个摔倒的老人是扶一把还是踩一脚。"),
       ("S1", "哎呦，年轻人，帮帮忙，我从轮椅上摔下来了。")],
      ["Wide static shot of %s. S1 is stationed just outside the roller shutter, facing the open "
       "yard; S5 leans in toward him with a worried expression. Bright even daylight, cool "
       "concrete tones." % SCENE_OFFICE,
       "S1 lifts one hand and waves S5 back toward the doorway without turning his head; S5 "
       "hesitates, takes two steps back under the walkway and stays there. S1 then grips both "
       "hand-rims and lets the chair roll half a metre forward onto the open concrete.",
       "The chair tilts and S1 slides out of it onto the ground, landing on one hip with an open "
       "palm flat on the concrete. The empty wheelchair rocks and settles on its side beside him. "
       "He looks up toward the still-closed doorway, deliberate rather than pained."],
      "Empty rear yard ambience, a light breeze, the faint metallic rattle of a wheelchair frame "
      "settling on concrete, fabric against stone. No speech, no voices.",
      "Low sustained strings with a faint pulse of suspense."),

    _shot(2, "shot02_youngman_passes", "中景 (MS)", "S1 + S3", "公司后门 · 白天",
      [("S1", "你干什么呢年轻人？我轮椅翻了，能不能扶我一把。"),
       ("S3", "我今天来面试主管岗，你别挡我前途，帮我叫一下保安也行。"),
       ("S3", "你这种老人我见多了，我要是因为你错过面试，你赔得起吗？"),
       ("S5", "顾董，第一个还要让他进面试吗？"),
       ("S1", "不用了。怕担责可以理解，但")],
      ["Medium shot from a low angle: S1 sits on the concrete with one arm reached out toward the "
       "left, looking up. The open yard behind him is empty and bright, the fallen wheelchair "
       "beside him.",
       "S3 walks briskly out of the doorway with the black portfolio under his arm, glancing at his "
       "cuff, and passes less than a metre in front of S1 without ever lowering his eyes to the "
       "ground. His polished shoes cross the foreground in three quick strides.",
       "Close on S1's outstretched hand as it slowly lowers and rests on his own knee. In the "
       "background, defocused, S3's light grey suit disappears off the right edge of frame without "
       "a single backward glance."],
      "Quick leather shoe steps crossing concrete and fading away, the rustle of a suit jacket, "
      "light wind. No speech, no voices.",
      "The strings descend a step, colder."),

    _shot(3, "shot03_oldman_waits", "中景 (MS)", "S1 + S4", "公司后门 · 白天",
      [("S1", "连一句求助都不愿意听完，这样的人进了公司也只会踩着别人往上爬。"),
       ("S4", "这什么味啊。"),
       ("S1", "姑娘，能不能扶我一下，我从轮椅上摔下来了。"),
       ("S4", "穿成这样怎么混到后门来的？"),
       ("S1", "我腿不方便，轮椅滑了一下，麻烦你搭把手。搭把手。我今天是来面")],
      ["Medium shot of S1 still seated on the concrete, propping himself up on one hand. He turns "
       "his head slowly toward the doorway, his white hair catching the daylight.",
       "At the top of the shallow steps by the roller shutter S4 stands with her folder pressed to "
       "her chest. She looks down at him once, a flat appraising glance, then lifts her chin and "
       "looks away across the yard.",
       "Close-up on S1's face: deep laugh lines, calm eyes, silver hair backlit by the open sky. He "
       "speaks toward her, unhurried, and his hand rises an inch off the ground and settles again."],
      "Distant traffic beyond the wall, a light breeze, a folder tapping softly against fabric. "
      "No speech, no voices.",
      "Sparse piano over sustained strings, restrained."),

    _shot(4, "shot04_whitesuit_cold", "中景 (MS)", "S1 + S4", "公司后门 · 白天",
      [("S1", "试行政经理的，我早上没吃饭，有点头晕，你帮我叫一下保安也行。"),
       ("S4", "你饿关我什么事？公司不是救助站。还有，公司连后门都管不好。"),
       ("S1", "姑娘说话不用这么难听，我已经够客气了，赶紧保安把你弄走，别影响面试心情。"),
       ("S5", "顾董，第二个也不用进了吧？"),
       ("S1", "今天的面试已经结")],
      ["Close-up of S1 on the concrete: he wipes his temple with the back of his hand, then lets "
       "the hand fall. His throat moves as he swallows. Bright hard daylight on his face.",
       "Medium shot of S4 standing above the steps, both arms folded, weight on one hip, chin "
       "raised. She looks past S1 rather than at him, and one shoe taps the concrete twice.",
       "She turns on the spot and walks away toward the doorway, her white trouser leg crossing the "
       "foreground. S1 watches her go from his seat on the ground, still propped on one hand."],
      "Wind, a heel tapping concrete, then steady unhurried footsteps receding. No speech, no voices.",
      "The piano thins to a single repeated note."),

    _shot(5, "shot05_lin_arrives", "中近景 (MCU)", "S2", "公司后门 · 白天",
      [("S1", "束一半了。"),
       ("S2", "大爷，您怎么摔地上了？"),
       ("S1", "轮椅滑了，我起不来。"),
       ("S2", "您先别急，有没有摔到头？手能动吗？"),
       ("S1", "头没事，就是没力气。你手上都是灰。"),
       ("S2", "早上吃饭了吗？"),
       ("S1", "没顾上吃，饿得有点发晕。"),
       ("S2", "那可不行，老人家最怕")],
      ["S2 hurries out through the roller shutter with the leather folder hugged against her chest "
       "and stops dead on the second step when she sees the man on the ground. Her expression "
       "shifts from hurry to concern in a single beat.",
       "She transfers the folder to her left arm, comes down the last steps quickly, then folds "
       "down at his side, one knee on the concrete, and lays a hand lightly on his forearm.",
       "Medium close-up: she leans in and looks carefully at his head and his hands, brow drawn, "
       "checking him the way a careful person checks an injured stranger. Her words are quiet and "
       "steady and her hand stays on his arm."],
      "Quick soft-soled steps on concrete, a folder pressed against cotton, the slight scrape of a "
      "knee touching down. No speech, no voices.",
      "The strings warm by a semitone as the piano returns."),

    _shot(6, "shot06_meal_offered", "中景 (MS)", "S2 + S1", "公司后门 · 白天",
      [("S2", "饿着。我带了中午饭，您先吃几口垫垫。"),
       ("S1", "这不是你的午饭吗？我吃了你怎么办？"),
       ("S2", "我家离这边远，中午回不去。"),
       ("S2", "您别嫌弃，先吃点热乎的。这排骨软烂，颜色也红亮。"),
       ("S1", "你")],
      ["Medium shot at ground level: S2 crouches beside the fallen wheelchair still holding S1's "
       "arm and speaks to him with an open, unguarded face. S1 listens with his eyes on her, testing.",
       "S2 reaches into the tote bag on her shoulder and lifts out a round stainless rice-cooker "
       "inner pot with its lid on, holding it in both hands at chest height.",
       "She holds the pot out toward him. S1 takes it with both hands, sets it on his knees and "
       "lifts the lid; steam rolls up into the cool air and he looks down into it, then back up at "
       "her."],
      "Fabric and a zip, the clack of a metal lid, rising steam, a light breeze. No speech, no voices.",
      "The piano gains a second, gentler voice."),

    _shot(7, "shot07_pot_and_ribs", "特写 (CU)", "S1 + S2", "公司后门 · 白天",
      [("S1", "你自己做的？"),
       ("S2", "是我自己做的。但真不是我厨艺多厉害，是这个爆汁红烧酱料太省事。排骨焯水后放电饭锅，倒一包酱料，加半碗水，按煮饭键就行。"),
       ("S1", "电饭锅能做成这样，确实不简单。"),
       ("S1", "你不怕扶我耽误面试？"),
       ("S2", "面试迟到可以解释，人摔在")],
      ["Close-up of S1 seated on the ground holding the open pot on his knees, chopsticks in his "
       "right hand. He lifts a piece of pork rib, puts it in his mouth and chews slowly; his eyes "
       "widen a fraction and his jaw stops moving for a beat.",
       "Insert close-up filling the frame: the rice-cooker pot packed with braised pork ribs, "
       "glossy deep-red sauce clinging to the meat over a bed of white rice. Daylight makes the "
       "sauce gleam and steam crosses the lens.",
       "Medium shot again: S2 crouches beside him speaking, one hand resting on her own knee. S1 "
       "turns his head toward her mid-chew, studying her face, and the corner of his mouth lifts."],
      "Chopsticks against metal, slow chewing, steam, distant wind. No speech, no voices.",
      "Warm piano, unhurried, almost tender."),

    _shot(8, "shot08_lin_goes_in", "中景 (MS)", "S2 + S1", "公司后门 · 白天",
      [("S2", "地上没人管，出事就来不及了。"),
       ("S2", "大爷，您要是不舒服，别一个人在后门待着，我进去帮您找人。"),
       ("S1", "好姑娘，你先进去。"),
       ("S3", "今天这个主管岗我势在必得。这种大公司最需要我这种懂形象管理的人。"),
       ("S3", "不好意思，我刚才在后门扶了摔倒")],
      ["Medium shot: S2 stands up, brushes the dust off her black trousers and settles the tote bag "
       "on her shoulder. She points toward the doorway and says something brief to S1.",
       "She walks to the roller shutter, stops, and turns back for one last look at the man on the "
       "ground. On S1's face something shifts, private assessment turning into approval.",
       "Empty shot of the open yard: the toppled wheelchair on the concrete beside the rice-cooker "
       "pot with its lid off, a few papers scattered near the gate, nobody in frame for a moment. "
       "Bright, still, quiet daylight."],
      "Footsteps on concrete moving away, the shutter frame creaking in the wind, paper turning "
      "over on the ground. No speech, no voices.",
      "A held string chord, unresolved."),

    _shot(9, "shot09_identity_reveal", "中景 (MS)", "S3 + S4 + S1", "公司会议室 · 白天",
      [("S3", "的大爷，所以耽误了几分钟。"),
       ("S4", "来面试还多管闲事，难怪迟到。"),
       ("S2", "老人摔倒了不先确认情况，难道看着他躺在地上吗？"),
       ("S4", "他怎么进来了？"),
       ("S5", "各位，这位是顾氏食品集团董事长顾怀山，顾董。"),
       ("S4", "董事长？顾董，我刚才不知道")],
      ["Medium shot in %s. S3 and S4 sit at the long table, portfolios open in front of them, both "
       "already relaxed and self-assured. S3 straightens his cuff and glances at the door." % SCENE_ROOM,
       "The door swings open and S5 pushes S1 in through it in the black wheelchair. S1 wears the "
       "same charcoal jacket, hands folded, expression mild. The chair rolls to the head of the "
       "table and stops. Both candidates look up.",
       "Medium shot with the table as foreground: S5 stands at S1's shoulder with one hand on the "
       "chair handle, announcing him to the room. S3's and S4's faces freeze and S4's folder slips "
       "an inch in her grip."],
      "A door latch, chair castors on a hard floor, papers shifting, quiet air conditioning. "
      "No speech, no voices.",
      "The strings tighten, one sharp accent as the door opens."),

    _shot(10, "shot10_interview_ends", "中景 (MS)", "S4 + S1 + S3", "公司会议室 · 白天",
      [("S4", "是您。"),
       ("S1", "不知道我是董事长？嫌我影响公司形象？"),
       ("S4", "我只是今天来面试，太紧张了。"),
       ("S1", "一个人最真实的样子，往往就在没人知道他身份的时候。二位，今天的面试到此结束。"),
       ("S4", "顾董，再给我一次机会吧。"),
       ("S3", "顾董，我学历很")],
      ["Medium shot: S4 half-rises from her chair, both hands flat on the table, leaning toward "
       "the head of the room. Her composure is gone and the words come out too fast. S3 sits rigid "
       "beside her.",
       "In %s, S1 sits in his wheelchair at the head of the table looking at her without speaking, "
       "hands still folded, entirely calm. The silence does the work." % SCENE_ROOM,
       "Wider shot of the whole table: S1 lifts one hand a few inches off his knee and lets it fall "
       "back, a minimal gesture of conclusion. A large wall panel behind him carries no readable text."],
      "A chair scraping, a folder closing, then complete room silence. No speech, no voices.",
      "Music drops out almost entirely, leaving one sustained low note."),

    _shot(11, "shot11_corridor", "中景 (MS)", "S1 + S2 + S4", "公司大堂走廊 · 白天",
      [("S3", "高，经验也足，我真的适合这个岗位。"),
       ("S1", "我们公司不缺会写简历的人，缺的是有良心的人。"),
       ("S2", "顾董，我刚才真的不知道你是董事长。"),
       ("S1", "我知道。你如果知道，也就测不出真心了。"),
       ("S2", "那我刚才把自己的饭给您吃，会不会不太礼貌？"),
       ("S1", "那不是不礼貌，那是你愿意把自己的午")],
      ["Wide shot of %s. S4 walks away down the corridor with her folder hugged to her chest, "
       "heels sharp on the marble, back straight and hurried." % SCENE_HALL,
       "S1's wheelchair sits still at the side of the corridor while S3 stands beside it, hands "
       "moving as he talks, leaning in. S1 looks up at him with an even, unhurried expression.",
       "S2 comes around the corner of the corridor with her tote bag and stops a few paces away, "
       "gives a small bow and waits to be noticed. The three of them hold the composition."],
      "Heels on marble fading, an elevator chime in the distance, low lobby ambience. No speech, "
      "no voices.",
      "Sparse, almost silent, a single held cello note."),

    _shot(12, "shot12_integrity_pass", "中近景 (MCU)", "S1 + S2", "公司大堂 · 白天",
      [("S1", "饭分给一个陌生老人，比任何面试回答都珍贵。"),
       ("S2", "谢谢顾董。"),
       ("S1", "林晚晴，你今天的人品这一关过了。"),
       ("S2", "那我的面试？"),
       ("S1", "你应聘的是公司食堂厨师助理，光心善还不够，手艺也得过关。你刚才那块红烧排骨我还没吃够，去公司食堂厨房完整做")],
      ["Close on S4 at the elevator doors: she turns her head back for one glance down the "
       "corridor, her expression complicated, and steps into the cabin as the doors close across her.",
       "Medium close-up of S1 turned in his wheelchair to face S2. For the first time his face "
       "opens: the appraisal is gone and something warmer replaces it. He speaks at an easy volume.",
       "Reverse on S2: she stands in front of the wheelchair with both hands on the strap of her "
       "tote bag, listening intently, lips slightly parted, nodding once. Bright lobby light from "
       "the side shapes her face."],
      "An elevator chime and doors closing, soft lobby air, the faint squeak of a wheelchair wheel. "
      "No speech, no voices.",
      "The piano comes back, warm and simple."),

    _shot(13, "shot13_kitchen_invite", "中景 (MS)", "S1 + S2 + SP", "大堂 → 食堂后厨 · 白天",
      [("S1", "一次给我看看。"),
       ("S2", "顾董，我平时自己带饭，就是因为家里这边远，今天正好带了常用的红烧酱料，我现场做一锅给您尝尝。"),
       ("S2", "顾董，今天我就用食堂的电饭锅给您做一道上排骨，省事还不弄得满身油烟。"),
       ("S2", "顾董，家人们，别再拿老一套方法做红烧排骨了。每天下班回家累得骨")],
      ["Medium shot in %s: S1 in his wheelchair speaks up to S2, who stands beside the table in "
       "her black blazer. She listens, then nods once with a small determined smile." % SCENE_HALL,
       "Cut to %s. S2, now in the pale blue shirt and beige apron, stands at the stainless counter "
       "and sets a slim red sauce pouch down flat on the steel surface beside a rice cooker."
       % SCENE_KITCHEN,
       "Medium shot from the counter: S2 looks toward the camera position and speaks directly, chin "
       "level, hands opening in a small explaining gesture. Behind her the range and hood are clean "
       "and bright; the product pouch sits in the foreground with its printed front panel turned "
       "square toward the camera."],
      "A change of room tone from lobby to kitchen: extractor hum, stainless counter resonance. "
      "No speech, no voices.",
      "Bright neutral cue as the scene moves into the kitchen.", ref=True),

    _shot(14, "shot14_pain_kitchen", "中景 (MS) + 特写", "S2 + SP", "食堂后厨 · 白天",
      [("S2", "头都快散架，想吃口硬菜，一想到要在闷热的厨房里切葱姜蒜，忍着热气炒糖色，吃完还得刷那口油腻腻的炒锅和灶台，瞬间就想点外卖了，对不对？"),
       ("S2", "今天我要彻底颠覆你的做饭体验。只要你家里有个电饭锅，这道饭店级别的软烂红")],
      ["Medium shot in the kitchen: S2 stands at the counter speaking straight down the lens, one "
       "hand raised, the other resting on the apron. The red pouch is beside her elbow.",
       "Insert: a board of chopped ginger, garlic and scallion on the counter with a knife mid-cut, "
       "then raw pork ribs tipped from a bowl into a pot of cold water with a small burst of spray.",
       "Close on the range: a wok of dark sugar syrup bubbling and smoking slightly, then cut to a "
       "stainless sink stacked with scorched pans and greasy bowls, the tap still running. The "
       "overhead extractor shadows the steel."],
      "Extractor hood hum, a knife on a board, water running, sugar syrup spitting in a hot wok. "
      "No speech, no voices.",
      "Restrained tension pulse under the kitchen ambience."),

    _shot(15, "shot15_twist_pour", "中景 (MS) + 特写", "S2 + SP", "食堂后厨 · 白天",
      [("S2", "烧排骨，闭着眼睛都能做成。家里那些落灰的八角、桂皮、酱油、老抽统统靠边站。排骨冷水下锅焯水，捞出来用温水洗净，直接扔进电饭锅里。"),
       ("S2", "然后重点来了，直接撕开一包这个爆汁红烧酱料倒进去，这里面是大厨给")],
      ["Medium shot: S2 speaks to camera with growing energy, both hands moving. The extractor hood "
       "and tiled wall frame her; the rice cooker lid is open on the counter behind her.",
       "Insert on the counter: a forearm sweeps two glass bottles and a small jar out of frame past "
       "the right edge; the red pouch is left alone in the centre of the clean steel, catching a "
       "specular highlight.",
       "Insert, slow and close: two hands tear the top off the red pouch and tilt it; a thick "
       "dark-red sauce pours out in a slow ribbon into the inner pot over the pale ribs waiting "
       "inside."],
      "Extractor hum, glass bottles pushed aside on steel, foil tearing, thick sauce pouring and "
      "settling. No speech, no voices.",
      "The pulse opens out, more confident.", ref=True),

    _shot(16, "shot16_press_cook", "特写 (CU)", "SP + S2", "食堂后厨 · 白天",
      [("S2", "你调配好的黄金比例。加半碗清水，盖上盖子，按下煮饭键，搞定，就这么简单。"),
       ("S2", "接下来你就可以彻底离开厨房了，不用吸油烟，不用盯火候，你去舒舒服服洗个澡，敷个面膜，刷两集剧。听到电饭锅一")],
      ["Extreme close-up inside the inner pot: the dark-red sauce coats every rib, sliding down the "
       "meat in slow glossy sheets. Bright kitchen light rings the rim of the pot.",
       "A hand tips half a bowl of clean water in; the surface rises around the ribs and the sauce "
       "streaks into the water in red threads.",
       "Close on the rice cooker: a thumb presses the cook lever down with a firm click, the lid "
       "settles closed and the indicator lamp comes on. The steel body holds a soft reflection of "
       "the kitchen."],
      "Sauce sliding on ceramic, water poured, a mechanical lever click, a lid settling. "
      "No speech, no voices.",
      "Light, satisfied kitchen cue, small and rhythmic."),

    _shot(17, "shot17_open_and_taste", "特写 (CU)", "SP + S1", "食堂后厨 · 白天",
      [("S2", "声，直接开饭。您看这出锅的色泽，排骨吸满了浓郁的酱汁，筷子一戳直接脱骨。"),
       ("S1", "还真是一戳就脱骨。"),
       ("S2", "关键是吃完只用洗一个电饭锅内胆，简直是咱们懒人和上班族的厨房之光。它配料表干干净净，家里")],
      ["Close on the rice cooker on the counter: steam lifts from the vent in a steady plume, the "
       "indicator lamp lit, a mobile phone lying face-down beside it. Nobody in frame.",
       "The lid opens and a heavy roll of steam escapes; inside, the ribs are deep red and glossy, "
       "the sauce reduced and thick, whole pieces holding their shape on the bone.",
       "Medium close-up: S1 sits in his wheelchair at the counter with chopsticks, lifts a rib and "
       "tugs. The meat slides clean off the bone into his mouth. His eyes crease with plain enjoyment."],
      "A steam vent hissing, a lid opening, chopsticks, a small satisfied breath. No speech, no voices.",
      "Warm piano returns, small and pleased."),

    _shot(18, "shot18_product_points", "中景 (MS) + 特写", "S2 + SP", "食堂后厨 · 白天",
      [("S2", "老人小孩甚至孕期嘴馋想吃点红烧口味的也能放心吃。拿它做红烧肉、红烧鱼、炖牛肉、炖羊肉，一包全部搞定。"),
       ("S2", "平时去超市买这么一包，少说也要七八块。今天在我们这里，点击左下角，九块九直接到手五包。还没完，现在拼手速下单的，我再自掏")],
      ["Medium shot: S2 stands in the clean kitchen holding the red pouch up in both hands at "
       "chest height, smiling straight down the lens. The washed inner pot sits on the counter "
       "beside her.",
       # ★ 首帧锚定镜（anchored=True）：袋面印刷交给关键帧，这里不再写 blank /
       #   No lettering（那会与首帧里已印刷的袋面直接矛盾）
       "Insert close-up filling the frame: the red pouch held square to camera, its printed front "
       "panel catching the light, the ivory header band across the top and the printed serving "
       "photograph across the bottom third.",
       "Medium close-up: S2 speaks to camera with one hand flat over her chest and the other "
       "holding the pouch at shoulder height, then sets it down on the counter."],
      "Kitchen room tone, apron fabric, a foil pouch crinkling in the hand. No speech, no voices.",
      "Bright confident cue, steady tempo.",
      anchored=True),

    _shot(19, "shot19_price_close", "中景 (MS) + 特写", "S2 + SP", "食堂后厨 · 白天",
      [("S2", "腰包多送你两包。九块九整整七包，给你包邮到家，折算下来一块多钱就能解决一顿大餐的调味。告别满身油烟。")],
      ["Insert close-up: a white plate of finished braised ribs, deep-red glossy sauce pooling at "
       "the base, chopped scallion scattered on top, steam still rising across the lens.",
       "Medium shot of the stainless counter: six identical red pouches laid out in a neat "
       "overlapping spread while S2's open palm sweeps across them left to right.",
       "Medium close-up: S2 faces the lens, chin up, right index finger raised beside her shoulder, "
       "hand steady, a clean closing pitch. The kitchen behind her is bright and empty."],
      "Kitchen room tone, foil pouches sliding across steel, a light hand tap on the counter. "
      "No speech, no voices.",
      "Drive forward, one strong final phrase."),

    _shot(20, "shot20_conscience_close", "中景 (MS) + 特写", "S1 + S2", "食堂后厨 · 白天",
      [("S1", "今天你先用一份饭救了一个老人，又用一道菜证明了手艺。一个人能不能留下，不只看简历。"),
       ("S1", "家人们，你们说说，我一个董事长坐轮椅摔在后门测试员工，是不是太现实了？可做食品的人，手艺可以慢慢练，产品可以慢慢学，良心不能没有。")],
      ["Wide shot of the clean kitchen: the counter wiped down, the rice cooker back on its shelf, "
       "the finished plate of ribs in the centre. Bright, orderly, quiet.",
       "S5 pushes S1's wheelchair into the kitchen and stops beside the counter. S2, back in the "
       "blue shirt with her hands folded in front of her, stands straight and looks at him. S1 "
       "looks up at her, then turns his chair to face the camera position.",
       "Close-up on S1's face: silver hair, deep lines, steady eyes. He speaks straight down the "
       "lens, unhurried and level, and holds the look to the last frame."],
      "Kitchen room tone, castors rolling on tile then stopping, quiet air. No speech, no voices.",
      "Strings resolve with the piano into one warm closing chord."),
]

assert len(SHOTS) == 20, len(SHOTS)
