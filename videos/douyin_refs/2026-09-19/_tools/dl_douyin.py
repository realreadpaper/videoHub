#!/usr/bin/env python3
"""抖音直链下载 + 元数据归档（配合 douyin-download 技能的 grab.py 使用）。

前置：先跑 grab.py <aweme_id>，让 /tmp/dy_api_<id>.json 就位。

用法:
  python3 dl_douyin.py <base_dir> <aweme_id> [<aweme_id> ...]

产出:
  <base_dir>/<id>.mp4              原始视频
  <base_dir>/<id>/metadata.json    该条完整元信息
  <base_dir>/metadata.json         按 aweme_id 索引的合并元信息（保留既有条目）
"""
import json
import os
import subprocess
import sys

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36")


def load_detail(vid: str) -> dict:
    dumps = json.load(open(f"/tmp/dy_api_{vid}.json"))
    for d in dumps:
        ad = json.loads(d["body"]).get("aweme_detail")
        if ad:
            return ad
    raise RuntimeError(f"{vid}: API 响应里没有 aweme_detail")


def entry_of(ad: dict, vid: str) -> dict:
    v = ad.get("video", {})
    return {
        "desc": ad.get("desc"),
        "create_time": ad.get("create_time"),
        "duration_ms": v.get("duration"),
        "duration_sec": round((v.get("duration") or 0) / 1000, 3),
        "width": v.get("width"),
        "height": v.get("height"),
        "ratio": v.get("ratio"),
        "music": (ad.get("music") or {}).get("title"),
        "author": (ad.get("author") or {}).get("nickname"),
        "stats": ad.get("statistics"),
        "play_urls": (v.get("play_addr") or {}).get("url_list"),
    }


def download(vid: str, ad: dict, base: str) -> tuple:
    urls = (ad["video"].get("play_addr") or {}).get("url_list") or []
    mp4 = os.path.join(base, f"{vid}.mp4")
    for u in urls:
        if "douyinvod.com" not in u:
            continue
        subprocess.run(["curl", "-sL", "--max-time", "600", "-A", UA,
                        "-H", "Referer: https://www.douyin.com/", u, "-o", mp4])
        if os.path.exists(mp4) and os.path.getsize(mp4) > 1_000_000:
            return True, os.path.getsize(mp4)
    return False, os.path.getsize(mp4) if os.path.exists(mp4) else 0


def main():
    base = sys.argv[1]
    ids = sys.argv[2:]
    os.makedirs(base, exist_ok=True)

    merged_path = os.path.join(base, "metadata.json")
    merged = {}
    if os.path.exists(merged_path):
        old = json.load(open(merged_path))
        if "aweme_id" in old:                      # 旧的扁平单条格式 -> 转成按 id 索引
            merged[old["aweme_id"]] = {k: v for k, v in old.items() if k != "aweme_id"}
        else:
            merged = old

    for vid in ids:
        ad = load_detail(vid)
        e = entry_of(ad, vid)
        ok, size = download(vid, ad, base)
        os.makedirs(os.path.join(base, vid), exist_ok=True)
        json.dump(e, open(os.path.join(base, vid, "metadata.json"), "w"),
                  ensure_ascii=False, indent=2)
        merged[vid] = e
        print(f"{vid}: {'下载成功' if ok else '下载失败'} {size/1048576:.1f} MB | "
              f"{e['duration_sec']}s {e['width']}x{e['height']}")
        print(f"   desc: {e['desc']}")
        print(f"   stats: 赞{e['stats'].get('digg_count')} 评{e['stats'].get('comment_count')} "
              f"藏{e['stats'].get('collect_count')} 转{e['stats'].get('share_count')}")

    json.dump(merged, open(merged_path, "w"), ensure_ascii=False, indent=2)
    print(f"合并元数据 -> {merged_path}（{len(merged)} 条）")


if __name__ == "__main__":
    main()
