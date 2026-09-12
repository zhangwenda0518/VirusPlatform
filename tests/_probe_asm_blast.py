# -*- coding: utf-8 -*-
"""验证 ③组装 新增的 contig 级 BLASTN 回填 + viral_contigs.fasta 落盘。

做法：在临时样品目录里放一份现成的 spades/contigs.fasta，让 assemble_and_classify
走"复用已有组装结果"分支（不跑 SPAdes），只验证分类 + BLAST + 产物契约。
"""
import os
import sys
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from Virus_Platform_Core.config import DIRS, get_config  # noqa: E402
from Virus_Platform_Core.utils import safe_open  # noqa: E402


def main():
    sample = os.path.join(DIRS['results'], 'probe_asm_blast')
    shutil.rmtree(sample, ignore_errors=True)
    a_dir = os.path.join(sample, '03_assembly', 'spades')
    os.makedirs(a_dir, exist_ok=True)
    src = os.path.join('examples', 'example_viral_contigs.fasta')
    shutil.copyfile(src, os.path.join(a_dir, 'contigs.fasta'))

    from Virus_Platform_Core.assembly import assemble_and_classify
    cfg = get_config()
    res = assemble_and_classify(sample, src, None, cfg.databases['virus'],
                                mode='metaviral', threads=8, min_contig_len=500)
    print('n_viral =', len(res.get('viral_contigs') or []))

    vt = os.path.join(sample, '03_assembly', 'virus_contigs.tsv')
    vf = os.path.join(sample, '03_assembly', 'viral_contigs.fasta')
    cb = os.path.join(sample, '03_assembly', 'contig_blast.tsv')
    print('viral_contigs.fasta 存在:', os.path.isfile(vf))
    print('contig_blast.tsv 存在:', os.path.isfile(cb))
    with safe_open(vt) as f:
        lines = f.read().strip().splitlines()
    print('表头:', lines[0])
    for ln in lines[1:]:
        print('  ', ln)
    hdr = lines[0].split('\t')
    assert 'blast_top_hit' in hdr and 'blast_species' in hdr, hdr
    filled = [ln for ln in lines[1:] if ln.split('\t')[5]]
    print(f'blast_top_hit 非空 {len(filled)}/{len(lines) - 1} 行')
    assert os.path.isfile(vf), 'viral_contigs.fasta 未落盘'
    shutil.rmtree(sample, ignore_errors=True)
    print('OK（临时样品已清理）')


if __name__ == '__main__':
    main()
