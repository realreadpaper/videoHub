#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三片「叙事骨架」复刻 —— 工作流生成器（原声锁轮，单权重连续流水线）

与 build_key_shots.py 的区别：
  * 权重换原声锁 Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8（一次性切换，全流水线不再换）
  * 音频挂 TTS 干声 voice/<key>.wav（14.750 s，干声前置），口型由干声驱动
  * 每片 8-12 镜，全部取自原片拆解产物（segments.md / shots_dialogue.md），台词不改写剧情

硬标准同 AGENTS.md §零：零 <d> / strict 段 / 微表情 / 方位锚点 / 末段收 14.750
加速：Turbo LoRA 4 步 + ck-attention（无 TeaCache）
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "wf", "_template_abtest.json")
OUT = os.path.join(HERE, "wf_skel")
SCENE_SECONDS = 14.750
UNET_REF2VA = "Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors"
AUDIO_DIR = "dy_voice"

ANTI_GREASY = (
    "true-to-life East Asian skin with visible pores, fine lines and a matte finish, "
    "neutral white balance, muted naturalistic colour, gentle filmic contrast with a soft highlight roll-off. "
    "No oily sheen and no glossy specular highlights on any face, no beauty-filter smoothing, no airbrushing, "
    "no waxy or plastic skin, no HDR glow, no bloom, no over-sharpening, no over-saturated colour, "
    "no orange or teal colour cast, no heavy vignette, no digital gloss or plastic AI sheen. "
)

NO_TEXT_SHORT = (
    "No subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no logo, no timestamp, no UI overlay. "
    "Never imitate or reproduce a subtitle strip or any text overlay from the source material; do not add any "
    "floating or superimposed lettering of any script - Chinese, Latin, digits or symbols - anywhere in the frame. "
    "Any paper, sign, plaque, package or printed surface in frame is blank or shows only soft unreadable blurred marks."
)

NO_TEXT_PROD = (
    "No subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no timestamp, no UI overlay. "
    "Never imitate or reproduce a subtitle strip, arrow sticker or floating lettering from the source material; "
    "the only printed surface in frame is the sauce pouch itself, rendered as part of the scene. "
)

STRICT = (
    "strict_output_constraints: Absolutely no subtitles, no captions, no burned-in text, "
    "no on-screen text of any kind, no watermark, no logo, no timestamp, no UI overlay, no lower-third. "
    "Any sign, plaque, paper, lettering, package or printed surface appearing in frame must render as "
    "completely illegible abstract marks - no readable characters, digits or words in any language whatsoever. "
    "Text-bearing props are set dressing only and must never be legible. "
    "Speech is driven only by the supplied reference audio; do not render any mouth shapes for lines that are not audible."
)

STRICT_PROD = (
    "strict_output_constraints: The only text permitted anywhere in frame is the printed packaging of the sauce "
    "pouch itself, which must follow the product reference picture exactly and stay sharp and legible exactly as "
    "printed - the packaging artwork, layout, colours, logo panel and characters must match the reference, never "
    "redrawn, never garbled, never paraphrased into other characters, never mirrored. "
    "Absolutely no subtitles, no captions, no burned-in titles, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no logo overlay, no timestamp, no UI overlay, no lower-third, "
    "no floating lettering of any script anywhere in the frame. "
    "Any sign, paper or printed surface other than the pouch itself must render as illegible abstract marks. "
    "Speech is driven only by the supplied reference audio; do not render any mouth shapes for lines that are not audible."
)


def style_block(lens, lighting, no_text=NO_TEXT_SHORT):
    return (
        "<Style & frame constraints - apply to the whole shot, every second of it: "
        "cinematic 9:16 vertical framing, ARRI Alexa look, %s, shallow depth of field, fine film grain, "
        "photorealistic live-action footage, %s, %s%s>"
        % (lens, lighting, ANTI_GREASY, no_text)
    )


# 片1 固定人物（取自原片审查结论）
P1_YOUNG = (
    "<Subject 1> (S1), a strikingly handsome 28-year-old East Asian man, clean-shaven with a crisp chiselled "
    "jawline and high cheekbones, bright expressive dark eyes, straight dark eyebrows, short black hair swept up "
    "and back with a close fade at the temples, wearing a well-tailored navy-blue wool suit over a crisp white "
    "shirt, a brown patterned silk tie, a folded brown patterned pocket square and a brown leather strap watch on "
    "his left wrist"
)
P1_YOUNG16 = (
    "<Subject 1> (S1), the same young man at sixteen: a thin, gaunt East Asian teenage boy with the same chiselled "
    "jawline and dark eyes, short untidy black hair, a healing cut on his forehead, wearing a worn grey cotton "
    "T-shirt, dirt-streaked dark trousers and cheap plastic sandals, a small cloth bundle at his feet"
)
P1_OLD = (
    "<Subject 2> (S2), a warm kind-faced 60-year-old East Asian man, thick silver-grey hair swept straight back, "
    "a weathered but gentle face with deep smile creases at the corners of the eyes, salt-and-pepper stubble, "
    "kind tired eyes, wearing a white mandarin-collar chef tunic with the sleeves rolled above the wrist and a "
    "beige canvas apron tied at the waist, dark cotton trousers"
)
POUCH = (
    "<Subject P> (P), a small stand-up deep crimson-red sauce pouch with a white brand panel at the top right, a "
    "vertical column of six large white Chinese characters down the upper left, a golden oval badge at the middle "
    "left and a cream rounded panel at the middle right, and a glossy braised fish photograph across the lower "
    "half; its printed face always reads correctly and is never mirrored"
)

SHOTS = []


def add(key, film, src_ts, line, seed, refs, prompt, strict=STRICT, audio=None):
    SHOTS.append(dict(key=key, film=film, src_ts=src_ts, line=line, seed=seed,
                      refs=refs, prompt=prompt, strict=strict, audio=audio))


# =====================================================================================
# 片1 · 被抛弃男孩报恩（原片 99 镜 → 骨架 10 镜，台词取自 segments.md）
# =====================================================================================
add(
    key="dy1_s01_open_kick", film="01_被抛弃男孩报恩", src_ts="00:05-00:14（段1）",
    line="爸爸不要我了，妈妈也不要我，我明天能去哪儿？", seed=20261001,
    refs=["dy1_s1_xiaozhou.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage boy (S1). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: "
        + P1_YOUNG16 + "; "
        "<Subject 2> (S2), a hard-faced 44-year-old East Asian man, the boy's father, close-cropped greying hair, "
        "a heavy jaw, wearing a dark short-sleeved shirt and dark trousers, standing one step above the boy on the "
        "threshold>\n\n"
        "<Scene reference - this entire shot takes place in: the concrete stairwell doorway of an old walk-up "
        "apartment building in the late afternoon. Grey painted concrete walls, a chipped wooden door standing "
        "half open with warm dim light spilling from inside, worn cement steps, a rusted steel handrail, the "
        "corridor behind falling into shadow. Completely bare walls - no signage, no lettering, no posters>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height",
            "overcast late-afternoon daylight from the left of frame, the doorway light behind the father rimming his "
            "shoulders, the boy's face kept in soft open shade",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) crouches on the lower step at the left of frame, "
        "elbows on his knees, his face turned up and to his right toward the doorway. He speaks, his mouth shaping "
        "the words: his brows are drawn up in the middle, his lower lip trembles once and presses flat, his eyes "
        "shine but stay dry, and his throat works as he swallows between phrases. His fingers pick at a loose "
        "thread on his knee.\n"
        "[00:05.000 - 00:10.000] <Subject 2> (S2) stands in the doorway on the right of frame, a step higher, "
        "looking down; his jaw sets, his eyes narrow, one hand grips the door edge and his knuckles whiten. S1's "
        "gaze drops to the concrete; his shoulders rise and fall once, and he wipes his nose with the back of his "
        "wrist, his expression shifting from pleading to a flat, resigned blankness.\n"
        "[00:10.000 - 00:14.750] S2 steps back and pulls the door half shut; the warm light on S1's face narrows to "
        "a band. S1 lowers his head, his fringe falling forward, and stares at his own sandals; his jaw tightens and "
        "his breathing slows. Dust drifts through the light behind him and the corridor settles into shadow, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Old stairwell ambience: a distant television, footsteps echoing somewhere below, the hum of a fluorescent "
        "tube, the small sound of a door latch. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A low sustained drone with a single mournful erhu line, very quiet.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s02_takein", film="01_被抛弃男孩报恩", src_ts="00:16-00:24（段2）",
    line="先进来，我给你擦擦，疼不疼？忍一下，马上就好。", seed=20261002,
    refs=["dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the older man (S2). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: "
        + P1_YOUNG16 + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the tiny back kitchen of a small neighbourhood "
        "restaurant at night. Tiled walls, a stainless-steel prep table with a small first-aid tin and a bowl of "
        "warm water on it, a single hanging bulb overhead, stacked aluminium pots blurred behind, steam in the far "
        "background. No lettering, no signage, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the prep table",
            "single warm practical bulb overhead as key light, faces lit from above, the tiled kitchen falling into "
            "soft warm shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot across the prep table. <Subject 1> (S1) sits on a low stool on the "
        "left of frame, shoulders hunched, the cut on his forehead clearly visible. <Subject 2> (S2) stands on the "
        "right of frame, leaning in with a cotton swab in his right hand. S2 speaks, his mouth shaping the words "
        "while his brow stays lifted with concern; he dabs gently at the cut, his wrist slowing each time the boy "
        "flinches. S1's eyes squeeze shut for a moment, then open.\n"
        "[00:05.000 - 00:10.000] S2 blows softly on the cut and reaches for a plaster; his mouth curves into a small "
        "reassuring smile that creases the corners of his eyes. S1's jaw unclenches; he risks a glance up at S2's "
        "face, then away, and his shoulders drop a few centimetres.\n"
        "[00:10.000 - 00:14.750] S2 smooths the plaster flat with his thumb and straightens up, wiping his hands on "
        "his apron; he gives the boy one short nod. S1 looks down at his own hands in his lap, blinks hard, and "
        "swallows; the faintest unsure smile appears and fades. The bulb hums and steam drifts behind them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Small night kitchen: the hum of the hanging bulb, water in a metal bowl, a pot simmering far behind, "
        "the soft scuff of a stool. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm sustained cello note with a soft string pad, gentle and sheltering.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s03_firstbowl", film="01_被抛弃男孩报恩", src_ts="00:35-00:42（段3）",
    line="叔，这肉真好吃。", seed=20261003,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage boy (S1), <Picture 2> is the older man (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P1_YOUNG16 + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the same small back kitchen at night, at a narrow "
        "wooden side table set for one. A white porcelain bowl of glossy braised pork in dark red sauce sits on the "
        "table, a pair of plain wooden chopsticks beside it, a small stainless-steel pot blurred behind, warm bulb "
        "light from above. No lettering, no signage, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at the seated boy's eye level",
            "warm practical bulb light from above and slightly behind, the bowl catching a single soft specular glint, "
            "the kitchen behind falling into shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot over the boy's shoulder. <Subject 1> (S1) sits on the left of frame "
        "facing right, lifting a chopstickful of braised pork; he chews, stops, and speaks, his mouth shaping the "
        "words. His eyes widen and his brows lift; a slow astonished smile breaks across his face, his cheeks "
        "rounding. On the right of frame <Subject 2> (S2) stands with both hands resting on the back of a chair, "
        "watching.\n"
        "[00:05.000 - 00:10.000] S1 goes back for a second bite, faster this time, and nods twice as he chews. S2's "
        "mouth opens in a quiet laugh; his eyes crease and his shoulders shake once. S1's shoulders give a small "
        "happy wriggle and he glances up at S2, then back down at the bowl.\n"
        "[00:10.000 - 00:14.750] S1 sets the chopsticks down carefully and sits back, one hand resting on his "
        "stomach, looking quietly satisfied. S2 reaches across and pushes the bowl an inch closer to him, still "
        "smiling, and rests a hand briefly on the back of the boy's shoulder. Steam rises from the bowl, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Small kitchen: the click of chopsticks on porcelain, a swallow, the simmer of a pot, the bulb hum. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A soft warm guitar figure with a gentle string swell underneath, homely.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s04_stay", film="01_被抛弃男孩报恩", src_ts="00:43-00:50（段3）",
    line="叔，我能留在这儿给你帮工吗？洗碗、切菜、擦灶台，什么活都行。", seed=20261004,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage boy (S1), <Picture 2> is the older man (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P1_YOUNG16 + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the same small back kitchen at night, the boy now "
        "standing at the wooden side table. Stacked dirty bowls in a plastic tub at the left of frame, a rack of "
        "hanging ladles blurred behind, warm bulb light overhead. No lettering, no signage, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height",
            "warm practical bulb overhead, soft shadows under the brows, the far kitchen falling into warm darkness",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 1> (S1) stands on the left of frame facing right, his "
        "hands clasped tightly in front of him. He speaks, his mouth shaping the words urgently: his brows lift and "
        "draw together, his words come faster than his breath, and he lists the tasks on his fingers one by one. "
        "<Subject 2> (S2) stands on the right of frame with a tea towel over one shoulder, listening.\n"
        "[00:05.000 - 00:10.000] S1's voice thins on the last phrase; his chin drops and he stares at the floor, "
        "bracing himself, then forces his eyes back up. S2's expression shifts from surprise to something softer; "
        "his brow furrows, he looks at the boy's thin shoulders, and his hand tightens on the tea towel.\n"
        "[00:10.000 - 00:14.750] S2 breathes out through his nose, unhooks the tea towel and holds it out toward "
        "the boy; his mouth settles into a kind, decisive smile. S1's whole face opens - his eyes fill and his mouth "
        "pulls into a trembling grin - and he takes the towel with both hands. The bulb hums overhead, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Small kitchen: the hum of the bulb, a distant motorbike passing outside, the rasp of a tea towel. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A slow warm piano chord with strings entering underneath, tentative then settling.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s05_recipe", film="01_被抛弃男孩报恩", src_ts="00:58-01:08（段5）",
    line="这包酱是咱店里的招牌，红烧肉、红烧排骨、红烧鱼，放这个就不用再加别的调料了。", seed=20261005,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage boy (S1), <Picture 2> is the older man (S2), "
        "<Picture 3> is the product pouch (P). Every subject keeps exactly the same face, hair, age, build and "
        "clothing throughout this shot: "
        + P1_YOUNG16 + "; " + P1_OLD + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the back kitchen of the small neighbourhood restaurant "
        "at night, at the stainless-steel prep table. A row of spice jars blurred behind, a cleaver resting on the "
        "board at the left of frame, warm bulb light from above. No lettering, no signage, no printed material "
        "anywhere except the sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the prep table",
            "warm practical bulb light from above, the red pouch catching a soft warm rim, the kitchen behind "
            "falling into gentle shadow",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 2> (S2) stands on the right of frame facing left, "
        "holding the pouch (P) upright in his left hand at chest height with its printed face turned toward the "
        "camera, never more than a third of the frame. He speaks, his mouth shaping the words while he taps the "
        "pouch twice with two fingers of his right hand; his brow lifts with quiet pride. <Subject 1> (S1) stands "
        "on the left of frame, leaning in to look at the pouch.\n"
        "[00:05.000 - 00:10.000] S2 turns the pouch a few degrees so the boy can see it better, then sets it down "
        "on the steel table between them, steady and upright. S1's eyes follow it down; his mouth parts a little "
        "and he nods, his expression shifting from doubt to focus. S2's mouth curves into a knowing half-smile.\n"
        "[00:10.000 - 00:14.750] S1 reaches out and touches the edge of the pouch with one finger, then looks up at "
        "S2, who nods once and rests a palm flat on the table beside it. Both look down at the pouch; the boy's "
        "shoulders straighten with purpose. The bulb glints off the steel, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Small kitchen: the hum of an extractor fan, the soft tap of a finger on packaging, a distant wok hiss. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A light warm plucked-string figure, unhurried and confident.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy1_s06_farewell", film="01_被抛弃男孩报恩", src_ts="01:14-01:22（段6）",
    line="出去闯吧，酱带上，想家的时候就炖个肉，跟你叔做的一个味儿。", seed=20261006,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2), "
        "<Picture 3> is the product pouch (P). Every subject keeps exactly the same face, hair, age, build and "
        "clothing throughout this shot: "
        + P1_YOUNG + "; " + P1_OLD + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the back doorway of the small restaurant at night, "
        "the young man leaving with a canvas holdall. A worn travel bag at his feet, the dark alley beyond the "
        "doorway, warm bulb light spilling from inside onto the threshold, damp stone underfoot. No lettering, no "
        "signage, no printed material anywhere except the sauce pouch>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height, slightly low angle",
            "warm interior bulb light spilling out through the doorway onto both faces, the alley behind falling "
            "into deep blue shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot at the threshold. <Subject 1> (S1) stands on the left of frame "
        "with a canvas holdall over his shoulder, facing right. <Subject 2> (S2) stands on the right of frame facing "
        "left, holding a small cloth bag out to him in both hands with a pouch (P) visible inside it. S2 speaks, "
        "his mouth shaping the words: his brows lift, his eyes shine, and he blinks hard between phrases, keeping "
        "his chin up.\n"
        "[00:05.000 - 00:10.000] S1 takes the cloth bag with both hands; his throat works and he looks down at it, "
        "then up at S2. S2's mouth firms into a brave, crooked smile; he grips S1's upper arm once, tightly, and "
        "lets go. S1's jaw tightens and his eyes redden.\n"
        "[00:10.000 - 00:14.750] S2 lifts one hand and waves him off toward the alley, then lowers it and turns "
        "back into the warm light. S1 stands one beat longer, swallows, bows his head once and turns away into the "
        "dark. The bulb glows on the empty threshold, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Night doorway: distant traffic, the hum of the bulb, the rasp of canvas, one slow footstep on stone. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm cello line over a low sustained pad, bittersweet and slow.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy1_s07_return", film="01_被抛弃男孩报恩", src_ts="02:06-02:13（段11）",
    line="叔，我回来看你了。", seed=20261007,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P1_YOUNG + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the small neighbourhood restaurant at night, ten years "
        "later. A narrow dining room with a few plain wooden tables, warm yellow ceiling lights, a steamed-up "
        "serving hatch blurred behind, the same whitewashed walls now faintly yellowed. No lettering, no signage, "
        "no posters>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height",
            "warm practical ceiling light, soft shadows, the serving hatch glowing behind the older man",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot from inside the doorway. <Subject 1> (S1) enters from the left of "
        "frame in his navy suit, closing a plain umbrella, and stops just inside. He looks across to the right of "
        "frame where <Subject 2> (S2) is wiping a table with a cloth. S1 speaks, his mouth shaping the words: his "
        "brows lift, his eyes brighten and his mouth opens into a wide open smile that reaches his eyes.\n"
        "[00:05.000 - 00:10.000] S2 freezes mid-wipe, the cloth still in his hand; his head comes up and his eyes "
        "widen, then his whole face crumples into a laugh, the creases at his eyes deepening. He blinks rapidly and "
        "lowers the cloth. S1 stays where he is, his smile trembling at the corners.\n"
        "[00:10.000 - 00:14.750] S2 crosses the few steps between them, wiping his hands on his apron, and stops "
        "an arm's length away; his mouth works once before he settles on a wide, watery smile. S1's shoulders drop "
        "and he breathes out, his eyes shining. The ceiling light hums above them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Small restaurant at night: the hum of a ceiling light, a chair scraping, distant traffic outside, the soft "
        "fold of a cloth. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm piano-and-strings swell, rising and holding, tender.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s08_samesauce", film="01_被抛弃男孩报恩", src_ts="02:22-02:31（段12）",
    line="现在我的店，一直用的就是同一款酱。", seed=20261008,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2), "
        "<Picture 3> is the product pouch (P). Every subject keeps exactly the same face, hair, age, build and "
        "clothing throughout this shot: "
        + P1_YOUNG + "; " + P1_OLD + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the old restaurant kitchen at night, at the same "
        "stainless-steel prep table. A dark cast-iron wok blurred behind, a wooden spoon resting on the board, warm "
        "bulb light overhead, steam drifting. No lettering, no signage, no printed material anywhere except the "
        "sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the prep table",
            "warm bulb light from above, the pouch catching a soft warm rim of light, the kitchen behind falling "
            "into warm shadow",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot across the steel table. <Subject 1> (S1) stands on the left of "
        "frame, his suit jacket off and the sleeves of his white shirt rolled, holding the pouch (P) upright in his "
        "right hand with its printed face turned to the camera, occupying no more than a third of the frame. He "
        "speaks, his mouth shaping the words: his chin lifts slightly, his eyes hold S2's, and his thumb rests "
        "against the pouch's lower edge.\n"
        "[00:05.000 - 00:10.000] S1 sets the pouch down on the steel table between them and slides it a few "
        "centimetres toward S2. On the right of frame S2 looks down at it; his brow furrows, his lips part, then "
        "his expression breaks open into a slow proud smile and he looks back up at the young man.\n"
        "[00:10.000 - 00:14.750] S2 picks the pouch up in both hands and turns it to read the printed face, nodding "
        "once; his eyes glisten and he presses his lips together. S1 watches him, his own smile quiet and steady, "
        "and rests one hand flat on the steel table. Steam drifts past behind them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Night kitchen: the hum of an extractor fan, a low simmer, the soft set-down of packaging on steel. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm sustained string bed with a single piano note on top, steady and full.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy1_s09_offer", film="01_被抛弃男孩报恩", src_ts="04:24-04:33（段22）",
    line="您去了不用干活，就在后厨坐镇就行。", seed=20261009,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P1_YOUNG + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the old restaurant kitchen at night, the stove banked "
        "down. A cold wok on the burner at the left of frame, hanging ladles blurred behind, warm bulb light "
        "overhead cutting through a little steam. No lettering, no signage, no posters>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height, gently pushing in over the shot",
            "warm practical bulb light from above, soft falloff into the shadowed kitchen behind",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 1> (S1) stands on the left of frame facing right, one "
        "hand open in a quiet gesture. He speaks, his mouth shaping the words: his brows lift in earnestness, his "
        "tone gentle, and he leans a few degrees closer. On the right of frame <Subject 2> (S2) stands with both "
        "hands hanging at his sides, his apron still tied on, listening.\n"
        "[00:05.000 - 00:10.000] S1 goes on, his hand turning palm-up, then still. S2's eyes drop to the cold wok, "
        "then to his own hands; his brows draw together and his jaw shifts once, his throat working. He looks up at "
        "S1 and away again, his mouth pressing flat.\n"
        "[00:10.000 - 00:14.750] S2's shoulders rise with a slow breath and settle; he looks at the young man for a "
        "long beat, and something in his face softens - the creases at his eyes deepening - though he does not yet "
        "answer. S1 waits, steady, his hand still open between them. The bulb hums and steam thins behind them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet night kitchen: the hum of the bulb, a cooling metal tick, distant traffic outside. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A low warm cello line with soft strings underneath, patient and unhurried.\n\n"
        + STRICT
    ),
)

add(
    key="dy1_s10_gate", film="01_被抛弃男孩报恩", src_ts="04:33-04:40（段23）",
    line="那您当年把我从后门口接进来，现在就换我接您走。", seed=20261010,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P1_YOUNG + "; " + P1_OLD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the narrow old alley behind the restaurant at night, "
        "at the same back door where they first met. Whitewashed plaster walls with worn patches, a dark wooden "
        "lattice window, one warm sodium street lamp overhead just outside the top of frame, maple leaves catching "
        "the lamp light along the top edge, old stone paving underfoot. The walls and door are completely bare>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height with only a faint hand-held breath",
            "naturalistic night-time lighting with the practical street lamp above them as the key light, faces "
            "exposed for the lamp, the alley falling into soft warm shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot in near profile. <Subject 1> (S1) stands on the right of frame "
        "facing left in three-quarter profile; <Subject 2> (S2) stands on the left of frame facing right, a little "
        "over a metre away. S1 speaks, his mouth shaping the words: his jaw works once as he swallows, the corners "
        "of his mouth tremble, and the words open into something warmer, his lower eyelids filling with held-back "
        "tears that do not yet fall. S2 listens with his head tilted, chin lifted, eyes fixed on S1's face.\n"
        "[00:05.000 - 00:10.000] The camera pushes in a few centimetres. S1 glances up and to his left, then back; "
        "his expression shifts into soft unguarded fondness and a single tear slides down his cheek, catching the "
        "lamp light. S2's brows lift, then draw together as he understands; his lips part and press shut again, and "
        "his shoulders rise with a slow deep breath and settle. S1's right hand comes up to S2's shoulder.\n"
        "[00:10.000 - 00:14.750] S2 lowers his gaze to the ground, blinks twice, and lifts his head again with a "
        "small nod; the tension leaves his shoulders and a faint answering smile appears on his weathered face. S1's "
        "smile steadies and widens, eyes still shining; he gives S2's shoulder one small squeeze and leaves his hand "
        "there. Both hold still and breathe. The lamp glows and the leaves stir overhead, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Night alley ambience: distant traffic hum, crickets, a light breeze in the leaves, the smallest rustle of "
        "cloth. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A single low sustained cello note with a soft warm string swell underneath, restrained and tender.\n\n"
        + STRICT
    ),
)


# =====================================================================================
# 片2 · 被误解的继母（原片 119 镜 → 骨架 10 镜，台词取自 segments.md）
# =====================================================================================
P2_MOYI = (
    "<Subject 1> (S1), an elegant, naturally beautiful 40-year-old East Asian woman, a refined oval face with soft "
    "warm almond eyes and graceful delicate features, shoulder-length dark brown hair parted in the middle and "
    "tucked behind one ear, light natural makeup, a small gold stud in each lobe, wearing a loose white cotton "
    "shirt with the sleeves pushed up to the forearm, a slim watch on her left wrist, light grey trousers"
)
P2_XIAOYOU = (
    "<Subject 2> (S2), a pretty 16-year-old East Asian girl with a sweet youthful face, long black hair gathered "
    "in a high ponytail with a few loose strands at the temples, slender, wearing a plain white long-sleeved top "
    "and dark school trousers"
)
P2_LAOWANG = (
    "<Subject 3> (S3), a handsome warm-faced 42-year-old East Asian man with a full head of short black hair, "
    "friendly bright eyes and an easy gentle smile, wearing an open brown-and-cream plaid flannel shirt over a "
    "plain white T-shirt and dark trousers"
)
P2_CAO = (
    "<Subject 4> (S4), a sturdy 56-year-old East Asian woman, the owner of an old-lane restaurant, short permed "
    "hair with grey at the temples, a broad kind face with deep laugh lines, wearing a dark red zip-up fleece over "
    "a printed blouse and a heavy dark apron tied at the waist"
)

add(
    key="dy2_s01_open", film="02_被误解的继母", src_ts="00:02-00:10（段1）",
    line="小优，地拖完了，把我和你爸的衬衫也洗了，领口记得用手好好搓一搓。", seed=20261011,
    refs=["dy2_s1_moyi.jpg", "dy2_s2_xiaoyou.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1), <Picture 2> is the teenage girl (S2). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P2_MOYI + "; " + P2_XIAOYOU + ">\n\n"
        "<Scene reference - this entire shot takes place in: the living room of a bright modern apartment in the "
        "early morning. Pale oak floor, cream walls, a low sofa blurred at the right of frame, morning light "
        "pouring through a window on the left, a laundry basket and a mop bucket at the left of frame. Completely "
        "bare walls - no framed text, no posters, no legible signage>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height",
            "bright soft morning daylight from the left window, gentle shadows on the floor, a clean neutral interior",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) stands on the right of frame facing left, one hand "
        "on her hip, the other pointing down toward the floor. She speaks, her mouth shaping the words in a cool, "
        "level tone: her chin stays level, her eyes narrow slightly, and she ticks off each task on her fingers. "
        "<Subject 2> (S2) crouches in the left foreground with her back three-quarters to the camera, wringing a "
        "grey mop into the bucket.\n"
        "[00:05.000 - 00:10.000] S2's shoulders stiffen; she pauses with the mop head dripping, then goes on "
        "wringing, harder. S1 watches for a beat, her mouth pressing flat with something unreadable behind her "
        "eyes, then turns and walks a few steps out of frame to the right. S2's head drops lower.\n"
        "[00:10.000 - 00:14.750] S2 sets the mop down, sits back on her heels and pushes her fringe out of her "
        "eyes with the back of her wrist; she lets out one slow breath and looks toward the empty doorway, her "
        "mouth set in a small resentful line. Morning dust drifts in the window light, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Early-morning apartment: water in a bucket, the wring of a mop, distant traffic, a clock ticking. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A quiet neutral piano figure, cool and unhurried.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s02_birthday", film="02_被误解的继母", src_ts="00:12-00:24（段2）",
    line="爸，今天是我十八岁生日，我什么礼物都不要，就想吃小时候咱们总去的老巷子饭店，吃一口曹阿姨做的红烧肉。",
    seed=20261012,
    refs=["dy2_s2_xiaoyou.jpg", "dy2_s3_laowang.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage girl (S1), <Picture 2> is the man (S2). Every subject "
        "keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P2_XIAOYOU + "; " + P2_LAOWANG + ">\n\n"
        "<Scene reference - this entire shot takes place in: the entrance hall of the same bright modern apartment "
        "in the early morning. A pale console table with a set of keys on it, a coat hook on the left wall, the "
        "front door behind the man, a window throwing morning light from the right. Completely bare walls>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height",
            "soft morning daylight from a window on the right, warm skin tones, gentle falloff into the hall behind",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 1> (S1) stands on the left of frame facing right, her "
        "hands clasped in front of her. She speaks, her mouth shaping the words: her brows lift and her eyes "
        "brighten as she says the first phrase, then her gaze drops and her voice thins; she glances up at the man "
        "through her fringe, hopeful and braced at once. <Subject 2> (S2) stands on the right of frame, pulling on "
        "his jacket.\n"
        "[00:05.000 - 00:10.000] S2 stops with one arm in his sleeve; his head comes up sharply and his eyes widen, "
        "then his whole face softens into a guilty, affectionate smile. He steps toward her and stops, one hand "
        "half-raised. S1's mouth pulls to one side, then she looks down and smiles at the floor, abashed.\n"
        "[00:10.000 - 00:14.750] S2 pats his pockets, pulls out a few folded notes and holds them out; his mouth "
        "opens to say something more, then closes. S1 looks at the money, then up at him, and her smile fades into "
        "something quieter and grateful. Morning light moves across the console table, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Morning apartment: keys jingling, a jacket zip, distant traffic, the hum of a refrigerator. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm gentle piano line with soft strings, hopeful then holding.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s03_snatch", film="02_被误解的继母", src_ts="00:26-00:34（段3）",
    line="老王，你干什么？谁允许你给他钱的？", seed=20261013,
    refs=["dy2_s1_moyi.jpg", "dy2_s3_laowang.jpg", "dy2_s2_xiaoyou.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1), <Picture 2> is the man (S2), <Picture 3> is the "
        "teenage girl (S3). Every subject keeps exactly the same face, hair, age, build and clothing throughout "
        "this shot: "
        + P2_MOYI + "; " + P2_LAOWANG + "; " + P2_XIAOYOU + ">\n\n"
        "<Scene reference - this entire shot takes place in: the living room of the bright modern apartment in the "
        "morning, by the low sofa. Cream walls, pale oak floor, a window throwing light from the left, the hallway "
        "doorway behind the man. Completely bare walls>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height",
            "daylight from a window on the left, even soft exposure on all three faces, the hallway behind falling "
            "into gentle shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium three-shot. <Subject 1> (S1) strides in from the left of frame and stops "
        "between the other two, facing right. She speaks, her mouth shaping the words hard and fast: her jaw sets, "
        "her brows draw down, and she snatches the folded notes out of <Subject 2> (S2)'s hand. S2 stands on the "
        "right of frame, his hand still half-open, his smile collapsing. In the background at the left of frame "
        "<Subject 3> (S3) stands with her back to the window, watching.\n"
        "[00:05.000 - 00:10.000] S2's mouth opens, closes; his shoulders lift in a helpless shrug and he glances "
        "past S1 toward the girl. S1 turns her head to follow his look, and for a beat her expression flickers - "
        "the anger still there but her eyes uncertain - before she turns back and presses her lips together.\n"
        "[00:10.000 - 00:14.750] S3 drops her gaze to the floor and turns away toward the hallway, her ponytail "
        "swinging; her shoulders come up. S1 watches her go, her hand tightening on the notes, then looks at S2 "
        "with a flat, closed face. S2 lets his hand fall to his side. The room is still, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Morning apartment: the rustle of banknotes, a sharp footstep, distant traffic, a clock ticking. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A low tense sustained string note, quiet and tight.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s04_callmom", film="02_被误解的继母", src_ts="00:48-01:00（段5）",
    line="喂，妈妈，今天是我生日，你能带我出去吃顿曹阿姨烧的红烧肉吗？", seed=20261014,
    refs=["dy2_s2_xiaoyou.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the teenage girl (S1). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: " + P2_XIAOYOU + ">\n\n"
        "<Scene reference - this entire shot takes place in: the girl's small bedroom in the modern apartment in "
        "the morning. A narrow single bed with a plain pale duvet against the left wall, a small desk with a lamp "
        "under the window, a closed door behind her, soft daylight from the window on the right. No lettering, no "
        "posters, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the room",
            "soft window daylight from the right on her face, the rest of the room a stop or two darker, gentle "
            "falloff",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) sits on the edge of the bed on the left of frame "
        "with a phone held to her right ear, her shoulders hunched and her free hand picking at the duvet. She "
        "speaks, her mouth shaping the words: she starts brightly, her brows lifted, then her voice thins and her "
        "eyes drop to her knees as she listens; her lower lip presses in.\n"
        "[00:05.000 - 00:10.000] Her head comes up sharply and her free hand stills on the duvet; her brows pull "
        "together and her mouth opens once, then shuts. She turns her face toward the window, blinking fast, and "
        "her shoulders rise with a breath she holds.\n"
        "[00:10.000 - 00:14.750] She lowers the phone slowly from her ear and stares at the screen; her face "
        "settles into a flat, dry-eyed disappointment. She sets the phone face-down on the duvet and rests both "
        "hands on her knees, breathing out. Dust drifts in the window light, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet bedroom: the hum of a distant air conditioner, traffic far below, the faint creak of a bed frame. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A single sustained piano note with a soft low pad, lonely and small.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s05_beg", film="02_被误解的继母", src_ts="01:14-01:22（段7）",
    line="曹阿姨，今天孩子十八岁，她就想吃您做的红烧肉，我想跟您学这道菜，亲手给她做一份，求您成全。", seed=20261015,
    refs=["dy2_s1_moyi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1). Every subject keeps exactly the same face, hair, "
        "age, build and clothing throughout this shot: " + P2_MOYI + "; " + P2_CAO + ">\n\n"
        "<Scene reference - this entire shot takes place in: the small front room of an old-lane restaurant in the "
        "late morning. Folding tables with red-and-white checked cloths, a glass counter with stacked bowls, a "
        "handwritten menu board blurred well behind and out of focus, warm daylight from the open street door on "
        "the right. No legible lettering anywhere>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the small table",
            "warm daylight from the open door on the right mixed with a hanging bulb, soft shadows under the table, "
            "the far kitchen glowing behind",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot across a small folding table. <Subject 1> (S1) sits on the left of "
        "frame, both hands flat on the tabletop, leaning slightly forward. She speaks, her mouth shaping the words: "
        "her brows lift and stay lifted, her eyes glisten, and she presses one hand to her chest on the last "
        "phrase. <Subject 2> (S2) stands on the right of frame with her arms folded, listening.\n"
        "[00:05.000 - 00:10.000] S2's arms stay folded; her chin lifts and her mouth sets into a firm, doubtful "
        "line, though her eyes soften a little at the corners. S1's hands slide together on the table and grip "
        "each other; her throat works and her eyes drop to the checked cloth.\n"
        "[00:10.000 - 00:14.750] S1 looks up again, her mouth opening on one more quiet phrase, and her eyes fill "
        "without spilling. S2 uncrosses one arm and rests that hand on the back of a chair, her head tilting a few "
        "degrees; her expression shifts from refusal to considering. Daylight moves across the table, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Old-lane restaurant: a fan whirring, a pot bubbling in the back, chairs scraping, distant street noise. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm sustained string note with a quiet erhu line, earnest.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s06_truth", film="02_被误解的继母", src_ts="01:33-01:41（段9）",
    line="今天她成年了，我就想亲手做一顿她记忆里的味道，哪怕她只肯吃一口，我也心满意足了。", seed=20261016,
    refs=["dy2_s1_moyi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1). Every subject keeps exactly the same face, hair, "
        "age, build and clothing throughout this shot: " + P2_MOYI + "; " + P2_CAO + ">\n\n"
        "<Scene reference - this entire shot takes place in: the same front room of the old-lane restaurant in the "
        "late morning, the two women still at the folding table. Checked cloth, stacked bowls on the counter "
        "behind, a hanging bulb overhead, warm daylight from the door on the right. No legible lettering>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height, a very slow push-in over the shot",
            "warm mixed daylight and bulb light, the woman's face softly lit from the right, the room behind warm "
            "and blurred",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium close two-shot. <Subject 1> (S1) sits on the left of frame, her hands loose "
        "on the table now. She speaks, her mouth shaping the words slowly: her eyes unfocus a little as she "
        "remembers, her brows lift, and a small sad smile appears and fades; she blinks once, slowly.\n"
        "[00:05.000 - 00:10.000] Her voice catches on the last phrase; her chin trembles once and she presses her "
        "lips together, then goes on, her hand turning palm-up on the table in a small open gesture. On the right "
        "of frame <Subject 2> (S2) watches her, arms no longer folded.\n"
        "[00:10.000 - 00:14.750] S2's face changes: her brows lift, her mouth softens, and she reaches across the "
        "table to lay one hand briefly over S1's. S1 looks down at the hand covering hers, her eyes filling, and "
        "lets out a breath that shakes a little. The bulb hums overhead, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Old-lane restaurant: a fan, a distant pot, the creak of a chair, one unsteady breath. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm piano-and-strings swell, gentle and resolving.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s07_cook", film="02_被误解的继母", src_ts="01:53-02:03（段11）",
    line="你看这肉一定要选五花三层的，冷水下锅加料酒焯透，不用加一滴油，也不用炒糖色。", seed=20261017,
    refs=["dy2_s1_moyi.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1), <Picture 2> is the product pouch (P). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P2_MOYI + "; " + P2_CAO + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the cramped back kitchen of the old-lane restaurant "
        "in the late morning. A stainless-steel prep table with a bowl of raw streaky pork, a gas burner with a "
        "stockpot of blanching pork sending up steam, tiled walls, a hanging bulb overhead, pots blurred behind. "
        "No lettering, no signage, no printed material anywhere except the sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the prep table",
            "warm bulb light from above with steam catching it, the tiles behind falling into warm shadow, "
            "specular glints only on the steel and the broth",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot across the steel table. <Subject 2> (S2) stands on the right of "
        "frame, demonstrating with a pair of long chopsticks over the bowl of pork. She speaks, her mouth shaping "
        "the words in a brisk teaching rhythm: her brows lift on each point, she taps the pork with the chopsticks, "
        "and she shakes her head once firmly. <Subject 1> (S1) stands on the left of frame, watching intently.\n"
        "[00:05.000 - 00:10.000] S1 leans in, her eyes following the chopsticks; she copies the gesture in the air "
        "with one finger, then stops, abashed, and looks back up. S2 notices, and her mouth twitches into the "
        "ghost of a smile before she goes on, waving toward the stockpot of blanching pork.\n"
        "[00:10.000 - 00:14.750] S1 turns her attention to the stockpot, steam rising across her face; she lifts "
        "the lid a few centimetres with a cloth and peers in, her brows lifting at what she sees. S2 folds her "
        "arms and watches her pupil, a small satisfied nod. Steam thickens behind them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Busy kitchen: the roar of a gas burner, water boiling, chopsticks tapping a bowl, a fan whirring. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A light warm plucked-string figure, brisk and teaching.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy2_s08_taste", film="02_被误解的继母", src_ts="02:26-02:33（段13）",
    line="哇塞，这肉Q弹入口，肥而不腻，瘦而不柴。", seed=20261018,
    refs=["dy2_s3_laowang.jpg", "dy2_s1_moyi.jpg", "dy2_s2_xiaoyou.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the man (S1), <Picture 2> is the woman (S2), <Picture 3> is the "
        "teenage girl (S3). Every subject keeps exactly the same face, hair, age, build and clothing throughout "
        "this shot: "
        + P2_LAOWANG + "; " + P2_MOYI + "; " + P2_XIAOYOU + ">\n\n"
        "<Scene reference - this entire shot takes place in: the dining room of the bright modern apartment at "
        "dusk. A pale wooden dining table with a white porcelain serving dish of glossy braised pork at the centre, "
        "three bowls of rice, warm ceiling light above, the window behind showing deep blue dusk. No lettering, no "
        "printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at seated eye level across the table",
            "warm ceiling light from above, soft shadows under the table edge, the dish catching one soft glint, "
            "the window behind cool blue",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium three-shot across the table. <Subject 1> (S1) sits centre-left of frame, "
        "lifting a chopstickful of braised pork. He speaks, his mouth shaping the words around the food: his eyes "
        "go wide, his brows shoot up, and he chews with an open delighted laugh, the chopsticks still raised. On "
        "the right of frame <Subject 2> (S2) stands with one hand on the back of a chair; on the left of frame "
        "<Subject 3> (S3) sits with her back three-quarters to camera.\n"
        "[00:05.000 - 00:10.000] S1 reaches for a second piece immediately, shaking his head in disbelief and "
        "laughing again; he taps his chopsticks on the rim of the dish. S2's hands tighten on the chair back and "
        "her mouth opens in a nervous half-smile that grows as she watches him; her eyes flick toward the girl.\n"
        "[00:10.000 - 00:14.750] S3, whose face stays averted, reaches out with her chopsticks for the first time "
        "and takes a piece. S2 sees it and her whole face changes: her eyes fill, her lips press together, and she "
        "looks down at the table, breathing once, deeply. S1 keeps eating, still talking, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Family dining room at dusk: chopsticks on porcelain, a chair creak, the hum of the ceiling light, one "
        "soft laugh. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm contented piano figure with soft strings, brightening.\n\n"
        + STRICT
    ),
)

add(
    key="dy2_s09_price", film="02_被误解的继母", src_ts="02:33-02:40（段13）",
    line="这料包不贵，一包才一块多钱，比买瓶酱油都便宜。", seed=20261019,
    refs=["dy2_s1_moyi.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1), <Picture 2> is the product pouch (P). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P2_MOYI + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the dining room of the bright modern apartment at "
        "dusk, the meal still on the table. A pale wooden table with the serving dish of braised pork, warm ceiling "
        "light above, the kitchen doorway blurred behind. No lettering, no signage, no printed material anywhere "
        "except the sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height, the woman standing centre of frame",
            "warm ceiling light from above, the red pouch catching a soft warm rim, the doorway behind glowing",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) stands centre of frame facing the camera, holding "
        "the pouch (P) upright in her right hand at chest height with its printed face turned toward the lens, "
        "filling no more than a third of the frame. She speaks, her mouth shaping the words lightly: her brows "
        "lift, her shoulders relax, and she tips the pouch a few degrees toward the camera to show it.\n"
        "[00:05.000 - 00:10.000] She sets the pouch down on the table beside the serving dish, still upright, and "
        "lays her palm beside it in a small open gesture. Her mouth curves into a calm, reassuring smile; her eyes "
        "move past the camera as if to someone at the table, and she nods once.\n"
        "[00:10.000 - 00:14.750] She picks the pouch up again and turns it slightly so the printed face catches the "
        "ceiling light, then sets it back down square to the camera and withdraws her hand. Her smile holds, "
        "quiet and certain. The ceiling light glints off the glazed pork, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Family dining room at dusk: the hum of the ceiling light, a chair settling, the soft set-down of "
        "packaging on wood. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A light warm plucked-string figure, easy and reassuring.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy2_s10_hug", film="02_被误解的继母", src_ts="04:40-04:47（拥抱）",
    line="谢谢妈妈。", seed=20261020,
    refs=["dy2_s1_moyi.jpg", "dy2_s2_xiaoyou.jpg", "dy2_s3_laowang.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the woman (S1), <Picture 2> is the teenage girl (S2), "
        "<Picture 3> is the man (S3). Every subject keeps exactly the same face, hair, age, build and clothing "
        "throughout this shot: "
        + P2_MOYI + "; "
        + P2_XIAOYOU.replace("for this entire shot her back is toward the camera and her face is never visible;",
                             "for this entire shot her back is toward the camera and her face is never visible;") + "; "
        + P2_LAOWANG + ">\n\n"
        "<Scene reference - this entire shot takes place in: the living room of a bright modern apartment at night. "
        "Warm white ceiling light with a floor lamp just outside the left of frame, cream painted walls, pale oak "
        "floor, a doorway opening into a lit hallway behind the subjects, soft blurred shelving on the right wall. "
        "Completely bare walls - no framed text, no posters, no legible signage>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height",
            "warm practical interior light from above and to the left, soft shadows, the hallway doorway glowing behind them",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 2> (S2)'s back fills the left foreground, her shoulders "
        "hunched; her head turns just enough to speak, the words carried by the reference audio. <Subject 1> (S1) "
        "stands centre-right with both arms wrapped around her, her right hand cradling the back of S2's head. "
        "S1's eyes are shut, her brow deeply furrowed, her mouth open in a silent broken exhale, her cheeks wet; "
        "her chin presses down into S2's hair. Behind them and to the right of frame <Subject 3> (S3) stands "
        "slightly out of focus, hands loose at his sides.\n"
        "[00:05.000 - 00:10.000] S1's eyes open, glossy; the furrow between her brows softens and her mouth curves "
        "into a small settled smile even as more tears slide down. She strokes the back of S2's head once, slowly, "
        "and her shoulders drop. S3's mouth curves into a moved half-smile; he blinks twice, swallows, glances down "
        "at the floor and back up.\n"
        "[00:10.000 - 00:14.750] S1 eases back just far enough to look at S2's averted face, keeping both hands on "
        "her shoulders; her smile widens and she blinks the tears away, breathing out through her nose. S3 takes "
        "one step closer and stops, tucking both hands into his trouser pockets, watching with a quiet proud smile. "
        "Nobody moves much and the room settles, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet apartment interior: the low hum of an air conditioner, faint fabric friction, one soft unsteady "
        "breath. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm sustained piano-and-strings bed, very soft, resolving slowly.\n\n"
        + STRICT
    ),
)


# =====================================================================================
# 片3 · 女总裁家挑食女儿（原片 155 镜 → 骨架 10 镜，台词取自 segments.md）
# =====================================================================================
P3_MAN = (
    "<Subject 1> (S1), a tall, good-looking 28-year-old East Asian man, clean-shaven with an open honest handsome "
    "face, warm dark eyes, short neat black hair, wearing a crisp white cotton shirt with an open collar and the "
    "sleeves rolled to the forearm, beige trousers"
)
P3_NANNAI = (
    "<Subject 2> (S2), a kind-faced 70-year-old East Asian woman, silver-grey hair pulled back into a small bun, "
    "gentle deep smile lines and crow's feet, slight build, wearing a navy-blue button-front blouse and small pearl "
    "stud earrings"
)
P3_GIRL = (
    "<Subject 3> (S3), an adorable six-year-old East Asian girl with a sweet round face and big bright dark eyes, "
    "long dark brown hair with a centre part, soft face-framing strands and the top half loosely tied back, wearing "
    "a soft pale-yellow puff-sleeve eyelet dress"
)
P3_BOSS = (
    "<Subject 4> (S4), a striking 35-year-old East Asian woman, the girl's mother, sharp intelligent eyes and high "
    "cheekbones, dark hair in a low chignon, wearing a tailored charcoal-grey blazer over a silk blouse and slim "
    "dark trousers, small diamond studs"
)
P3_STEWARD = (
    "<Subject 5> (S5), a pompous 52-year-old East Asian man, the household steward, thinning combed-back hair, a "
    "soft double chin, wearing a black waistcoat over a white shirt with a black bow tie and dark trousers"
)

add(
    key="dy3_s01_open", film="03_女总裁挑食女儿", src_ts="00:03-00:12（段1）",
    line="三个月九个厨师，我女儿瘦了四斤。", seed=20261021,
    refs=["dy3_s3_nver.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the little girl (S3). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: "
        + P3_BOSS + "; " + P3_GIRL + "; " + P3_STEWARD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of a wealthy house in the late "
        "morning. A dark polished wood dining table with a half-eaten plate of plain food, a crystal chandelier "
        "glowing above, pale walls with a blurred framed painting, tall windows throwing soft daylight on the left. "
        "No lettering, no printed material>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height across the table",
            "soft daylight from the left windows mixed with chandelier glow, gentle shadows under the table edge, "
            "the far room falling into warm shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium three-shot across the table. <Subject 1> (S1) stands on the right of frame "
        "with both hands flat on the tabletop, leaning in. She speaks, her mouth shaping the words tightly: her jaw "
        "sets, her brows draw down, and she holds up fingers as she counts, her eyes flashing between the other "
        "two. On the left of frame <Subject 3> (S3) sits small in her chair, her back three-quarters to camera, "
        "pushing her plate a few centimetres away.\n"
        "[00:05.000 - 00:10.000] S3's shoulders rise and she drops her chin, her hands folding in her lap. Behind "
        "them at the right of frame <Subject 2> (S2) stands with his hands clasped, his mouth opening once and "
        "closing again. S1's hand flattens harder on the table; her throat works and she looks down at the child, "
        "her expression flickering from anger to fear.\n"
        "[00:10.000 - 00:14.750] S1 straightens and turns her head toward the steward, her mouth pressing into a "
        "flat line; she lifts one hand and lets it fall. S3 stays slumped, tracing a pattern on the tabletop with "
        "one finger. The chandelier glints above them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet wealthy dining room: the hum of air conditioning, a plate nudged on wood, distant traffic outside. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A low tense sustained string note with a soft piano tick underneath.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s02_meet", film="03_女总裁挑食女儿", src_ts="00:42-00:50（段3）",
    line="你做的饭也这么好吃吗？", seed=20261022,
    refs=["dy3_s3_nver.jpg", "dy3_s1_xiaohuozi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the little girl (S3), <Picture 2> is the young man (S1). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + P3_GIRL + ">\n\n"
        "<Scene reference - this entire shot takes place in: a quiet paved side street beside a large gated house "
        "in the late morning, dappled shade from street trees. A low stone wall on the left, the gate and hedge of "
        "the house blurred behind on the right, warm sunlight filtering through leaves. No lettering, no signage>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at the child's eye level, the camera slightly low",
            "dappled late-morning sunlight through leaves, warm gentle exposure, the background hedge softly blurred",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 2> (S2) crouches on the right of frame at the child's level, "
        "holding out half a plain flat pancake wrapped in paper. <Subject 1> (S1) stands on the left of frame facing "
        "right, clutching something small in both hands. She speaks, her mouth shaping the words: her head tilts, "
        "her brows lift high, and she leans a few degrees toward him, entirely serious.\n"
        "[00:05.000 - 00:10.000] S2's mouth opens in a surprised laugh; his eyes crinkle and he glances down at the "
        "pancake and back at her. He shrugs one shoulder and holds the food out a little closer. S1's eyes follow "
        "the pancake, then lift to his face; she nods once, slowly.\n"
        "[00:10.000 - 00:14.750] S1 takes the pancake with both hands and bites into it, her cheeks rounding as she "
        "chews; her eyes widen and she nods faster. S2 watches her, his smile going soft and a little amazed. "
        "Leaves shift overhead and dappled light moves across them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet street: leaves in a light breeze, birdsong, distant traffic, the soft tear of paper. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A light warm guitar figure with soft strings, curious and warm.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s03_interview", film="03_女总裁挑食女儿", src_ts="01:20-01:28（段5）",
    line="他是救我的哥哥，你们不许欺负他。", seed=20261023,
    refs=["dy3_s3_nver.jpg", "dy3_s1_xiaohuozi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the little girl (S3), <Picture 2> is the young man (S1). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + P3_GIRL + "; " + P3_STEWARD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the wide marble entrance hall of the wealthy house at "
        "midday. Polished cream marble floor, a sweeping staircase blurred behind on the right, tall windows "
        "throwing daylight from the left, a heavy dark console table against the far wall. No lettering, no "
        "signage>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height, the child in the near foreground",
            "bright daylight from tall windows on the left, strong soft falloff into the hall behind, the marble "
            "throwing a gentle bounce",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium three-shot. <Subject 2> (S2) stands small in the left foreground with her "
        "back to the camera, fists clenched at her sides. She speaks, her mouth shaping the words loud and clear: "
        "her head comes up, her shoulders square, and she stamps one small foot on the marble. On the right of "
        "frame <Subject 1> (S1) stands with his hands open at his sides; behind him <Subject 3> (S3) stands with "
        "his chin lifted.\n"
        "[00:05.000 - 00:10.000] S3's mouth opens, then shuts; his eyes drop to the child and his posture deflates "
        "a few degrees. S1 looks down at the girl, his brows lifting, and something in his face breaks open - his "
        "mouth curves and his eyes shine. He lifts one hand a few centimetres toward her, then lets it fall.\n"
        "[00:10.000 - 00:14.750] S3 turns his head away and gestures stiffly toward the hall, his mouth set. S2 "
        "stays where she is, her small shoulders still squared, and turns her head just enough to look back up at "
        "S1. Daylight lies bright across the marble, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Marble entrance hall: a small footfall echoing, the hum of air conditioning, birds outside. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm determined piano figure with strings entering underneath.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s04_fury", film="03_女总裁挑食女儿", src_ts="01:40-01:48（段6）",
    line="你查了九个厨师的身份，我女儿瘦了四斤，还有什么要查的？", seed=20261024,
    refs=[],
    prompt=(
        "integrated_multimodal_description:\n"
        "Every subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_BOSS + "; " + P3_STEWARD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the formal living room of the wealthy house at midday. "
        "A long pale sofa blurred at the right of frame, a low glass coffee table, tall windows on the left "
        "throwing daylight across the cream walls, a large abstract painting out of focus behind. No lettering, no "
        "printed material>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height, a very slow push-in",
            "bright soft window daylight from the left, the woman's face the brightest thing in frame, the far room "
            "falling two stops darker",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 1> (S1) stands on the left of frame facing right, one "
        "hand cutting the air. She speaks, her mouth shaping the words with cold precision: her eyes narrow, her "
        "chin lifts, and each phrase lands sharper than the last; her free hand grips her own elbow. On the right "
        "of frame <Subject 2> (S2) stands with his hands folded in front of him.\n"
        "[00:05.000 - 00:10.000] S2's folded hands tighten; his mouth opens once and closes, and his eyes flick "
        "away to the window. S1 takes one step closer, her heel clicking on the floor; her throat works and for a "
        "beat the mask slips, her brows pulling together in something close to pleading before she flattens it.\n"
        "[00:10.000 - 00:14.750] S2 lowers his head a few degrees and says nothing; his shoulders sink. S1 holds "
        "her ground, her hand still raised, her breathing slowing as she waits. Daylight moves across the wall "
        "behind them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet living room: the hum of air conditioning, one heel on a hard floor, birds outside. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A low sustained string drone with a single high piano note, tense.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s05_asktaste", film="03_女总裁挑食女儿", src_ts="02:05-02:14（段7）",
    line="她平时最不想吃什么？半年了，加到碗里也不动。", seed=20261025,
    refs=["dy3_s1_xiaohuozi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + P3_BOSS + "; " + P3_NANNAI + ">\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of the wealthy house in the "
        "afternoon. The dark polished wood table, a crystal chandelier glowing warm yellow above, the windows "
        "behind showing bright afternoon light, three chairs drawn up. No lettering, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the table",
            "warm chandelier light from above mixed with afternoon window light, soft shadows, gentle specular "
            "glints on the glassware only",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium three-shot across the table. <Subject 1> (S1) stands on the left of frame "
        "with his hands loose at his sides. <Subject 2> (S2) sits on the right of frame, one forearm on the "
        "tabletop, leaning in. She speaks, her mouth shaping the words: her brows lift in urgent hope, her eyes "
        "moving between the young man and the old woman, and her fingers tap once against the wood.\n"
        "[00:05.000 - 00:10.000] On the far right <Subject 3> (S3) sits with a hand pressed to her cheek; her mouth "
        "opens, her eyes go shiny and she presses her lips together, blinking fast. S2's expression shifts from "
        "urgency to a tight, controlled worry; she looks down at the tabletop.\n"
        "[00:10.000 - 00:14.750] S1 lifts his chin and looks from one to the other, his mouth setting into a quiet, "
        "focused line; he gives one small nod as if making up his mind. S2 looks back up at him, her brows raised, "
        "waiting. The chandelier glints above them, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room: the hum of air conditioning, a chair settling, one soft sniffle. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A gentle warm piano figure with soft strings underneath, searching.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s06_mock", film="03_女总裁挑食女儿", src_ts="02:22-02:30（段9）",
    line="就这，倒一包现成的酱，就叫做菜？", seed=20261026,
    refs=["dy3_s1_xiaohuozi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1). Every subject keeps exactly the same face, "
        "hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + P3_STEWARD + ">\n\n"
        "<Scene reference - this entire shot takes place in: the large professional kitchen of the wealthy house in "
        "the afternoon. A long stainless-steel worktop, a row of hanging copper pans blurred behind, a chrome "
        "extractor hood above, bright even kitchen lighting, a stack of white plates at the left. No lettering, no "
        "signage, no printed material>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height across the worktop",
            "even bright practical kitchen lighting, soft shadows under the worktop edge, specular glints only on "
            "the steel and copper",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot across the steel worktop. <Subject 1> (S1) stands on the left of "
        "frame facing right, hands resting on the worktop edge. <Subject 2> (S2) stands on the right of frame with "
        "one hand on his hip. S2 speaks, his mouth shaping the words with heavy sarcasm: his lip curls, his brows "
        "lift in mock surprise, and he flicks one hand dismissively toward the worktop.\n"
        "[00:05.000 - 00:10.000] S1's hands stay flat on the steel; his jaw tightens once and his eyes narrow a "
        "little, then he lets out a slow breath through his nose and his shoulders settle. His mouth curves into a "
        "small, unafraid half-smile. S2's smirk falters a degree at the lack of reaction.\n"
        "[00:10.000 - 00:14.750] S1 lifts one hand from the worktop and turns his palm up in a calm open gesture, "
        "holding the steward's eye. S2's chin lifts and he folds his arms, his mouth pressing flat. Neither looks "
        "away. The extractor fan hums steadily, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Large kitchen: the hum of an extractor fan, a distant tap, the clink of steel. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A quiet staccato low string figure, needling.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s07_cook", film="03_女总裁挑食女儿", src_ts="02:45-02:57（段10）",
    line="不放油，不放盐，连料酒都不搁，一包酱倒进去就等着。", seed=20261027,
    refs=["dy3_s1_xiaohuozi.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the product pouch (P). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the large professional kitchen of the wealthy house in "
        "the afternoon, at the stainless-steel worktop. A heavy stockpot of braised pork on the burner, a wooden "
        "spoon, stacked white plates, bright even kitchen light, steam rising. No lettering, no signage, no printed "
        "material anywhere except the sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height across the worktop",
            "bright even kitchen lighting with steam catching it, the pouch catching a soft warm rim, the pans "
            "behind blurred",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) stands centre-left of frame, holding the pouch (P) "
        "in his right hand above the stockpot with its printed face turned toward the camera, no more than a third "
        "of the frame. He speaks, his mouth shaping the words easily: his brows lift on each item, and he shakes "
        "his head once, smiling, then squeezes the pouch so the thick dark sauce folds out into the pot.\n"
        "[00:05.000 - 00:10.000] He sets the empty pouch down on the steel beside the pot, upright, and picks up the "
        "wooden spoon; he stirs once, slowly, the sauce coating the pork glossy and dark. His expression settles "
        "into calm concentration; he glances up toward the camera and gives one short nod.\n"
        "[00:10.000 - 00:14.750] He sets the spoon across the rim of the pot and crosses his arms, waiting, his "
        "mouth still curved. Steam rises steadily between him and the lens, the pouch standing sharp and upright on "
        "the steel beside his hand, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Large kitchen: a low simmer, the hum of the extractor fan, the soft set-down of packaging on steel. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A light warm plucked-string figure, easy and confident.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy3_s08_eat", film="03_女总裁挑食女儿", src_ts="03:12-03:20（段13）",
    line="嗯，好吃，好好吃。", seed=20261028,
    refs=["dy3_s1_xiaohuozi.jpg", "dy3_s2_nannai.jpg", "dy3_s3_nver.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the elderly woman (S2), "
        "<Picture 3> is the little girl (S3). Every subject keeps exactly the same face, hair, age, build and "
        "clothing throughout this shot: "
        + P3_MAN + "; " + P3_NANNAI + "; "
        + P3_GIRL + " - for this entire shot her back is toward the camera and her face is never visible; she holds "
        "a pair of plain dark chopsticks in her right hand>\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of the wealthy house at night. "
        "A dark polished wood dining table, pale walls, a large crystal chandelier glowing warm yellow above and "
        "slightly behind the subjects, soft warm pools of light, the background blurred into gentle shadow. No "
        "lettering, no signage, no printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at the seated child's eye level",
            "warm interior practical lighting from the chandelier, soft falloff into the background, gentle "
            "specular glints on the glassware only",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot from behind the seated child. <Subject 3> (S3)'s small back fills the "
        "bottom centre foreground, her head bowed; her right hand lifts the chopsticks from the plate to her mouth "
        "and she chews, her jaw working, her shoulders giving a small happy wriggle as she speaks, the words "
        "carried by the reference audio. On the left of frame <Subject 1> (S1) stands behind the table; his smile "
        "starts tight and doubtful and then opens into a broad delighted grin, the corners of his eyes crinkling. "
        "On the right of frame <Subject 2> (S2) stands beside the table with both hands pressed flat over her "
        "mouth, eyes wide and brimming.\n"
        "[00:05.000 - 00:10.000] S3 reaches onto the plate again, faster this time, and nods once. S1's grin "
        "collapses into an astonished silent laugh; his shoulders shake once and he presses one hand flat against "
        "his chest. S2's hands slide down from her mouth to her collarbone; her face crumples for a beat and then "
        "breaks into a wide wet smile; she wipes under one eye with the back of her hand.\n"
        "[00:10.000 - 00:14.750] S3 sets the chopsticks down and sits back a little, relaxed. S1 looks across to S2 "
        "and nods once at her; S2 nods back, still dabbing her eyes, and the two of them settle into quiet still "
        "smiles, watching the child. The chandelier glints above them and the room is warm and calm, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room: the hum of air conditioning, the small click of chopsticks on porcelain, a chair "
        "settling, one soft sniffle. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A gentle warm piano figure with soft strings underneath, small and moving.\n\n"
        + STRICT
    ),
)

add(
    key="dy3_s09_buy", film="03_女总裁挑食女儿", src_ts="04:15-04:25（段17）",
    line="九块九七包，一包才一块多钱，比去菜市场买瓶酱油都便宜。", seed=20261029,
    refs=["dy3_s1_xiaohuozi.jpg", "product_pouch.jpg"],
    strict=STRICT_PROD,
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the young man (S1), <Picture 2> is the product pouch (P). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + POUCH + ">\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of the wealthy house at night, "
        "the meal still on the dark polished wood table. A white porcelain dish of glossy braised pork, the crystal "
        "chandelier glowing warm above, the room behind blurred into warm shadow. No lettering, no signage, no "
        "printed material anywhere except the sauce pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height, the young man centre of frame",
            "warm chandelier light from above, the red pouch catching a soft warm rim of light, the background "
            "falling into gentle warm shadow",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 1> (S1) stands centre of frame facing the camera, holding "
        "the pouch (P) upright in both hands at chest height with its printed face turned squarely to the lens, "
        "filling a little under half the frame height. He speaks, his mouth shaping the words in an easy, friendly "
        "rhythm: his brows lift, his shoulders are loose, and he tips the pouch a few degrees toward the camera as "
        "he makes the comparison.\n"
        "[00:05.000 - 00:10.000] He holds the pouch out a little closer, turning it once so the printed face catches "
        "the chandelier light, then brings it back square. His smile stays open and unforced; his eyes move past "
        "the camera as if to someone at the table, and he nods twice.\n"
        "[00:10.000 - 00:14.750] He lowers the pouch to the tabletop and stands it upright beside the serving dish, "
        "withdrawing both hands; his palm opens once toward it in a simple offering gesture. His expression stays "
        "warm and certain. The chandelier glows behind him, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room: the hum of air conditioning, the soft set-down of packaging on wood, distant traffic. "
        "Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A bright warm plucked-string figure with light percussion, upbeat and plain-spoken.\n\n"
        + STRICT_PROD
    ),
)

add(
    key="dy3_s10_promise", film="03_女总裁挑食女儿", src_ts="04:52-05:00（段19）",
    line="你负责吃饭，我负责做饭，拉钩，一百年不许变。", seed=20261030,
    refs=["dy3_s3_nver.jpg", "dy3_s1_xiaohuozi.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity reference: <Picture 1> is the little girl (S3), <Picture 2> is the young man (S1). Every "
        "subject keeps exactly the same face, hair, age, build and clothing throughout this shot: "
        + P3_MAN + "; " + P3_GIRL + ">\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of the wealthy house at night, "
        "the table cleared. The dark polished wood table empty but for a small glass of water, the crystal "
        "chandelier glowing warm above, the room behind soft and blurred, the windows dark. No lettering, no "
        "printed material>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at the child's height",
            "warm chandelier light from above and slightly behind, soft gentle exposure on both faces, the room "
            "behind falling into warm shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot. <Subject 2> (S2) sits on a chair at the left of frame, legs "
        "swinging slightly, her face turned up toward the right. <Subject 1> (S1) crouches at her level on the "
        "right of frame. S2 speaks, her mouth shaping the words: her brows lift, she holds up one small hand with "
        "the little finger extended, and her eyes shine with a serious, delighted certainty.\n"
        "[00:05.000 - 00:10.000] S1's face breaks into a wide soft smile; he lifts his own hand and hooks his "
        "little finger around hers, his thumb pressing to her thumb. They hold the hook for a beat. S2's mouth "
        "opens in a silent giggle, her shoulders coming up.\n"
        "[00:10.000 - 00:14.750] They rock their linked hands once, then let go; S1 rests his forearms on his knees "
        "and stays crouched there, his smile quiet and steady, while S2 swings her legs and beams up at him. The "
        "chandelier glows warm above them and the room settles, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room at night: the hum of air conditioning, a small laugh, the soft scuff of shoes on the "
        "floor. Human speech only as carried by the supplied reference audio.\n\n"
        "non_diegetic_music:\n"
        "A warm full piano-and-strings swell, bright and closing.\n\n"
        + STRICT
    ),
)


def build():
    os.makedirs(OUT, exist_ok=True)
    tpl = json.load(open(TPL, encoding="utf-8"))
    # 一次性切换到原声锁权重，全流水线不再换参
    tpl["1"]["inputs"]["unet_name"] = UNET_REF2VA
    tpl["7"]["inputs"]["model"] = ["2", 0]          # 无 TeaCache
    tpl["14"]["inputs"]["scene_duration_seconds"] = SCENE_SECONDS

    manifest = []
    for s in SHOTS:
        w = json.loads(json.dumps(tpl))
        w["6"]["inputs"]["prompt"] = s["prompt"]
        w["9"]["inputs"]["noise_seed"] = s["seed"]
        w["12"]["inputs"]["filename_prefix"] = "dy_skel/" + s["key"]
        audio = s.get("audio") or (AUDIO_DIR + "/" + s["key"] + ".wav")
        w["13"]["inputs"]["audio"] = audio
        for i, fn in enumerate(s["refs"]):
            nid = str(300 + i)
            w[nid] = {"class_type": "LoadImage", "inputs": {"image": "dy_refs/" + fn}}
            w["6"]["inputs"]["ref_images.ref_image_%d" % i] = [nid, 0]
        p = os.path.join(OUT, "wf_%s.json" % s["key"])
        json.dump(w, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        manifest.append({k: s[k] for k in ("key", "film", "src_ts", "line", "seed")})
        print("[built] %-24s prompt=%d chars  refs=%d" % (s["key"], len(s["prompt"]), len(s["refs"])))
    json.dump(manifest, open(os.path.join(OUT, "_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[built] %d workflows -> %s" % (len(SHOTS), OUT))


if __name__ == "__main__":
    build()
