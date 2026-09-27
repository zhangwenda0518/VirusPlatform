# -*- coding: utf-8 -*-
"""数据库/目录类 API 的路径绝对性检查。

背景（历史事故）：`/api/dbs` 曾对内置病毒库返回 `databases/<rel>` —— 相对
**数据库根**的路径。前端原样回传，后端却按 PLATFORM_ROOT 解析，于是分发版
（数据库包与程序目录分离）下选库直接 400「病毒库不存在」。源码树里
`PLATFORM_ROOT/databases` 恰好就是数据库根，所以只在分发版暴露；更阴的是
两边都存在时会**静默用错库**。

因此约定：凡是要回传给前端的「库/目录」路径，必须是绝对路径。

用法: python tests/_check_db_paths.py
退出码: 0 = 全部绝对；1 = 存在相对路径。
"""
import os
import sys

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import app  # noqa: E402

SEP = ('/', '\\')

# 这些字段名装的是**给人看的标签/说明**，含斜杠也正常，不参与路径判定。
# 例：/api/dbs 的 virus_libs[].name = 'kunpeng_db/plant'（下拉显示名，
# option 的 value 走的是同一对象的 path 字段，那里必须是绝对路径）；
# /api/kv_index_list 的 manifest.layout 是一段中文说明；
# manifest.notes / fix_script / original_broken_backup 是数据集的**来源记录**
# （修复脚本名、破损备份位置等，全库 grep 无任何代码消费），同为说明字段。
LABEL_KEYS = ('name', 'label', 'title', 'note', 'notes', 'desc', 'layout',
              'hint', 'text', 'msg', 'message',
              'fix_script', 'original_broken_backup')


def _is_label_field(path):
    leaf = path.rsplit('.', 1)[-1].split('[')[0].lower()
    return leaf in LABEL_KEYS


def walk_paths(obj, path=''):
    """递归收集所有「看起来像路径」的字符串值及其字段路径。"""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out += walk_paths(v, f'{path}.{k}')
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out += walk_paths(v, f'{path}[{i}]')
    elif isinstance(obj, str):
        if len(obj) > 3 and not obj.startswith('http') and any(s in obj for s in SEP):
            out.append((path, obj))
    return out


def main():
    c = app.app.test_client()
    bad = []
    for ep in ['/api/dbs', '/api/host_dbs', '/api/kv_index_list']:
        r = c.get(ep)
        if r.status_code != 200:
            print(f'{ep}: HTTP {r.status_code}（跳过）')
            continue
        ps = [x for x in walk_paths(r.get_json()) if not _is_label_field(x[0])]
        rel = [(k, v) for k, v in ps if not os.path.isabs(v)]
        print(f'{ep}: 路径字段 {len(ps)} 个，非绝对 {len(rel)} 个')
        for k, v in rel:
            print(f'    △ {k} = {v}')
            bad.append(f'{ep} {k}={v}')
    print()
    if bad:
        print(f'✘ 存在 {len(bad)} 个相对路径（分发版下会解析错库）')
        return 1
    print('✔ 库/目录类 API 返回的路径全部为绝对路径')
    return 0


if __name__ == '__main__':
    sys.exit(main())
