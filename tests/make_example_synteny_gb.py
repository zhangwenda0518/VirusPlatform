# -*- coding: utf-8 -*-
"""把 3 个「共线性」示例 .gb 的 ORIGIN 从占位 N 改为**真实同源**的基因组序列。

问题：example_synteny_{A,B,C}.gb 的 ORIGIN 全是 N（设计上是为展示 CDS 基因
家族布局，CDS 的 /translation 蛋白是真实的，但基因组核苷酸是占位）。导致
「全长序列」路径（比对 / 基因组图谱）读到的 genome.fa 全是 N → 比对全 N。

本脚本：
  1) 以固定随机种子生成一条 ~3300bp、GC≈55% 的母序列；
  2) A = 母序列；B = 母序列 2% 替换；C = 母序列 8% 替换（三者同源 → 比对有意义）；
  3) 重写每个 .gb 的 ORIGIN 段（每组 10 bp、每行 60 bp、行首坐标）；
  4) 删除集合并重跑 extract_collection_features，重建 genome.fa / CDS.fa / PEP.fa。
     （PEP 优先取 /translation 真实蛋白，故共线性示例的基因家族不受影响。）

用法：python tests/make_example_synteny_gb.py
"""
from __future__ import annotations

import io
import os
import random
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EX = os.path.join(ROOT, 'examples')
GBS = [os.path.join(EX, f'example_synteny_{x}.gb') for x in 'ABC']


def _gen_len(path: str) -> int:
    for ln in io.open(path, encoding='utf-8'):
        if ln.startswith('LOCUS'):
            m = re.search(r'(\d+)\s+bp', ln)
            return int(m.group(1)) if m else 3300
    return 3300


def _revcomp(s: str) -> str:
    return s.translate(str.maketrans('ACGTacgt', 'TGCAtgca'))[::-1]


def _mutate(seq: str, rate: float, rng: random.Random) -> str:
    out = []
    for ch in seq:
        if rng.random() < rate:
            out.append(rng.choice('ACGT'))
        else:
            out.append(ch)
    return ''.join(out)


def _gb_origin(seq: str) -> str:
    """GenBank ORIGIN 格式：每组 10 bp、每行 60 bp、行首坐标。"""
    lines = ['ORIGIN']
    for start in range(0, len(seq), 60):
        chunk = seq[start:start + 60]
        groups = ' '.join(chunk[i:i + 10] for i in range(0, len(chunk), 10))
        lines.append(f'{start + 1:9d} {groups}')
    return '\n'.join(lines) + '\n//\n'


def _replace_origin(path: str, seq: str) -> None:
    txt = io.open(path, encoding='utf-8').read()
    i = txt.find('ORIGIN')
    if i < 0:
        raise RuntimeError(f'{path} 无 ORIGIN')
    before = txt[:i].rstrip('\n')
    new = before + '\n' + _gb_origin(seq)
    io.open(path, 'w', encoding='utf-8', newline='').write(new)


def main() -> int:
    lengths = [_gen_len(p) for p in GBS]
    print('各基因组长度:', dict(zip('ABC', lengths)))

    # 固定随机种子 → 可复现
    rng = random.Random(20260910)
    base_art = [rng.choice('ACGT') for _ in range(lengths[0])]
    # 提升 GC 含量到 ~55%（更像真病毒基因组）
    for i in range(len(base_art)):
        if rng.random() < 0.15:
            base_art[i] = rng.choice('CG')
    base = ''.join(base_art)

    genomes = {'A': base,
               'B': _mutate(base, 0.02, random.Random(11)),
               'C': _mutate(base, 0.08, random.Random(12))}

    # 等长化（B/C 突变不改变长度，无需补位）
    for k in GBS:
        name = 'A' if 'A' in os.path.basename(k) else ('B' if 'B' in os.path.basename(k) else 'C')
        s = genomes[name]
        if len(s) != lengths[0]:
            s = s[:lengths[0]].ljust(lengths[0], 'N')
        _replace_origin(k, s)
        print(f'  → {os.path.basename(k)} ORIGIN 已写真实序列（{len(s)} bp）')

    # 重建集合：整目录删掉 → 重新导入（会重新拷贝新的 .gb）→ 重跑特征提取
    from vp.gb_collection import (extract_collection_features, gb_collection_dir,
                                  import_local_gb)
    cdir = gb_collection_dir('EXAMPLE_SET')
    if os.path.isdir(cdir):
        shutil.rmtree(cdir, ignore_errors=True)
    print('  重新导入 EXAMPLE_SET（拷贝真实 .gb）…')
    import_local_gb('EXAMPLE_SET', GBS)
    summ = extract_collection_features('EXAMPLE_SET')
    gf = os.path.join(cdir, 'extract', 'genome.fa')
    if os.path.isfile(gf):
        from collections import Counter
        recs = {}
        name = None
        buf = []
        for ln in io.open(gf, encoding='utf-8'):
            ln = ln.rstrip('\n')
            if ln.startswith('>'):
                if name:
                    recs[name] = ''.join(buf)
                name = ln[1:].split()[0]
                buf = []
            else:
                buf.append(ln)
        if name:
            recs[name] = ''.join(buf)
        for n, s in recs.items():
            c = Counter(s)
            print(f'  genome.fa {n:20s} len={len(s)}  '
                  f'N占比={c.get("N", 0) / max(len(s), 1):.1%}  '
                  f'GC={100 * (c.get("G", 0) + c.get("C", 0)) / max(len(s), 1):.1f}%')

    from vp.gb_collection import collection_records
    n_rec = sum(1 for _ in collection_records('EXAMPLE_SET'))
    print(f'  集合重建完成：{n_rec} 条记录')
    return 0


if __name__ == '__main__':
    sys.exit(main())
