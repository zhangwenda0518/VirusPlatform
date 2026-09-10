# -*- coding: utf-8 -*-
"""打包产物端到端验证：对一个正在运行的平台实例做只读 HTTP 检查。

用法:
    python tests/_verify_package.py [http://127.0.0.1:8900]
默认目标 http://127.0.0.1:8900（打包 exe 启动时打印的地址）。
退出码 0 = 全部通过。
"""
import json
import sys
import urllib.error as ue
import urllib.parse as up
import urllib.request as u

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8900'
fails = []


def check(cond, msg):
    print(('  OK   ' if cond else '  FAIL ') + msg)
    if not cond:
        fails.append(msg)


def get(path):
    try:
        with u.urlopen(BASE + path, timeout=60) as r:
            return r.status, r.read()
    except ue.HTTPError as e:
        return e.code, e.read()


def post(path, payload, timeout=300):
    req = u.Request(BASE + path, data=json.dumps(payload).encode(),
                    headers={'Content-Type': 'application/json'})
    try:
        with u.urlopen(req, timeout=timeout) as r:
            return r.status, r.read()
    except ue.HTTPError as e:
        return e.code, e.read()


print(f'== 目标 {BASE} ==')
for p in ('/', '/primer', '/settings', '/tools?g=sample', '/results'):
    try:
        s, b = get(p)
        check(s == 200 and len(b) > 1000, f'GET {p} → {s} ({len(b)} B)')
    except Exception as e:
        check(False, f'GET {p} 失败: {e}')

s, b = get('/api/settings')
d = json.loads(b)
check('examples_effective' in d and d['examples_effective'],
      f"示例根生效: {d.get('examples_effective')}")

s, b = get('/api/example_paths')
ex = json.loads(b)
check(s == 200 and ex.get('files'), f"示例路径表 {len(ex.get('files', {}))} 个文件")

s, b = get('/api/examples')
check(s == 200 and len(json.loads(b)) > 0,
      f"示例结果清单 {len(json.loads(b))} 个模块")

fa = (ex.get('files') or {}).get('example_viral_contigs.fasta')
if fa:
    s, b = get('/api/example_input/example_viral_contigs.fasta')
    check(s == 200 and len(b) > 1000, f'示例输入读取 {s} ({len(b)} B)')
    s, b = get('/api/seqview?path=' + up.quote(fa))
    check(s == 200 and len(json.loads(b).get('rows', [])) >= 1,
          f'序列查看器 {s}')
    s, b = post('/api/tool/genoplot_preview', {'fasta': fa, 'mode': 'circular'})
    ok = s == 200 and '<svg' in (json.loads(b) if s == 200 else {}).get('svg', '')
    check(ok, f'图谱预览（gbdraw）→ {s}')
else:
    check(False, '未取到示例 FASTA 绝对路径')

s, b = post('/api/meta/collection/./delete', {})
check(s == 400, f'越权删除被拒 → {s}')
s, b = get('/api/example_input/platform.json')
check(s == 404, f'示例输入越界被拒 → {s}')

print('\n' + '=' * 52)
if fails:
    print(f'FAILED: {len(fails)} 项')
    for f in fails:
        print('  - ' + f)
    sys.exit(1)
print('打包产物端到端验证通过 ✔')
