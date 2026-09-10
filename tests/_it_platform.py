# -*- coding: utf-8 -*-
"""平台级自测：所有页面 200 + 关键 API 结构 + 页面渲染含示例按钮/示例文件
+ 既有样品报告与结果中心数据。只读，不启动分析任务。"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vp.config import PLATFORM_ROOT  # noqa: E402

EX = os.path.join(PLATFORM_ROOT, 'databases', 'examples')

PAGES = ['/', '/pipeline', '/samples', '/hostremoval', '/hostpredict',
         '/orf', '/annotation', '/genome', '/primer', '/build', '/results',
         '/tools', '/settings', '/meta', '/download', '/logan', '/submit',
         '/virome', '/tools?g=virus', '/tools?g=annotate', '/tools?g=compare']


def check(cond, msg):
    print(('  ok ' if cond else '  FAIL ') + msg, flush=True)
    assert cond, msg


def main():
    import app as appmod  # noqa: E402
    c = appmod.app.test_client()

    # ---------- 1. 页面 ----------
    print('--- 页面渲染 ---', flush=True)
    for p in PAGES:
        r = c.get(p)
        check(r.status_code == 200, f'GET {p} -> {r.status_code}')

    # 页面内含示例按钮（本次补充的示例入口都要真实渲染出来）
    html = c.get('/tools?g=compare').get_data(as_text=True)
    for marker, where in [('seqPrepExample()', '参考序列获取卡'),
                          ('ictvPreview()', 'ICTV 选参预览'),
                          ('id="spCascade"', 'ICTV 级联下拉容器'),
                          ('tbBuild(this)', '进化树构建·集合建树'),
                          ('id="tbSource"', '建树来源类型'),
                          ('id="alSource"', '比对来源类型'),
                          ('id="al_fa_extra"', '比对卡额外序列'),
                          ('alignRun(this)', '序列比对·运行'),
                          ('alignEditToggle()', '比对查看器·编辑模式'),
                          ('alignSave(this)', '比对查看器·保存副本'),
                          ("fillExample('al_fa', EXAMPLE_SET_FASTA)", '比对卡示例'),
                          ('fillExample(\'qt_fa\', EXAMPLE_SET_FASTA)', 'FASTA 建树'),
                          ('fillExample(\'tv_file\', EXAMPLE_TREE_NWK)', '树查看'),
                          ('fillExample(\'ms_fa\', EXAMPLE_SET_FASTA)', 'MSA 查看'),
                          ('fillExample(\'sd_fa\', EXAMPLE_SET_FASTA)', 'SDT 卡'),
                          ('fillExample(\'s_files\', EXAMPLE_SYNTENY_GBS)', '导入示例 .gb')]:
        check(marker in html, f'tools 页渲染含 {where}')
    # 比较组四模块结构：参考序列获取 / 进化树构建 / SDT / 共线性
    for gone in ('id="t-contigs-struct"', 'id="t-ncbi"', 'id="t-synteny-gb"',
                 'id="t-msa"', 'id="t-tree"', 'id="s_style"', 'id="s_lovis4u"'):
        check(gone not in html, f'旧结构已移除: {gone}')
    for present in ('id="t-seqprep"', 'id="t-treebuild"', 'id="t-sdt"',
                    'id="t-synteny"'):
        check(present in html, f'新模块存在: {present}')
    js = open(os.path.join(PLATFORM_ROOT, 'webapp', 'static', 'app.js'),
              encoding='utf-8').read()
    for fn in ('ictvCascadeRefetch', 'ictvPreview', 'ictvDownload', 'loadTbColls',
               'tbBuild', 'tbBuildFor', 'alignRun', 'alignLoad', 'alignRender',
               'alignEditToggle', 'alignSave', 'alignSend', 'tbSourceChanged',
               'alSourceChanged', 'alFillFromSource', 'loadAlColls'):
        check(f'function {fn}' in js or f'async function {fn}' in js,
              f'app.js 定义 {fn}')
    # 旧项目归档：样品/集合列表不再出现下划线与归档项
    r = c.get('/api/samples')
    names = [x['name'] for x in r.get_json()]
    check(all(not n.startswith('_') for n in names), '样品列表无下划线项')
    r = c.get('/api/samples/archived')
    check(r.status_code == 200 and len(r.get_json()) > 0,
          f'归档样品列表可用（{len(r.get_json())} 个）')
    r = c.get('/api/gb/collections')
    check(all(not x['name'].startswith('_') for x in r.get_json()),
          '集合列表无下划线项')
    html = c.get('/annotation').get_data(as_text=True)
    check("fillExample('oa_fa')" in html, '注释页渲染含示例按钮')
    html = c.get('/genome').get_data(as_text=True)
    check('EXAMPLE_GENBANK_GB' in html, '图谱页渲染含示例 GenBank 按钮')
    # 预览缩放：linear 图原始宽 2000+px（gbdraw canvas.linear.width 固定），
    # 侧栏直接显示必横向滚很长，故默认「适应宽度」并给 100%/150% 切换。
    check('id="gp_zoom"' in html and "gpZoom('fit')" in html
          and 'data-zoom="1.5"' in html,
          '图谱页预览含缩放控制（适应宽度 / 100% / 150%）')
    html = c.get('/primer').get_data(as_text=True)
    # /primer 已重构为交互式 primer3 设计器（原「模式感知示例」随旧页面下线），
    # 断言改为新页面的示例入口：填充 pd_fa + 复用内置示例常量。
    check("fillExample('pd_fa'" in html and 'EXAMPLE_FASTA' in html,
          '引物页渲染含示例按钮')
    js = open(os.path.join(PLATFORM_ROOT, 'webapp', 'static', 'app.js'),
              encoding='utf-8').read()
    for const in ('EXAMPLE_FASTA', 'EXAMPLE_SET_FASTA', 'EXAMPLE_TREE_NWK',
                  'EXAMPLE_GENBANK_GB', 'EXAMPLE_SYNTENY_GBS',
                  'EXAMPLE_CONSERVED_FASTA'):
        check(const in js, f'app.js 定义 {const}')

    # 示例文件齐全
    need = ['example_viral_contigs.fasta', 'example_virus_set.fasta',
            'example_conserved_set.fasta', 'example_tree.nwk',
            'example_genome.gb'] + \
        [f'example_synteny_{x}.gb' for x in 'ABC']
    for fn in need:
        check(os.path.isfile(os.path.join(EX, fn)), f'示例文件存在: {fn}')

    # ---------- 2. 关键 API ----------
    print('--- 关键 API ---', flush=True)
    for api in ('/api/tools', '/api/dbs', '/api/samples', '/api/queue',
                '/api/ictv/cascade',
                '/api/settings', '/api/tool/runs', '/api/msa/samples',
                '/api/ncbi/collections', '/api/gb/collections',
                '/api/submit/tables', '/api/submit/contig_runs',
                '/api/meta/collections', '/api/logan/jobs',
                '/api/dl/batches', '/api/tool/viral_contigs?run=x'):
        r = c.get(api)
        check(r.status_code in (200, 400), f'GET {api} -> {r.status_code}'
              + ('（空参数 400 属预期）' if r.status_code == 400 else ''))

    # ---------- 3. 既有样品报告 ----------
    print('--- 样品报告 ---', flush=True)
    r = c.get('/api/samples')
    samples = [x['name'] for x in r.get_json()]
    check(len(samples) > 0, f'样品列表 {len(samples)} 个')
    for s in samples:
        r = c.get(f'/report/{s}/')
        if r.status_code == 200:
            check(True, f'样品 {s} 报告可访问')
            break
    else:
        print('  SKIP（无样品带报告）')

    # ---------- 3a. contigs 卡：Krona 前置 / 宿主筛选与自动预测 / ID 复制 / 跳转 ----
    hv = c.get('/tools?g=virus').get_data(as_text=True)
    # Krona 旭日块已并入分类报告折叠区（summary=分类旭日图（可下钻））。
    # 报告区顺序（2026-09-09 用户确认）：分类表 → contig 明细 → 宿主预测统计 → 旭日图
    # 注：宿主预测统计在 contig 明细下方是用户明确要求（DEVELOPMENT_NOTES 五十五）；
    #     旭日图并入折叠区后排在最后，故断言为 det < host < sun。
    _i_host = hv.find('id="hostRptSec"')
    _i_det = hv.find('病毒序列分类（contig 明细）')
    _i_sun = hv.find('id="sunC"')
    check(0 < _i_det < _i_host < _i_sun,
          '报告区顺序：分类表 → contig 明细 → 宿主预测统计 → 旭日图')
    check(hv.count('<section class="card" id="t-contigs">') == 1
          and hv.count('<section class="card" id="t-assemble">') == 1,
          '④ contigs / ③ assemble 卡存在且唯一')
    check(hv.count('id="hostRptSec"') == 1, '宿主预测统计块唯一（无错插副本）')
    for marker, where in [("vEx('tmv')", '示例病毒 TMV'),
                          ("vEx('pstvd')", '示例病毒 PSTVd'),
                          ("vEx('mix')", '示例病毒 Mix All')]:
        check(marker in hv, f'病毒识别组渲染含 {where}')
    for fn in ('example_tmv.fasta', 'example_pvy.fasta', 'example_cmv.fasta',
               'example_pstvd.fasta', 'example_mix.fasta'):
        check(os.path.isfile(os.path.join(EX, fn)), f'Metabuli 示例病毒存在: {fn}')
    check('id="anaRun"' not in hv and 'id="anaRunLabel"' in hv,
          '分类表「选择运行」下拉已去除（自动跟随最新运行标签）')
    for marker, where in [('id="vcHostF"', '宿主筛选下拉'),
                          ('autoHostIfMissing', '宿主预测自动运行（无宿主列时自动触发）'),
                          ('copyContigSeq(', 'ID 点击复制序列'),
                          ('anaJump(', '四件套跳转注释分析'),
                          ('processAnaJump', '跳转自动续接')]:
        check(marker in hv, f'病毒识别组渲染含 {where}')
    ha = c.get('/tools?g=annotate').get_data(as_text=True)
    check(all(f"'{a}'" in ha for a in ('blastn', 'blastx', 'primer')),
          't-hom 卡含 BLASTN / BLASTX / Primer 分析')
    for marker in ('Best E-value', 'Conserved Domains', 'Primer design complete',
                   'ncbiCdd', 'ncbiNuc'):
        check(marker in ha, f'metabuli 风格结果渲染含 {marker}')

    # ---------- 3b. 模块历史运行组件（折叠/衔接/删除） ----------
    import os as _os
    # 工具工作台各组页渲染的是同一份 tools.html（卡片由前端按组显隐），
    # 故历史容器数直接从模板推导，避免硬编码数量随卡片增删而漂移。
    with open(_os.path.join(PLATFORM_ROOT, 'webapp', 'templates',
                            'tools.html'), encoding='utf-8') as _f:
        _n_rh = _f.read().count('class="rh" id="rh-')
    for pg, n in [('/tools?g=sample', _n_rh), ('/tools?g=compare', _n_rh),
                  ('/hostremoval', 1), ('/hostpredict', 1), ('/orf', 1),
                  ('/annotation', 1), ('/genome', 1), ('/primer', 1)]:
        h = c.get(pg).get_data(as_text=True)
        check(h.count('class="rh" id="rh-') == n, f'{pg} 历史容器 {n} 个')
    _os.makedirs(_os.path.join(PLATFORM_ROOT, 'run', 'tool_runs', 'it_rh_chk'),
                 exist_ok=True)
    r = c.post('/api/tool/runs/it_rh_chk/delete')
    check(r.status_code == 200
          and not _os.path.isdir(_os.path.join(PLATFORM_ROOT, 'run', 'tool_runs',
                                               'it_rh_chk')),
          '运行目录删除 API')
    r = c.post('/api/tool/runs/no_such_run/delete')
    check(r.status_code == 400, '删除不存在运行 400')

    # ---------- 3c. 导航项 ↔ 卡片一一对应 ----------
    # showModule() 只切换 <main> 的直接子元素（:scope > *）。若某个导航项
    # 对应的 id 不是 main 的直接子元素（例如被嵌在别的卡片里），点它就是
    # 空白页——2026-09-09 的 t-kvchain 正是如此（曾是 t-kvsuite 内的 div）。
    from html.parser import HTMLParser as _HP
    from vp.web.pages import NAV_GROUPS as _NAV

    class _MainKids(_HP):
        def __init__(self):
            super().__init__()
            self.depth = 0
            self.main_depth = None
            self.ids = set()

        def handle_starttag(self, tag, attrs):
            d = dict(attrs)
            if tag == 'main':
                self.main_depth = self.depth
            if (self.main_depth is not None
                    and self.depth == self.main_depth + 1 and d.get('id')):
                self.ids.add(d['id'])
            if tag not in ('br', 'img', 'input', 'meta', 'link', 'hr'):
                self.depth += 1

        def handle_endtag(self, tag):
            if tag not in ('br', 'img', 'input', 'meta', 'link', 'hr'):
                self.depth -= 1
            if tag == 'main':
                self.main_depth = None

    _mk = _MainKids()
    _mk.feed(hv)
    _want = {it['id'] for g in _NAV for it in g['items'] if it.get('id')}
    _missing = sorted(_want - _mk.ids)
    check(not _missing,
          f'导航项均有 <main> 直接子卡片（缺失: {_missing or "无"}）')

    # ---------- 3d. 基因组图谱：gbdraw 两子命令参数差异 ----------
    # gbdraw 0.14 的 circular / linear 参数集与取值集都不同，而前端 gb_opts
    # 是面向圈图语义的一套键（labels / track_type / species / label_placement…），
    # _run_gbdraw 必须按子命令翻译，否则 linear 报 unrecognized arguments
    # （退出码 2）→ 预览 / 出图 500。2026-09-09 用户实测踩到。
    try:
        import tempfile as _tf
        from vp.gbdraw_plot import _run_gbdraw as _rg
        _gopts = {'labels': 'out', 'track_type': 'tuckin', 'species': 'T',
                  'strain': 'S', 'feature_width': 20,
                  'multi_record_canvas': True, 'gc_content_width': 300,
                  'gc_skew_radius': 300, 'no_gc': True, 'no_skew': True,
                  'label_placement': 'horizontal'}
        _gp = _os.path.join(_tf.gettempdir(), 'vp_it_gbdraw', 'g')
        _made = _rg(gbk=_os.path.join(EX, 'example_genome.gb'),
                    out_prefix=_gp, mode='both', opts=_gopts)
        check(len(_made) == 2,
              f'gbdraw 圈图+线图双模式出图（前端全量参数），实际 {len(_made)} 张')
        with open(_made[0], encoding='utf-8', errors='replace') as _f:
            _svg = _f.read()
        check('hypothetical protein' in _svg,
              'gbdraw 出图含基因名（labels 翻译生效）')
    except Exception as _e:
        check(False, f'gbdraw 双模式出图失败: {_e}')

    # ---------- 3e. 内置示例体系 ----------
    # 所有模块都应能一键填示例；示例文件必须齐全，且与 UI 文案一致
    # （UI 写「CMV RNA1-3」「四病毒混合 6 条」，文件就必须是 3 段 / 6 条）。
    _exjs = open(_os.path.join(PLATFORM_ROOT, 'webapp', 'static',
                               'examples.js'), encoding='utf-8').read()
    check('CARD_EXAMPLES' in _exjs or 'var MAP' in _exjs,
          'examples.js 定义卡片示例映射')
    check('examples.js' in hv, '/tools 接入 examples.js')
    for _fn in ('example_R1.fastq.gz', 'example_R2.fastq.gz'):
        check(_os.path.isfile(_os.path.join(EX, _fn)), f'示例测序数据存在: {_fn}')
    from vp.utils import iter_fasta as _if
    _n_cmv = len(list(_if(_os.path.join(EX, 'example_cmv.fasta'))))
    _n_mix = len(list(_if(_os.path.join(EX, 'example_mix.fasta'))))
    check(_n_cmv == 3, f'CMV 示例含三分体（实际 {_n_cmv} 段）')
    check(_n_mix == 6, f'Mix All 示例含 6 条记录（实际 {_n_mix} 条）')

    # 示例结果 API（只读 databases/examples/results/，与真实结果隔离）
    _r = c.get('/api/examples')
    _ex = _r.get_json() or []
    check(_r.status_code == 200 and len(_ex) >= 10,
          f'示例结果清单可用（{len(_ex)} 个模块）')
    _r = c.get('/api/examples/orf')
    _files = (_r.get_json() or {}).get('files', []) if _r.status_code == 200 else []
    check(len(_files) > 0, f'示例结果详情可读（orf {len(_files)} 个产物）')
    _r = c.get('/api/examples/orf/03_assembly/summary.json')
    check(_r.status_code == 200, '示例结果单文件可取')

    # 在线工具（CDD / BLASTN·BLASTX）与 LOGAN 的示例也要有输入与产物
    check(_os.path.isfile(_os.path.join(EX, 'example_contig_1.fasta')),
          '单 contig 示例文件存在（CDD/BLAST 粘贴用）')
    check("cddSeqText: 'CONTIGS_TEXT'" in _exjs and
          "homSeqText: 'CONTIGS_TEXT'" in _exjs,
          't-cdd / t-hom 示例填入序列正文（textarea）')
    check("'t-cdd': 'cdd'" in _exjs and "'t-hom': 'hom'" in _exjs and
          "'/logan': 'logan'" in _exjs,
          'RESULT_MAP 覆盖 cdd / hom / logan')
    _r = c.get('/api/examples/logan')
    _lgan = (_r.get_json() or {}).get('files', []) if _r.status_code == 200 else []
    check(any(f['path'].endswith('.html') and f['kind'] == 'html'
              for f in _lgan),
          f'LOGAN 示例报告可按 html 内联预览（{len(_lgan)} 个产物）')
    _r = c.get('/api/examples/synteny')
    _syn = (_r.get_json() or {}).get('files', []) if _r.status_code == 200 else []
    check(any(f['path'].endswith('.png') for f in _syn) and
          any(f['path'].endswith('.html') for f in _syn),
          f'共线性比较示例含图与报告（{len(_syn)} 个产物）')
    _r = c.get('/api/examples/sdt')
    _sdt = (_r.get_json() or {}).get('files', []) if _r.status_code == 200 else []
    check(any(f['path'].endswith('.pdf') and f['kind'] == 'pdf' for f in _sdt)
          and any(f['path'].endswith('.png') and f['kind'] == 'image'
                  for f in _sdt),
          'PDF 单列 pdf（内嵌预览）且 PNG 仍为 image')
    _man = json.load(open(_os.path.join(EX, 'results', 'manifest.json'),
                          encoding='utf-8'))
    _missing = [m for m in _man
                if not _os.path.isdir(_os.path.join(EX, 'results', m))]
    check(not _missing, f'示例结果清单与目录一致（{len(_man)} 个模块）')
    check(len(_man) >= 26, f'示例结果覆盖 ≥26 个模块（实际 {len(_man)}）')

    # ---------- 3f. 本地比对引擎（离线：blastn / DIAMOND / mmseqs2） ----------
    from vp.local_search import engine_status as _eng_status
    _st = _eng_status()
    check(bool(_st.get('ok')), '本地 blastn 就绪（病毒参考核酸库 + BLAST+）')
    check(bool(_st.get('ok_blastx')), '本地 DIAMOND blastx 就绪（viral_prot.dmnd）')
    check(bool(_st.get('ok_cdd')), '本地 CDD 就绪（mmseqs2 + cdd_db）')
    check('cdd_engine' in hv and 'hom_engine' in hv and
          'value="local" selected' in hv,
          '前端可切换本地 / 在线引擎（cdd_engine / hom_engine）')
    _seq1 = ''.join(
        ln.strip() for ln in open(_os.path.join(EX, 'example_contig_1.fasta'),
                                  encoding='utf-8')
        if ln.strip() and not ln.startswith('>'))
    _r = c.get('/api/tool/analysis',
               query_string={'contig': 'example_contig_1', 'action': 'blastn',
                             'engine': 'local', 'seq': _seq1})
    _bl = _r.get_json() or {}
    check(_r.status_code == 200 and _bl.get('engine') == 'local' and
          len(_bl.get('hits') or []) > 0,
          f"本地 blastn 结果可经 API 读取（{len(_bl.get('hits') or [])} 条命中）")
    for _mod, _fn, _key in (('cdd', 'example_contig_1_cdd_local.json', 'coord'),
                            ('hom', 'example_contig_1_blastx_local.json', None)):
        _p = _os.path.join(EX, 'results', _mod, _fn)
        check(_os.path.isfile(_p), f'本地示例产物存在: {_mod}/{_fn}')
        _d = json.load(open(_p, encoding='utf-8'))
        check(_d.get('engine') == 'local' and len(_d.get('hits') or []) > 0,
              f"{_mod}/{_fn}: engine=local 且有命中"
              f"（{len(_d.get('hits') or [])} 条）")
        if _key:
            check(_d.get(_key) == 'nt' and _d.get('query_len'),
                  '本地 CDD 用核酸坐标（coord=nt + query_len）')

    # ---------- 4. 静态资源 ----------
    r = c.get('/static/app.js')
    check(r.status_code == 200, 'app.js 静态资源 200')
    r = c.get('/static/i18n.js')
    check(r.status_code == 200, 'i18n.js 静态资源 200')

    print('PLATFORM CHECKS PASSED', flush=True)


if __name__ == '__main__':
    main()
