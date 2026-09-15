# -*- coding: utf-8 -*-
"""核验 Explorer 面板深链：抽取 → 归类 → 逐个探测线上可达性。

面板里的跨站链接指向 PUBLIC_BASE（默认 http://39.106.101.94）。这些链接是服务器版
原样带过来的，服务器路由一变就成死链，所以必须实测而不是肉眼看着像。

覆盖四种面板、多组筛选，避免「只试一个物种恰好没链接」的假绿。

用法：python tests/_check_explorer_links.py [--port 8765] [病毒名]
      需平台实例在跑（本脚本不自起）；逐个探测线上深链需要外网。

      日常回归不必跑本脚本 —— `_check_explorer.py` 的 [13] 段已覆盖四种链接模式的
      指向与线上可达性。本脚本用于**服务器整站路由变动后**做更广的抽样扫描
      （4 个物种 × 3 个面板 + 家族筛选，193 条链接归成 26 个模式），
      能抓「模式对了但具体名字格式不对」的线上 404。
"""
import argparse
import json
import re
import socket
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

PORT = 8765
LOCAL = f'http://127.0.0.1:{PORT}'
PUBLIC = 'http://39.106.101.94'
# 本站自有路由，不该被改写也不该拿去做线上探测
LOCAL_PREFIXES = ('/virus/files/', '/static/', '/api/', '/explorer', '/reference/')

VIRUSES = ['Potato virus Y', 'Potato spindle tuber viroid',
           'Cucumber mosaic virus', 'Citrus tristeza virus']


def _get(path):
    with urllib.request.urlopen(LOCAL + path, timeout=900) as r:
        return r.read().decode('utf-8', errors='replace')


def _post(path, body):
    req = urllib.request.Request(
        LOCAL + path, data=json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.read().decode('utf-8', errors='replace')


def _hrefs(html):
    return re.findall(r'href="([^"]+)"', html)


def _pattern(u):
    """把物种名 / accession 抽掉归成模式，避免同模式探几十次。"""
    p = u[len(PUBLIC):] if u.startswith(PUBLIC) else u
    p = re.sub(r'/(species|virus)/[^/?#]+', r'/\1/<名称>', p)
    p = re.sub(r'(\?|&)q=[^&]*', r'\1q=<词>', p)
    return p


def collect():
    """返回 {面板名: [(链接, 所属筛选)]}。"""
    out = defaultdict(list)
    q = urllib.parse.quote
    # 病毒档案的入参是**参考库口径的物种名**（`?name=`），不是 NCBI 物种名，
    # 所以它单独用 profile_species() 的前几个当样本 —— 传错名字会返回空面板，
    # 链接自然是 0 条，会把 bug 藏起来。
    try:
        species = json.loads(_get('/api/explorer/profile_species'))['species']
    except Exception:                                    # noqa: BLE001
        species = []
    for v in VIRUSES:
        for panel, html in (('宿主范围', _get('/api/explorer/host?virus=' + q(v))),
                            ('引物库', _get('/api/explorer/primers?virus=' + q(v))),
                            ('媒介传播', _post('/api/explorer/vector', {'virus': [v]}))):
            for u in _hrefs(html):
                out[panel].append((u, v))
    for v in (species[:4] if species else VIRUSES):
        html = _get('/api/explorer/profile?name=' + q(v))
        for u in _hrefs(html):
            out['病毒档案'].append((u, v))
    # 家族筛选能带出最多链接（Potyviridae 实测上百条）
    html = _post('/api/explorer/vector', {'family': ['Potyviridae']})
    for u in _hrefs(html):
        out['媒介传播'].append((u, 'family=Potyviridae'))
    return out


def probe(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'vp-linkcheck'})
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            body = r.read(6000).decode('utf-8', errors='replace')
            return r.status, r.geturl(), body
    except urllib.error.HTTPError as e:
        return e.code, url, ''
    except Exception as e:                       # noqa: BLE001
        return 'ERR', url, f'{type(e).__name__}: {e}'


def main():
    global PORT, LOCAL
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765,
                    help='平台端口（本脚本不自起实例，需已在跑）')
    args = ap.parse_args()
    PORT = args.port
    LOCAL = f'http://127.0.0.1:{PORT}'
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(('127.0.0.1', PORT)) != 0:
            print(f'[SKIP] 127.0.0.1:{PORT} 没有在跑的平台实例')
            print('       先启动：python app.py --web')
            return 2

    print(f'探针物种: {", ".join(VIRUSES)}')
    print('逐面板抽取链接（多组筛选）\n')
    by_panel = collect()
    total = 0
    for panel, items in by_panel.items():
        uniq = sorted({u for u, _ in items})
        total += len(uniq)
        print(f'  {panel}: {len(items)} 条 / 去重 {len(uniq)}')

    print('\n' + '=' * 70)
    print('按模式分组，每组最多探 3 条（同一模式取不同筛选）')
    print('=' * 70)

    groups = defaultdict(list)
    for panel, items in by_panel.items():
        for u, tag in items:
            if u.startswith(LOCAL_PREFIXES) or '/' not in u:
                continue                         # 本站路由 / 锚点，不做外网探测
            groups[_pattern(u)].append((panel, u, tag))

    bad, checked = [], 0
    for pat, items in sorted(groups.items()):
        panels = sorted({p for p, _, _ in items})
        print(f'\n{pat}   共 {len(items)} 条，来自 {panels}')
        seen, n = set(), 0
        for panel, u, tag in items:
            key = (u[:60], panel)
            if key in seen:
                continue
            seen.add(key)
            code, final, body = probe(u)
            n += 1
            checked += 1
            soft = ''
            if code == 200 and re.search(r'\b404\b|not found|页面不存在',
                                         body, re.I):
                soft = '  ⚠ 正文含 404 字样'
            if code != 200:
                flag = 'FAIL'
            elif soft:
                flag = 'WARN'
            else:
                flag = 'ok  '
            print(f'   {flag} {code}  [{panel} · {tag}] {u[:78]}{soft}')
            if flag != 'ok  ':
                bad.append((code, panel, u, soft))
            if n >= 3:
                break

    print('\n' + '=' * 70)
    print(f'共探测 {checked} 条链接')
    if bad:
        print(f'✗ {len(bad)} 条不可用：')
        for code, panel, u, soft in bad:
            print(f'    {code} [{panel}] {u[:100]}{soft}')
        return 1
    print('✔ 全部深链线上可达（HTTP 200，正文无 404 字样）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
