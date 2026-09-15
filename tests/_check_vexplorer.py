# -*- coding: utf-8 -*-
"""真浏览器验证 Explorer 页的四个面板（Playwright）。

覆盖：
  1. 概览：KPI 有值、6 张图都真的画出来了（Plotly 图例非空）
  2. 宿主范围：属级柱图 + 明细表；点「下钻」能到种级、面包屑更新
  3. 媒介传播：Sankey 有节点/链路 + 层标题、明细表有行、筛「病毒科」后记录数下降
  4. 全基因组变异：输入物种 → 实跑 MAFFT → 保守度/窗口/热图三图 + 热点表
  5. 全程无 JS 控制台报错

用法：
    python tests/_check_vexplorer.py            # 自起临时实例（端口 18767）
    python tests/_check_vexplorer.py --shots    # 另存截图到 tests/_shots/
    python tests/_check_vexplorer.py --base http://127.0.0.1:8765   # 用已在跑的实例

无 playwright（开发依赖未装）时打印 [SKIP] 并返回 0，与 _check_pages_console.py
同口径 —— 开发依赖缺失不该让 CI 变红。
"""
import os
import sys

# 仓库根入 sys.path：自起临时实例要 `import app`，而直接跑本脚本时
# sys.path[0] 是 tests/ 而不是仓库根（与 _check_pages_console.py 同做法）。
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

PORT = 18767
SHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '_shots')

PASS, FAIL = [], []


def _resolve_base():
    """--base 指定则用之；否则自起一个临时实例。

    自起比要求外部 8765 在跑更稳：既能进批量测试套件，也不受开发机
    端口占用/旧实例的影响。
    """
    if '--base' in sys.argv:
        return sys.argv[sys.argv.index('--base') + 1].rstrip('/')
    from werkzeug.serving import make_server
    import threading
    import app as app_module
    srv = make_server('127.0.0.1', PORT, app_module.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    import time
    time.sleep(1.0)
    return f'http://127.0.0.1:{PORT}'


def check(name, cond, detail=''):
    (PASS if cond else FAIL).append(name)
    print(f'  [{"ok" if cond else "FAIL"}] {name}'
          + (f'  — {detail}' if detail else ''))


def chart_ok(page, div_id):
    """Plotly 图是否真的渲染了（有 trace 且 trace 里有数据点）。

    Sankey 的规模不在 x/y/z 上，而在 node.label / link.value —— 不单独处理
    会得出「ok 但 0 项」的误报（2026-09-15 首轮实测踩过）。
    """
    return page.evaluate("""(id) => {
        const gd = document.getElementById(id);
        if (!gd || !gd.data || !gd.data.length) return {ok:false, n:0, traces:0};
        let n = 0;
        for (const t of gd.data) {
            for (const k of ['x','y','z','values','labels','link']) {
                if (t[k] && t[k].length) n = Math.max(n, t[k].length);
            }
            if (t.node && t.node.label) n = Math.max(n, t.node.label.length);
            if (t.link && t.link.value) n = Math.max(n, t.link.value.length);
        }
        return {ok: true, n, traces: gd.data.length};
    }""", div_id)


def wait_charts(page, div_ids, timeout=45000, extra_ready=None):
    """等一组图全部拿到数据。

    必须显式等：vxQuery() → vxRenderCharts() 是**未 await** 的浮空 Promise
    （保持原来的调用方式，改它会动到既有渲染顺序），表格先出、图后到，
    测试若在 KPI 一变就断言，必然抓到还没画的空容器。
    """
    ids = ','.join("'%s'" % i for i in div_ids)
    cond = ("() => [%s].every(id => { const g = document.getElementById(id);"
            " return g && g.data && g.data.length; })" % ids)
    if extra_ready:
        cond = cond[:-1] + f' && ({extra_ready})'
    page.wait_for_function(cond, timeout=timeout)


def main():
    shots = '--shots' in sys.argv
    if shots:
        os.makedirs(SHOT_DIR, exist_ok=True)

    try:
        import playwright  # noqa: F401
        from playwright.sync_api import sync_playwright
    except ImportError:
        # playwright 属开发依赖（requirements-dev.txt），未装时跳过而非失败
        print('[SKIP] 未安装 playwright，跳过 Explorer 面板真浏览器验证')
        return 0

    ORIGIN = _resolve_base()
    errors = []

    with sync_playwright() as pw:
        # 受限环境下 chromium 的沙箱与 /dev/shm 会引发随机段错误
        b = pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-dev-shm-usage', '--disable-gpu'])
        pg = b.new_page(viewport={'width': 1600, 'height': 1100})
        pg.on('console', lambda m: errors.append(f'{m.type}: {m.text}')
              if m.type == 'error' else None)
        pg.on('pageerror', lambda e: errors.append(f'pageerror: {e}'))

        print('=' * 68)
        print('Explorer 四面板真浏览器验证')
        print('=' * 68)

        # ---------------- ① 概览 ----------------
        print('\n[1] 概览与导出')
        pg.goto(ORIGIN + '/vexplorer', wait_until='load')
        pg.wait_for_selector('#kpiTotal', timeout=15000)
        pg.wait_for_function(
            "() => (document.getElementById('kpiTotal')||{}).textContent"
            " !== '—'", timeout=30000)
        total = pg.inner_text('#kpiTotal')
        check('KPI 序列总数已填充', total not in ('', '—'), f'= {total}')
        # 概览的 6 张联动图来自 vxQuery → vxRenderCharts（未 await 的浮空
        # Promise），必须等它们落地再断言，否则抓到的是空容器（实测踩过）
        wait_charts(pg, ('vxChartYear', 'vxChartGeo', 'vxChartFamily',
                         'vxChartHost', 'vxChartMol', 'vxChartMap'))
        for div in ('chartYear', 'chartGeo', 'vxChartYear', 'vxChartGeo',
                    'vxChartFamily', 'vxChartHost', 'vxChartMol',
                    'vxChartMap'):
            r = chart_ok(pg, div)
            check(f'图 {div} 已渲染', r['ok'] and r['n'] > 0,
                  f"{r.get('n')} 数据点")
        rows = pg.eval_on_selector_all('.vx-pick', 'els => els.length')
        check('结果表有可勾选行', rows > 0, f'{rows} 行')
        if shots:
            pg.screenshot(path=os.path.join(SHOT_DIR, '1_overview.png'),
                          full_page=False)

        # ---------------- ② 宿主范围 ----------------
        print('\n[2] 宿主范围')
        pg.click("button[data-tab='host']")
        pg.wait_for_selector('#vxHostChart', state='visible')
        pg.wait_for_function(
            "() => { const g = document.getElementById('vxHostChart');"
            " return g && g.data && g.data.length; }", timeout=30000)
        r = chart_ok(pg, 'vxHostChart')
        check('宿主属柱图已渲染', r['ok'] and r['n'] > 0, f"{r.get('n')} 条")
        hrows = pg.eval_on_selector_all('#vxHostTable tbody tr',
                                        'els => els.length')
        check('宿主明细表有行', hrows > 0, f'{hrows} 行')
        info = pg.inner_text('#vxHostInfo')
        check('统计行含宿主属数量', '宿主属' in info or 'host genera' in info,
              info[:70])
        # 下钻：点第一行的「下钻」按钮
        crumbs_before = pg.inner_text('#vxHostCrumb')
        pg.eval_on_selector_all(
            '#vxHostTable tbody tr',
            "els => { const b = els[0].querySelector('button'); if(b) b.click(); }")
        pg.wait_for_function(
            "() => document.getElementById('vxHostCrumb')"
            ".innerText.includes('›')", timeout=20000)
        crumbs_after = pg.inner_text('#vxHostCrumb')
        check('下钻后面包屑出现属名', '›' in crumbs_after,
              crumbs_after.replace('\n', ' ')[:60])
        d_rows = pg.eval_on_selector_all('#vxHostTable tbody tr',
                                         'els => els.length')
        check('下钻后为种级表', d_rows > 0, f'{d_rows} 行')
        if shots:
            pg.screenshot(path=os.path.join(SHOT_DIR, '2_host.png'),
                          full_page=False)
        # 回到属级，避免影响后续
        pg.click("button:has-text('回到属级')")
        pg.wait_for_timeout(1200)

        # ---------------- ③ 媒介传播 ----------------
        print('\n[3] 媒介传播网络')
        pg.click("button[data-tab='vec']")
        pg.wait_for_function(
            "() => { const g = document.getElementById('vxVecSankey');"
            " return g && g.data && g.data.length; }", timeout=60000)
        r = chart_ok(pg, 'vxVecSankey')
        n_nodes = pg.evaluate(
            "() => { const d = document.getElementById('vxVecSankey').data[0];"
            " return {nodes: d.node.label.length, links: d.link.value.length}; }")
        check('Sankey 已渲染', r['ok'] and n_nodes['nodes'] > 0,
              f"{n_nodes['nodes']} 节点 / {n_nodes['links']} 链路")
        check('Sankey 节点数 > 50', n_nodes['nodes'] > 50, str(n_nodes))
        check('Sankey 链路数 > 100', n_nodes['links'] > 100, str(n_nodes))
        # 层标题：Plotly 不画列名，必须靠 annotation 补，否则 6 层图无法分辨层序
        annots = pg.evaluate(
            "() => { const g = document.getElementById('vxVecSankey');"
            " const a = g.layout.annotations || [];"
            " return {n: a.length, texts: a.map(x => x.text)}; }")
        check('Sankey 有层标题标注', annots['n'] >= 6,
              f"{annots['n']} 个: {annots['texts'][:3]}")
        check('层标题含病毒科与媒介目',
              any('病毒科' in x or 'family' in x.lower()
                  for x in annots['texts'])
              and any('媒介目' in x or 'vector order' in x.lower()
                      for x in annots['texts']),
              str(annots['texts']))
        vrows = pg.eval_on_selector_all('#vxVecTable tbody tr',
                                        'els => els.length')
        check('关系明细表有行', vrows > 0, f'{vrows} 行')
        vinfo = pg.inner_text('#vxVecInfo')
        check('统计行含层数', '层' in vinfo or 'layers' in vinfo, vinfo[:80])
        if shots:
            pg.screenshot(path=os.path.join(SHOT_DIR, '3_vector.png'),
                          full_page=False)
        # 按病毒科筛选：应显著减少记录
        pg.select_option('#vf_family', 'Potyviridae')
        pg.click("button:has-text('应用筛选')")
        pg.wait_for_function(
            "() => document.getElementById('vxVecInfo')"
            ".innerText.includes('137')", timeout=30000)
        vinfo2 = pg.inner_text('#vxVecInfo')
        check('筛 Potyviridae 后记录数变为 137', '137' in vinfo2, vinfo2[:80])

        # ---------------- ④ 全基因组变异 ----------------
        print('\n[4] 全基因组变异（实跑 MAFFT，约 7 秒）')
        pg.click("button[data-tab='var']")
        pg.wait_for_selector('#vxVarSpecies', state='visible')
        pg.fill('#vxVarSpecies', 'Potyvirus yituberosi')
        pg.fill('#vxVarMaxSeqs', '12')
        pg.click("button:has-text('比对并分析')")
        pg.wait_for_function(
            "() => { const g = document.getElementById('vxVarCons');"
            " return g && g.data && g.data.length; }", timeout=180000)
        cinfo = pg.inner_text('#vxVarInfo')
        check('统计行含位点数', '位点' in cinfo or 'sites' in cinfo, cinfo[:110])
        check('比对位点 > 5000（验证选中全长簇）',
              any(t in cinfo for t in ('9748', '9681', '9,748'))
              or pg.evaluate(
                  "() => { const g = document.getElementById('vxVarCons');"
                  " return g.data[0].x.length; }") > 5000,
              f"位点列数 = {pg.evaluate('() => document.getElementById(\"vxVarCons\").data[0].x.length')}")
        for div in ('vxVarCons', 'vxVarWin', 'vxVarHeat'):
            r = chart_ok(pg, div)
            check(f'图 {div} 已渲染', r['ok'] and r['n'] > 0,
                  f"{r.get('n')} 数据点")
        hrows2 = pg.eval_on_selector_all('#vxVarHot tbody tr',
                                         'els => els.length')
        check('热点表有行', hrows2 > 0, f'{hrows2} 行')
        if shots:
            pg.screenshot(path=os.path.join(SHOT_DIR, '4_variation.png'),
                          full_page=False)

        b.close()

    # ---------------- 控制台错误 ----------------
    print('\n[5] 控制台')
    real = [e for e in errors
            if 'favicon' not in e and 'Failed to load resource' not in e]
    check('无 JS 控制台报错', not real,
          '; '.join(real[:3]) if real else f'{len(errors)} 条（已滤 favicon）')

    print('\n' + '=' * 68)
    print(f'结果: {len(PASS)} 通过 / {len(FAIL)} 失败')
    for f in FAIL:
        print('  FAIL:', f)
    print('=' * 68)
    return 1 if FAIL else 0


if __name__ == '__main__':
    raise SystemExit(main())
