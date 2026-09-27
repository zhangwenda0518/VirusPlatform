# -*- coding: utf-8 -*-
"""校验 spec 里 webapp 的 datas 展开逻辑：**既不漏文件，也不带工具残留**。

为什么单独测这个：`dev_tools/VirusPlatform.spec` 里把 `webapp/` 打进 `datas`
时，原先直接写 `(目录, 目标)`，PyInstaller 会整棵拷贝 —— 连
`webapp/templates/.mimosa`（编辑器 hook 缓存）一起进分发版。改成逐文件展开
（`_tree`）后，风险反转成"**漏掉某个前端文件 → 界面某个页面挂掉**"。

spec 是 exec 式的，没法直接 import（尾部会触发真正的 Analysis/EXE）。
所以这里用 AST 把 `_tree` **单独抽出来**编译执行 —— 测的是 spec 里那份真代码，
不是复制品。

判据：
  1. webapp 下所有非残留文件都在 datas 里（集合相等）→ 不漏
     （例外：*.bak / *.bak_* 是开发期手工备份，2026-09-18 起 spec 有意
      不打进分发版 —— 期望集合同样剔除，不算"漏"）
  2. 没有任何条目来自 `.mimosa` / `__pycache__` 等残留 → 不多
  3. 目标路径为 posix 风格、且都在 webapp/ 下
  4. 嵌套文件的目录映射正确
  5. 备份文件确实不在 datas 里（正面对照，防止排除逻辑被改坏）
"""
import ast
import fnmatch
import os
import sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SPEC = os.path.join(ROOT, 'dev_tools', 'VirusPlatform.spec')
EXCLUDE = ('.mimosa', '__pycache__', '.git', '.github')
BAK_PATTERNS = ('*.bak', '*.bak_*')


def _is_bak(name):
    return any(fnmatch.fnmatch(name, p) for p in BAK_PATTERNS)

fails = []


def check(label, cond, detail=''):
    print(f'  {"OK  " if cond else "FAIL"} {label}' + (f'  {detail}' if detail else ''))
    if not cond:
        fails.append(label)


print('spec datas 展开校验：')

# --- 从 spec 里抽出 _tree 并编译执行 ---------------------------------
with open(SPEC, encoding='utf-8') as f:
    src = f.read()
tree = ast.parse(src)
fn = next((n for n in tree.body
           if isinstance(n, ast.FunctionDef) and n.name == '_tree'), None)
check('spec 中能找到 _tree', fn is not None)
if fn is None:
    print('\n✘ 无法继续')
    raise SystemExit(1)

seg = ast.get_source_segment(src, fn)
ns = {'os': os}
exec(compile(seg, SPEC, 'exec'), ns)
_tree = ns['_tree']

webapp = os.path.join(ROOT, 'webapp')
check('webapp 目录存在', os.path.isdir(webapp))

# --- 实际展开 --------------------------------------------------------
datas = _tree(webapp, 'webapp')
got_src = {os.path.relpath(s, ROOT).replace('\\', '/') for s, _d in datas}

# --- 期望集合：webapp 下所有非残留、非备份文件 --------------------------
want_src = set()
bak_src = set()
for cur, dns, files in os.walk(webapp):
    dns[:] = [d for d in dns if d not in EXCLUDE]
    for fnm in files:
        if fnm in EXCLUDE:
            continue
        rel = os.path.relpath(os.path.join(cur, fnm), ROOT).replace('\\', '/')
        if _is_bak(fnm):
            bak_src.add(rel)
            continue
        want_src.add(rel)

missing = sorted(want_src - got_src)
extra = sorted(got_src - want_src)
check(f'不漏文件（{len(want_src)} 个）', not missing,
      f'缺 {missing[:5]}' if missing else '')
check('不带残留', not extra, f'多 {extra[:5]}' if extra else '')

# --- 备份文件确实被排除（正面对照，防止 _tree 的排除逻辑被改坏）---------
bak_leak = sorted(got_src & bak_src)
check('备份文件（*.bak*）不在 datas 里', not bak_leak,
      f'混入 {bak_leak[:3]}' if bak_leak else '')
check('源码树里确实存在备份文件（否则本条无意义）', bool(bak_src))

# --- 残留确实被排掉（正面对照，避免"两边都错"）-------------------------
residue = [s for s, _d in datas if '.mimosa' in s or '__pycache__' in s]
check('残留被显式排除', not residue, f'{residue[:3]}' if residue else '')
check('源码树里确实存在 .mimosa（否则本条无意义）',
      any('.mimosa' in p for p in want_src) or
      os.path.exists(os.path.join(webapp, 'templates', '.mimosa')))

# --- 目标路径 --------------------------------------------------------
bad_dest = [d for _s, d in datas if '\\' in d or not d.startswith('webapp')]
check('目标路径为 posix 且都在 webapp/ 下', not bad_dest, f'{bad_dest[:3]}')

# 嵌套文件的目录映射：对**任意**一层嵌套做通用校验（不绑定具体文件名）
nested = [(s, d) for s, d in datas
          if os.path.relpath(s, webapp).replace('\\', '/').count('/') >= 1]
check('存在嵌套文件可供校验', bool(nested))
if nested:
    s0, d0 = nested[0]
    rel_dir = os.path.dirname(os.path.relpath(s0, webapp)).replace('\\', '/')
    check('嵌套文件目录映射正确',
          d0 == 'webapp/' + rel_dir,
          f'{os.path.basename(s0)} -> {d0!r}（期望 webapp/{rel_dir!r}）')

# --- 空目录边界：_tree 逐文件展开，不会创建空目录 -----------------------
# 原来写 (目录, 目标) 时 PyInstaller 会连空目录一起建；改成逐文件后不会。
# webapp 下若出现空目录（例如预留给上传的 static/uploads），产物里就会**静默消失**。
empty_dirs = []
for cur, dns, files in os.walk(webapp):
    dns[:] = [d for d in dns if d not in EXCLUDE]
    if not files and not dns and cur != webapp:
        empty_dirs.append(os.path.relpath(cur, webapp).replace('\\', '/'))
check('webapp 下无空目录（_tree 不创建空目录）', not empty_dirs,
      f'需处理: {empty_dirs}')

print()
if fails:
    print(f'✘ {len(fails)} 项未通过: {fails}')
    raise SystemExit(1)
print(f'✔ 全部通过（datas 覆盖 {len(datas)} 个前端文件，零残留）')
