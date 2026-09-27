# -*- coding: utf-8 -*-
"""自检 pyz_vs_source._cmp 的灵敏度：确保它不是"恒等返回真"。

做法：拿两段**确实不同**的源码编译出来的 code 对象做比较，必须报出差异；
再拿同一段源码编译两次做比较，必须报无差异。
"""
import os
import sys

# 控制台编码兜底：Windows 默认代码页是 GBK，本脚本末尾的 ✔/✘ 会让 print 抛
# UnicodeEncodeError（与其余测试同款问题）。只改错误处理为 replace。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(errors='replace')
    except (AttributeError, OSError):
        pass

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from dev_tools.pyz_vs_source import _cmp  # noqa: E402

A = "def f(x):\n    return x + 1\n"
B = "def f(x):\n    return x + 2\n"          # 仅常量 1 -> 2
C = "def f(x):\n    return x - 1\n"          # 运算符不同
D = "def f(x):\n    return x + 1\n\ndef g():\n    return 42\n"  # 多一个函数

fails = []


def check(label, src_a, src_b, expect_diff):
    a = compile(src_a, 'a.py', 'exec')
    b = compile(src_b, 'b.py', 'exec')
    diffs = []
    _cmp(a, b, 'M', diffs, max_diffs=6)
    ok = bool(diffs) == expect_diff
    print(f'  {"OK " if ok else "FAIL"} {label}: '
          f'{"发现差异" if diffs else "无差异"} (期望{"有" if expect_diff else "无"})')
    if not ok:
        fails.append(label)


print('灵敏度自检：')
check('同一源码两遍', A, A, False)
check('常量改动 1->2', A, B, True)
check('运算符 + -> -', A, C, True)
check('新增函数 g', A, D, True)
# 函数内部改动（模块级 co_names 看不出来的那种）
E = "X = 1\n\ndef f(a):\n    return a * 2\n"
F = "X = 1\n\ndef f(a):\n    return a * 3\n"
check('函数体内部常量改动', E, F, True)

print()
if fails:
    print(f'✘ 自检未通过: {fails}')
    raise SystemExit(1)
print('✔ 自检通过：比较器能区分不同字节码，且对相同字节码不误报')
