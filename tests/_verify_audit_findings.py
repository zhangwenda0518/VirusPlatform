# -*- coding: utf-8 -*-
"""审计发现的可复现验证脚本（只读 + 非破坏性）。

对每条审计结论做一次实测：能复现的打印 REPRO，不能复现的打印 NOT-REPRO。
破坏性操作（如 rmtree meta_search）一律用「干跑」代替：只验证路径解析结果，
不真正执行删除。

用法: python tests/_verify_audit_findings.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

results = []


def rep(tag, ok, detail=''):
    results.append((tag, ok, detail))
    print(f'[{"REPRO" if ok else "NOT-REPRO"}] {tag}' + (f'  — {detail}' if detail else ''))


# ---------------------------------------------------------------- 1
print('=== 1. db_migrate: from .config import cfg ===')
try:
    src = io.open(os.path.join(ROOT, 'vp', 'db_migrate.py'),
                  encoding='utf-8').read()
    rep('db_migrate.py 源码含 `from .config import cfg`',
        'from .config import cfg' in src)
    try:
        from vp.config import cfg  # noqa: F401
        rep('vp.config.cfg 可导入', False, '竟然存在')
    except ImportError as e:
        rep('vp.config.cfg 不存在 → db-migrate 会 ImportError', True, str(e))
except Exception as e:
    rep('导入 vp.db_migrate', False, repr(e))

# ---------------------------------------------------------------- 2
print('\n=== 2. taxonomy 目录映射 ===')
from vp.config import DIRS, _DATABASE_KEYS, PLATFORM_ROOT  # noqa: E402
rep('_DATABASE_KEYS["taxonomy"] 指向 databases/taxonomy（真实布局为 databases/tax/core）',
    _DATABASE_KEYS.get('taxonomy') == os.path.join('databases', 'taxonomy'),
    f'_DATABASE_KEYS={_DATABASE_KEYS.get("taxonomy")!r}, '
    f'真实存在={os.path.isdir(os.path.join(PLATFORM_ROOT, "databases", "tax", "core"))}')
# 模拟 apply_database_root 的映射结果（不真正调用，避免建目录）
fake = os.path.join(PLATFORM_ROOT, _DATABASE_KEYS['taxonomy'])
rep('按该映射得到的 taxonomy 目录无 nodes.dmp',
    not os.path.isfile(os.path.join(fake, 'nodes.dmp')),
    fake)

# ---------------------------------------------------------------- 3
print('\n=== 3. meta.py 引擎脚本路径 ===')
mp = os.path.join(ROOT, 'vp', 'web', 'meta.py')
txt = io.open(mp, encoding='utf-8').read()
bad = os.path.join(os.path.dirname(mp), 'vp', 'public_meta', 'search_engine.py')
rep('meta.py 拼出的 search_engine.py 路径不存在',
    not os.path.isfile(bad), bad)
rep('正确路径存在',
    os.path.isfile(os.path.join(ROOT, 'vp', 'public_meta', 'search_engine.py')))

# ---------------------------------------------------------------- 4
print('\n=== 4. refs.py /api/tree/data 任意文件读取 ===')
import app as appmod  # noqa: E402
c = appmod.app.test_client()
# 造一个最小样品目录结构（只读验证，用已有样品）
samples = [d for d in os.listdir(os.path.join(ROOT, 'run', 'results'))
           if os.path.isdir(os.path.join(ROOT, 'run', 'results', d))
           and not d.startswith('_')]
probe_sample, probe_group = None, None
for s in samples:
    ph = os.path.join(ROOT, 'run', 'results', s, '05_phylo')
    if os.path.isdir(ph):
        for g in os.listdir(ph):
            if os.path.isdir(os.path.join(ph, g)):
                probe_sample, probe_group = s, g
                break
    if probe_sample:
        break
if probe_sample:
    target = os.path.join(ROOT, 'platform.json')
    r = c.get('/api/tree/data',
              query_string={'sample': probe_sample, 'group': probe_group,
                            'file': target})
    body = r.get_data(as_text=True)
    rep(f'/api/tree/data?file=<平台内绝对路径> 返回 200 并泄露文件内容 '
        f'(sample={probe_sample}/{probe_group})',
        r.status_code == 200 and 'threads' in body,
        f'status={r.status_code}, 含 threads={("threads" in body)}')
else:
    rep('存在可用于验证的 05_phylo 分组', False, '跳过')

# ---------------------------------------------------------------- 5
print('\n=== 5. meta 删除接口 name="." 解析 ===')
from vp.config import DIRS  # noqa: E402
from vp.utils import check_path  # noqa: E402
try:
    p = check_path(os.path.join(DIRS['meta_search'], '.'),
                   must_exist=True, in_platform=True)
    rep('check_path(meta_search/.) 返回 meta_search 根本身 → rmtree 会清空全部检索项目',
        os.path.normpath(p) == os.path.normpath(DIRS['meta_search']), p)
except Exception as e:
    rep('check_path(meta_search/.) 被拒绝', False, repr(e))
rep('meta.py 删除路由缺 name 白名单',
    "re.fullmatch" not in io.open(os.path.join(ROOT, 'vp', 'web', 'meta.py'),
                                  encoding='utf-8').read().split(
        'def api_meta_collection_delete')[1][:400])

# ---------------------------------------------------------------- 6
print('\n=== 6. request.get_json(force=True) 对 null 返回 None ===')
r = c.post('/api/ncbi/search', data='null',
           content_type='application/json')
rep('POST /api/ncbi/search body=null 返回 500（应为 400 JSON）',
    r.status_code == 500, f'status={r.status_code}')
r = c.post('/api/analyze', data='null', content_type='application/json')
rep('POST /api/analyze body=null 返回 500',
    r.status_code == 500, f'status={r.status_code}')

# ---------------------------------------------------------------- 7
print('\n=== 7. examples_api 可读平台内任意文件 ===')
r = c.get('/api/example_input/platform.json')
rep('GET /api/example_input/platform.json 返回 200（应限 databases/examples/）',
    r.status_code == 200, f'status={r.status_code}')

# ---------------------------------------------------------------- 8
print('\n=== 8. 前端示例按钮（引物页）===')
html = c.get('/primer').get_data(as_text=True)
rep('/primer 页面含示例按钮',
    'EXAMPLE_FASTA' in html or 'fillExample' in html)

print('\n' + '=' * 62)
bad_n = sum(1 for _t, ok, _d in results if ok)
print(f'可复现的审计发现: {bad_n}/{len(results)}')
for t, ok, _d in results:
    if ok:
        print('  - ' + t)
