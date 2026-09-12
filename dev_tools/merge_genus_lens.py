# -*- coding: utf-8 -*-
"""把一个外部 genus_lens（如 MMPV-RNA 版）合并进平台的
`databases/genus_lens.tsv`。

背景
----
平台自算的 genus_lens 只覆盖「病毒参考库（virusref_db/final.cluster.ref.fasta，
植物病毒为主）」中能走到 genus rank 的属（~211 属），另有 1,828 条参考序列
挂在 `unclassified XXXviridae` 之类 no rank 层，父链上没有 genus。

MMPV-RNA 的 `database/genus_lens`（2,593 属）来自 NCBI Assembly Reports 的
`species_genome_size.txt --taxid 10239`，覆盖面是**全病毒组**，属名带 `g__`
前缀，可作为外部补充源。

合并策略
--------
- 属名归一化：去掉 `g__` 前缀（平台侧是裸属名）。
- **平台自算值优先**（口径一致：平台参考库 + 平台 tax_db 父链）。
  外部表只填补平台没有的属。
- 报告冲突项（两表都有但值不同）供人工复核，默认不覆盖。

用法
----
    python dev_tools/merge_genus_lens.py --external <path> [--dry-run] [--write]
    python dev_tools/merge_genus_lens.py --restore      # 从 .bak_premerge_* 还原

不加 --write 时只打印差异报告，不改文件。
"""
import argparse
import glob
import os
import shutil
import sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
PLATFORM_ROOT = os.path.dirname(HERE)
TARGET = os.path.join(PLATFORM_ROOT, 'databases', 'genus_lens.tsv')
DEFAULT_EXTERNAL = (r'D:\桌面\延伸基因组\MMPV-RNA\database\genus_lens')
HEADER = 'genus\ttotal'


def read_tsv(path, prefixes=('g__',)):
    """读 genus_lens → {genus: float}。自动剥离 g__ 前缀。"""
    out = {}
    bad = []
    with open(path, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip('\n').rstrip('\r')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) != 2:
                continue
            name = parts[0].strip()
            if name.lower() == 'genus':
                continue
            for p in prefixes:
                if name.startswith(p):
                    name = name[len(p):]
                    break
            try:
                val = float(parts[1])
            except ValueError:
                bad.append((i, name, parts[1]))
                continue
            if val <= 0:
                bad.append((i, name, parts[1]))
                continue
            out[name] = val
    return out, bad


def write_tsv(path, mapping):
    lines = [HEADER]
    for g in sorted(mapping):
        lines.append('%s\t%.2f' % (g, mapping[g]))
    with open(path, 'wt', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--external', default=DEFAULT_EXTERNAL,
                    help='外部 genus_lens 路径')
    ap.add_argument('--target', default=TARGET)
    ap.add_argument('--write', action='store_true', help='真正落盘')
    ap.add_argument('--restore', action='store_true', help='从备份还原')
    args = ap.parse_args()

    target = args.target

    if args.restore:
        cands = sorted(glob.glob(target + '.bak_premerge_*'))
        if not cands:
            print('未找到 .bak_premerge_* 备份，无法还原')
            return 1
        src = cands[-1]
        shutil.copy2(src, target)
        print('已从 %s 还原 -> %s' % (os.path.basename(src), target))
        return 0

    if not os.path.isfile(target):
        print('目标不存在: %s' % target)
        return 1
    if not os.path.isfile(args.external):
        print('外部表不存在: %s' % args.external)
        return 1

    plat, plat_bad = read_tsv(target)
    ext, ext_bad = read_tsv(args.external)
    print('平台表   : %-8s -> %d 属' % (os.path.basename(target), len(plat)))
    print('外部表   : %-8s -> %d 属' % (os.path.basename(args.external), len(ext)))
    if plat_bad:
        print('  平台表跳过异常行 %d 条: %s' % (len(plat_bad), plat_bad[:3]))
    if ext_bad:
        print('  外部表跳过异常行 %d 条: %s' % (len(ext_bad), ext_bad[:3]))

    only_plat = sorted(set(plat) - set(ext))
    only_ext = sorted(set(ext) - set(plat))
    both = sorted(set(plat) & set(ext))
    conflicts = [(g, plat[g], ext[g]) for g in both]
    disagree = [(g, p, e) for g, p, e in conflicts if abs(p - e) / max(p, 1e-9) > 0.05]

    print()
    print('只在平台表（自算独有）  : %d' % len(only_plat))
    print('只在外部表（可补充）    : %d' % len(only_ext))
    print('两表都有                : %d' % len(both))
    print('  其中值差异 >5%%        : %d' % len(disagree))

    merged = dict(plat)
    for g in only_ext:
        merged[g] = ext[g]

    print()
    print('合并后                  : %d 属' % len(merged))

    if disagree:
        print()
        print('--- 值差异 >5%% 的属（前 20，平台值优先保留）---')
        print('%-32s %14s %14s' % ('genus', '平台(保留)', '外部'))
        for g, p, e in sorted(disagree, key=lambda x: -abs(x[1] - x[2]))[:20]:
            print('%-32s %14.2f %14.2f' % (g, p, e))

    if only_plat:
        print()
        print('--- 平台独有（外部表较旧，前 10）---')
        print(', '.join(only_plat[:10]) + (' ...' if len(only_plat) > 10 else ''))

    if not args.write:
        print()
        print('[dry-run] 未落盘。加 --write 执行合并。')
        return 0

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    bak = '%s.bak_premerge_%s' % (target, stamp)
    shutil.copy2(target, bak)
    write_tsv(target, merged)
    print()
    print('已备份 -> %s' % os.path.basename(bak))
    print('已写入 -> %s (%d 属, %d 字节)'
          % (target, len(merged), os.path.getsize(target)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
