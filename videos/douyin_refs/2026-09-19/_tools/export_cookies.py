import sys
sys.path.insert(0, '/Users/jianglong/.workbuddy/binaries/node/versions/22.22.2-3/lib/node_modules/@hypit/hypit/services/yt-dlp/.venv/lib/python3.13/site-packages')
try:
    from yt_dlp.cookies import extract_cookies_from_browser
    jar = extract_cookies_from_browser('chrome', None)
    jar.save('/tmp/dy_cookies.txt', ignore_discard=True, ignore_expires=True)
    print('OK saved')
    dy = [c for c in jar if 'douyin' in c.domain]
    print(f'douyin cookies: {len(dy)}')
    for c in dy[:15]:
        print(f'  {c.domain:25s} {c.name:20s} expires={c.expires}')
except Exception as e:
    print(f'FAIL: {type(e).__name__}: {e}')
