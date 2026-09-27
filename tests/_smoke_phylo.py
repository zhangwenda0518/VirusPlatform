# -*- coding: utf-8 -*-
"""冒烟测试：MAFFT -> trimAl -> FastTree / RAxML-NG 链路（合成小比对）。

合成序列用固定算术规则生成（非随机），保证可复现且无随机性告警。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Virus_Platform_Core.config import PLATFORM_ROOT, get_config  # noqa: E402
from Virus_Platform_Core.phylo import (_run_mafft, _run_trimal, _run_fasttree,  # noqa: E402
                      _run_raxml_ng, _parse_raxml_log, _raxml_threads,
                      RAXML_NG_THREAD_CAP)
from Virus_Platform_Core.utils import check_path, write_fasta_record, safe_open  # noqa: E402

BASES = 'ACGT'


def mutate(base_seq, k):
    """第 k 个变体：按固定步长替换 ~80 个位点，确定性生成。"""
    s = list(base_seq)
    n = len(s)
    for j in range(80):
        p = (j * 97 + k * 311) % n
        s[p] = BASES[(BASES.index(s[p]) + 1 + (j + k) % 3) % 4]
    return ''.join(s)


work = check_path(os.path.join(PLATFORM_ROOT, 'run', 'results', '_smoke_phylo'),
                  in_platform=True)
os.makedirs(work, exist_ok=True)

base = ''.join(BASES[(i * i + i // 3) % 4] for i in range(1500))
with safe_open(os.path.join(work, 'seqs.fa'), 'wt') as f:
    write_fasta_record(f, 'WT_ref', base)
    for i in range(1, 6):
        write_fasta_record(f, f'variant_{i}', mutate(base, i))

cfg = get_config()
print('tools:', {k: cfg.tools.get(k) for k in ('mafft', 'trimal', 'gblocks',
                                              'fasttree', 'raxml-ng')})

aln = check_path(os.path.join(work, 'aln.fasta'))
_run_mafft(check_path(os.path.join(work, 'seqs.fa')), aln, threads=4)
with safe_open(aln) as f:
    print('MAFFT OK, first seq line length:',
          len(f.readlines()[1].strip()))

aln_trim = check_path(os.path.join(work, 'aln.trim.fasta'))
aln_used, trim_info = _run_trimal(aln, aln_trim)
print('trimAl:', trim_info, '->', os.path.basename(aln_used))

t1 = check_path(os.path.join(work, 'tree.nwk'))
_run_fasttree(aln_used, t1)
with safe_open(t1) as f:
    print('FastTree OK:', f.read()[:80], '...')

pf = check_path(os.path.join(work, 'raxml'))
nwk = _run_raxml_ng(aln_used, pf, threads=4)
with safe_open(nwk) as f:
    print('RAxML-NG OK:', f.read()[:80], '...')
print('raxml log parse:', _parse_raxml_log(pf))

# ---- 负控：RAxML-NG 的两条护栏必须「不护栏就真的坏」才值得存在 ----
# ① <4 条序列：RAxML-NG 硬性要求 ≥4（报 "less than 4 sequences"），
#    平台侧提前降级（分析管道→NJ、集合建树→FastTree）
three = check_path(os.path.join(work, 'three.fa'))
with safe_open(three, 'wt') as f:
    write_fasta_record(f, 'a', base)
    write_fasta_record(f, 'b', mutate(base, 1))
    write_fasta_record(f, 'c', mutate(base, 2))
try:
    _run_raxml_ng(three, check_path(os.path.join(work, 'three_x')), threads=4)
    raise SystemExit('负控失败：RAxML-NG 竟然接受了 3 条序列')
except Exception as e:
    print('3-taxon negative control OK（按预期失败）:', str(e)[:70])

# ② 全 N 无信息比对：所有列完全不确定 → 似然恒 0，触发底层 pll 断言崩溃
#    （实测 exit 1536，合成集合 it_synteny 即此形态）；平台侧降级 FastTree
#    ——这里同时证明降级目标对同款数据可用
alln = check_path(os.path.join(work, 'alln.fa'))
with safe_open(alln, 'wt') as f:
    for nm in ('n1', 'n2', 'n3', 'n4'):
        write_fasta_record(f, nm, 'N' * 600)
try:
    _run_raxml_ng(alln, check_path(os.path.join(work, 'alln_x')), threads=4)
    raise SystemExit('负控失败：RAxML-NG 竟然接受了全 N 比对')
except Exception as e:
    print('all-N negative control OK（按预期失败）:', str(e)[:70])
alln_nwk = check_path(os.path.join(work, 'alln.nwk'))
_run_fasttree(alln, alln_nwk)
with safe_open(alln_nwk) as f:
    print('降级目标 FastTree 对全 N 比对可用:', f.read()[:60], '...')

# ③ 线程封顶：19 线程实测比 8 线程慢（见 phylo.RAXML_NG_THREAD_CAP 注释）
assert _raxml_threads(19) == RAXML_NG_THREAD_CAP, _raxml_threads(19)
assert _raxml_threads(2) == 2, _raxml_threads(2)
print('thread cap OK: 19 ->', _raxml_threads(19), '| 2 ->', _raxml_threads(2))
print('ALL SMOKE TESTS PASSED')
