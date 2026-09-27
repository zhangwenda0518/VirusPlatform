# -*- coding: utf-8 -*-
"""生成「进化树 + 基因组叠加」示例数据（Archaeopteryx.js genomeOverlay 的数据侧）。

产物（写进平台根 examples/，与 example_tree.nwk 同级）：
  examples/example_synteny_tree.nwk           3 叶 NJ 树；叶名 = 集合 accession，
                                              与 overlay 的 track 名一致（查看器按名匹配）
  examples/example_synteny_tree.overlay.json  {tracks, links}；属色带与基因家族配色
                                              由查看器自推（genusColors / famColor）

数据来源与口径（全部来自平台内置示例，不引入外部数据）：
  · 轨道 tracks：examples/example_synteny_{A,B,C}.gb 的 CDS
    （start / end / strand / product），cid 按 ORF 序共享（ORF1..ORF6 → F01..F06）；
  · 连线 links：同一 cid 的 /translation 蛋白逐对比对
    （identity = 相等字符数 / 较短长度 × 100，口径与 SDT 的"仅计可比位点"一致）；
    三对基因组 × 6 个家族 = 18 条；
  · 树：串联 CDS（三基因组同序等长，无需再比对）→ 平台 phylo 的 NJ
    （identity 距离，Saitou–Nei；与「③ 树查看」的 NJ 建树同一实现）。

确定性：无随机数，同一输入重复运行结论一致（NJ 无平局随机项）。

用法：python tests/make_example_overlay.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# 控制台编码兜底（Windows 默认代码页 GBK，本脚本的 →/· 会抛 UnicodeEncodeError）
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

from Bio import SeqIO                                   # noqa: E402

from Virus_Platform_Core import phylo                    # noqa: E402

EX = os.path.join(ROOT, 'examples')
ACCS = ['example_synteny_A', 'example_synteny_B', 'example_synteny_C']
GENUS = 'Potexvirus'
TREE_OUT = os.path.join(EX, 'example_synteny_tree.nwk')


def _identity(a: str, b: str):
    """两条等长/不等长蛋白的同一性（%）：仅计可比位点，口径同 SDT。"""
    n = min(len(a), len(b))
    if n == 0:
        return None
    hit = sum(1 for i in range(n) if a[i] == b[i])
    return round(100.0 * hit / n, 1)


def read_genome(acc: str):
    """→ (记录长度, 按起点排序的 CDS 列表)，CDS 带 cid / id / 蛋白序列。"""
    rec = SeqIO.read(os.path.join(EX, acc + '.gb'), 'genbank')
    genes = []
    for feat in rec.features:
        if feat.type != 'CDS':
            continue
        q = feat.qualifiers
        genes.append({
            'start': int(feat.location.start) + 1,       # 1-based，同 GenBank 展示
            'end': int(feat.location.end),
            'strand': '-' if feat.location.strand == -1 else '+',
            'product': (q.get('product') or [''])[0],
            'gene': (q.get('gene') or [''])[0],
            'prot': (q.get('translation') or [''])[0],
        })
    genes.sort(key=lambda g: g['start'])
    n_seq = len(rec.seq)
    out_of_range = [g for g in genes if g['start'] < 1 or g['end'] > n_seq]
    if out_of_range:
        raise RuntimeError(
            '%s: CDS 超出记录长度 %d bp → %s' % (
                acc, n_seq,
                ', '.join('%s..%s' % (g['gene'] or i + 1, g['end'])
                          for i, g in enumerate(out_of_range))))
    for i, g in enumerate(genes):
        g['cid'] = 'F%02d' % (i + 1)                     # 三基因组同序 ⇒ 同 cid 即同源家族
        g['id'] = '%s__%s' % (acc, g['gene'] or ('ORF%d' % (i + 1)))
    return rec, genes


def build_tracks(genomes):
    tracks = []
    for acc in ACCS:
        rec, genes = genomes[acc]
        tracks.append({
            'name': acc, 'acc': acc, 'genus': GENUS, 'length': int(len(rec.seq)),
            'genes': [{'id': g['id'], 'start': g['start'], 'end': g['end'],
                       'strand': g['strand'], 'product': g['product'],
                       'cid': g['cid']} for g in genes],
        })
    return tracks


def build_links(genomes):
    by = {acc: {g['cid']: g for g in genomes[acc][1]} for acc in ACCS}
    links = []
    for i, a in enumerate(ACCS):
        for b in ACCS[i + 1:]:
            for cid in sorted(by[a]):
                gb = by[b].get(cid)
                if not gb:
                    continue
                links.append({'q': by[a][cid]['id'], 't': gb['id'],
                              'ident': _identity(by[a][cid]['prot'], gb['prot'])})
    return links


def build_tree(genomes):
    """串联 CDS → NJ（identity 距离）。三基因组同序等长，无需先做 MSA。"""
    with tempfile.TemporaryDirectory() as td:
        fa = os.path.join(td, 'concat.fasta')
        with io.open(fa, 'w', encoding='ascii', newline='\n') as f:
            for acc in ACCS:
                rec, genes = genomes[acc]
                seq = ''.join(str(rec.seq[g['start'] - 1:g['end']]) for g in genes)
                f.write('>%s\n%s\n' % (acc, seq.upper()))
        names, dist = phylo._nj_distance_matrix(fa)
        return phylo._neighbor_joining(dist, names)


def main() -> int:
    genomes = {acc: read_genome(acc) for acc in ACCS}
    tracks = build_tracks(genomes)
    links = build_links(genomes)
    nwk = build_tree(genomes)

    payload = {
        'note': ('Platform built-in example: tracks from examples/example_synteny_'
                 '{A,B,C}.gb CDS; links = per-family protein identity of the '
                 '/translation qualifiers; tree = NJ over concatenated CDS.'),
        'tracks': tracks,
        'links': links,
    }
    ovl_out = TREE_OUT[:-len('.nwk')] + '.overlay.json'
    with io.open(TREE_OUT, 'w', encoding='ascii', newline='\n') as f:
        f.write(nwk + '\n')
    with io.open(ovl_out, 'w', encoding='utf-8', newline='\n') as f:
        f.write(json.dumps(payload, ensure_ascii=False, indent=1) + '\n')

    print('ok %s' % os.path.relpath(TREE_OUT, ROOT))
    print('ok %s' % os.path.relpath(ovl_out, ROOT))
    for tr in tracks:
        print('  %-18s %5d bp · %d CDS' % (tr['name'], tr['length'],
                                           len(tr['genes'])))
    ids = [l['ident'] for l in links if l['ident'] is not None]
    print('  连线 %d 条 · identity %.1f%%–%.1f%%（中位 %.1f%%）'
          % (len(links), min(ids), max(ids), sorted(ids)[len(ids) // 2]))
    print('  树 %s' % nwk)
    return 0


if __name__ == '__main__':
    sys.exit(main())
