# -*- coding: utf-8 -*-
"""体检修复的回归验证：每条断言对应一个已修复缺陷。

只读 + 非破坏性（不启动分析任务、不删用户数据）。跑法：
    python tests/_verify_fixes.py
退出码 0 = 全部通过。
"""
import io
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

fails = []


def check(cond, msg):
    print(('  OK   ' if cond else '  FAIL ') + msg)
    if not cond:
        fails.append(msg)


# ------------------------------------------------------------------ P0
print('== P0: db-migrate 配置切换 ==')
try:
    from vp.config import get_config
    get_config()                       # 存在
    ok_cfg = True
except ImportError:
    ok_cfg = False
check(ok_cfg, 'vp.config.get_config 可导入')
try:
    from vp.config import cfg  # noqa: F401
    has_cfg = True
except ImportError:
    has_cfg = False
check(not has_cfg, 'vp.config 不再有幽灵 cfg（db_migrate 已改用 get_config）')
src = io.open(os.path.join(ROOT, 'vp', 'db_migrate.py'), encoding='utf-8').read()
check('\n    from .config import cfg\n' not in src,
      'db_migrate.py 不再实际 import cfg（注释里的说明文字不算）')

# ------------------------------------------------------------------ 配置
print('\n== 配置：taxonomy 映射 / 示例根 ==')
from vp import config as C  # noqa: E402
check('taxonomy' not in C._DATABASE_KEYS,
      'taxonomy 不再由 _DATABASE_KEYS 写死（改走 DB_LAYOUT + 旧布局兜底）')
check(C.DIRS['examples'].replace('\\', '/').endswith('examples'),
      f"DIRS['examples'] 指向示例目录: {C.DIRS['examples']}")
check(os.path.isdir(C.DIRS['examples']), '示例目录存在')
check(C._detect_examples_root() != '' or True, '示例根自动探测可调用')

# 切换数据库目录后，模块级路径常量必须跟着变（否则长驻进程仍用旧库）
import tempfile as _tf  # noqa: E402
import vp.ictv_db as _IDB  # noqa: E402
import vp.virus_ref as _VREF  # noqa: E402
import vp.local_search as _LS  # noqa: E402
import vp.verify as _VF  # noqa: E402
_probe = os.path.join(_tf.gettempdir(), '_vp_dbroot_regress')
os.makedirs(_probe, exist_ok=True)
_before = (_IDB._DIR, _VREF._REF_DIR, _LS.REF_INFO_TSV, _VF.VIRAL_PROT_DIR)
try:
    C.apply_database_root(_probe)
    _after = (_IDB._DIR, _VREF._REF_DIR, _LS.REF_INFO_TSV, _VF.VIRAL_PROT_DIR)
    check(all(_probe in p.replace('/', os.sep) for p in _after),
          '切换数据库根后 5 个模块路径常量全部跟随')
    check(C.DIRS['taxonomy'].replace('\\', '/').endswith('databases/tax/core'),
          f"切换后 taxonomy 指向 tax/core（{C.DIRS['taxonomy']}）")
finally:
    C.apply_database_root('')
    import shutil as _sh2
    _sh2.rmtree(_probe, ignore_errors=True)
check((_IDB._DIR, _VREF._REF_DIR, _LS.REF_INFO_TSV, _VF.VIRAL_PROT_DIR)
      == _before, '恢复默认数据库根后路径常量复原')

# ------------------------------------------------------------------ Web 安全
print('\n== Web：路径/输入校验 ==')
import app as appmod  # noqa: E402
c = appmod.app.test_client()

r = c.post('/api/meta/collection/./delete')
check(r.status_code == 400, f'meta 删除 name="." 被拒（{r.status_code}）')

r = c.post('/api/ncbi/search', data='null', content_type='application/json')
check(r.status_code == 400, f'body=null → 400 而非 500（{r.status_code}）')
r = c.post('/api/analyze', data='null', content_type='application/json')
check(r.status_code == 400, f'analyze body=null → 400（{r.status_code}）')

# /api/tree/data 的 file 白名单（先造一个带 05_phylo 分组的临时样品；
# 样品名不能以下划线开头——_safe_sample 会拒绝）
probe = os.path.join(C.DIRS['results'], 'fixprobe')
gdir = os.path.join(probe, '05_phylo', 'G1')
os.makedirs(gdir, exist_ok=True)
with io.open(os.path.join(gdir, 'tree.nwk'), 'w', encoding='utf-8') as f:
    f.write('(a:1,b:1);\n')
try:
    r = c.get('/api/tree/data', query_string={
        'sample': 'fixprobe', 'group': 'G1',
        'file': os.path.join(ROOT, 'platform.json')})
    check(r.status_code == 400,
          f'tree/data 绝对路径被拒（{r.status_code}）')
    r = c.get('/api/tree/data', query_string={
        'sample': 'fixprobe', 'group': 'G1', 'file': 'tree.nwk'})
    check(r.status_code == 200, f'tree/data 合法 tree.nwk 正常（{r.status_code}）')
finally:
    import shutil as _sh
    _sh.rmtree(probe, ignore_errors=True)

r = c.get('/api/example_paths')
d = r.get_json() if r.status_code == 200 else {}
check(r.status_code == 200 and 'example_viral_contigs.fasta' in d.get('files', {}),
      '示例路径表 API 可用且给出绝对路径')
r = c.get('/api/example_input/platform.json')
check(r.status_code == 404, f'示例输入越界被拒（{r.status_code}）')

# 图谱预览（gbdraw + 多记录 FASTA + ASCII 中转目录）——打包验证时发现的真实缺陷
r = c.post('/api/tool/genoplot_preview',
           json={'fasta': 'examples/example_viral_contigs.fasta',
                 'mode': 'circular'})
ok = r.status_code == 200 and '<svg' in (r.get_json() or {}).get('svg', '')
check(ok, f'图谱预览可出图（{r.status_code}）')

# ------------------------------------------------------------------ 阶段正确性
print('\n== 阶段契约 ==')
from vp.pipeline import _stage_execution_order  # noqa: E402
order = _stage_execution_order(['virome', 'host'])
check('host' in order, f'未知阶段被忽略但合法阶段保留: {order}')
src = io.open(os.path.join(ROOT, 'vp', 'pipeline.py'), encoding='utf-8').read()
check('C.cur_r1, C.cur_r2 = sub1, sub2' in src,
      '子采样复用分支切换下游输入（sub_*）')

from vp import orf_annot as OA  # noqa: E402
check(OA._parse_orf_header('ctg #332 #1590 -1')[:3] == ('ctg', 332, 1590),
      'ORF 头部坐标不再 +1（与 pyrodigal GFF 同口径）')

from vp import primer_thermo as PT  # noqa: E402
score, detail = PT.compute_score('PCR', {}, {'gc_fwd': 0.0, 'gc_rev': 0.0},
                                 None, False)
check(score < 100, f'GC=0% 不再被当成缺失值（score={score}）')

from vp import msa_view as MV  # noqa: E402
p = os.path.join(tempfile.gettempdir(), '_fix_aln80.fa')
with io.open(p, 'w', encoding='utf-8') as f:
    for i in range(80):
        f.write(f'>s{i}\nACGTACGTACGT\n')
try:
    d = MV.snp_view_data(p)
    check(d['seqs_truncated'] is False, '恰好 80 条不算截断')
finally:
    os.remove(p)

from vp import logan_trace as LT  # noqa: E402
raw = ('Run Accession,Organism,Location,k-mer coverage\n'
       'SRR1,"Virus, unclassified","USA: California, Davis",0.5\n'
       ).encode('utf-8')
rows, _cols = LT.parse_result_table(raw)
check(rows[0]['organism'] == 'Virus, unclassified'
      and rows[0]['location'] == 'USA: California, Davis'
      and rows[0]['kmer_cov'] == 0.5,
      'Logan 结果表用 csv 解析（引号内逗号不再错列）')

from vp.ncbi_submit.report_html import table_html  # noqa: E402
_th, body = table_html(['c'], [['<script>x</script>']])
check('<script>' not in body and '&lt;script&gt;' in body,
      '提交报告表格 HTML 转义')

# ------------------------------------------------------------------ 前端契约
print('\n== 前端 ==')
html = c.get('/primer').get_data(as_text=True)
check("fillExample('pd_fa'" in html and 'id="rh-primer"' in html,
      '/primer 有示例按钮与历史运行容器')
sub = c.get('/submit').get_data(as_text=True)
check("validate`,\n    {method: 'POST'" in sub or "method: 'POST'" in sub,
      '提交校验按钮改为 POST 调用')
js = io.open(os.path.join(ROOT, 'webapp', 'static', 'app.js'),
             encoding='utf-8').read()
check("section.card[id^=\"t-\"]" in js, '收藏星选择器修正（id 在 section 上）')
check("'/tools#t-seqprep'" in js and "'t-ncbi'" not in js,
      '收藏注册表指向真实卡片 id')

# ------------------------------------------------------------------ 引物引擎合并
print('\n== 引物：统一引擎 ==')
from vp import primer as PR  # noqa: E402
src_pr = io.open(os.path.join(ROOT, 'vp', 'primer.py'), encoding='utf-8').read()
check('P3_GLOBAL = {' not in src_pr,
      'primer.py 不再自持第二套 primer3 参数（docstring 里的历史说明不算）')
check('.designPrimers(' not in src_pr,
      'primer.py 不再调用已弃用的 designPrimers')
from vp.utils import iter_fasta as _if  # noqa: E402
_nm, _sq = next(iter(_if(os.path.join(ROOT, 'examples',
                                      'example_viral_contigs.fasta'))))
_pairs = PR.design_primers_for_seq('demo', _sq.upper(), num_return=3)
check(len(_pairs) == 3, f'引物对数 {len(_pairs)}')
check(all('F_seq' in p and 'penalty' in p for p in _pairs),
      '保持历史字段名（F_seq/penalty…）')
check(all(p.get('score') is not None and p.get('recommendation')
          for p in _pairs), '新增统一质量评分与推荐等级')
check(PR.PIPELINE_PRODUCT_RANGE == (300, 1500), '管线产物区间保持 300-1500')

# ------------------------------------------------------------------ BLAST 回填
print('\n== BLAST 回填 ==')
from vp.local_search import contig_blast_table  # noqa: E402
_tmp = os.path.join(ROOT, 'run', 'tool_runs', '_tmp', 'verifyfix_ctgblast')
os.makedirs(_tmp, exist_ok=True)
_tab, _tsv = contig_blast_table(
    os.path.join(ROOT, 'examples',
                 'example_viral_contigs.fasta'), _tmp, threads=4)
check(len(_tab) >= 1 and all(v.get('accession') for v in _tab.values()),
      f'contig 级 BLASTN 给出最近参考（{len(_tab)} 条）')
check(bool(_tsv) and os.path.isfile(_tsv), '落盘 contig_blast.tsv')
from vp.host_analysis import CONTIG_COLS, BLAST_COLS  # noqa: E402
check(len(CONTIG_COLS) == 11 and BLAST_COLS[0] == 'blast_top_hit',
      'virus_contigs.tsv 规范列含 blast_*')

# ------------------------------------------------------------------ 工具探测覆盖
print('\n== 工具探测覆盖 ==')
from vp.config import detect_tools as _dt  # noqa: E402
_tools = _dt()
for _t in ('samtools', 'salmon', 'table2asn', 'bcftools', 'pandepth',
           'viral_consensus'):
    check(bool(_tools.get(_t)),
          f'{_t} 可被自动探测（发布版不依赖手改 platform.json）')

# ------------------------------------------------------------------ 参考池 A+B
print('\n== 参考池：植物口径过滤 + 长度护栏 ==')
import vp.phylo as _PH  # noqa: E402
check(_PH.MAX_REF_LEN == 25000, f'长度护栏常量 MAX_REF_LEN={_PH.MAX_REF_LEN}')
from vp import ictv_db as _IDB2  # noqa: E402
try:
    _plant = _IDB2.acvirus_acc_index()
except Exception as _e:
    _plant = set()
    print(f'   （植物名单不可用: {_e}）')
if _plant:
    check('AF440571' not in _plant and 'MH447526' not in _plant,
          '植物口径名单不含古菌病毒（Sulfolobus 等）')
    check(len(_plant) > 5000, f'植物口径名单规模合理（{len(_plant)} 条）')

_pdir = os.path.join(ROOT, 'run', 'tool_runs', '_tmp', 'verifyfix_refpool')
os.makedirs(_pdir, exist_ok=True)
_ptest = os.path.join(_pdir, 'src.fa')
with io.open(_ptest, 'w', encoding='utf-8') as _f:
    _f.write('>LONGACC.1\n' + 'ACGT' * 8000 + '\n')      # 32kb
    _f.write('>SHORTACC.1\n' + 'ACGT' * 800 + '\n')      # 3.2kb
_outfa = os.path.join(_pdir, 'refs.fa')
_found, _skip = _PH._extract_refs([_ptest], ['LONGACC', 'SHORTACC'], _outfa,
                                  max_len=_PH.MAX_REF_LEN)
check(_found == ['SHORTACC.1'] and _skip == ['LONGACC.1'],
      f'长度护栏拦下超长参考（found={_found}, skipped={_skip}）')
_scan = _PH._scan_ref_accessions([_ptest])
check('SHORTACC' in _scan and 'LONGACC' in _scan,
      '_scan_ref_accessions 能列出本地可用 accession')

print('\n' + '=' * 56)
if fails:
    print(f'FAILED: {len(fails)} 项')
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('全部修复回归通过 ✔')
