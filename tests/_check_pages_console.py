# -*- coding: utf-8 -*-
"""全页面控制台巡检（Playwright）：每个页面真实加载，收集 JS 报错 / 页面异常 /
失败的请求，另验证关键全局函数存在。2026-09-13 app.js 拆分时引入，防拆分回归。

运行: python tests/_check_pages_console.py [--base http://127.0.0.1:8765]
不带 --base 时自起 Flask 服务（werkzeug 线程），跑完即关。
"""
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BASE = None
if '--base' in sys.argv:
    BASE = sys.argv[sys.argv.index('--base') + 1]

if not BASE:
    from werkzeug.serving import make_server
    import threading
    import app as app_module
    _srv = make_server('127.0.0.1', 18766, app_module.app, threaded=True)
    threading.Thread(target=_srv.serve_forever, daemon=True).start()
    BASE = 'http://127.0.0.1:18766'
    import time
    time.sleep(1.0)


def pages_to_check():
    """全部无参数的 GET 页面路由（排除 API / 静态 / virome SPA）。"""
    import app as app_module
    out = []
    for rule in app_module.app.url_map.iter_rules():
        if 'GET' not in rule.methods:
            continue
        r = rule.rule
        if (r.startswith('/api/') or r.startswith('/static')
                or '<' in r or r.rstrip('/').endswith('/virome')
                or r == '/virome'):
            continue
        out.append(r)
    return sorted(set(out))


def main():
    from playwright.sync_api import sync_playwright
    pages = pages_to_check()
    print(f'待巡检页面 {len(pages)} 个')
    bad = []
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={'width': 1440, 'height': 900})
        page = ctx.new_page()
        issues = []

        page.on('pageerror', lambda e: issues.append(('pageerror', str(e)[:200])))
        page.on('console', lambda m: issues.append(('console.' + m.type, m.text[:200]))
                if m.type == 'error' else None)
        page.on('response', lambda r: issues.append(('http ' + str(r.status), r.url[:120]))
                if r.status >= 400 else None)

        for p in pages:
            issues.clear()
            try:
                page.goto(BASE + p, wait_until='networkidle', timeout=20000)
            except Exception as e:
                # networkidle 对轮询页可能超时：退回 load
                try:
                    issues.clear()
                    page.goto(BASE + p, wait_until='load', timeout=20000)
                    page.wait_for_timeout(800)
                except Exception as e2:
                    bad.append((p, 'goto失败: ' + str(e2)[:120]))
                    continue
            page.wait_for_timeout(400)
            if issues:
                bad.append((p, ' | '.join(f'{k}:{v}' for k, v in issues[:4])))

        # 关键全局函数抽查（拆分后 app.js / app-compare.js 的函数仍为全局）
        checks = [
            ('/tools', 'jfetch', 'function'),
            ('/tools', 'rhRefresh', 'function'),
            # 比较基因组（⑤⑥ + ⑦MSA/⑧树/⑨SDT 工作区）内嵌在工具页
            ('/tools', 'loadGbCollections', 'function'),
            ('/tools', 'defaultCollName', 'function'),
            ('/results', 'pagerHtml', 'function'),
            ('/results', 'rhRefresh', 'function'),
            ('/pipeline', 'selectSample', 'function'),
            ('/pipeline', 'pasteSeq', 'function'),
        ]
        for route, fn, want in checks:
            issues.clear()
            try:
                page.goto(BASE + route, wait_until='load', timeout=20000)
                page.wait_for_timeout(300)
            except Exception:
                pass
            got = page.evaluate(f'typeof {fn}')
            if got != want:
                bad.append((route, f'全局 {fn} = {got}（期望 {want}）'))

        browser.close()

    print('=' * 64)
    if bad:
        print(f'✘ {len(bad)} 个问题:')
        for p, msg in bad:
            print(f'  {p}\n      {msg}')
        sys.exit(1)
    print(f'✔ 全部 {len(pages)} 个页面加载无 JS 报错，全局函数抽查通过')


if __name__ == '__main__':
    main()
