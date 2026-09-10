# -*- coding: utf-8 -*-
"""跨层契约审计：前端 URL ↔ 后端路由、i18n 键、模板静态资源、模块可达性。

这是「体检」工具，只读不改；发现的差异需要人工判定（有些是合法的动态拼接）。
退出码：0 = 无硬性差异；1 = 存在需要修复的差异。

用法:
    python tests/_audit_contract.py            # 全量审计
    python tests/_audit_contract.py --verbose  # 打印全部明细
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

WEBAPP = os.path.join(ROOT, 'webapp')
STATIC = os.path.join(WEBAPP, 'static')
TEMPLATES = os.path.join(WEBAPP, 'templates')

# 第三方构建产物：不参与审计（我们只审计自己写的代码）
SKIP_DIRS = ('virome', 'vendor')
SKIP_FILES = ('plotly.min.js',)


def _skip(path):
    rel = os.path.relpath(path, WEBAPP).replace('\\', '/')
    if any(rel.startswith(d + '/') for d in SKIP_DIRS):
        return True
    base = os.path.basename(path)
    if base in SKIP_FILES or '.bak' in base:
        return True
    return False


def _walk_web():
    for dp, dns, fns in os.walk(WEBAPP):
        dns[:] = [d for d in dns if d not in SKIP_DIRS]
        for fn in fns:
            p = os.path.join(dp, fn)
            if _skip(p):
                continue
            if fn.endswith(('.js', '.html')):
                yield p


def _read(path):
    with io.open(path, 'r', encoding='utf-8', errors='replace') as f:
        return f.read()


# ------------------------------------------------------------------
# 1. 后端路由表
# ------------------------------------------------------------------
def backend_rules():
    """返回 {rule: sorted(methods)}，来自真实 Flask url_map。"""
    import app as appmod
    rules = {}
    for r in appmod.app.url_map.iter_rules():
        if r.endpoint == 'static':
            continue
        methods = sorted(m for m in r.methods if m not in ('HEAD', 'OPTIONS'))
        rules[r.rule] = methods
    return rules


def _rule_regex(rule):
    """Flask rule → 正则（<conv:name> → 单段通配，<path:name> → 多段通配）。"""
    parts = []
    for seg in rule.split('/'):
        if seg.startswith('<') and seg.endswith('>'):
            inner = seg[1:-1]
            parts.append('.*' if inner.startswith('path:') else '[^/]+')
        else:
            parts.append(re.escape(seg))
    return re.compile('^' + '/'.join(parts) + '/?$')


# ------------------------------------------------------------------
# 2. 前端 URL 提取
# ------------------------------------------------------------------
_URL_RE = re.compile(r"""['"`](/[A-Za-z0-9_\-./${}():\\ ]*?)['"`]""")
_URL_BARE_RE = re.compile(r"""(/api/[A-Za-z0-9_\-./${}():\\]*)""")
_HTML_ATTR_RE = re.compile(r"""(?:href|src|action)\s*=\s*["'](/[^"']*)["']""")
# 模板表达式 {{ x }} / JS 插值 ${x} 一律视为「单段通配」
_PLACEHOLDER_RE = re.compile(r'\{\{[^}]*\}\}|\$\{[^}]*\}')


def frontend_urls():
    """返回 {url: [引用位置]}。只收以 / 开头的站内路径。"""
    out = {}
    for p in _walk_web():
        txt = _read(p)
        rel = os.path.relpath(p, ROOT).replace('\\', '/')
        for i, line in enumerate(txt.splitlines(), 1):
            for rx in (_URL_RE, _URL_BARE_RE, _HTML_ATTR_RE):
                for m in rx.finditer(line):
                    u = m.group(1)
                    if not u.startswith('/'):
                        continue
                    if u.startswith(('/static/', '/favicon')):
                        continue
                    u = _PLACEHOLDER_RE.sub('*', u)
                    u = u.split('?')[0].split('#')[0]
                    if len(u) < 2:
                        continue
                    # 单段片段（如 JS 拼接残留 '/cancel'）不单独判定
                    if u.count('/') < 2 and not u.startswith('/api'):
                        continue
                    out.setdefault(u, []).append(f'{rel}:{i}')
    return out


def _match_url(u, rules):
    """判断前端 URL 是否命中某条后端路由。

    支持 JS 字符串拼接导致的截断（如 '/api/task/' + tid + '/cancel'）
    与模板插值 '*'。
    """
    u2 = u.rstrip('/') or '/'
    pat_u = re.escape(u2).replace(r'\*', '.*')
    try:
        rx_u = re.compile('^' + pat_u + '$')
    except re.error:
        rx_u = None
    for rule in rules:
        if _rule_regex(rule).match(u2):
            return rule
        r2 = rule.rstrip('/') or '/'
        # 截断前缀：/api/task 是 /api/task/<tid>/cancel 的前缀
        if r2.startswith(u2 + '/'):
            return rule
        if rx_u is not None and rx_u.match(r2):
            return rule
    return None


# ------------------------------------------------------------------
# 3. i18n
# ------------------------------------------------------------------
# 键可以多个写在同一行（'a.b': 'x', 'c.d': 'y'），故不能锚定行首。
# 值多为中文，ASCII 纯字母值后紧跟冒号的情形不存在，误匹配风险可忽略。
_KEY_RE = re.compile(r"""['"]([A-Za-z0-9_.\-]+)['"]\s*:""")
_USE_RE = re.compile(r"""\bt\(\s*['"]([A-Za-z0-9_.\-]+)['"]""")
_ATTR_RE = re.compile(r"""data-i18n(?:-ph|-title)?\s*=\s*["']([A-Za-z0-9_.\-]+)["']""")


def i18n_report():
    p = os.path.join(STATIC, 'i18n.js')
    txt = _read(p)
    # 只取 I18N_DICT 对象体：其后的语言切换代码里也有形如 'Content-Type': ... 的
    # 字符串，若全文件扫描会产生假阳性。
    start = txt.find('I18N_DICT')
    if start < 0:
        start = 0
    end = txt.find('\n};', start)
    body = txt[start:end if end > 0 else len(txt)]
    cut = body.find('\n  en:')
    if cut < 0:
        cut = len(body)
    zh_keys = set(_KEY_RE.findall(body[:cut]))
    en_keys = set(_KEY_RE.findall(body[cut:]))

    used = {}
    for fp in _walk_web():
        if os.path.basename(fp) == 'i18n.js':
            continue
        rel = os.path.relpath(fp, ROOT).replace('\\', '/')
        for i, line in enumerate(_read(fp).splitlines(), 1):
            for rx in (_USE_RE, _ATTR_RE):
                for m in rx.finditer(line):
                    used.setdefault(m.group(1), []).append(f'{rel}:{i}')
    return zh_keys, en_keys, used


# ------------------------------------------------------------------
# 4. 模板静态资源存在性
# ------------------------------------------------------------------
_ASSET_RE = re.compile(r"""["'(](/static/[^"')?\s]+)""")


def static_assets():
    out = {}
    for p in _walk_web():
        rel = os.path.relpath(p, ROOT).replace('\\', '/')
        for i, line in enumerate(_read(p).splitlines(), 1):
            for m in _ASSET_RE.finditer(line):
                out.setdefault(m.group(1).split('?')[0], []).append(f'{rel}:{i}')
    return out


# ------------------------------------------------------------------
# 5. 模块可达性（vp 下哪些模块从未被 import）
# ------------------------------------------------------------------
_IMPORT_RE = re.compile(
    r"""^\s*(?:from\s+(\.?[\w.]*)\s+import\s+([^\n(]*)|import\s+(\.?[\w.]+))""",
    re.M)


def _pkg_of(rel_path):
    """文件相对仓库根的路径 → 其所在包名（如 vp/web/tasks.py → vp.web）。"""
    parts = rel_path.replace('\\', '/').split('/')[:-1]
    return '.'.join(parts)


def _imported_modules(txt, rel_path):
    """用 AST 提取被 import 的模块全名集合（正确处理相对导入与括号续行）。"""
    import ast
    out = set()
    pkg = _pkg_of(rel_path)
    try:
        tree = ast.parse(txt)
    except SyntaxError:
        return out
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ''
            if node.level:
                # 相对导入：node.level=1 表示当前包
                up = node.level - 1
                base_pkg = pkg
                for _ in range(up):
                    base_pkg = base_pkg.rsplit('.', 1)[0] if '.' in base_pkg else ''
                base = (base_pkg + '.' + base) if base else base_pkg
            base = base.strip('.')
            if base:
                out.add(base)
            for a in node.names:
                if a.name == '*':
                    continue
                full = (base + '.' + a.name).strip('.') if base else a.name
                out.add(full)
    return {x for x in out if x}


def module_reachability():
    pkg = os.path.join(ROOT, 'vp')
    mods = {}
    for dp, dns, fns in os.walk(pkg):
        dns[:] = [d for d in dns if d != '__pycache__']
        for fn in fns:
            if not fn.endswith('.py') or '.bak' in fn:
                continue
            p = os.path.join(dp, fn)
            rel = os.path.relpath(p, ROOT).replace('\\', '/')
            name = rel[:-3].replace('/', '.')
            if name.endswith('.__init__'):
                name = name[:-9]
            mods[name] = rel
    refs = set()
    string_refs = set()   # 以字符串形式被引用的模块名（子进程脚本等）
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns
                  if d not in ('__pycache__', '.git', 'build', 'dist',
                               'node_modules', 'tools', 'bin', '_archive')
                  and not d.startswith(('_backup', '_audit'))]
        for fn in fns:
            if not fn.endswith('.py') or '.bak' in fn:
                continue
            fp = os.path.join(dp, fn)
            txt = _read(fp)
            rel = os.path.relpath(fp, ROOT)
            for mod in _imported_modules(txt, rel):
                if not mod:
                    continue
                refs.add(mod)
                # vp.a.b 也记 vp.a
                parts = mod.split('.')
                for k in range(1, len(parts)):
                    refs.add('.'.join(parts[:k]))
            for m in re.finditer(r"""['"]([A-Za-z_][\w]*\.py)['"]""", txt):
                string_refs.add(m.group(1))
    unreachable = []
    for name, rel in sorted(mods.items()):
        if name in ('vp', 'vp.web'):
            continue
        if name in refs:
            continue
        # 检查是否有子模块被引用
        if any(r.startswith(name + '.') for r in refs):
            continue
        # 以 .py 文件名形式被字符串引用（子进程脚本：engine_entry 等）
        if os.path.basename(rel) in string_refs:
            continue
        unreachable.append((name, rel))
    return unreachable


# ------------------------------------------------------------------
def main():
    verbose = '--verbose' in sys.argv
    problems = []

    print('=' * 68)
    print('跨层契约审计')
    print('=' * 68)

    # --- 1/2 前端 ↔ 后端 ---
    rules = backend_rules()
    urls = frontend_urls()
    print(f'\n[1] 后端路由 {len(rules)} 条 / 前端站内路径 {len(urls)} 个')
    unmatched = []
    for u in sorted(urls):
        if _match_url(u, rules) is None:
            unmatched.append((u, urls[u]))
    if unmatched:
        print(f'  ⚠ 前端引用但后端无匹配路由 {len(unmatched)} 个:')
        for u, locs in unmatched:
            print(f'      {u}   ({locs[0]}'
                  + (f' 等 {len(locs)} 处' if len(locs) > 1 else '') + ')')
        problems.append(f'前端 URL 无后端路由: {len(unmatched)}')
    else:
        print('  ✔ 前端引用的站内路径全部命中后端路由')

    # 后端有但前端从未引用的 API（页面路由除外）
    used_rules = set()
    for u in urls:
        r = _match_url(u, rules)
        if r:
            used_rules.add(r)
    orphan_api = [r for r in sorted(rules)
                  if r.startswith('/api/') and r not in used_rules]
    print(f'  · 前端未引用的 /api/ 路由 {len(orphan_api)} 条'
          '（可能仅供 CLI/测试使用）')
    if verbose:
        for r in orphan_api:
            print(f'      {r}')

    # --- 3 i18n ---
    zh, en, used = i18n_report()
    print(f'\n[2] i18n：zh 定义 {len(zh)} 键 / en 定义 {len(en)} 键 / '
          f'代码使用 {len(used)} 键')
    only_zh = sorted(zh - en)
    only_en = sorted(en - zh)
    missing = sorted(k for k in used if k not in zh and k not in en)
    unused = sorted(k for k in zh if k not in used)
    if only_zh:
        print(f'  ⚠ 仅 zh 有、en 缺失 {len(only_zh)} 键: {only_zh[:12]}'
              + (' ...' if len(only_zh) > 12 else ''))
        problems.append(f'i18n en 缺 {len(only_zh)} 键')
    if only_en:
        print(f'  ⚠ 仅 en 有、zh 缺失 {len(only_en)} 键: {only_en[:12]}'
              + (' ...' if len(only_en) > 12 else ''))
        problems.append(f'i18n zh 缺 {len(only_en)} 键')
    if missing:
        print(f'  ⚠ 代码使用但字典未定义 {len(missing)} 键:')
        for k in missing[:30]:
            print(f'      {k}   ({used[k][0]})')
        if len(missing) > 30:
            print(f'      ... 另有 {len(missing) - 30} 个')
        problems.append(f'i18n 未定义键 {len(missing)}')
    if not (only_zh or only_en or missing):
        print('  ✔ i18n 键完整（zh/en 一致，使用键全部有定义）')
    print(f'  · 字典中未被使用的键 {len(unused)} 个')

    # --- 4 静态资源 ---
    assets = static_assets()
    missing_assets = []
    for a, locs in sorted(assets.items()):
        p = os.path.join(WEBAPP, a.lstrip('/').replace('/', os.sep))
        if not os.path.exists(p):
            missing_assets.append((a, locs[0]))
    print(f'\n[3] 模板/JS 引用静态资源 {len(assets)} 个')
    if missing_assets:
        print(f'  ⚠ 缺失 {len(missing_assets)} 个:')
        for a, loc in missing_assets:
            print(f'      {a}   ({loc})')
        problems.append(f'静态资源缺失 {len(missing_assets)}')
    else:
        print('  ✔ 全部存在')

    # --- 5 模块可达性 ---
    unreachable = module_reachability()
    print('\n[4] vp 包模块可达性')
    if unreachable:
        print(f'  · 未被任何模块 import 的 {len(unreachable)} 个'
              '（可能是 CLI 延迟导入或废弃）:')
        for name, rel in unreachable:
            print(f'      {rel}')
    else:
        print('  ✔ 全部模块均被引用')

    print('\n' + '=' * 68)
    if problems:
        print('审计结论：存在 %d 类需要处理的差异' % len(problems))
        for p in problems:
            print('  - ' + p)
        return 1
    print('审计结论：✔ 无硬性差异')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
