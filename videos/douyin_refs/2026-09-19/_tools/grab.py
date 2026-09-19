import asyncio, json, sys
from playwright.async_api import async_playwright

def load_netscape_cookies(path):
    cookies = []
    for line in open(path, encoding='utf-8'):
        line = line.rstrip('\n')
        if not line or line.startswith('#'):
            continue
        parts = line.split('\t')
        if len(parts) != 7:
            continue
        domain, include_sub, path, secure, expiry, name, value = parts
        try:
            exp = int(float(expiry))
        except (ValueError, TypeError):
            exp = -1
        if exp <= 0:
            exp = -1
        elif exp > 1e14:          # WebKit 微秒时间戳 -> unix 秒
            exp = int(exp / 1_000_000) - 11644473600
        elif exp > 4102444800:    # 封顶到 2100 年
            exp = 4102444800
        cookies.append({
            'name': name, 'value': value, 'domain': domain, 'path': path or '/',
            'expires': exp if exp > 0 else -1,
            'secure': secure.upper() == 'TRUE',
        })
    cookies = [c for c in cookies if c['name']]
    return cookies

async def main():
    video_id = sys.argv[1]
    url = f'https://www.douyin.com/video/{video_id}'
    api_dumps = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel='chrome', headless=True, args=['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'])
        ctx = await browser.new_context(
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/153.0.0.0 Safari/537.36',
            viewport={'width': 1280, 'height': 900},
            extra_http_headers={'Accept-Language': 'zh-CN,zh;q=0.9'},
        )
        cookies = [c for c in load_netscape_cookies('/tmp/dy_cookies.txt') if 'douyin' in c['domain']]
        print(f'注入抖音 cookies: {len(cookies)} 个')
        await ctx.add_cookies(cookies)
        page = await ctx.new_page()

        async def on_response(resp):
            u = resp.url
            if ('aweme/detail' in u) or ('aweme/post' in u) or ('/play/' in u and 'mime_type' in u):
                try:
                    body = await resp.text()
                    api_dumps.append({'url': u[:300], 'body': body})
                except Exception:
                    pass
        page.on('response', lambda r: asyncio.create_task(on_response(r)))

        await page.goto(url, wait_until='domcontentloaded', timeout=60000)
        await page.wait_for_timeout(15000)

        videos = await page.evaluate('''() => {
            const out = [];
            document.querySelectorAll('video').forEach(v => {
                out.push({src: v.src || null, currentSrc: v.currentSrc || null});
            });
            return out;
        }''')
        title = await page.title()
        await page.screenshot(path=f'/tmp/dy_shot_{video_id}.png')
        await browser.close()

    print('TITLE:', title)
    print('VIDEO ELEMENTS:', json.dumps(videos, ensure_ascii=False))
    with open(f'/tmp/dy_api_{video_id}.json', 'w') as f:
        json.dump(api_dumps, f, ensure_ascii=False)
    print(f'API responses captured: {len(api_dumps)}')
    for d in api_dumps:
        print('  API:', d['url'][:150])

asyncio.run(main())
