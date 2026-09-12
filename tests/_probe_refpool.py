# -*- coding: utf-8 -*-
"""验证参考池修复（A 植物口径过滤 + B 长度护栏）。

构造一个"③无分类表"的样品（走 ref_tax 兜底选参，正是此前混入 40kb 古菌
病毒的路径），用**真实**参考库跑 build_phylo，然后检查 refs.fa：
  - 无超过 MAX_REF_LEN 的序列
  - 无古菌病毒（Sulfolobus / Betalipothrixvirus / Acidianus / Captovirus）
  - 参考池落在植物口径内
"""
import os
import sys
import shutil
import json
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
from Virus_Platform_Core.utils import safe_open, write_fasta_record, iter_fasta  # noqa: E402
from Virus_Platform_Core.phylo import build_phylo, MAX_REF_LEN  # noqa: E402

ARCHAEAL = ('Sulfolobus', 'Betalipothrixvirus', 'Acidianus', 'Captovirus',
            'Sulfobales', 'Lipothrixvirus', 'Twarogvirinae', 'Rudivirus')


def main():
    work = os.path.join(DIRS['results'], 'probe_refpool')
    shutil.rmtree(work, ignore_errors=True)
    a_dir = os.path.join(work, '03_assembly')
    os.makedirs(a_dir, exist_ok=True)
    src = os.path.join('examples', 'example_viral_contigs.fasta')
    ids = []
    with safe_open(os.path.join(a_dir, 'contigs.filtered.fasta'), 'wt') as f:
        for h, s in iter_fasta(src):
            cid = h.split()[0]
            ids.append(cid)
            write_fasta_record(f, cid, s)
    with safe_open(os.path.join(a_dir, 'summary.json'), 'wt') as f:
        json.dump({'viral_contigs': ids}, f)

    # 不传 db_virus / 不建 virus_classification.tsv → 走 ref_tax 兜底选参
    logs = []

    class _L:
        def log(self, msg, level='INFO'):
            logs.append((level, str(msg)))
            print(f'   [{level}] {msg}')

        def close(self):
            pass

    import time
    t0 = time.time()
    summary = build_phylo(work, top_n_refs=10, tree_tool='fasttree',
                          logger=_L())
    elapsed = time.time() - t0
    g = summary['groups'][0]
    gdir = os.path.join(work, '05_phylo', g['dir'])
    refs_fa = os.path.join(gdir, 'refs.fa')
    print(f'\nbuild_phylo 耗时 {elapsed:.1f}s | 树文件: '
          f'{os.path.isfile(os.path.join(gdir, g.get("tree") or "tree.nwk"))}')

    lens, heads = [], []
    for h, s in iter_fasta(refs_fa):
        heads.append(h[:90])
        lens.append(len(s))
    print(f'\n参考条数 = {len(lens)}')
    if lens:
        print(f'长度 min/中位/max = {min(lens)} / '
              f'{sorted(lens)[len(lens) // 2]} / {max(lens)} bp')
    print('refs.fa 前几条:')
    for h in heads[:10]:
        print('   ', h)

    over = [h for h, L in zip(heads, lens) if L > MAX_REF_LEN]
    arch = [h for h in heads
            if any(a.lower() in h.lower() for a in ARCHAEAL)]
    print(f'\n超过 {MAX_REF_LEN}bp 的参考 = {len(over)}')
    for h in over:
        print('   ⚠', h)
    print(f'古菌病毒参考 = {len(arch)}')
    for h in arch:
        print('   ⚠', h)
    print('combined 条数 =', sum(1 for _ in iter_fasta(
        os.path.join(gdir, 'combined.fa'))))

    ok = not over and not arch
    print('\n' + ('✔ A+B 生效：参考池无超长、无古菌病毒' if ok
                  else '✘ 仍混入不合格参考'))

    # 层级抽样（macro/genus/lineage）也走 ref_tax，验证过滤后仍能选到参考
    for mode in ('genus', 'macro', 'lineage'):
        try:
            s2 = build_phylo(work, top_n_refs=5, tree_tool='fasttree',
                             sampling=mode, force=True)
            g2 = (s2.get('groups') or [{}])[0]
            gd2 = os.path.join(work, '05_phylo', g2.get('dir') or '')
            rf = os.path.join(gd2, 'refs.fa')
            n = sum(1 for _ in iter_fasta(rf)) if os.path.isfile(rf) else 0
            mx = max((len(s) for _h, s in iter_fasta(rf)), default=0)
            print(f'  抽样 {mode:8s} → 参考 {n} 条（最长 {mx} bp）')
            assert n >= 1 and mx <= MAX_REF_LEN, f'{mode} 抽样异常'
        except Exception as e:
            print(f'  抽样 {mode:8s} → 失败: {type(e).__name__}: {e}')
            ok = False

    shutil.rmtree(work, ignore_errors=True)
    print('\n' + ('✔ 全部通过（含 macro/genus/lineage 抽样）' if ok
                  else '✘ 存在问题'))
    return 0 if ok else 1


if __name__ == '__main__':
    raise SystemExit(main())
