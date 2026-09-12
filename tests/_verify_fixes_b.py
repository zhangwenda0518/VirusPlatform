# -*- coding: utf-8 -*-
"""验证 Logan 结果表解析（带引号+内嵌逗号）与 msa_view 截断标记。"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Virus_Platform_Core.logan_trace import parse_result_table

raw = ('Run Accession,Organism,Location,k-mer coverage\n'
       'SRR12345,"Virus, unclassified","USA: California, Davis",0.5\n'
       'ERR99999,"Solemoviridae sp.","China: Ningxia, Yinchuan",0.25\n'
       ).encode('utf-8')
rows, cols = parse_result_table(raw)
print('mapped cols =', cols)
for r in rows:
    print('  ', {k: v for k, v in r.items() if v not in ('', None)})
assert rows[0]['organism'] == 'Virus, unclassified', rows[0]
assert rows[0]['location'] == 'USA: California, Davis', rows[0]
assert rows[0]['kmer_cov'] == 0.5, rows[0]
print('CSV 解析 OK')

from Virus_Platform_Core.msa_view import snp_view_data
import tempfile
p = os.path.join(tempfile.gettempdir(), '_vp_aln80.fa')
with open(p, 'w', encoding='utf-8') as f:
    for i in range(80):
        f.write('>s%d\nACGTACGTACGT\n' % i)
d = snp_view_data(p)
print('n_seq=%d seqs_truncated=%s' % (d['n_seq'], d['seqs_truncated']))
assert d['n_seq'] == 80 and d['seqs_truncated'] is False, d['seqs_truncated']
with open(p, 'w', encoding='utf-8') as f:
    for i in range(81):
        f.write('>s%d\nACGTACGTACGT\n' % i)
d = snp_view_data(p)
print('n_seq=%d seqs_truncated=%s' % (d['n_seq'], d['seqs_truncated']))
assert d['n_seq'] == 80 and d['seqs_truncated'] is True
os.remove(p)
print('msa_view 截断标记 OK')

# primer3 amplicon 语义
from Virus_Platform_Core import primer_design as pd
import random
random.seed(7)
seq = ''.join(random.choice('ACGT') for _ in range(1200))
res = pd.run_design(fasta_text='>t\n' + seq, ptype='PCR',
                    core={'product_min': 100, 'product_max': 400,
                          'num_return': 3}, adv={})
for rec in res['records']:
    for pr in rec['pairs']:
        print('product=%s span=%s amp=[%s,%s]'
              % (pr.get('product'), pr['amplicon_span'],
                 pr['amp_start'], pr['amp_end']))
        assert pr['amplicon_span'] == pr.get('product'), (pr['amplicon_span'],
                                                          pr.get('product'))
print('引物扩增子坐标口径 OK')
