# -*- coding: utf-8 -*-
"""把 PYZ 里的字节码与磁盘源码**逐字段对照** —— 证明「改的源码真的进了包」。

和 pyz_probe.py 的分工：
  - pyz_probe.py 打印 co_names / 字符串常量，靠人工判断"这串符号是不是新写法的标志"
  - 本工具做**结构化等价比较**：把源码重新 compile 一遍，与 PYZ 里取出的 code
    对象逐字段比（co_code / co_names / co_varnames / co_freevars / co_cellvars /
    co_flags / 参数个数 ...），并**递归**进嵌套 code。

为什么必须递归：函数内部的改动在模块级 co_names 里看不见（历史上 consensus
的路径兜底改动就踩过这个坑）。递归比较能覆盖到每一个函数体。

为什么这比"跑一下 selfcheck"强：selfcheck 只证明"模块能导入"，证明不了
某个具体函数体里的常量/分支已经换成新写法。

用法:
  python dev_tools/pyz_vs_source.py <exe|pyz> [模块名...]
      不给模块名时，自动比较 PYZ 里所有 Virus_Platform_Core.* 模块。
  python dev_tools/pyz_vs_source.py <exe|pyz> --root <源码根> [模块名...]
      源码根默认取本脚本上一级目录（即平台根）。

退出码: 0 = 全部一致；1 = 存在差异或缺失。
"""
import os
import sys
import types

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 比较时忽略的字段（与"逻辑是否一致"无关）：
#   co_filename / co_firstlineno 随编译路径变化；co_qualname 亦然
_SKIP = ('co_filename', 'co_firstlineno', 'co_qualname', 'co_linetable',
         'co_exceptiontable', 'co_positions')


def _sig(c):
    """code 对象的"逻辑签名"：只保留影响执行结果的字段。"""
    return (
        c.co_code,
        c.co_names,
        c.co_varnames,
        c.co_freevars,
        c.co_cellvars,
        c.co_flags,
        c.co_argcount,
        getattr(c, 'co_posonlyargcount', 0),
        getattr(c, 'co_kwonlyargcount', 0),
        c.co_nlocals,
        c.co_stacksize,
    )


def _cmp(a, b, path, diffs, max_diffs):
    """递归比较两个 code 对象，把差异写进 diffs。"""
    if len(diffs) >= max_diffs:
        return
    if isinstance(a, types.CodeType) != isinstance(b, types.CodeType):
        diffs.append(f'{path}: 一侧是 code 一侧不是')
        return
    if not isinstance(a, types.CodeType):
        if a != b:
            diffs.append(f'{path}: 常量不同  src={a!r}  pyz={b!r}')
        return

    sa, sb = _sig(a), _sig(b)
    if sa != sb:
        fields = ('co_code', 'co_names', 'co_varnames', 'co_freevars',
                  'co_cellvars', 'co_flags', 'co_argcount', 'co_posonlyargcount',
                  'co_kwonlyargcount', 'co_nlocals', 'co_stacksize')
        for i, f in enumerate(fields):
            if sa[i] != sb[i]:
                va, vb = sa[i], sb[i]
                if f == 'co_code':
                    diffs.append(f'{path}: {f} 长度不同 '
                                 f'(src={len(va)}B, pyz={len(vb)}B)')
                else:
                    diffs.append(f'{path}: {f} 不同\n'
                                 f'      src={va!r}\n'
                                 f'      pyz={vb!r}')
                if len(diffs) >= max_diffs:
                    return
    # 递归进常量里的嵌套 code
    ca, cb = a.co_consts, b.co_consts
    if len(ca) != len(cb):
        diffs.append(f'{path}: co_consts 个数不同 src={len(ca)} pyz={len(cb)}')
        return
    for i, (x, y) in enumerate(zip(ca, cb)):
        _cmp(x, y, f'{path}[{i}]', diffs, max_diffs)


def _load_pyz(path):
    from PyInstaller.archive.readers import ZlibArchiveReader
    if path.lower().endswith('.exe'):
        import tempfile
        from PyInstaller.archive.readers import CArchiveReader
        car = CArchiveReader(path)
        blob = car.extract('PYZ.pyz')
        fd, tmp = tempfile.mkstemp(suffix='.pyz', prefix='vp_pyz_cmp_')
        with os.fdopen(fd, 'wb') as f:
            f.write(blob)
        path = tmp
    return ZlibArchiveReader(path)


def main(argv):
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass

    args = list(argv[1:])
    root = ROOT
    if '--root' in args:
        i = args.index('--root')
        root = args[i + 1]
        del args[i:i + 2]
    if not args:
        print(__doc__)
        return 2

    pyz_path, mods = args[0], args[1:]
    z = _load_pyz(pyz_path)

    if not mods:
        mods = sorted(n for n in z.toc if n.startswith('Virus_Platform_Core.'))

    n_ok = n_bad = n_missing = n_nosrc = 0
    problems = []
    for name in mods:
        if name not in z.toc:
            n_missing += 1
            problems.append(f'✘ {name}: PYZ 里没有这个模块')
            continue
        rel = name.replace('.', os.sep) + '.py'
        src = os.path.join(root, rel)
        if not os.path.isfile(src):
            # 包：模块名对应 <rel>/__init__.py
            pkg = os.path.join(root, name.replace('.', os.sep), '__init__.py')
            if os.path.isfile(pkg):
                src = pkg
            else:
                n_nosrc += 1
                problems.append(f'? {name}: 源码文件不存在 ({rel})，跳过')
                continue
        with open(src, 'rb') as f:
            source = f.read()
        try:
            ref = compile(source, src, 'exec')
        except SyntaxError as e:
            n_nosrc += 1
            problems.append(f'? {name}: 源码编译失败 {e}')
            continue
        try:
            got = z.extract(name)
        except Exception as e:
            n_bad += 1
            problems.append(f'✘ {name}: PYZ 解压失败 {type(e).__name__}: {e}')
            continue

        diffs = []
        _cmp(ref, got, name, diffs, max_diffs=6)
        if diffs:
            n_bad += 1
            problems.append(f'✘ {name}: 与源码不一致\n    ' + '\n    '.join(diffs))
        else:
            n_ok += 1

    print(f'PYZ: {pyz_path}')
    print(f'源码根: {root}')
    print(f'比较模块: {len(mods)}')
    print(f'  一致 : {n_ok}')
    print(f'  不一致: {n_bad}')
    if n_missing:
        print(f'  PYZ 缺失: {n_missing}')
    if n_nosrc:
        print(f'  无源码 : {n_nosrc}')
    if problems:
        print('\n---- 详情 ----')
        for p in problems:
            print(p)
    return 0 if (n_bad == 0 and n_missing == 0) else 1


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
