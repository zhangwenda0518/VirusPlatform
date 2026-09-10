# -*- coding: utf-8 -*-
"""验证宿主预测的「BLAST 最后回退」现在真的会触发。

构造一份**没有 kunpeng 分类**（taxid 列空）的 contig 表 + 配套 FASTA：
修复前 blast_* 永远是空串 → 全部落 Unknown；修复后 local BLASTN 给出
最近参考 accession → class_source=blast 且宿主可判。
"""
import os
import sys
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from vp.config import PLATFORM_ROOT  # noqa: E402
from vp.utils import safe_open, write_fasta_record, iter_fasta  # noqa: E402

RUN = '_probe_blast_fallback'


def main():
    run_dir = os.path.join(PLATFORM_ROOT, 'run', 'tool_runs', RUN)
    shutil.rmtree(run_dir, ignore_errors=True)
    os.makedirs(run_dir, exist_ok=True)

    fa = os.path.join('databases', 'examples', 'example_viral_contigs.fasta')
    recs = [(h.split()[0], s) for h, s in iter_fasta(fa)]
    vfa = os.path.join(run_dir, 'viral_contigs.fasta')
    with safe_open(vfa, 'wt') as f:
        for cid, s in recs:
            write_fasta_record(f, cid, s)
    # 只有 contig/length/taxon 列（无 kunpeng_taxid、无 blast_*）——
    # 模拟"③ 未分类成功"或外部自备 contig 表
    tsv = os.path.join(run_dir, 'virus_classification.tsv')
    with safe_open(tsv, 'wt') as f:
        f.write('contig\tlength\ttaxon\n')
        for cid, s in recs:
            f.write(f'{cid}\t{len(s)}\t\n')

    import app as appmod
    c = appmod.app.test_client()
    r = c.post('/api/tool/hostpredict_run', json={'run': RUN})
    if r.status_code != 200:
        print('启动失败:', r.status_code, r.get_data(as_text=True)[:300])
        return 1
    tid = r.get_json()['task']
    import time
    rec = None
    for _ in range(600):
        with c.get(f'/api/task/{tid}') as _r:
            rec = _r.get_json()
        if rec['status'] in ('done', 'failed', 'cancelled'):
            break
        time.sleep(1)
    print('任务状态:', rec['status'], rec.get('error') or '')
    assert rec['status'] == 'done', rec.get('error')

    vt = os.path.join(run_dir, '03_assembly', 'virus_contigs.tsv')
    with safe_open(vt) as f:
        lines = f.read().strip().splitlines()
    print('归一表表头:', lines[0])
    for ln in lines[1:]:
        print('  ', ln)
    hp = os.path.join(run_dir, '08_host_analysis', 'host_prediction.tsv')
    with safe_open(hp) as f:
        rows = list(__import__('csv').DictReader(f, delimiter='\t'))
    srcs = {}
    for r_ in rows:
        srcs[r_['class_source']] = srcs.get(r_['class_source'], 0) + 1
    print('class_source 分布:', srcs)
    out = {'class_source': srcs,
           'final_host': sorted({r_['final_host'] for r_ in rows}),
           'blast_cols': [ln.split('\t')[5] for ln in lines[1:]]}
    print(json.dumps(out, ensure_ascii=False))
    assert srcs.get('blast', 0) > 0, f'BLAST 回退仍未生效: {srcs}'
    assert all(out['blast_cols']), 'blast_top_hit 仍有空值'
    print('\n✔ BLAST 最后回退已生效')
    shutil.rmtree(run_dir, ignore_errors=True)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
