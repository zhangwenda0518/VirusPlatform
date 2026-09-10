# -*- coding: utf-8 -*-
"""合并前的一致性核对：旧路径(P3_GLOBAL+designPrimers) vs 新引擎(primer_design)。

匹配 product_range=300-1500、num_return=3 后应给出同一批引物对；
若一致，说明"换引擎"不会改变管线⑧的既有产物。
"""
import os
import sys
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vp.utils import iter_fasta  # noqa: E402

fa = os.path.join('examples', 'example_viral_contigs.fasta')
seqs = [(h.split()[0], s.upper()) for h, s in iter_fasta(fa)]
random.seed(11)
seqs.append(('random', ''.join(random.choice('ACGT') for _ in range(2000))))

import primer3  # noqa: E402

# 合并前的管线参数表（vp/primer.P3_GLOBAL，已随合并移除）。
# 这里内联保留，作为"换引擎不改变产物"的对照基线。
LEGACY_P3_GLOBAL = {
    'PRIMER_OPT_SIZE': 20, 'PRIMER_MIN_SIZE': 18, 'PRIMER_MAX_SIZE': 24,
    'PRIMER_OPT_TM': 60.0, 'PRIMER_MIN_TM': 57.0, 'PRIMER_MAX_TM': 63.0,
    'PRIMER_MIN_GC': 40.0, 'PRIMER_MAX_GC': 60.0,
    'PRIMER_MAX_POLY_X': 4,
    'PRIMER_PRODUCT_SIZE_RANGE': [[300, 1500]],
    'PRIMER_NUM_RETURN': 3,
    'PRIMER_EXPLAIN_FLAG': 1,
    'PRIMER_PICK_LEFT_PRIMER': 1, 'PRIMER_PICK_RIGHT_PRIMER': 1,
    'PRIMER_PICK_INTERNAL_OLIGO': 0,
}


def old_way(name, seq, num_return=3):
    opts = dict(LEGACY_P3_GLOBAL)
    opts['PRIMER_NUM_RETURN'] = num_return
    if len(seq) < 300:
        opts['PRIMER_PRODUCT_SIZE_RANGE'] = [[60, max(len(seq), 80)]]
    import warnings
    with warnings.catch_warnings():
        warnings.simplefilter('ignore')
        res = primer3.bindings.designPrimers(
            {'SEQUENCE_ID': name[:40], 'SEQUENCE_TEMPLATE': seq}, opts)
    out = []
    for i in range(res.get('PRIMER_PAIR_NUM_RETURNED', 0)):
        out.append((res.get(f'PRIMER_LEFT_{i}_SEQUENCE', ''),
                    res.get(f'PRIMER_RIGHT_{i}_SEQUENCE', ''),
                    res.get(f'PRIMER_PAIR_{i}_PRODUCT_SIZE', 0),
                    round(res.get(f'PRIMER_LEFT_{i}_TM', 0), 1),
                    round(res.get(f'PRIMER_RIGHT_{i}_TM', 0), 1),
                    round(max(res.get(f'PRIMER_LEFT_{i}_SELF_ANY_TH', 0),
                              res.get(f'PRIMER_RIGHT_{i}_SELF_ANY_TH', 0)), 1),
                    round(max(res.get(f'PRIMER_LEFT_{i}_HAIRPIN_TH', 0),
                              res.get(f'PRIMER_RIGHT_{i}_HAIRPIN_TH', 0)), 1)))
    return out


def new_way(name, seq, num_return=3):
    """合并后的真实入口：vp.primer.design_primers_for_seq（内部走 primer_design）。"""
    from vp.primer import design_primers_for_seq
    out = []
    for p in design_primers_for_seq(name, seq, num_return=num_return):
        out.append((p['F_seq'], p['R_seq'], p['product'], round(p['F_tm'], 1),
                    round(p['R_tm'], 1), round(p['self_any_max'], 1),
                    round(p['hairpin_max'], 1)))
    return out


allsame = True
for name, seq in seqs:
    a, b = old_way(name, seq), new_way(name, seq)
    same = a == b
    allsame &= same
    print(f'{name} ({len(seq)}bp): 旧 {len(a)} 对 / 新 {len(b)} 对 → '
          + ('一致 ✔' if same else '不一致 ✘'))
    if not same:
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else None
            y = b[i] if i < len(b) else None
            print('   旧:', x)
            print('   新:', y)
print('\n全部一致' if allsame else '\n存在差异（需在合并时决定口径）')
