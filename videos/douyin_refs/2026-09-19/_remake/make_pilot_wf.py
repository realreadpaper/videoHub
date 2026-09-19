#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成试拍 4 镜的 ComfyUI API 工作流 + 便于人工审阅的 prompt 文本。

底盘 = 服务器已验证的 768x1344 一步直出模板：
  ref2va(Singularity int8) + turbo_v4_step600_ema LoRA + 4 步
  + dual_clock_euler / native_flow + shift_video 12 / shift_audio 3
  + ck-attention（启动参数里）+ 无 TeaCache（2026-09-19 用户决定）

镜长统一 107 帧 = 4.458s（17n+5 @24fps）。
prompt 四条硬标准：零 <d> 标签 / 微表情≥3 / 方位锚点 / 末段时间戳==scene_duration_seconds。
★ 4 镜都带台词干声，音景段一律写 "Human speech only as carried by the supplied
  reference audio"（写死 No speech 会让口型和音轨对不上）。
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "wf")
TXTDIR = os.path.join(HERE, "wf_prompt")

DUR = 4.458                      # 107 / 24 == 4.458333
FRAMES = 107
TAIL_TS = "[00:03.100 - 00:04.458]"
STEPS = 8                        # 服务器现行实验口径（wf_S8，对照 wf_S12）；旧模板的 4 步已弃

NO_GREASE = (
    "true-to-life East Asian skin with visible pores, fine lines and a matte finish, "
    "neutral white balance, muted naturalistic colour, gentle filmic contrast with a soft "
    "highlight roll-off. No oily sheen and no glossy specular highlights on any face, no "
    "beauty-filter smoothing, no airbrushing, no waxy or plastic skin, no HDR glow, no bloom, "
    "no over-sharpening, no over-saturated colour, no orange or teal colour cast, no heavy "
    "vignette, no digital gloss or plastic AI sheen. "
)

NO_TEXT = (
    "Absolutely no subtitles, no captions, no burned-in titles, no text banner or bar across the "
    "frame, no lower-third, no on-screen text, no watermark, no logo overlay, no timestamp, no UI "
    "overlay, no floating lettering of any script, no arrow stickers or annotation graphics, no "
    "coloured highlight boxes or callout marks anywhere in the frame. Any sign, poster, notice, "
    "menu board or printed surface other than what is explicitly described above must render as "
    "illegible abstract marks. "
)

POUCH = (
    "<Product identity reference: <Picture 1> is the product (P), a small stand-up retort sauce "
    "pouch that must stay the exact same product in every second of this shot; the printed artwork "
    "must follow the reference picture precisely: a deep crimson-red pouch with a soft satin sheen, "
    "a white rectangular panel at the top right bearing the brand logo in red, the insurer mark "
    "PICC with small Chinese characters and fine print beneath it, one vertical column of six large "
    "white Chinese characters 鲍汁红烧酱料 running down the upper left with a thin vertical line of "
    "small Latin letters beside it, a golden oval badge at the middle left printed in red with the "
    "digit 0 above the two characters 蔗糖, and a cream-coloured rounded panel at the middle right "
    "headed by the two large brown characters 鲍汁 and listing exactly five small red-character "
    "dish names, each appearing exactly once: 红烧排骨, 红烧猪蹄, 红烧牛羊肉, 红烧鱼, 红烧肉; "
    "across the entire lower half a rich appetising photograph of a glossy braised fish in bright "
    "red-brown sauce with scattered chopped scallions, a small white price label 建议零售价 8元 at "
    "the lower left and a white net-weight band 净含量:80克 near the bottom edge. Every character, "
    "digit and the logo on the pouch always face the camera and read in the correct direction and "
    "upright orientation - never mirrored, never reversed, never upside down, never rotated, even "
    "while the pouch is tilted or squeezed; the artwork keeps this layout, these colours and these "
    "proportions unchanged; the pouch is <Subject P> (P)>\n"
)

SPEECH = "Human speech only as carried by the supplied reference audio."

# ==================================================== 1. 剧情镜 · 后门对峙（2 人 · 高低分层）
P_STOMP = """integrated_multimodal_description:
<Face identity reference: <Picture 1> is <Subject S1>, the young man who speaks in this shot; keep his face, hair, age and clothing exactly as in the reference picture. <Subject S1> is a lean East Asian man in his early thirties, short black hair combed flat, a narrow face with small dark eyes, wearing an inexpensive charcoal-grey suit jacket over a light blue shirt with the top button undone and no tie, dark trousers and scuffed black leather shoes. <Subject S2>, the man on the ground, is a heavyset East Asian man in his sixties: thinning grey-black hair, a broad weathered face with deep nasolabial folds and heavy stubble, wearing a faded navy-blue quilted work jacket over a grey knit sweater and dark trousers; he sits on the wet concrete with his back half against a low kerb, one hand braced flat on the ground, the backs of both hands smeared with grey dust. The two men never touch, are never arranged on the same plane and never both face the camera: S1 stays upright on his feet in the midground and S2 stays low on the ground in the foreground for the whole shot.>

<Scene reference - this entire shot takes place in: the narrow service alley behind an office building in flat overcast daylight. A bare grey concrete wall runs along the right of frame with a closed steel service door set into it, a faded yellow-black hazard stripe painted along the base of the wall, a low concrete kerb step, a dented galvanised bucket and a folded aluminium wheelchair leaning against the wall further back, a rusted drain grating at the lower left of frame. Completely bare walls - no signage, no lettering, no posters, no notices, no painted numbers>

<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, ARRI Alexa look, 35 mm spherical lens, camera at chest height with one continuous slow move as described below, shallow depth of field, fine film grain, photorealistic live-action footage, soft flat overcast daylight entering from the upper left of frame, no direct sun, cool ambient fill in the shaded alley, }NG{

[00:00.000 - 00:01.500] Wide-to-medium shot of the alley. <Subject S1> strides in from the left edge of frame and crosses rightwards with the brisk unbroken rhythm of a man late for something: his gaze stays fixed ahead and slightly down, his jaw is set, his eyebrows are drawn together into a small impatient knot, and one hand flicks his jacket cuff straight as he walks. He does not look down. In the near foreground at the lower right of frame, out of focus and cropped by the bottom edge, <Subject S2> sits hunched on the concrete, one dusty hand braced against the ground, chest rising and falling with slow laboured breaths, his head turned up toward the passing figure. The composition is deliberately split and layered: S1 upright, sharp and left-of-centre in the midground, S2 low, soft and blurred in the foreground at the lower right. The camera slides slowly rightwards, keeping S1 in the left third of frame.

[00:01.500 - 00:03.100] The camera continues its slow dolly-in, closing about ten per cent on <Subject S1> while tilting down a few degrees so that both men share the frame: S1 standing in the midground on the left, his torso angled three-quarters toward camera but his chin turned down toward the lower right; <Subject S2> sitting on the ground in the right foreground, neck extended, looking up at S1 from below, mouth slightly open, one shallow breath of steam leaving his lips in the cold air. The two men are separated by height and by depth and are never level with one another. S1 stops on his back foot, his fingers curl and uncurl once at his side, his nostrils flare, and he gives one short dismissive click of the tongue; his eyes flick down to the man and then away, and the corner of his mouth tightens.

[00:03.100 - 00:04.458] Closer medium-close shot on S1, who now fills the left two thirds of frame, seen slightly from below. He turns his head down and to the right to address the man on the ground, speaking with a flat contemptuous calm - the lips, jaw and throat move exactly with the supplied reference audio. His expression travels from tight irritation into open disdain: the corners of his mouth pull down, one eyebrow lifts, his eyes narrow and rake once up and down over S2 before he looks away. <Subject S2> stays low in the blurred right foreground, only the back of his grey head and one dusty hand inside frame, absolutely still. In the background the concrete wall and the closed steel door hold the frame behind S1. }NG{

overall_soundscape:
An empty concrete service alley in the afternoon: a faint distant traffic hum beyond the building, the hollow ring of a loose drain cover, the dry scuff of a leather sole on concrete, cloth rustling, one short nasal exhalation. }SP{

non_diegetic_music:
One low sustained string note, cold and thin, almost inaudible, holding flat under the whole shot.

strict_output_constraints: The only permitted text anywhere in frame is described above; everything else must be illegible. }NT{"""

# ==================================================== 2. 产品镜 · 撕包倒入（包装还原）
P_TEAROPEN = """integrated_multimodal_description:
}PK{

<Scene reference - this entire shot takes place in: the staff kitchen of an office canteen in the middle of the day. A brushed stainless-steel prep counter runs across the lower frame with faint long-use scratches, a small white rice cooker with its lid open sits centre frame, a glass bottle of cooking oil and a steel colander stand blurred behind it, plain off-white tiled walls and a blurred brushed-steel extractor hood in the background. Clean, everyday, functional - no clutter, no wall clock, no posters. Completely bare walls - no signage, no lettering, no notices, no printed material anywhere except the pouch>

<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, ARRI Alexa look, 85 mm macro lens, locked-off camera looking slightly down onto the counter, shallow depth of field with the pouch face held sharp and the background falling softly out of focus, fine film grain, photorealistic live-action footage, soft cool daylight from the left of frame mixed with a warm overhead kitchen strip light, clean neutral whites, specular glints only on the wet steel and the sauce. }NG{

[00:00.000 - 00:01.500] Macro shot on the stainless counter beside the open rice cooker. A pair of adult East Asian women's hands enters from the right of frame and sets the sauce pouch (<Subject P>) down upright on the steel, then turns it so that its printed face is square to the camera and fully sharp; the pouch occupies the centre of frame and reads clean and legible, the crimson-red artwork bright under the kitchen light. The fingers are bare, clean and unhurried, moving with the practised ease of someone who cooks every day. No face and no other person enters the frame - only the hands and the pouch. The camera holds absolutely still.

[00:01.500 - 00:03.100] Without cutting, the camera pushes in a few centimetres. The same hands pinch the top edge of the pouch between both thumbs and forefingers and tear the seam open in one short decisive pull; the torn mouth of the pouch opens a little and a thin breath of steam and spice escapes and drifts up past the lens. The pouch stays essentially upright through the tear - it is never tilted more than about thirty degrees and its printed face stays turned to the camera and stays legible throughout; the artwork never flips, never mirrors and never turns away. The fingers shift their grip to the base of the pouch and the forearm tightens.

[00:03.100 - 00:04.458] Still in one continuous take, the hands lift the opened pouch over the open rice cooker and tip it gently, no more than about thirty-five degrees from upright, letting a slow thick ribbon of glossy red-brown sauce fall into the pot; the sauce catches the light as it coils and pools over the blanched ribs already sitting in the inner pot. The pouch face is angled across the frame but is still readable and still the right way round. At the end the wrist stops, the last of the sauce hangs and drops, and the hands hold steady above the pot. }NG{

overall_soundscape:
A quiet working kitchen at midday: the low hum of the extractor hood, the crisp crackle of the foil seam tearing, the soft wet sound of thick sauce falling into a pot, the faint tick of the steel counter. }SP{ The voice belongs to an off-screen cook - no face and no mouth is visible anywhere in this shot, so the speech is heard purely as a voice-over over the hands.

non_diegetic_music:
A light warm ukulele-and-handclap bed at low volume, easy and domestic, sitting well under the sound effects.

strict_output_constraints: The only text permitted anywhere in frame is the printed packaging of the sauce pouch itself, which must follow the product reference picture exactly and stay sharp and legible exactly as printed - the packaging artwork, layout, colours, logo panel and characters must match the reference, never redrawn, never garbled, never paraphrased into other characters, never mirrored or reversed. }NT{"""

# ==================================================== 3. 剧情镜 · 餐馆揭穿（3 人同框 · 防糊重点）
P_EXPOSE = """integrated_multimodal_description:
<Face identity reference: <Picture 1> is the scene of this shot and the face of the young woman who speaks in it. Keep her face, hair, age, build and clothing exactly as in the reference picture, and keep the same room, the same table and the same lamp light: <Subject S1>, the young woman who speaks, an expensively groomed East Asian woman in her late twenties, long straight dark hair with a slight wave, sharp eyebrows, glossy pink lips, long pale manicured nails, wearing a cream wool coat over a pale silk blouse. <Subject S2>, the man across the table, is a composed East Asian man in his early forties, short black hair cropped close at the sides, a squared jaw, light two-day stubble, wearing a plain dark grey crew-neck sweater over a collared shirt - deliberately unremarkable clothes. <Subject S3>, the woman who appears at the doorway, is a brisk East Asian woman in her thirties with her hair tied back, wearing a dark tailored blazer and carrying a slim document folder. These three are NEVER arranged in a row, NEVER side by side and NEVER all facing the camera: S1 sits at the left of frame in three-quarter profile turned toward the right, S2 sits across the table facing the left of frame, and S3 stands further back near the right of frame turned between the two. The three sit at three clearly different depths in the room.>

<Scene reference - this entire shot takes place in: the small dining room of a modest neighbourhood eatery in the evening. Two plain melamine-topped tables pushed together with a worn dark timber edge, a bowl of rice and a dish of braised ribs with a little steam rising between them, paper napkins in a steel holder and a glass teapot in the near foreground, warm pendant lamps with pale shades hanging low, plain cream-painted walls, a beaded curtain and a doorway to the street in the background right. Plain and lived-in, not upmarket. Completely bare walls - no menus on the wall, no signage, no lettering, no posters, no notices, no neon>

<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, ARRI Alexa look, 50 mm spherical lens, camera at seated eye level with one continuous move as described below, shallow depth of field, fine film grain, photorealistic live-action footage, warm low pendant light as key from above and slightly right, practical lamp falloff into the room behind, specular glints only on the glazed ceramics and the teapot, clean warm ambience with no colour cast. }NG{

[00:00.000 - 00:01.500] Medium shot, layered composition. <Subject S1> sits at the left of frame in three-quarter profile, her body turned toward the right of frame and her head turned further still, looking past the table toward the doorway behind her; her chin is slightly lifted, one eyebrow arches, and her hand stops mid-air with a soup spoon still in it as she registers what she has just heard. Along the bottom of frame the bowl of rice and the steaming dish of ribs sit soft and out of focus in the near foreground, and in the blurred background at the centre-right <Subject S2> is setting his chopsticks down on the rest. The camera slowly arcs rightwards around the table, holding S1 in the left third.

[00:01.500 - 00:03.100] The camera continues its arc and pulls back slightly, keeping S1 sharp in the left third while the depth of the room opens behind her. <Subject S3> steps into frame at the right, standing well behind the table near the beaded curtain, turned half toward the two of them with the document folder held against her chest, her weight on one hip, looking at S2. <Subject S2> sits in the centre of the background facing the left of frame, unhurried, and lifts his eyes from the table to meet S1's look without any change of posture. The three people occupy three clearly separate depths - S1 sharp in the left midground, S3 soft in the right background, S2 soft in the centre background - and none of them stands beside another. Steam from the dish drifts across the bottom of frame and softens the near edge.

[00:03.100 - 00:04.458] The camera settles back onto a medium-close shot of <Subject S1> on the left of frame, now the dominant figure in the left two thirds. She turns her head from the doorway and levels her eyes across the table toward the centre of frame, speaking with a cool, level, needling calm - the lips, jaw and throat move exactly with the supplied reference audio. Her expression travels from surprise into something harder: the arch of her brow drops, her eyes narrow slightly, one corner of her mouth lifts in a small dry smile and then flattens, and her fingers tap once on the table edge. Behind her, out of focus, S2 and S3 remain still and small in the depth of the room. }NG{

overall_soundscape:
A small neighbourhood eatery in the evening: the low murmur of a room settling, one spoon touching a ceramic bowl, a faint sizzle somewhere off-screen, the soft chime of the beaded curtain as someone steps through it. }SP{

non_diegetic_music:
A sparse, cool piano figure with a low held pad beneath it - quiet, unhurried, slightly wry.

strict_output_constraints: The only permitted text anywhere in frame is described above; everything else must be illegible. }NT{"""

# ==================================================== 4. 产品镜 · 排骨脱骨特写（酱汁质感）
P_TENDER = """integrated_multimodal_description:
<Reference frame: <Picture 1> shows the exact subject, framing, light and colour of this shot - the finished braised pork ribs in the inner pot, glossy deep red-brown sauce, scattered chopped scallion. Reproduce that same food, that same sauce colour, that same pot and that same camera position; nothing else belongs in frame. The sauce is a rich glossy chestnut red-brown, the same family of colour as the product's packaging artwork.>

<Scene reference - this entire shot takes place in: a small home kitchen in the evening, tight on the open inner pot of a white electric rice cooker standing on a pale timber counter. The pot's non-stick interior is a soft warm grey, the ribs sit glistening in their reduced sauce below the rim, a folded cloth and the blurred curve of a ceramic plate sit soft in the background, plain warm-white wall tiles behind. Clean, tidy and domestic. Completely bare walls - no signage, no lettering, no magnets, no packaging, no printed material anywhere in frame>

<Style & frame constraints - apply to the whole shot, every second of it: cinematic 9:16 vertical framing, ARRI Alexa look, 85 mm macro lens on a locked-off camera looking down into the pot at about forty-five degrees, very shallow depth of field, fine film grain, photorealistic live-action footage, warm key light from the upper right falling across the food with soft falloff, gentle steam catching the light from behind, specular glints only on the sauce and the moist meat, clean warm whites with no colour cast apart from the natural warmth of the lamp. }NG{

[00:00.000 - 00:01.500] Macro shot down into the open inner pot. The braised ribs lie in a shallow pool of glossy red-brown sauce, each piece lacquered with a slow-moving sheen; a single thin thread of steam rises past the upper right of frame and curls out of focus. The sauce surface trembles very slightly as the pot settles, and one small bubble breaks at the edge and releases a breath of steam. Nothing else moves. The camera holds absolutely still and the ribs stay the sharpest thing in frame.

[00:01.500 - 00:03.100] A pair of pale wooden chopsticks enters from the top of frame and comes down unhurried onto the largest rib, closing on the meat just above the bone; the pressure is light and the meat gives slightly under the tips, a little sauce welling up around them. The chopsticks lift and turn the piece a quarter turn so the light runs along the fibres of the meat, then settle back onto it and press down again at the joint - the meat begins to part from the bone along a clean seam. The surface of the sauce in the pot rocks gently with the movement.

[00:03.100 - 00:04.458] The chopsticks lift the rib clear of the pot; the meat slides off the bone in one soft, complete movement, hanging from the tips with a short glossy thread of sauce stretching and then breaking back into the pot. The bare bone drops back and rings faintly against the porcelain. The chopsticks turn the freed meat once, showing its lacquered surface and the fibres pulling apart, then hold it steady and low in frame while the steam passes across it. The shot ends on the glistening meat above the pot, steam drifting, the counter warm and still. }NG{

overall_soundscape:
A quiet home kitchen in the evening: a faint low hum from a fridge somewhere off-screen, the soft wet shift of thick sauce in a pot, the small click of a bone touching porcelain, one quiet breath of steam. }SP{ No person is visible in this shot at all - the voice is an off-screen narrator speaking over the food.

non_diegetic_music:
A warm unhurried guitar-and-pad bed at low volume, homely and appetising.

strict_output_constraints: The only permitted text anywhere in frame is described above; everything else must be illegible. There is no packaging and no printed material in this shot at all. }NT{"""

JOBS = [
    # (key, prompt, 参考图, 首帧, 末帧, 干声, 输出前缀, seed, 挂在, 类型)
    ("dy4_u007_stomp", P_STOMP, "dy4_ref/dy4_u007_stomp.jpg",
     "dy4_first/dy4_u007_stomp.jpg", "dy4_last/dy4_u007_stomp.jpg",
     "dy4_voice/dy4_u007_stomp.wav", "dy4_pilot/dy4_u007_stomp", 20260970, 8188, "剧情"),
    ("dy4_u060_tearopen", P_TEAROPEN, "dy4_ref/dy4_u060_tearopen.jpg",
     "dy4_first/dy4_u060_tearopen.jpg", "dy4_last/dy4_u060_tearopen.jpg",
     "dy4_voice/dy4_u060_tearopen.wav", "dy4_pilot/dy4_u060_tearopen", 20260971, 8188, "产品"),
    ("dy5_u055_expose", P_EXPOSE, "dy4_ref/dy5_u055_expose.jpg",
     "dy4_first/dy5_u055_expose.jpg", "dy4_last/dy5_u055_expose.jpg",
     "dy4_voice/dy5_u055_expose.wav", "dy4_pilot/dy5_u055_expose", 20260972, 8189, "剧情"),
    ("dy5_u042_tender", P_TENDER, "dy4_ref/dy5_u042_tender.jpg",
     "dy4_first/dy5_u042_tender.jpg", "dy4_last/dy5_u042_tender.jpg",
     "dy4_voice/dy5_u042_tender.wav", "dy4_pilot/dy5_u042_tender", 20260973, 8189, "产品"),
]


def render(prompt):
    return (prompt.replace("}PK{", POUCH)
                  .replace("}SP{", SPEECH)
                  .replace("}NG{", NO_GREASE)
                  .replace("}NT{", NO_TEXT))


def build(prompt, ref_file, first_file, last_file, voice, out_prefix, seed):
    """结构对齐服务器现行做法（/workspace/dy_key/wf_S8/）：
    Hybrid 任务类型 + ref_images.ref_image_0 + first_frame + last_frame 三张图，
    node 7 必须带 av_latent（缺它会 400: required_input_missing）。"""
    return {
        "1": {"class_type": "UNETLoader", "inputs": {
            "unet_name": "Minimax-h3_Singularity_ref2va_Pruned_v1.3_int8.safetensors",
            "weight_dtype": "default"}},
        "2": {"class_type": "LoraLoaderBypassModelOnly", "inputs": {
            "lora_name": "minimax_h3_turbo_v4_step600_ema_pruned_comfyui.safetensors",
            "strength_model": 1.0, "model": ["1", 0]}},
        "3": {"class_type": "CLIPLoader", "inputs": {
            "clip_name": "minimax_h3/qwen3vl_32b_minimax_h3_int8_convrot.safetensors",
            "type": "minimax", "device": "default"}},
        "4": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_video_vae_fp16.safetensors"}},
        "5": {"class_type": "VAELoader", "inputs": {"vae_name": "minimax_h3_audio_vae_fp32.safetensors"}},
        "6": {"class_type": "MiniMaxH3AudioConditioningT8", "inputs": {
            "prompt": prompt, "width": 768, "height": 1344, "length": ["14", 1],
            "task_type": "Hybrid", "audio_mode": "lock_source", "audio_denoise_strength": 0.0,
            "add_source_as_reference": True, "prompt_primary_audio_ordinal": 1,
            "strict_prompt_tags": True, "ref_image_size": "max",
            "reference_video_policy": "official_2_to_15s", "clip": ["3", 0], "video_vae": ["4", 0],
            "audio_vae": ["5", 0], "drive_audio": ["14", 0],
            "ref_images.ref_image_0": ["300", 0],
            "first_frame": ["302", 0], "last_frame": ["303", 0]}},
        "7": {"class_type": "MiniMaxH3DualClockSamplerT8", "inputs": {
            "steps": STEPS, "shift_video": 12.0, "shift_audio": 3.0,
            "sampler_name": "dual_clock_euler", "scheduler": "native_flow",
            "model": ["2", 0], "av_latent": ["6", 1]}},
        "8": {"class_type": "BasicGuider", "inputs": {"model": ["7", 0], "conditioning": ["6", 0]}},
        "9": {"class_type": "RandomNoise", "inputs": {"noise_seed": seed}},
        "10": {"class_type": "SamplerCustomAdvanced", "inputs": {
            "noise": ["9", 0], "guider": ["8", 0], "sampler": ["7", 1], "sigmas": ["7", 2],
            "latent_image": ["6", 1]}},
        "11": {"class_type": "MiniMaxH3AVDecodeT8", "inputs": {
            "av_latent": ["10", 0], "video_vae": ["4", 0], "audio_vae": ["5", 0]}},
        "12": {"class_type": "MiniMaxH3SafeAVSaveT8Advanced", "inputs": {
            "images": ["15", 0], "audio": ["15", 1], "filename_prefix": out_prefix, "crf": 19}},
        "13": {"class_type": "LoadAudio", "inputs": {"audio": voice}},
        "14": {"class_type": "MiniMaxH3AudioWindowT8", "inputs": {
            "scene_start_seconds": 0.0, "scene_duration_seconds": DUR, "warmup_seconds": 0.0,
            "cooldown_seconds": 0.0, "ensure_minimum_context": True, "audio": ["13", 0]}},
        "15": {"class_type": "MiniMaxH3OutputTrimT8", "inputs": {
            "start_seconds": ["14", 2], "duration_seconds": ["14", 3], "fps": 24,
            "frames": ["11", 0], "audio": ["6", 2]}},
        "300": {"class_type": "LoadImage", "inputs": {"image": ref_file}},
        "302": {"class_type": "LoadImage", "inputs": {"image": first_file}},
        "303": {"class_type": "LoadImage", "inputs": {"image": last_file}},
    }


def check(key, p):
    errs = []
    if "<d>" in p:
        errs.append("含 <d> 标签（会烧字幕）")
    if "strict_output_constraints" not in p:
        errs.append("缺 strict_output_constraints 段")
    if TAIL_TS not in p:
        errs.append("末段时间戳 %s 缺失" % TAIL_TS)
    if "%.3f" % DUR not in TAIL_TS:
        errs.append("末段时间戳与 scene_duration_seconds 不一致")
    for need in ("overall_soundscape", "non_diegetic_music", "<Scene reference", "<Style & frame"):
        if need not in p:
            errs.append("缺 %s 段" % need)
    # 不油腻 / 禁字 是否真的替换进去了（大小写不敏感比较）
    pl = p.lower()
    if "matte finish" not in pl or "oily sheen" not in pl or "beauty-filter" not in pl:
        errs.append("不油腻写法缺失")
    if "no subtitles" not in pl or "no watermark" not in pl:
        errs.append("禁字写法缺失")
    # 方位锚点（多人镜必须有）
    if "right of frame" not in p and "left of frame" not in p:
        errs.append("无方位锚点")
    # 残留下的占位符
    for ph in ("}NG{", "}NT{", "}SP{", "}PK{"):
        if ph in p:
            errs.append("占位符未替换: %s" % ph)
    return errs


def main():
    os.makedirs(OUT, exist_ok=True)
    os.makedirs(TXTDIR, exist_ok=True)
    allok = True
    for key, prompt, ref, first, last, voice, out_prefix, seed, port, kind in JOBS:
        p = render(prompt)
        errs = check(key, p)
        wf = build(p, ref, first, last, voice, out_prefix, seed)
        json.dump(wf, open(os.path.join(OUT, "wf_%s.json" % key), "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        open(os.path.join(TXTDIR, key + ".txt"), "w", encoding="utf-8").write(p)
        flag = "OK " if not errs else "!! "
        print("[%s] %-22s %-4s %5d 字符  → :%d  steps=%d 三图齐=%s" %
              (flag, key, kind, len(p), port, STEPS,
               all([ref, first, last])))
        for e in errs:
            allok = False
            print("      ✗ %s" % e)
    print("\n%s" % ("✅ 4 份工作流全部通过硬标准自检" if allok else "❌ 有未通过项，见上"))
    print("   镜长 %.3fs / %d 帧 | %d 步 | 输出目录 %s" % (DUR, FRAMES, STEPS, OUT))


if __name__ == "__main__":
    main()
