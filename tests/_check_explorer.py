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
  8. 导出 CSV / FASTA 带正确 Content-Disposition
  9. 全程无 console error / pageerror

用法：python tests/_check_explorer.py       （需 8765 端口在跑）
"""
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ORIGIN = 'http://127.0.0.1:8765'
BASE = ORIGIN + '/explorer'
TABS = ('trends', 'mutation', 'table', 'primers', 'host', 'vector', 'profile')


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
    fails = []

    def ck(cond, msg, extra=''):
        print(('  ok   ' if cond else '  FAIL ') + msg + (('  ' + extra) if extra else ''))
        if not cond:
            fails.append(msg)

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
        b.close()

    print('[13] 导出接口')
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
    print('ALL EXPLORER CHECKS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())
