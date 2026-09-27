# -*- coding: utf-8 -*-
"""示例结果清单一致性检查：manifest.json 声明 ↔ examples/results 实际文件。

背景：平台「专项分析」各工具卡都有「👁 示例结果」入口。前端列表页的文件数
现在取**实际文件数**（见 web/examples_api.py 的 _count_files），详情页也是遍历
真实目录，因此 manifest 的 files 列表只作「一次完整运行会产生哪些产物」的
文档快照 —— 为控制仓库体积清理过大文件（run.log / *.fastq.gz / SPAdes 中间
产物）后它允许落后，不算缺陷。

因此本检查的**硬性失败**只针对：
  1. manifest 条目结构非法；
  2. 声明的模块目录不存在（入口点进去必然空列表）。
其余（声明缺失 / 存在未声明）只作提示，便于人工判断要不要同步快照。

用法: python tests/_check_examples_manifest.py [--verbose]
退出码: 0 = 无硬性差异；1 = 存在硬性差异。
"""
import json
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'examples', 'results')
MANIFEST = os.path.join(EX, 'manifest.json')

# 这些是运行期产生的辅助文件，不要求在清单里出现
IGNORE = {'.gitkeep', 'Thumbs.db', '.DS_Store'}


def main():
    verbose = '--verbose' in sys.argv
    if not os.path.isfile(MANIFEST):
        print(f'✘ 找不到 {MANIFEST}')
        return 1
    man = json.load(open(MANIFEST, encoding='utf-8'))
    if not isinstance(man, dict):
        print('✘ manifest 顶层应为 {工具名: {files: [...]}}')
        return 1

    missing, undeclared, badstruct, nodir = [], [], [], []
    for tool, info in sorted(man.items()):
        files = info.get('files') if isinstance(info, dict) else info
        if not isinstance(files, list):
            badstruct.append(f'{tool}: files 应为列表，实际 {type(files).__name__}')
            continue
        base = os.path.join(EX, tool)
        if not os.path.isdir(base):
            nodir.append(tool)
        declared = set()
        for f in files:
            rel = f.get('path') if isinstance(f, dict) else f
            if not rel:
                badstruct.append(f'{tool}: 存在无 path 的条目')
                continue
            declared.add(rel)
            if not os.path.exists(os.path.join(EX, tool, rel)):
                missing.append(f'{tool}/{rel}')
        if os.path.isdir(base):
            for dp, dns, fns in os.walk(base):
                for fn in fns:
                    if fn in IGNORE:
                        continue
                    rel = os.path.relpath(os.path.join(dp, fn), base)
                    rel = rel.replace(os.sep, '/')
                    if rel not in declared:
                        undeclared.append(f'{tool}/{rel}')

    print(f'manifest 工具条目 {len(man)} 个')
    hard = False
    if badstruct:
        hard = True
        print(f'\n✘ 结构异常 {len(badstruct)} 处:')
        for b in badstruct:
            print('   ' + b)
    if nodir:
        hard = True
        print(f'\n✘ 声明的模块目录不存在 {len(nodir)} 个'
              '（示例入口点进去必然空列表）:')
        for m in nodir:
            print('   ' + m)
    if missing:
        print(f'\n△ 快照声明但文件已不在 {len(missing)} 个'
              '（多为清理大文件所致，非缺陷）:')
        for m in (missing if verbose else missing[:12]):
            print('   ' + m)
        if not verbose and len(missing) > 12:
            print(f'   ... 另有 {len(missing) - 12} 个（--verbose 看全部）')
    if undeclared:
        print(f'\n△ 文件存在但快照未声明 {len(undeclared)} 个:')
        for u in (undeclared if verbose else undeclared[:12]):
            print('   ' + u)
        if not verbose and len(undeclared) > 12:
            print(f'   ... 另有 {len(undeclared) - 12} 个（--verbose 看全部）')

    print()
    if hard:
        print('✘ 示例清单存在硬性差异（见上）')
        return 1
    print('✔ 无硬性差异（列表/详情均以实际文件为准，计数已对齐）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
