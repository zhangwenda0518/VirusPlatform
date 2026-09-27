# -*- coding: utf-8 -*-
"""给 docs/data 的 Info 表追加 Segment_std 列（用平台规范化规则）。

- 原始文件先备份为 <名>.bak_segmentstd；
- 列追加在末尾，其余列与行序原样保留（逐行文本处理，不重排引号）；
- 规范化用 norm_segment_ctx（Segment + Family + Molecule_type 上下文）。
"""

import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from Virus_Platform_Core.segment_norm import norm_segment_ctx  # noqa: E402

DATA = r'D:\桌面\C-host_classify\plant_virus_db_pipeline\docs\data'
TARGETS = [
    os.path.join(DATA, 'Plant_Virus_Full.Info.tsv'),
    os.path.join(DATA, 'Plant_Virus.complete_ref_info.tsv'),
    os.path.join(DATA, 'Plant_Virus_Ref.Info.tsv'),
]


def col_index(header):
    low = [h.strip().lstrip('#').lower() for h in header]
    def find(*names):
        for n in names:
            if n in low:
                return low.index(n)
        return None
    return (find('segment'), find('family'), find('molecule_type'),
            find('moleculetype'))


def main() -> int:
    for path in TARGETS:
        if not os.path.isfile(path):
            print('跳过（不存在）:', path)
            continue
        bak = path + '.bak_segmentstd'
        if not os.path.isfile(bak):
            shutil.copy2(path, bak)
        else:
            print('  备份已存在，沿用:', bak)
        with open(path, encoding='utf-8', errors='replace') as f:
            lines = f.read().split('\n')
        # 去掉末尾空行后处理，再统一补回
        trail = 0
        while lines and lines[-1] == '':
            lines.pop()
            trail += 1
        header = lines[0].split('\t')
        if col_index(header)[0] is None:
            print('跳过（无 Segment 列）:', path)
            continue
        i_seg, i_fam, i_mol = col_index(header)[:3]
        if i_seg is None:
            print('跳过（无 Segment 列）:', path)
            continue
        out = [lines[0] + '\tSegment_std']
        n = 0
        for line in lines[1:]:
            if not line:
                continue
            cols = line.split('\t')

            def at(idx):
                if idx is not None and idx < len(cols):
                    return cols[idx].strip()
                return ''

            std = norm_segment_ctx(at(i_seg), at(i_fam), at(i_mol))
            out.append(line + '\t' + std)
            n += 1
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write('\n'.join(out) + '\n')
        name = os.path.basename(path)
        print(f'✔ {name}: {n} 行已追加 Segment_std 列')
    print('DONE')
    return 0


if __name__ == '__main__':
    sys.exit(main())
