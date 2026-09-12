# -*- coding: utf-8 -*-
"""把外部 genus_lens 转成平台格式并**替代** databases/genus_lens.tsv。

平台格式
--------
    genus<TAB>total
    裸属名<TAB>平均长度保留 2 位小数

外部格式（MMPV-RNA `database/genus_lens`，来自 make_genus-length.py）
------------------------------------------------------------------
    genus<TAB>total
    g__Genus<TAB>avg

转换动作
--------
1. 剥离 `g__` 前缀
2. 数值统一保留 2 位小数（外部表是 %.1f~%.2f 混排）
3. 按属名字典序排序
4. 写入平台目标路径，写入前自动备份

用法
----
    python dev_tools/convert_genus_lens.py --dry-run
    python dev_tools/convert_genus_lens.py --write
    python dev_tools/convert_genus_lens.py --restore
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
DEFAULT_SOURCE = r'D:\桌面\延伸基因组\MMPV-RNA\database\genus_lens'
HEADER = 'genus\ttotal'
PREFIX = 'g__'


def read_external(path):
    """读外部表 → ({genus: float}, [异常行])。剥离 g__ 前缀。"""
    out, bad, dup = {}, [], []
    with open(path, encoding='utf-8', errors='replace') as f:
        for i, line in enumerate(f, 1):
            line = line.rstrip('\n').rstrip('\r')
            if not line:
                continue
            parts = line.split('\t')
            if len(parts) < 2:
                continue
            name = parts[0].strip()
            if name.lower() == 'genus':
                continue
            if name.startswith(PREFIX):
                name = name[len(PREFIX):]
            if not name:
                bad.append((i, line))
                continue
            try:
                val = float(parts[1])
            except ValueError:
                bad.append((i, line))
                continue
            if val <= 0:
                bad.append((i, line))
                continue
            if name in out:
                dup.append(name)
                continue
            out[name] = val
    return out, bad, dup


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--source', default=DEFAULT_SOURCE)
    ap.add_argument('--target', default=TARGET)
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--restore', action='store_true')
    args = ap.parse_args()

    if args.restore:
        cands = sorted(glob.glob(args.target + '.bak_*'))
        if not cands:
            print('找不到备份')
            return 1
        src = cands[-1]
        shutil.copy2(src, args.target)
        print('已还原: %s -> %s' % (os.path.basename(src), args.target))
        return 0

    if not os.path.isfile(args.source):
        print('源文件不存在: %s' % args.source)
        return 1

    data, bad, dup = read_external(args.source)
    print('源文件 : %s' % args.source)
    print('解析出 : %d 属' % len(data))
    if bad:
        print('异常行 : %d 条（已跳过）' % len(bad))
        for i, l in bad[:5]:
            print('   L%d: %r' % (i, l[:60]))
    if dup:
        print('重复属 : %d 个（保留首次出现）%s' % (len(dup), dup[:5]))

    if not data:
        print('无有效数据，中止')
        return 1

    if args.target and os.path.isfile(args.target):
        old = sum(1 for _ in open(args.target, encoding='utf-8',
                                  errors='replace')) - 1
        print('现有目标: %d 属（将被替代）' % max(old, 0))

    print('转换后 : %d 属，升序排列' % len(data))
    print('样例   :')
    for g in sorted(data)[:3]:
        print('   %s\t%.2f' % (g, data[g]))
    print('   ...')
    for g in sorted(data)[-2:]:
        print('   %s\t%.2f' % (g, data[g]))

    if args.dry_run or not args.write:
        print()
        print('[dry-run] 未写入。加 --write 执行。')
        return 0

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    if os.path.isfile(args.target):
        bak = '%s.bak_replace_%s' % (args.target, stamp)
        shutil.copy2(args.target, bak)
        print()
        print('已备份 -> %s' % os.path.basename(bak))

    lines = [HEADER] + ['%s\t%.2f' % (g, data[g]) for g in sorted(data)]
    with open(args.target, 'wt', encoding='utf-8', newline='\n') as f:
        f.write('\n'.join(lines) + '\n')
    print('已写入 -> %s (%d 属, %d 字节)'
          % (args.target, len(data), os.path.getsize(args.target)))
    return 0


if __name__ == '__main__':
    sys.exit(main())
