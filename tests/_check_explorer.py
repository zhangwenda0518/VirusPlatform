# -*- coding: utf-8 -*-
"""真浏览器验证「病毒浏览器 Explorer」（服务器版 7 页签移植，Playwright）。

覆盖：
  1. 数据就绪（198,819 条 / 6,168 物种，与线上 39.106.101.94/explorer 一致）
  2. 七个页签齐全；初始化后六个筛选下拉被填充
  3. 主查询 → KPI 有值；时空三图**真的画出来**（断言 traces 里有数据点，
     不是只断言容器存在 —— 本项目踩过「接口正常但页面空白」的坑）
  4. 数据浏览表：行数、排序、页内搜索、翻页
  5. 宿主范围 / 引物数据库：面板出现真实表格
  6. 媒介传播：Sankey 真渲染（用 Potyviridae 家族取到媒介记录）
  7. 病毒档案：选物种后出现注释图与下载链接
  8. 深链指向与跳转：面板里的跨站链接必须指向线上整站（PUBLIC_BASE）而不是裸的
     根相对路径（否则点出本站 404）；真点一次确认弹出新页并能打开；本站
     `/virus/files/` 下载链接未被改写且真能下到文件
  9. 导出 CSV / FASTA 带正确 Content-Disposition
  10. 全程无 console error / pageerror

用法：python tests/_check_explorer.py [--port 8765]
      端口已在跑就直接用；没在跑则自起一个临时实例（跑完自动关）。
      [13] 深链跳转需要外网；断网或 VP_SKIP_ONLINE=1 时该段自动 SKIP 而不判失败。
      未安装 playwright 时整体 SKIP 并返回 0。
"""
import argparse
import atexit
import io
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

try:
    from playwright.sync_api import sync_playwright
except ImportError:                                  # 开发依赖未装
    sync_playwright = None

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ORIGIN = 'http://127.0.0.1:8765'
BASE = ORIGIN + '/explorer'
# 面板里的跨站深链指向的线上整站（后端 PUBLIC_BASE / VP_EXPLORER_PUBLIC）
PUBLIC_BASE = 'http://39.106.101.94'
TABS = ('trends', 'mutation', 'table', 'primers', 'host', 'vector', 'profile')


def _kill_proc(proc):
    """收尾关掉自起的临时实例（正常返回、断言失败、异常退出都要关）。"""
    try:
        if proc.poll() is None:
            proc.kill()
    except Exception:                                # noqa: BLE001
        pass


def _port_open(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(('127.0.0.1', port)) == 0


def _free_port(start=8791):
    for p in range(start, start + 40):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(('127.0.0.1', p))
                return p
            except OSError:
                continue
    raise RuntimeError('没有可用端口')


def _start_server(port):
    """起临时平台实例（服务日志落文件：PIPE 写满会让服务阻塞）。

    照抄 tests/_check_kvchain_ui.py 的写法，连同那条坑：项目自带绿色版 Python
    目录下有 `python312._pth`，该文件存在时 Python 进入 isolated 模式，`-c` 的
    sys.path **不含当前工作目录**，于是 `import app` 直接 ModuleNotFoundError、
    服务永远起不来（用脚本文件跑时 sys.path[0] 是脚本目录，所以只有这种
    `-c` 起子进程的写法会中招）。故必须在 `-c` 里显式注入 sys.path。
    """
    logpath = os.path.join(tempfile.gettempdir(), f'vp_explorer_{port}.log')
    logf = io.open(logpath, 'w', encoding='utf-8', errors='replace')
    proc = subprocess.Popen(
        [sys.executable, '-c',
         'import sys\n'
         f'sys.path.insert(0, {ROOT!r})\n'
         'from werkzeug.serving import make_server\n'
         'import app\n'
         f"s = make_server('127.0.0.1', {port}, app.app, threaded=True)\n"
         "print('ready', flush=True)\n"
         's.serve_forever()'],
        cwd=ROOT, env=dict(os.environ, VP_NO_RECOVER='1'),
        stdout=logf, stderr=subprocess.STDOUT)
    for _ in range(120):
        if _port_open(port):
            return proc, logpath
        if proc.poll() is not None:
            break
        time.sleep(0.3)
    proc.kill()
    print('服务启动失败，日志:', logpath)
    return None, logpath


def _json(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(ORIGIN + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.load(r)


def _head(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(ORIGIN + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=600) as r:
        return r.status, dict(r.headers), r.read()


def _text(path, data=None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(ORIGIN + path, data=body,
                                 headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=900) as r:
        return r.read().decode('utf-8', errors='replace')


def _stray(hrefs):
    """挑出会落到本站 404 的裸根相对链接。

    面板里的链接只允许两种：指向线上整站（PUBLIC_BASE + '/...'）或本站自有下载
    路由 `/virus/files/...`。裸的 `/species/xxx`、`/vector/` 这类点下去会命中
    127.0.0.1:8765 的 404 —— 后端 `_retarget_links` 漏改就是这个症状。
    """
    return sorted({h for h in hrefs
                   if h.startswith('/') and not h.startswith('//')
                   and not h.startswith('/virus/files/')})


def _plot_stat(pg, sel):
    """返回 plotly 图的 (trace 数, 数据点总数)。未渲染返回 (0, 0)。

    ⚠️ 必须读**渲染后**的 `el._fullData`，不能读 `el.data`：
    Plotly 6.x 的 `to_plotly_json()` 把 numpy 数组编成 `{dtype, bdata}` 二进制串
    （base64 TypedArray，plotly.js 原生认）。那是 dict、没有 `.length`，
    直接数 `el.data` 会得到 0 点，把画得好好的图误判成空白 —— 本项目已经因
    「容器在但没内容」踩过坑，反过来「有内容但数不出来」同样会误报。

    Sankey 另有一层坑：数据不在 trace 顶层，而是 `node.label` / `link.value`。
    """
    return pg.evaluate(
        """(sel) => {
             const el = document.querySelector(sel);
             if (!el || !el._fullData) return [0, 0];
             const KEYS = ['x','y','z','lat','lon','locations','values','labels',
                           'text','source','target','value'];
             let n = 0;
             for (const t of el._fullData) {
               const cands = [];
               for (const k of KEYS) cands.push(t[k]);
               if (t.link) cands.push(t.link.value, t.link.source, t.link.target);
               if (t.node) cands.push(t.node.label, t.node.color);
               for (const v of cands) {
                 if (v != null && typeof v.length === 'number' && v.length > 0) {
                   n += v.length; break;
                 }
               }
             }
             return [el._fullData.length, n];
           }""", sel)


def main() -> int:
    global ORIGIN, BASE

    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765,
                    help='平台端口；没在跑就自起一个临时实例（默认 8765）')
    args = ap.parse_args()

    if sync_playwright is None:
        print('[SKIP] 未安装 playwright，跳过真浏览器验证')
        print('       安装: python -m pip install -r requirements-dev.txt')
        return 0

    # 套件不保证外部已有服务在跑 —— 没有就自己起一个，跑完（含异常退出）自动关。
    # 已有实例则直接复用，不动它。
    proc = None
    if _port_open(args.port):
        print(f'复用已在运行的平台实例 127.0.0.1:{args.port}\n')
    else:
        proc, logpath = _start_server(args.port)
        if proc is None:
            print(f'[FAIL] 无法在 127.0.0.1:{args.port} 起服务')
            return 1
        atexit.register(_kill_proc, proc)
        print(f'自起临时实例 127.0.0.1:{args.port}（日志 {logpath}）\n')
    ORIGIN = f'http://127.0.0.1:{args.port}'
    BASE = ORIGIN + '/explorer'
    # ⚠️ 数据是**惰性加载**的：`/status` 只报状态、不触发加载（新实例的
    # n_records 就是 None）。必须先打一次 `/init` 把全量数据（457MB FASTA，
    # 有 pickle 缓存时约 1s）拉起来，再轮询 status.loaded 才算就绪。
    for _ in range(4):
        try:
            _json('/api/explorer/init')
            break
        except Exception:                            # noqa: BLE001
            time.sleep(0.5)
    for _ in range(240):
        try:
            if _json('/api/explorer/status').get('loaded'):
                break
        except Exception:                            # noqa: BLE001
            pass
        time.sleep(0.5)

    fails = []
    skips = []

    def ck(cond, msg, extra=''):
        print(('  ok   ' if cond else '  FAIL ') + msg + (('  ' + extra) if extra else ''))
        if not cond:
            fails.append(msg)

    def sk(msg, why=''):
        """需要外网才能判定的项：拿不到外网记 SKIP，不当作失败。

        本脚本在 `_run_all.py --quick` 里跑，断网环境不该因探测线上站而变红；
        但真的返回了就照常断言。
        """
        print('  SKIP ' + msg + (('  ' + why) if why else ''))
        skips.append(msg)

    def is_offline(e):
        return isinstance(e, (urllib.error.URLError, TimeoutError, OSError))

    # 项目约定：联网段可用 VP_SKIP_ONLINE=1 显式跳过（见 tests/_run_all.py
    # 的 _ONLINE_HINT）。[13] 要探线上整站，属于这一类。
    no_net = bool(os.environ.get('VP_SKIP_ONLINE'))

    print('[1] 数据状态')
    st = _json('/api/explorer/status')
    ck(st['ok'] is True, 'status.ok')
    ck(not st['missing'], '核心数据无缺失', str(st['missing']))
    ck(st['n_records'] == 198819, '记录数 198,819（与线上一致）', str(st.get('n_records')))
    ck(st['n_species'] == 6168, '物种数 6,168（与线上一致）', str(st.get('n_species')))

    print('[2] 初始化接口')
    ini = _json('/api/explorer/init')
    ck(ini['ok'] is True, 'init.ok')
    for k, lo in (('host_options', 1000), ('country_options', 100),
                  ('family_options', 40), ('virus_options', 5000)):
        ck(len(ini[k]) >= lo, f'{k} 有数据（≥{lo}）', f'{len(ini[k])}')
    ck(len(ini['category_options']) == 2, '类别选项 2 个')
    ck(ini['year_bounds'] == [1970, 2025], '年份边界 1970..2025', str(ini['year_bounds']))

    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        pg = b.new_page(viewport={'width': 1680, 'height': 1150})
        errs = []
        pg.on('console', lambda m: errs.append(m.text) if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.on('dialog', lambda d: d.accept())
        pg.add_init_script("try{localStorage.setItem('vp_example_seen','1')}catch(e){}")

        pg.goto(BASE, wait_until='domcontentloaded')
        pg.wait_for_selector('#exApply', state='visible', timeout=30000)

        print('[3] 页面骨架与页签')
        ck(pg.locator('.ex-tab').count() == 7, '7 个页签',
           str(pg.locator('.ex-tab').count()))
        for t in TABS:
            ck(pg.locator(f'.ex-tab[data-tab="{t}"]').count() == 1, f'页签 {t} 存在')
        ck(pg.locator('#exMissing').is_hidden(), '未显示「数据缺失」告警')
        dup = pg.evaluate(
            """() => {
                 const seen = {}, dup = [];
                 for (const el of document.querySelectorAll('[id]')) {
                   if (seen[el.id]) { if (dup.indexOf(el.id) < 0) dup.push(el.id); }
                   else seen[el.id] = 1;
                 }
                 return dup;
               }""")
        # 重复 id 会让 getElementById 只认文档里靠前的那个（曾把宿主面板写成
        # <select id="exHost"> 的同名 div，导致面板内容被灌进下拉框）
        ck(not dup, '页面无重复 id', ', '.join(dup[:5]))

        print('[4] 筛选器初始化')
        # init 是异步链（status → init 约 930KB → 逐个填下拉），必须先等它落地。
        # 早先直接读 options 会在 init 完成前读到 0，误报成「下拉为空」。
        pg.wait_for_function(
            "() => document.querySelector('#exVirus').options.length > 5000",
            timeout=180000)
        for sel, lo in (('#exHost', 100), ('#exCountry', 100),
                        ('#exFamily', 40), ('#exVirus', 5000)):
            n = pg.evaluate(f'document.querySelector("{sel}").options.length')
            ck(n >= lo, f'{sel} 选项已填充（≥{lo}）', str(n))
        ck(pg.input_value('#exYearMin') == '1970', '起始年 1970',
           pg.input_value('#exYearMin'))
        ck(pg.locator('#exVirus').evaluate(
            'el => Array.from(el.selectedOptions).map(o => o.value)')
            == ['Potato spindle tuber viroid'],
            '默认选中 Potato spindle tuber viroid')

        print('[5] 主查询 + 时空三图（断言真的画出来了）')
        pg.wait_for_function(
            "() => document.getElementById('exKpiTotal').textContent"
            " && document.getElementById('exKpiTotal').textContent !== '—'",
            timeout=180000)
        ck(pg.inner_text('#exKpiTotal') not in ('—', ''), 'KPI 命中序列数有值',
           pg.inner_text('#exKpiTotal'))
        ck(pg.inner_text('#exKpiCommon').startswith('Potato'),
           'KPI 最常见物种 = PSTVd', pg.inner_text('#exKpiCommon'))
        pg.wait_for_function(
            "() => {const e = document.querySelector('#exFigTime');"
            " return e && e._fullData && e._fullData.length > 0;}", timeout=60000)
        for sel, need in (('#exFigTime', 1), ('#exFigCountry', 1), ('#exFigMap', 2)):
            ntr, npt = _plot_stat(pg, sel)
            ck(ntr >= need and npt > 0, f'{sel} 已渲染（traces≥{need}, 点数>0）',
               f'traces={ntr} points={npt}')

        print('[6] 数据浏览页签')
        pg.click('.ex-tab[data-tab="table"]')
        pg.wait_for_selector('.ex-pane[data-pane="table"].active', timeout=10000)
        rows = pg.evaluate('document.querySelectorAll("#exTable tbody tr").length')
        ck(rows > 0, '表格有数据行', str(rows))
        ck(rows <= 50, '表格分页生效（首页 ≤50 行）', str(rows))
        pg.fill('#exTblSearch', 'NC_001')
        pg.wait_for_timeout(300)
        filtered = pg.evaluate('document.querySelectorAll("#exTable tbody tr").length')
        ck(0 < filtered <= rows, '页内搜索缩小了结果', f'{rows} → {filtered}')
        pg.fill('#exTblSearch', '')
        pg.wait_for_timeout(200)
        pg.click('#exPageNext')
        pg.wait_for_timeout(300)
        info = pg.inner_text('#exPageInfo')
        # 文案形如「第 2 / 58 页」。早先用 .replace('/', ' /') 拼串反而制造了
        # 双空格，把正确的文案判成失败 —— 直接用正则取页码。
        ck(re.search(r'第\s*2\s*/', info) is not None, '翻页到第 2 页', info)
        total_txt = pg.inner_text('#exPageRows')
        ck(re.search(r'\d', total_txt) is not None, '分页行数统计存在', total_txt)

        print('[7] 宿主范围页签')
        pg.click('.ex-tab[data-tab="host"]')
        pg.wait_for_function(
            "() => document.querySelector('#exHostPanel .vx-table,"
            " #exHostPanel .vx-alert') !== null", timeout=60000)
        ck(pg.locator('#exHostPanel table').count() >= 1, '宿主面板含表格',
           str(pg.locator('#exHostPanel table').count()))
        pg.wait_for_timeout(1500)
        htr, hpt = _plot_stat(pg, '#exHostPanel .vx-plot')
        ck(htr >= 1 and hpt > 0, '宿主面板的柱状图已渲染',
           f'traces={htr} points={hpt}')

        print('[8] 媒介传播页签（先筛 Potyviridae）')
        pg.click('.ex-tab[data-tab="trends"]')
        pg.select_option('#exFamily', ['Potyviridae'])
        pg.locator('#exVirus').evaluate(
            'el => Array.from(el.options).forEach(o => { o.selected = false; })')
        pg.wait_for_timeout(400)
        pg.click('#exApply')
        # 等查询真正跑完：runQuery 期间会把按钮 disable，收尾再置回。
        # 只看 KPI 不行 —— 它上一轮已经有值，不进 '—' 状态，等于没等。
        pg.wait_for_function(
            "() => !document.getElementById('exApply').disabled"
            " && document.getElementById('exKpiTotal').textContent !== '—'",
            timeout=180000)
        pg.click('.ex-tab[data-tab="vector"]')
        pg.wait_for_function(
            "() => {const e = document.querySelector('#exVector .vx-plot');"
            " return e && e._fullData && e._fullData.length > 0;}", timeout=180000)
        vtr, vpt = _plot_stat(pg, '#exVector .vx-plot')
        ck(vtr >= 1 and vpt > 0, 'Sankey 已渲染', f'traces={vtr} points={vpt}')
        ck(pg.locator('#exVector table').count() >= 1, '媒介关系明细表存在')
        ck(pg.locator('#exVector a').count() >= 1, '媒介表含深链')

        print('[9] 引物数据库页签')
        pg.click('.ex-tab[data-tab="primers"]')
        pg.wait_for_function(
            "() => document.querySelector('#exPrimers .vx-table,"
            " #exPrimers .vx-alert, #exPrimers .vx-text') !== null", timeout=120000)
        ck(pg.locator('#exPrimers table').count() >= 1, '引物面板含表格',
           str(pg.locator('#exPrimers table').count()))

        print('[10] 病毒档案页签')
        pg.click('.ex-tab[data-tab="profile"]')
        opts = pg.evaluate('document.querySelector("#exProfileSel").options.length')
        ck(opts > 0, '病毒档案下拉有选项', str(opts))
        first = pg.evaluate(
            'document.querySelector("#exProfileSel").options[0].value')
        pg.select_option('#exProfileSel', first)
        pg.wait_for_function(
            "() => {const e = document.getElementById('exProfile');"
            " return e && (e.querySelector('table') || e.querySelector('.vx-plot')"
            " || e.querySelector('.vx-alert') || e.querySelector('.vx-text'));}",
            timeout=120000)
        pg.wait_for_timeout(2500)
        ck(pg.locator('#exProfile table, #exProfile .vx-plot, #exProfile .vx-alert')
           .count() >= 1, '档案面板有内容', first[:40])

        print('[11] 全基因组变异页签')
        pg.click('.ex-tab[data-tab="mutation"]')
        pg.wait_for_timeout(300)
        ck(pg.locator('#exMutationVirus').evaluate(
            'el => el.options.length') > 0, '变异页签病毒下拉有选项')
        pg.select_option('#exMutationVirus', 'Potato virus Y')
        pg.click('#exRunVar')
        pg.wait_for_function(
            "() => {const e = document.querySelector('#exFigVar');"
            " return e && e._fullData && e._fullData.length > 0;}", timeout=300000)
        vtr2, vpt2 = _plot_stat(pg, '#exFigVar')
        htr2, hpt2 = _plot_stat(pg, '#exFigHeat')
        ck(htr2 >= 1 and hpt2 > 0, '碱基丰度热图已渲染', f'traces={htr2} points={hpt2}')
        ck(vtr2 >= 1 and vpt2 > 0, '多态率曲线已渲染', f'traces={vtr2} points={vpt2}')

        print('[12] 控制台干净')
        real = [e for e in errs
                if 'favicon' not in e.lower() and 'net::ERR' not in e]
        ck(not real, '无 console error / pageerror', '; '.join(real[:3]))

        print('[13] 深链指向与跳转')
        anchors = pg.evaluate("""() => {
            const out = [];
            for (const sel of ['#exVector', '#exPrimers', '#exProfile',
                               '#exHostPanel']) {
              for (const a of document.querySelectorAll(sel + ' a[href]')) {
                out.push({href: a.getAttribute('href'),
                          text: (a.textContent || '').trim().slice(0, 40)});
              }
            }
            return out;
        }""")
        ck(len(anchors) > 0, '面板里有可跳转的深链', f'{len(anchors)} 条')
        hrefs = {a['href'] for a in anchors}

        # 只允许两种 href：指向线上整站（PUBLIC_BASE）或本站自有下载路由。
        # 出现裸的根相对链接（如 /species/xxx）说明 _retarget_links 漏改了 ——
        # 点下去会落到 127.0.0.1:8765/species/xxx 的 404。
        ck(not _stray(hrefs), '无会落到本站 404 的裸相对链接',
           '; '.join(_stray(hrefs)[:4]))

        # 接口层再扫一遍：页签懒加载时某些面板不带 virus= 就不产生跨站链接
        # （如引物库），只查当前 DOM 会漏掉那些模式。这里用**确定入参**覆盖全部模式。
        _sp = json.loads(_text('/api/explorer/profile_species'))['species']
        panel_html = {
            '宿主范围': _text('/api/explorer/host?virus=Potato%20virus%20Y'),
            '引物库': _text('/api/explorer/primers?virus=Potato%20virus%20Y'),
            '病毒档案': _text('/api/explorer/profile?name='
                          + urllib.parse.quote(_sp[0])),
            '媒介传播': _text('/api/explorer/vector',
                          {'virus': ['Potato virus Y']}),
        }
        all_hrefs = set()
        for panel, html in panel_html.items():
            hs = re.findall(r'href="([^"]+)"', html)
            all_hrefs.update(hs)
            ck(not _stray(hs), f'{panel}接口无裸相对链接',
               '; '.join(_stray(hs)[:3]))
        for pat, label in (('/virus/', '媒介→物种页'), ('/vector/', '媒介站'),
                           ('/species/', '引物→物种页'),
                           ('/primers/search', '引物检索')):
            got = sorted(h for h in all_hrefs
                         if pat in h and h.startswith(PUBLIC_BASE))
            ck(bool(got), f'{label} 深链已指向线上整站', f'{len(got)} 条')
            # 指向对了不代表能打开：名字格式不对（如 ICTV 名 vs NCBI 名）照样线上
            # 404。每种模式真发一次请求 —— 这才是「跳转正常」的判据。
            if not got:
                continue
            if no_net:
                sk(f'{label} 线上可打开', 'VP_SKIP_ONLINE=1')
                continue
            u = got[0]
            try:
                with urllib.request.urlopen(
                        urllib.request.Request(
                            u, headers={'User-Agent': 'vp-linkcheck'}),
                        timeout=30) as r:
                    code, n = r.status, len(r.read(20000))
                ck(code == 200 and n > 0, f'{label} 线上可打开',
                   f'HTTP {code} / {n}B')
            except Exception as e:                       # noqa: BLE001
                if is_offline(e):
                    sk(f'{label} 线上可打开', '外网不可达')
                else:
                    ck(False, f'{label} 线上可打开', f'{type(e).__name__}: {e}')
        ck(bool([h for h in all_hrefs if h.startswith('/virus/files/')]),
           '档案面板保留本站下载链接（未被改写）',
           f'{len([h for h in all_hrefs if h.startswith("/virus/files/")])} 条')

        # 真点一次线上的深链，确认弹出新页且能打开（不是死链）
        pg.click('.ex-tab[data-tab="vector"]')
        victim = pg.locator(
            '#exVector a[href^="%s/virus/"]' % PUBLIC_BASE).first
        victim.wait_for(state='visible', timeout=30000)
        target = victim.get_attribute('href')
        ck(victim.get_attribute('target') == '_blank',
           '深链 target=_blank（新标签打开）', str(victim.get_attribute('target')))
        with pg.context.expect_page() as pop:
            victim.click()
        p2 = pop.value
        if no_net:
            sk('线上深链可跳转', 'VP_SKIP_ONLINE=1')
            try:
                p2.close()
            except Exception:                        # noqa: BLE001
                pass
        else:
            try:
                p2.wait_for_load_state('domcontentloaded', timeout=60000)
                loaded = True
                why = ''
            except Exception as e:                   # noqa: BLE001
                loaded, why = False, f'{type(e).__name__}: {e}'
            if not loaded and is_offline(e):
                sk('线上深链可跳转', '外网不可达：' + why)
            else:
                ck(p2.url.startswith(PUBLIC_BASE), '点击后打开的是线上站页面',
                   p2.url[:80])
                try:
                    with urllib.request.urlopen(
                            urllib.request.Request(
                                p2.url, headers={'User-Agent': 'vp-linkcheck'}),
                            timeout=30) as r:
                        code, n = r.status, len(r.read(20000))
                    ck(code == 200 and n > 0, '线上深链可打开且有内容',
                       f'HTTP {code} / {n}B  {target[:60]}')
                except Exception as e2:              # noqa: BLE001
                    if is_offline(e2):
                        sk('线上深链可打开且有内容', '外网不可达')
                    else:
                        ck(False, '线上深链可打开且有内容',
                           f'{type(e2).__name__}: {e2}  {target[:60]}')
            p2.close()

        # 本站下载路由真能下到文件
        local = sorted(h for h in all_hrefs if h.startswith('/virus/files/'))
        if local:
            try:
                with urllib.request.urlopen(
                        urllib.request.Request(
                            ORIGIN + urllib.parse.quote(local[0]),
                            headers={'User-Agent': 'vp-linkcheck'}),
                        timeout=60) as r:
                    code, n, cd = r.status, len(r.read()), r.headers.get(
                        'Content-Disposition', '')
                ck(code == 200 and n > 100 and 'attachment' in cd,
                   '本站下载链接可下载到文件',
                   f'HTTP {code} / {n}B  {cd[:40]}')
            except Exception as e:                       # noqa: BLE001
                ck(False, '本站下载链接可下载到文件',
                   f'{type(e).__name__}: {e}')
        b.close()

    print('[14] 导出接口')
    for path, ctype, name in (
            ('/api/explorer/export/csv', 'text/csv', 'plantvirus_alignment_metadata.csv'),
            ('/api/explorer/export/fasta', 'text/plain', 'plantvirus_sequences.fasta')):
        code, hdrs, body = _head(path, {'virus': 'Potato virus Y'})
        ck(code == 200, f'{path} 返回 200', str(code))
        ck(ctype in hdrs.get('Content-Type', ''), f'{path} Content-Type 正确',
           hdrs.get('Content-Type', ''))
        ck(name in hdrs.get('Content-Disposition', ''), f'{path} 文件名正确',
           hdrs.get('Content-Disposition', ''))
        ck(len(body) > 100, f'{path} 有内容', f'{len(body)} 字节')

    print()
    if fails:
        print(f'FAILED {len(fails)} 项:')
        for f in fails:
            print('  -', f)
        return 1
    if skips:
        print(f'SKIPPED {len(skips)} 项（需外网）: {", ".join(skips)}')
    print('ALL EXPLORER CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
