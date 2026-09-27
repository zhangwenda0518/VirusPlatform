# -*- coding: utf-8 -*-
"""矫正鉴定库 ref_info 的 Segment 值（原位规范化，带备份）。

对 databases/virusref_db/{pv_full,pv_complete}/reference.ref_info.tsv：
  - Segment 列原位规范化（307 种原始写法 → 受控词表）；
  - 家族/分子类型上下文从 docs/data 全库 Info 按 accession 精确取；
  - 原文件备份为 .bak_segmentstd。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from Virus_Platform_Core.segment_norm import norm_segment_ctx  # noqa: E402
from Virus_Platform_Core.config import DIRS  # noqa: E402

DATA = os.path.join('D:', os.sep, '桌面', 'C-host_classify',
                    'plant_virus_db_pipeline', 'docs', 'data')
LIBS = [
    os.path.join(DIRS['virus_src'], 'pv_full', 'reference.ref_info.tsv'),
    os.path.join(DIRS['virus_src'], 'pv_complete', 'reference.ref_info.tsv'),
]


def build_acc_context():
    """accession(去版本号) → (family, molecule)。"""
    import polars as pl
    ctx = {}
    src = os.path.join(DATA, 'Plant_Virus_Full.Info.tsv')
    if os.path.isfile(src):
        df = pl.read_csv(src, separator='\t', infer_schema_length=0,
                         truncate_ragged_lines=True)
        for acc, fam, mol in zip(df['Accession'].to_list(),
                                 df['Family'].to_list(),
                                 df['Molecule_type'].to_list()):
            key = (acc or '').split('.')[0]
            if key and key not in ctx:
                ctx[key] = (fam or '', mol or '')
    return ctx


def main() -> int:
    acc_ctx = build_acc_context()
    print(f'accession 上下文条目: {len(acc_ctx)}')
    for path in LIBS:
        if not os.path.isfile(path):
            print('跳过（不存在）:', path)
            continue
        bak = path + '.bak_segmentstd'
        if not os.path.isfile(bak):
            shutil.copy2(path, bak)
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
        while lines and lines[-1] == '':
            lines.pop()
        header = lines[0].split('\t')
        low = [h.strip().lower() for h in header]
        i_acc = low.index('accession')
        i_seg = low.index('segment')
        out = [lines[0]]
        n_fixed = 0
        for line in lines[1:]:
            cols = line.split('\t')
            if len(cols) <= i_seg:
                out.append(line)
                continue
            acc = cols[i_acc].strip()
            fam, mol = acc_ctx.get(acc.split('.')[0], ('', ''))
            fixed = norm_segment_ctx(cols[i_seg].strip(), fam, mol)
            if fixed != cols[i_seg].strip():
                n_fixed += 1
            cols[i_seg] = fixed
            out.append('\t'.join(cols))
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(out) + '\n')
        name = os.path.basename(os.path.dirname(path))
        print(f'OK {name}: 矫正 {n_fixed} 个 Segment 值')
    return 0


if __name__ == '__main__':
    sys.exit(main())
