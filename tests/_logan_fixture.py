# -*- coding: utf-8 -*-
"""测试夹具：为 LOGAN 自测挑一个可用的来源样品。

原实现把样品名硬编码为 'REGRESS'，该样品在当前工作区不存在（已被归档/
删除），两个 LOGAN 测试因此必失败。改为按内容挑：扫描 results/ 下含
`03_assembly/virus_contigs.tsv` 且至少 1 条 contig 的样品。

用法:
    from _logan_fixture import pick_sample, skip_if_none
    SAMPLE = pick_sample()          # 找不到时返回 None
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from Virus_Platform_Core.config import DIRS  # noqa: E402


def _usable(sample):
    p = os.path.join(DIRS['results'], sample, '03_assembly',
                     'virus_contigs.tsv')
    if not os.path.isfile(p):
        return 0
    try:
        with open(p, 'r', encoding='utf-8', errors='replace') as f:
            return max(0, sum(1 for _ in f) - 1)     # 减去表头
    except OSError:
        return 0


def pick_sample(prefer=('REGRESS',)):
    """返回第一个可用样品名；优先 prefer 里的名字，其次按名字排序。"""
    base = DIRS['results']
    if not os.path.isdir(base):
        return None
    names = [d for d in sorted(os.listdir(base))
             if os.path.isdir(os.path.join(base, d)) and not d.startswith('_')]
    for n in prefer:
        if n in names and _usable(n):
            return n
    for n in names:
        if _usable(n):
            return n
    return None


def skip_if_none(sample, who):
    """没有可用样品时跳过（数据依赖型测试的正确姿态）。

    两种运行环境都兼容：tests/_run_all.py 子进程里沿用打印 + exit(0)；
    pytest 下 sys.exit 会炸成 INTERNALERROR，改用 pytest 模块级跳过。"""
    if sample:
        return False
    msg = (f'[SKIP] {who}: 未找到含病毒 contigs 的样品'
           f'（需要 results/<样品>/03_assembly/virus_contigs.tsv）')
    if 'pytest' in sys.modules:
        import pytest
        pytest.skip(msg, allow_module_level=True)
    print(msg)
    sys.exit(0)
