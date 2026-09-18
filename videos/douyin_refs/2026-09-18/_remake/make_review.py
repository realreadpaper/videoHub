#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成「抖音三片 · 一镜关键」复刻样片审查页

输入：out/preview/prev_<key>.mp4（服务器压的小预览）
      out/stills/<key>_NN.jpg（640 宽静帧，2 秒一张）
      ../<视频ID>/keyframes/<原片关键帧>.jpg
产出：审片对照.html
"""
import os
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
PREV = os.path.join(HERE, "out", "preview")
STILLS = os.path.join(HERE, "out", "stills")

SPEC = [
    dict(
        key="dy1_baoen_gate", film="01 被抛弃男孩报恩",
        vid="7661613126736204025", src="frame-280_170s.jpg",
        ts="04:33.9 - 04:40.2", dur="14.750s / 354 帧", cost="641 s（冷启）",
        line="那您当年把我从后门口接进来，现在就换我接您走。",
        why="恩情闭环的收口 —— 全片最花钱的一镜：主角把当年的救命之恩原样还回去。"
            "也是这条（赞 1.7 万，另两条的 2.3-2.7 倍）区别于普通打脸剧的地方。",
        good=["构图对上了：两人近身対峙、小周右手搭在老赵肩上、夜灯在下压出暖光",
              "小周「笑中含泪」做出来了：12 秒那帧眼睑里有水光，笑意没散",
              "老赵的白色立领厨师服 + 米色围裙还原到（原片是这个造型）",
              "零字幕：原片在这镜有烧死的黄字字幕 + 红色箭头 + 底部水印，复刻帧一条都没有",
              "皮肤哑光、有纹理，没有塑料反光"],
        bad=["墙面偏软偏「画」了一点，白灰墙的斑驳质感不如原片硬",
              "小周的领带/口袋巾是棕色花纹，原片是深棕斜纹，接近但不算复刻"],
        hi=True,
    ),
    dict(
        key="dy2_jimu_hug", film="02 被误解的继母",
        vid="7686341460064787045", src="frame-283_000s.jpg",
        ts="04:40 - 04:47", dur="14.750s / 354 帧", cost="641 s（冷启）",
        line="谢谢妈妈 / 哎，我的好闺女。",
        why="误解翻案后的情感落点 —— 一声改口，把前 1 分钟的「恶继母」全部兑现成真心。",
        good=["三人方位完全对上：小优背影在左前景、莫姨中景、老王在后景右侧",
              "莫姨是「哭中带笑」的脸：眼角水光、眉间沟、嘴角在上扬，不是木头人",
              "老王的格子法兰绒 + 白 T 还原到了（原片就是这个造型）",
              "零字幕、零水印",
              "暖光下肤色不发黄、不油腻"],
        bad=["★ 尾段（约 13 秒后）前景出现明显拖影/涂抹：小优的背和莫姨的手臂糊成一团剪影",
              "老王头顶出现一块深色伪影",
              "这是三镜里最需要重做的一镜"],
        hi=False,
    ),
    dict(
        key="dy3_picky_table", film="03 女总裁家挑食女儿",
        vid="7664454812574337402", src="frame-195_670s.jpg",
        ts="03:11 - 03:20", dur="14.750s / 354 帧", cost="551 s（热态）",
        line="嗯，好吃好好吃 / 半年了，都没自己动过筷子。",
        why="全片唯一的价值验证点 —— 挑剔的孩子自己动筷子，产品承诺当场被兑现。"
            "这一镜立不住，后面 1 分 20 秒的产品段全是空话。",
        good=["三镜里最好的一镜：构图、机位、表演全部对上原片",
              "女儿背影在下方前景（马尾 + 小发圈 + 淡黄上衣 + 右手拿筷子）",
              "小伙子左侧大笑、楠奶右侧双手捂嘴落泪 —— 表情落差就是这条片子的卖点",
              "水晶吊灯 + 深色木桌 + 暖调的质感出来了",
              "零字幕（原片这里烧着「剧情演绎 无不良引导」水印，复刻没有）",
              "皮肤纹理、老太太的皱纹都在，不糊不油"],
        bad=["楠奶双手是「合十捂嘴」，原片是双手交叠捂嘴，手势略有差别",
              "桌上菜品的细节密度比实拍低（可接受）"],
        hi=True,
    ),
]


def info(p):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", p], capture_output=True, text=True)
    try:
        return "%.2fs" % float(r.stdout.strip())
    except Exception:
        return "?"


def main():
    cards = []
    for sp in SPEC:
        pv = os.path.join(PREV, "prev_%s.mp4" % sp["key"])
        st = sorted(f for f in os.listdir(STILLS) if f.startswith("hi_%s_" % sp["key"]))
        cards.append((sp, os.path.relpath(pv, HERE) if os.path.exists(pv) else None,
                      [os.path.relpath(os.path.join(STILLS, f), HERE) for f in st]))

    h = []
    h.append("""<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8">
<title>抖音三片 · 一镜关键 复刻样片审查</title>
<style>
:root{--ink:#1a1d21;--sub:#5b6470;--line:#e3e6ea;--bg:#f5f6f8;--card:#fff;--hot:#c0392b;--ok:#1e7e34;--warn:#b8860b}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.75 -apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
header{padding:26px 32px 20px;background:#fff;border-bottom:1px solid var(--line)}
h1{margin:0 0 8px;font-size:22px}
.sub{color:var(--sub);font-size:13px;line-height:1.9}
.wrap{padding:22px 32px 70px;max-width:1180px;margin:0 auto}
.hero{background:#fff;border:1px solid var(--line);border-radius:12px;padding:18px 22px;margin-bottom:22px}
.hero h2{margin:0 0 10px;font-size:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}
.kv{background:#fafbfc;border:1px solid var(--line);border-radius:8px;padding:10px 12px;font-size:13px}
.kv b{display:block;color:var(--sub);font-weight:600;font-size:12px;margin-bottom:2px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:20px 22px;margin:0 0 22px}
.card h2{margin:0 0 6px;font-size:18px}
.meta{color:var(--sub);font-size:13px;margin-bottom:10px}
.line{background:#fff8e6;border-left:3px solid #e0a800;padding:8px 12px;border-radius:0 6px 6px 0;margin:10px 0;font-size:14px}
.why{color:#40484f;font-size:14px;background:#f7f9fb;border-radius:8px;padding:10px 12px;margin:10px 0}
.duo{display:flex;gap:16px;flex-wrap:wrap;align-items:flex-start;margin:14px 0}
.col{flex:1 1 300px;min-width:270px}
.col h3{margin:0 0 8px;font-size:13px;color:var(--sub);font-weight:600}
.col img,.col video{width:100%;border-radius:8px;border:1px solid var(--line);display:block;background:#000}
.strip{display:flex;gap:6px;overflow-x:auto;padding:4px 0 8px}
.strip img{width:104px;border-radius:6px;border:1px solid var(--line);flex:0 0 auto}
.sec{margin:14px 0 4px;font-size:13px;font-weight:600}
ul.v{margin:6px 0 0;padding:0;list-style:none}
ul.v li{padding:6px 0 6px 24px;position:relative;font-size:14px;border-top:1px dashed var(--line)}
ul.ok li:before{content:"\\2713";position:absolute;left:2px;color:var(--ok);font-weight:700}
ul.bad li:before{content:"\\26A0";position:absolute;left:2px;color:var(--warn)}
.tag{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;background:#eef1f5;color:#445;margin-right:6px}
.tag.hot{background:#fdecea;color:var(--hot)}
.tag.ok{background:#e8f5e9;color:var(--ok)}
</style></head><body>""")
    h.append("<header><h1>抖音三片 · 一镜关键 —— 复刻样片审查</h1>")
    h.append("<div class='sub'>一步直出 768×1344 · 4 步 Turbo LoRA + TeaCache + ck-attention · "
             "双 A100 分别跑（8188/8189）· 首轮只审画面，台词留待原声锁那一遍</div></header><div class='wrap'>")

    h.append("<div class='hero'><h2>这一轮怎么跑的</h2><div class='grid'>"
             "<div class='kv'><b>分辨率 / 帧率</b>768×1344（9:16）· 24 fps · 14.750 s / 354 帧 · 每镜带 AAC 音轨</div>"
             "<div class='kv'><b>加速链</b>Turbo LoRA v4 step600（4 步）＋ MiniMaxH3TeaCache（阈值 0.2）＋ ck-attention</div>"
             "<div class='kv'><b>双卡调度</b>GPU0 跑「报恩 + 挑食」、GPU1 跑「继母」，同时起步</div>"
             "<div class='kv'><b>实测用时</b>641 s（冷启）+ 641 s（冷启）+ 551 s（热态）＝ 总挂钟 <b>19 分 52 秒</b></div>"
             "<div class='kv'><b>摆位与提示词</b>零 &lt;d&gt; 标签 · strict_output_constraints 段 · 文字道具 illegible</div>"
             "<div class='kv'><b>音轨</b>本轮挂 silent（只审画面）；台词的口型留给下一轮 TTS 原声锁</div>"
             "</div></div>")

    for sp, pv, st in cards:
        h.append("<div class='card'>")
        h.append("<h2>%s <span class='tag'>%s</span><span class='tag'>原片 %s</span>"
                 "<span class='tag hot'>关键镜</span></h2>" % (sp["film"], sp["ts"].split(" ")[0], sp["ts"]))
        h.append("<div class='meta'>原片 ID %s ｜ 生成 %s ｜ 用时 %s</div>" % (sp["vid"], sp["dur"], sp["cost"]))
        h.append("<div class='line'>关键台词：%s</div>" % sp["line"])
        h.append("<div class='why'>为什么挑这一镜 —— %s</div>" % sp["why"])
        h.append("<div class='duo'>")
        h.append("<div class='col'><h3>原片关键帧（带烧死字幕 + 水印）</h3>"
                 "<img src='../%s/keyframes/%s'></div>" % (sp["vid"], sp["src"]))
        if pv:
            h.append("<div class='col'><h3>复刻样片（384 宽预览，可播放）</h3>"
                     "<video src='%s' autoplay loop muted playsinline controls></video></div>" % pv)
        h.append("</div>")
        if st:
            h.append("<div class='sec'>复刻 · 每 2 秒一张（640 宽）</div><div class='strip'>%s</div>"
                     % "".join("<img src='%s' loading='lazy'>" % p for p in st))
        h.append("<div class='sec'>已经过关的</div><ul class='v ok'>%s</ul>"
                 % "".join("<li>%s</li>" % x for x in sp["good"]))
        h.append("<div class='sec'>还要改的</div><ul class='v bad'>%s</ul>"
                 % "".join("<li>%s</li>" % x for x in sp["bad"]))
        h.append("</div>")

    h.append("<div class='card'><h2>请你重点看这四件事</h2><ul class='v bad' style='border-top:none'>"
             "<li>不油腻：皮肤是不是哑光、有毛孔质感？有没有网红滤镜那种塑料光泽 / 过饱和 / HDR 发光？</li>"
             "<li>零字幕：画面里绝对不能有可读的中文、数字、水印（原片这几个位置全是烧死黄字 + 底部水印）</li>"
             "<li>表情到位：三段里情绪有没有真的走（哭→笑、惊讶→欣慰），还是三个人杵着当木头</li>"
             "<li>像不像该片：报恩是克制的悲喜交加、继母是误解释怀、挑食是「终于吃了」的释放 —— 味道对不对</li>"
             "</ul></div>")

    h.append("<div class='card'><h2>这一轮暴露的问题与下一步</h2><ul class='v bad' style='border-top:none'>"
             "<li><b>继母镜尾段拖影</b> —— 最大嫌疑是 TeaCache 在只有 4 步的情况下缓存过狠。"
             "修法两条：把阈值从 0.2 收到 0.05，或者这一镜直接关 TeaCache 走 6 步（慢约 40%）</li>"
             "<li><b>肢体交叠镜天生难</b> —— 拥抱/拉扯这类两人缠在一起的动作，是这个模型的老毛病。"
             "可以改成「先抱住 → 停住 → 只动表情和手」，把大动势挪到别的小节</li>"
             "<li><b>台词口型</b> —— 本轮是静音审片，下一轮接 TTS 干声走原声锁，口型才作数</li>"
             "<li><b>全片展开</b> —— 三片拆解共 373 镜，按这轮口径（热态 551 s/镜、双卡并行）"
             "全量估算：373 ÷ 2 × 551 s ≈ <b>28.5 小时</b>挂钟。建议先只做每片 8-12 镜的「关键叙事骨架」</li>"
             "</ul></div>")

    h.append("</div></body></html>")
    p = os.path.join(HERE, "审片对照.html")
    open(p, "w", encoding="utf-8").write("\n".join(h))
    print("[written]", p)
    for sp, pv, st in cards:
        print("  %-18s preview=%s stills=%d" % (sp["key"], bool(pv), len(st)))


if __name__ == "__main__":
    main()
