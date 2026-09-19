#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三部抖音片「一镜关键」复刻样片 —— 工作流生成器

输入：wf/_template_abtest.json（上个会话已验证过的 768x1344 一步直出模板）
产出：wf_out/wf_<key>.json  （3 个 API 格式工作流，可直接喂 /root/s2/submit_api.py）

硬标准（AGENTS.md §零）：
  S1 零字幕 —— 无 <d> 标签 + 尾部 strict_output_constraints 段 + 文字道具 illegible
  S2 表情到位 —— 微表情 >=3 / 情绪过渡 >=1 / 无完全静态词
  S3 位置逻辑 —— 多人镜每段都有左右方位锚点
  S4 技术对齐 —— 末段结束时间 = 14.750 = AudioWindow 的 scene_duration

加速链：turbo LoRA v4 step600 (4 步) + ck-attention（TeaCache 已禁用，会出拖影）
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TPL = os.path.join(HERE, "wf", "_template_abtest.json")
OUT = os.path.join(HERE, "wf_out")

SCENE_SECONDS = 14.750

# --- 复用：禁字 + 不油腻，两段公共文本 -------------------------------------------------
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

STRICT = (
    "strict_output_constraints: Absolutely no subtitles, no captions, no burned-in text, "
    "no on-screen text of any kind, no watermark, no logo, no timestamp, no UI overlay, no lower-third. "
    "Any sign, plaque, paper, lettering, package or printed surface appearing in frame must render as "
    "completely illegible abstract marks - no readable characters, digits or words in any language whatsoever. "
    "Text-bearing props are set dressing only and must never be legible."
)

# --- 产品镜专用：包装印刷是全画面唯一合法文字，且必须按参考图还原 ---------------------
NO_TEXT_PROD = (
    "No subtitles, no captions, no burned-in titles, no lower-thirds, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no timestamp, no UI overlay. "
    "Never imitate or reproduce a subtitle strip, arrow sticker or floating lettering from the source material; "
    "do not add any superimposed lettering of any script anywhere in the frame - "
    "the only printed surface in frame is the sauce pouch itself, rendered as part of the scene. "
)

STRICT_PROD = (
    "strict_output_constraints: The only text permitted anywhere in frame is the printed packaging of the sauce "
    "pouch itself, which must follow the product reference picture exactly and stay sharp and legible exactly as "
    "printed - the packaging artwork, layout, colours, logo panel and characters must match the reference, never "
    "redrawn, never garbled, never paraphrased into other characters. "
    "Absolutely no subtitles, no captions, no burned-in titles, no text banner or bar across the frame, "
    "no on-screen text, no watermark, no logo overlay, no timestamp, no UI overlay, no lower-third, "
    "no floating lettering of any script anywhere in the frame. "
    "Any sign, paper or printed surface other than the pouch itself must render as illegible abstract marks."
)


def style_block(lens, lighting, no_text=NO_TEXT_SHORT):
    return (
        "<Style & frame constraints - apply to the whole shot, every second of it: "
        "cinematic 9:16 vertical framing, ARRI Alexa look, %s, shallow depth of field, fine film grain, "
        "photorealistic live-action footage, %s, %s%s>"
        % (lens, lighting, ANTI_GREASY, no_text)
    )


PRODUCT_POUCH = (
    "<Product identity reference: <Picture 1> is the product (P), a small stand-up retort sauce pouch that must stay "
    "the exact same product in every second of this shot; the printed artwork must follow the reference picture "
    "precisely: a deep crimson-red pouch with a soft satin sheen, a white rectangular panel at the top right bearing "
    "the brand logo in red, the insurer mark PICC with small Chinese characters and fine print beneath it, one "
    "vertical column of six large white Chinese characters 鲍汁红烧酱料 running down the upper left with a thin "
    "vertical line of small Latin letters beside it, a golden oval badge at the middle left reading 0蔗糖 in red - "
    "one large digit 0 on top and the two characters 蔗糖 side by side beneath it - and a cream-coloured rounded "
    "panel at the middle right headed by the two large brown characters 鲍汁 and listing exactly five small "
    "red-character dish names, each appearing exactly once: 红烧排骨, 红烧猪蹄, 红烧牛羊肉, 红烧鱼, 红烧肉; across "
    "the entire lower half a rich appetising photograph of a glossy braised fish in bright red-brown sauce with "
    "scattered chopped scallions, a small white price label 建议零售价 8元 at the lower left and a white net-weight "
    "band 净含量:80克 near the bottom edge. Every character, digit and the logo on the pouch always faces the camera "
    "and reads in the correct direction and upright orientation - never mirrored, never reversed, never upside down, "
    "even while the pouch is held or moved; the artwork keeps this layout, these colours and these proportions "
    "unchanged; the pouch is <Subject P> (P)>"
)


SHOTS = []

# =====================================================================================
# 1) 被抛弃男孩报恩 · 04:33-04:37「当年您把我从后门口接进来，现在就换我接您走」
# =====================================================================================
SHOTS.append(dict(
    key="dy1_baoen_gate",
    film="01_被抛弃男孩报恩",
    src_ts="04:33.9-04:40.2",
    line="那您当年把我从后门口接进来，现在就换我接您走。",
    seed=20260919,
    refs=["dy1_s1_xiaozhou.jpg", "dy1_s2_laozhao.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity references: <Picture 1> is the young man (S1), <Picture 2> is the older man (S2). "
        "Every subject keeps exactly the same face, hair, age, build and clothing throughout this shot; "
        "each subject's facial identity must match his picture reference: "
        "<Subject 1> (S1), a strikingly handsome 28-year-old East Asian man, clean-shaven with a crisp chiselled "
        "jawline and high cheekbones, bright expressive dark eyes, straight dark eyebrows, short black hair swept up "
        "and back with a close fade at the temples, wearing a well-tailored navy-blue wool suit over a crisp white "
        "shirt, a brown patterned silk tie, a folded brown patterned pocket square and a brown leather strap watch on "
        "his left wrist; "
        "<Subject 2> (S2), a warm kind-faced 60-year-old East Asian man, thick silver-grey hair swept straight back, "
        "a weathered but gentle face with deep smile creases at the corners of the eyes, salt-and-pepper stubble, "
        "kind tired eyes, wearing a white mandarin-collar chef tunic with the sleeves rolled above the wrist and a "
        "beige canvas apron tied at the waist, dark cotton trousers>\n\n"
        "<Scene reference - this entire shot takes place in: a narrow old alley at night, in front of the back door of "
        "a small neighbourhood restaurant. Whitewashed plaster walls with worn patches, a dark wooden lattice window, "
        "one warm sodium street lamp overhead just outside the top of frame, dense maple leaves catching the lamp light "
        "along the top edge of the frame, a deep navy night sky above the roofline, old stone paving underfoot. "
        "The walls, the door and the window are completely bare - no signage, no lettering, no plaques, no posters>\n\n"
        + style_block(
            "35 mm spherical lens, locked-off camera at chest height with only a faint hand-held breath",
            "naturalistic night-time lighting with the practical street lamp above them as the key light, "
            "faces exposed for the lamp, the surrounding alley falling into soft warm shadow",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium two-shot in near profile. <Subject 1> (S1) stands on the right of frame facing "
        "left in three-quarter profile; <Subject 2> (S2) stands on the left of frame facing right, a little over one "
        "metre away. S1's right hand rests on S2's shoulder. S1 begins with a tight, polite smile that does not reach "
        "his eyes, his jaw working once as he swallows; the corners of his mouth tremble, then the smile opens into "
        "something warmer and more determined, and his lower eyelids fill with held-back tears that do not yet fall. "
        "S2 listens with his head tilted a few degrees, chin lifted, eyes fixed on S1's face.\n"
        "[00:05.000 - 00:10.000] The camera pushes in a few centimetres, slowly. S1 glances up and to his left for a "
        "moment, then back to S2; his expression shifts from that determined smile into a soft, unguarded fondness, and "
        "a single tear slides a short way down his cheek, catching the lamp light. S2's brows lift, then draw together "
        "as he understands; his lips part and press shut again; his shoulders rise with a slow deep breath and settle. "
        "S1's thumb moves once against S2's shoulder.\n"
        "[00:10.000 - 00:14.750] S2 lowers his gaze to the ground, blinks twice, and lifts his head again with a small "
        "nod; the tension leaves his shoulders and a faint answering smile appears on his weathered face. S1's smile "
        "steadies and widens, eyes still shining; he gives S2's shoulder one small squeeze and leaves his hand there. "
        "Both hold still and breathe. The lamp above them glows and the leaves along the top of the frame stir in a "
        "light breeze, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Night alley ambience: a faint distant traffic hum, crickets, a light breeze moving the leaves overhead, the "
        "smallest rustle of cloth. No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A single low sustained cello note with a soft warm string swell underneath, restrained and tender.\n\n"
        + STRICT
    ),
))

# =====================================================================================
# 2) 被误解的继母 · 04:40「谢谢妈妈」后的拥抱
# =====================================================================================
SHOTS.append(dict(
    key="dy2_jimu_hug",
    film="02_被误解的继母",
    src_ts="04:40-04:47",
    line="谢谢妈妈 / 哎，我的好闺女。",
    seed=20260920,
    refs=["dy2_s1_moyi.jpg", "dy2_s2_xiaoyou.jpg", "dy2_s3_laowang.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity references: <Picture 1> is the woman (S1), <Picture 2> is the teenage girl (S2), "
        "<Picture 3> is the man (S3). Every subject keeps exactly the same face, hair, age, build and clothing "
        "throughout this shot; each subject's facial identity must match the picture reference: "
        "<Subject 1> (S1), an elegant, naturally beautiful 40-year-old East Asian woman, a refined oval face with soft "
        "warm almond eyes and graceful delicate features, shoulder-length dark brown hair parted in the middle and "
        "tucked behind one ear, light natural makeup, a small gold stud in each lobe, wearing a loose white cotton "
        "shirt with the sleeves pushed up to the forearm, a slim watch on her left wrist, light grey trousers; "
        "<Subject 2> (S2), a pretty 16-year-old East Asian girl with a sweet youthful face, long black hair gathered "
        "in a high ponytail with a few loose strands at the temples, slender, wearing a plain white long-sleeved top - "
        "for this entire shot her back is toward the camera and her face is never visible; "
        "<Subject 3> (S3), a handsome warm-faced 42-year-old East Asian man with a full head of short black hair, "
        "friendly bright eyes and an easy gentle smile, wearing an open brown-and-cream plaid flannel shirt over a "
        "plain white T-shirt and dark trousers>\n\n"
        "<Scene reference - this entire shot takes place in: the living room of a bright modern apartment at night. "
        "Warm white ceiling light with a floor lamp just outside the left of frame, cream painted walls, pale oak floor, "
        "a doorway opening into a lit hallway behind the subjects, soft blurred shelving on the right wall. "
        "Completely bare walls - no framed text, no posters, no legible signage>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at chest height",
            "warm practical interior light from above and to the left, soft shadows, the hallway doorway glowing behind them",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot. <Subject 2> (S2)'s back fills the left foreground, her shoulders hunched. "
        "<Subject 1> (S1) stands centre-right and has both arms wrapped around her, her right hand cradling the back of "
        "S2's head. S1's eyes are shut, her brow deeply furrowed, her mouth open in a silent broken exhale, her cheeks "
        "wet; her chin presses down into S2's hair. Behind them and to the right of frame <Subject 3> (S3) stands "
        "slightly out of focus, hands loose at his sides, watching them.\n"
        "[00:05.000 - 00:10.000] S1's eyes open, glossy; the furrow between her brows softens and her mouth curves into "
        "a small settled smile even as more tears slide down. She strokes the back of S2's head once, slowly, and her "
        "shoulders drop. S3's mouth curves into a moved half-smile; he blinks twice, swallows, glances down at the "
        "floor and back up.\n"
        "[00:10.000 - 00:14.750] S1 eases back just far enough to look at S2's averted face, keeping both hands on her "
        "shoulders; her smile widens and she blinks the tears away, breathing out through her nose. S3 takes one step "
        "closer and stops, tucking both hands into his trouser pockets, watching with a quiet proud smile. Nobody moves "
        "much and the room settles, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet apartment interior: the low hum of an air conditioner, faint fabric friction, one soft unsteady breath. "
        "No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A warm sustained piano-and-strings bed, very soft, resolving slowly.\n\n"
        + STRICT
    ),
))

# =====================================================================================
# 3) 女总裁家挑食女儿 · 03:15「半年了，都没自己动过筷子」
# =====================================================================================
SHOTS.append(dict(
    key="dy3_picky_table",
    film="03_女总裁挑食女儿",
    src_ts="03:11-03:20",
    line="嗯，好吃好好吃 / 半年了，半年了都没自己动过筷子。",
    seed=20260921,
    refs=["dy3_s1_xiaohuozi.jpg", "dy3_s2_nannai.jpg", "dy3_s3_nver.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        "<Face identity references: <Picture 1> is the young man (S1), <Picture 2> is the elderly woman (S2), "
        "<Picture 3> is the little girl (S3). Every subject keeps exactly the same face, hair, age, build and clothing "
        "throughout this shot; each subject's facial identity must match the picture reference: "
        "<Subject 1> (S1), a tall, good-looking 28-year-old East Asian man, clean-shaven with an open honest handsome "
        "face, warm dark eyes, short neat black hair, wearing a crisp white cotton shirt with an open collar and the "
        "sleeves rolled to the forearm, beige trousers; "
        "<Subject 2> (S2), a kind-faced 70-year-old East Asian woman, silver-grey hair pulled back into a small bun, "
        "gentle deep smile lines and crow's feet, slight build, wearing a navy-blue button-front blouse and small pearl "
        "stud earrings; "
        "<Subject 3> (S3), an adorable six-year-old East Asian girl with a sweet round face and big bright dark eyes, "
        "long dark brown hair with a centre part, soft face-framing strands and the top half loosely tied back, wearing "
        "a soft pale-yellow puff-sleeve eyelet dress - for this entire shot her back is toward the camera and her face "
        "is never visible; she holds a pair of plain dark chopsticks in her right hand>\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of a wealthy house at night. A dark "
        "polished wood dining table, pale walls, a large crystal chandelier glowing warm yellow above and slightly "
        "behind the subjects, soft warm pools of light, the background blurred into gentle shadow. No lettering, no "
        "signage, no printed material anywhere>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera at the seated child's eye level",
            "warm interior practical lighting from the chandelier, soft falloff into the background, gentle specular glints on the glassware only",
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Medium shot from behind the seated child. <Subject 3> (S3)'s small back fills the bottom "
        "centre foreground, her head bowed; her right hand lifts the chopsticks from the plate to her mouth and she "
        "chews, her jaw working, her shoulders giving a small happy wriggle. On the left of frame <Subject 1> (S1) "
        "stands behind the table; his smile starts tight and doubtful and then opens into a broad delighted grin, the "
        "corners of his eyes crinkling. On the right of frame <Subject 2> (S2) stands beside the table with both hands "
        "pressed flat over her mouth, eyes wide and brimming, tears spilling over her fingers.\n"
        "[00:05.000 - 00:10.000] S3 reaches onto the plate again, faster this time, and nods once. S1's grin collapses "
        "into an astonished silent laugh; his shoulders shake once and he presses one hand flat against his chest. S2's "
        "hands slide down from her mouth to her collarbone; her face crumples for a beat and then breaks into a wide wet "
        "smile; she wipes under one eye with the back of her hand.\n"
        "[00:10.000 - 00:14.750] S3 sets the chopsticks down and sits back a little, relaxed. S1 looks across to S2 and "
        "nods once at her; S2 nods back, still dabbing her eyes, and the two of them settle into quiet still smiles, "
        "watching the child. The chandelier glints above them and the room is warm and calm, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room: the hum of air conditioning, the small click of chopsticks on porcelain, a chair settling, "
        "one soft sniffle. No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A gentle warm piano figure with soft strings underneath, small and moving.\n\n"
        + STRICT
    ),
))


# =====================================================================================
# 4) 产品镜 A · 继母款正面 hero（原片 02:03.4，袋占 ~75%，全三片唯一正面静置特写）
# =====================================================================================
SHOTS.append(dict(
    key="dy2_prod_hero",
    film="02_被误解的继母",
    src_ts="02:03.4（原片 hero 帧构图）",
    line="就这一包酱（复刻构图，静音审画面）",
    seed=20260922,
    refs=["product_pouch.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        + PRODUCT_POUCH + "\n\n"
        "<Scene reference - this entire shot takes place in: the kitchen counter of a bright modern apartment at "
        "night. A warm-toned polished wood-veneer countertop, a softly blurred cream kitchen with warm under-cabinet "
        "light far behind, one gentle warm key light from above and slightly left of frame. Completely bare "
        "background - no lettering, no packaging other than the pouch, no printed material>\n\n"
        + style_block(
            "85 mm macro lens, locked-off camera at countertop height facing the pouch squarely, head-on",
            "warm practical interior light from above and slightly left, soft single shadow falling to the right of the pouch, "
            "gentle warm falloff into the blurred background",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Close product shot. A pair of elegant slender East Asian women's hands, one with a "
        "thin plain band ring, brings the pouch (<Subject P>) up into frame from below, holding it upright and "
        "squarely facing the camera by its upper sides, fingers resting only on the outer edges so the printed face "
        "is never covered. The pouch settles to a perfect standstill, filling roughly three quarters of the frame "
        "height, razor sharp.\n"
        "[00:05.000 - 00:10.000] The hands lower the pouch the last few centimetres and stand it upright on the "
        "countertop, giving it one tiny adjustment of a degree or two until it faces the lens perfectly; the fingers "
        "release the edges, hover for a breath, then glide down and out of frame. The pouch stands alone, undented, "
        "gusset open, its printed face dead-on to the camera.\n"
        "[00:10.000 - 00:14.750] The pouch stands perfectly still and sharp filling about three quarters of the "
        "frame while the camera creeps forward one slow breath, background falling softer and warmer; a faint wisp "
        "of steam drifts up through the far background light. Nothing touches the pouch; its printed artwork stays "
        "locked and legible to the final frame, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet apartment kitchen: the low hum of a refrigerator, one soft papery settle of the pouch touching down, "
        "a distant clock. No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A soft warm piano note with a gentle sustained pad, intimate and inviting.\n\n"
        + STRICT_PROD
    ),
))

# =====================================================================================
# 5) 产品镜 B · 挑食款手持 hero（原片 03:40.2，袋占 ~55%，烛光餐桌）
# =====================================================================================
SHOTS.append(dict(
    key="dy3_prod_handhero",
    film="03_女总裁挑食女儿",
    src_ts="03:40.2（原片手持 hero 构图）",
    line="不放油不放盐（复刻构图，静音审画面）",
    seed=20260923,
    refs=["product_pouch.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        + PRODUCT_POUCH + "\n\n"
        "<Scene reference - this entire shot takes place in: the formal dining room of a wealthy house at night, "
        "seen from across a dark polished wood dining table. A lit crystal chandelier melts into a warm golden blur "
        "above and behind, two tall white taper candles in glass holders burn softly out of focus at the left and "
        "right edges of the background, a white bone-china plate with a small bloom of dark red-brown sauce sits far "
        "behind on the table, blurred. No lettering, no printed material anywhere except the pouch>\n\n"
        + style_block(
            "50 mm spherical lens, locked-off camera just above tabletop height facing the hands",
            "warm candlelight and chandelier glow from above and behind, the red pouch catching a soft warm rim of light "
            "on its edges, deep gentle shadows in the corners",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Two clean well-kept East Asian men's hands rise into frame from below the table "
        "edge, holding the pouch (<Subject P>) upright between them: both thumbs press flat against the BACK of the "
        "pouch only, and the fingertips curl around the narrow left and right side edges without ever crossing onto "
        "the printed front face; the lower corners of the pouch, including the small white price label at the lower "
        "left, stay completely uncovered. They lift it to just above tabletop height, square "
        "to the lens, and hold it steady; the pouch fills a little over half the frame height, sharp.\n"
        "[00:05.000 - 00:10.000] The hands present the pouch a touch closer to the lens and let it tilt back to "
        "perfectly vertical, a single candle flame glinting once along the pouch's left edge; the fingers stay "
        "absolutely steady, only a small slow breath of movement in the wrists. The printed artwork stays locked on "
        "the camera.\n"
        "[00:10.000 - 00:14.750] The hands rotate the pouch barely ten degrees to catch the chandelier light across "
        "its surface, then turn it back dead-on and settle, holding the pose as the flames behind sway gently and "
        "the background booshimmers; the pouch remains sharp, legible and centred to the final frame, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet dining room: the soft hum of air conditioning, the faint flutter of candle flames, one distant "
        "clink of porcelain. No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A tender warm string swell, small and grateful, resolving softly.\n\n"
        + STRICT_PROD
    ),
))

# =====================================================================================
# 6) 产品镜 C · 报恩款倒酱道具镜（原片 00:28.8 / 02:27.5 首尾呼应，袋永远 ≤30%）
# =====================================================================================
SHOTS.append(dict(
    key="dy1_prod_pour",
    film="01_被抛弃男孩报恩",
    src_ts="00:28.8（原片倒酱特写构图）",
    line="倒酱入碗 · 十年闭环首镜（复刻构图，静音审画面）",
    seed=20260924,
    refs=["product_pouch.jpg"],
    prompt=(
        "integrated_multimodal_description:\n"
        + PRODUCT_POUCH + "\n\n"
        "<Scene reference - this entire shot takes place in: the small back kitchen of an old neighbourhood "
        "restaurant at night. A clean stainless-steel prep counter with soft scratches of long use, a plain white "
        "porcelain bowl sitting centre frame, a single warm hanging bulb above casting a soft pool of light, the "
        "kitchen behind falling into gentle dark shadow with the blurred shapes of stacked bowls and a hanging "
        "strainer. No lettering, no signage, no printed material anywhere except the pouch>\n\n"
        + style_block(
            "85 mm macro lens, locked-off camera looking slightly down at the bowl on the counter",
            "single warm practical bulb overhead as key, rich warm falloff into the shadowed kitchen behind, "
            "specular glints only on the sauce and the steel",
            NO_TEXT_PROD,
        ) + "\n\n"
        "[00:00.000 - 00:05.000] Macro shot of the white porcelain bowl on the steel counter. A weathered older East "
        "Asian man's hand enters from the right of frame carrying the pouch (<Subject P>) perfectly upright and sets "
        "it down on the steel counter beside the bowl, its printed face turned squarely toward the camera and sharp; "
        "the pouch occupies only the upper right corner of frame, never more than a third of the picture, standing "
        "upright and correct - never tilted, never mirrored, every character reading the right way round. The hand "
        "then picks up a wooden spoon from beside the bowl.\n"
        "[00:05.000 - 00:10.000] The spoon dips into the bowl and lifts a thick ribbon of glossy red-brown sauce; "
        "the ribbon stretches, glows in the bulb light and folds slowly back into the bowl, steam curling up past "
        "the upright pouch. The hand stirs the sauce one slow half turn; the surface settles glossy and deep "
        "red-brown with a slow sheen moving across it.\n"
        "[00:10.000 - 00:14.750] The spoon rests against the rim of the bowl. The pouch (<Subject P>) stands "
        "perfectly upright and sharp beside the full bowl of glistening sauce, its printed artwork dead-on to the "
        "camera and never mirrored; steam rises past it and the shot settles on the warm still scene, "
        + ANTI_GREASY + "\n\n"
        "overall_soundscape:\n"
        "Quiet night kitchen: the low hum of a distant refrigerator compressor, the soft thick sound of sauce "
        "falling into the bowl, one spoon click against porcelain. No speech, no voices, no dialogue.\n\n"
        "non_diegetic_music:\n"
        "A single warm cello line, unhurried and homely, with a soft low pad underneath.\n\n"
        + STRICT_PROD
    ),
))


def build():
    os.makedirs(OUT, exist_ok=True)
    tpl = json.load(open(TPL, encoding="utf-8"))

    # TeaCache 已禁用（2026-09-19 用户决定：尾段拖影/涂抹，宁可慢也要干净）
    # 链路恢复为 UNet(1) -> LoRA(2) -> Sampler(7)，加速只靠 Turbo LoRA 4 步 + ck-attention
    tpl["7"]["inputs"]["model"] = ["2", 0]
    # 静音驱动音轨（首轮只审画面，台词留到原声锁那一遍）
    tpl["13"]["inputs"]["audio"] = "silent_15s.wav"
    tpl["14"]["inputs"]["scene_duration_seconds"] = SCENE_SECONDS

    manifest = []
    for s in SHOTS:
        w = json.loads(json.dumps(tpl))
        w["6"]["inputs"]["prompt"] = s["prompt"]
        w["9"]["inputs"]["noise_seed"] = s["seed"]
        w["12"]["inputs"]["filename_prefix"] = "dy_key/" + s["key"]
        # 锁脸参考图：原片裁出的干净人脸 -> LoadImage -> node6."ref_images.ref_image_N"（0 起始）
        for i, fn in enumerate(s.get("refs", [])):
            nid = str(300 + i)
            w[nid] = {"class_type": "LoadImage", "inputs": {"image": "dy_refs/" + fn}}
            w["6"]["inputs"]["ref_images.ref_image_%d" % i] = [nid, 0]
        p = os.path.join(OUT, "wf_%s.json" % s["key"])
        json.dump(w, open(p, "w", encoding="utf-8"), ensure_ascii=False)
        manifest.append({k: s[k] for k in ("key", "film", "src_ts", "line", "seed")})
        print("[built] %s  prompt=%d chars  seed=%d" % (p, len(s["prompt"]), s["seed"]))

    json.dump(manifest, open(os.path.join(OUT, "_manifest.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    print("[built] %d workflows -> %s" % (len(SHOTS), OUT))


if __name__ == "__main__":
    build()
