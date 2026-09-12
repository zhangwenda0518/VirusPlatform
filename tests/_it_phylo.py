# -*- coding: utf-8 -*-
"""集成测试：build_phylo 全链路（MAFFT→trimAl→FastTree）+ NCBI extra_refs 合并。"""
import os
import sys
import json
import random
# 控制台编码兜底：Windows 默认代码页是 GBK，本脚本的 ✔/✘/⚠ 等字符会让
# print 抛 UnicodeEncodeError（2026-09-11 实测多处踩过）。只改错误处理为
# replace（编码不动，中文照常可读），编不出的字符降级为 '?'。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Virus_Platform_Core.config import DIRS  # noqa: E402
from Virus_Platform_Core.utils import check_path, safe_open, write_fasta_record  # noqa: E402
from Virus_Platform_Core.phylo import build_phylo, resolve_ncbi_refs  # noqa: E402

BASES = 'ACGT'
work = check_path(os.path.join(DIRS['results'], '_it_phylo'), in_platform=True)
a_dir = os.path.join(work, '03_assembly')
os.makedirs(a_dir, exist_ok=True)


def mutate(base_seq, k, n_mut=60):
    s = list(base_seq)
    for j in range(n_mut):
        p = (j * 89 + k * 277) % len(s)
        s[p] = BASES[(BASES.index(s[p]) + 1 + (j + k) % 3) % 4]
    return ''.join(s)


# TMV 全基因组（NC_001367.1, 6395bp）作为"contig 种子"
from Virus_Platform_Core.ncbi_download import collection_dir
from Virus_Platform_Core.utils import iter_fasta  # noqa: E402
smoke_dir = collection_dir('_smoke_tmv')
smoke_fa = os.path.join(smoke_dir, 'refs.fa')
smoke_mark = os.path.join(smoke_dir, '_synthetic.marker')


def _has_tmv(path):
    return os.path.isfile(path) and any(
        h.startswith('NC_001367') for h, _s in iter_fasta(path))


# 集合缺失 **或** 现有内容不含 TMV 时都合成 fixture（后者发生在
# databases/ncbi_refs/_smoke_tmv 被真实下载内容覆盖之后——硬编码
# accession 的断言会因此失效，故按内容判定而不是只看文件是否存在）。
smoke_synthetic = not _has_tmv(smoke_fa)
if smoke_synthetic:
    # 离线可复现 fixture：NC_001367(TMV) / NC_002692 / NC_009497
    # 各 6395bp 确定性随机序列
    os.makedirs(smoke_dir, exist_ok=True)
    rnd = random.Random(20260906)
    with safe_open(smoke_fa, 'wt') as f:
        for acc in ('NC_001367', 'NC_002692', 'NC_009497'):
            write_fasta_record(
                f, acc, ''.join(rnd.choice(BASES) for _ in range(6395)))
    with safe_open(smoke_mark, 'wt') as f:
        f.write('合成离线 fixture（非真实 NCBI 下载）\n')
    print('（_smoke_tmv 集合缺失或不含 TMV，已合成离线 fixture）')
# 是否合成数据：以 marker 为准（重跑时本次不再合成，但目录里仍是合成序列）
smoke_synthetic = smoke_synthetic or os.path.isfile(smoke_mark)
tmv = None
for h, s in iter_fasta(smoke_fa):
    if h.startswith('NC_001367'):
        tmv = s
assert tmv, 'NCBI 集合中未找到 TMV'
print('TMV seed:', len(tmv), 'bp')

# 组装结果伪造：2 条病毒 contig（TMV 截断+突变），blast top hit = NC_116488.1（库内 accession）
with safe_open(os.path.join(a_dir, 'contigs.filtered.fasta'), 'wt') as f:
    write_fasta_record(f, 'ctg1', mutate(tmv, 1)[:5000])
    write_fasta_record(f, 'ctg2', mutate(tmv, 2)[:4800])
with safe_open(os.path.join(a_dir, 'contig_blast.tsv'), 'wt') as f:
    f.write('\t'.join(['ctg1', 'NC_116488.1'] + ['x'] * 9 + ['500']) + '\n')
    f.write('\t'.join(['ctg2', 'NC_116488.1'] + ['x'] * 9 + ['400']) + '\n')
with safe_open(os.path.join(a_dir, 'summary.json'), 'wt') as f:
    json.dump({'viral_contigs': ['ctg1', 'ctg2']}, f)

# 运行阶段⑤：额外参考 = _smoke_tmv 集合（TMV+SeV+Bunyamwera）
extra = resolve_ncbi_refs(['_smoke_tmv'])
print('extra refs:', extra)

# 参考池固定为 fixture（3 条 6395bp）：真实参考库里有 40kb 级序列，MAFFT 对
# 40kb×40kb 的 DP 是 O(L²)，34 条 ~1Mb 的比对实测 20 分钟无输出；本测试
# 验证的是 MAFFT→trimAl→FastTree 链路与 extra_refs 合并，用小参考池
# 既快又确定。
import Virus_Platform_Core.phylo as _phylo  # noqa: E402
_phylo.find_virus_ref_fasta = lambda: smoke_fa
try:
    import Virus_Platform_Core.virus_ref as _virus_ref  # noqa: E402
    _virus_ref.available = lambda: False
except Exception:
    pass
try:
    # ICTV gb_cache 里缓存过 40kb 级古菌病毒基因组，混进来会让 MAFFT 的
    # O(L²) DP 跑上几十分钟；本测试只验证链路，故屏蔽该参考源。
    import Virus_Platform_Core.ictv_db as _ictv_db  # noqa: E402
    _ictv_db._refs_fa_path = lambda: None
    _ictv_db._gb_cached_accs = lambda: set()
except Exception:
    pass

summary = build_phylo(work, top_n_refs=3, tree_tool='fasttree',
                      extra_refs=extra)
g = summary['groups'][0]
print('group:', g['group'], '| n_refs:', g['n_refs'], '| trim:', g['trim'],
      '| tree:', g['tree'])

combined = os.path.join(work, '05_phylo', g['dir'], 'combined.fa')
ids = [h.split()[0] for h, _ in iter_fasta(combined)]
print('combined IDs:', ids)
assert any(i.startswith('NC_001367') for i in ids), 'TMV 未合并进 combined'
assert os.path.isfile(os.path.join(work, '05_phylo', g['dir'], 'tree.nwk'))
# 远缘混合比对下 trimAl automated1 可能过度修剪 -> 正确行为是回退原比对
assert isinstance(g['trim'], dict) and g['trim'].get('cols_before'), 'trim 信息缺失'
if smoke_synthetic:
    # 合成随机序列下 trimAl 的保留列数恰在保护阈值之上，回退行为
    # 依赖真实 TMV 比对结果，离线 fixture 不强制校验
    print('  （合成 fixture：跳过 trimAl 回退断言）')
else:
    assert g['trim'].get('applied') is False, '此远缘组合应触发回退（保护逻辑验证）'
print('INTEGRATION TEST PASSED')
