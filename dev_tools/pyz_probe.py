# -*- coding: utf-8 -*-
"""从 PyInstaller 的 PYZ 里取出模块字节码 —— 用于确认「修复是否真的进了打包产物」。

为什么需要它：打包后 `Virus_Platform_Core` 的代码在 exe 的 PYZ 里，不是磁盘上的
.py 文件。改完源码重新打包后，如果只跑 `--cli selfcheck`，只能证明"模块能导入"，
**证明不了某个具体的路径常量已经换成新写法**；而函数内部的改动更是完全没有
外部可观测的入口。本工具直接读 PYZ 里的 code 对象，把符号表打出来对照。

用法:
  python dev_tools/pyz_probe.py <PYZ路径或exe路径> --list
      列出全部模块名（可 grep 定位）
  python dev_tools/pyz_probe.py <PYZ路径或exe路径> <模块名> [<模块名>...]
      打印这些模块（**递归**含嵌套 code 对象）的全部 co_names 与字符串常量

路径可以是：
  - `build/<名字>/PYZ-00.pyz`（PyInstaller 的 --workpath；注意 package.py
    跑完会把 build/ 删掉，所以通常直接给 exe）
  - 打包好的 `VirusPlatform.exe` —— 内嵌的 `PYZ.pyz` 会被自动抽到临时文件再读
想拿到"修复前"的对照，就在重新打包前先把 build/ 改名留存
（例如 `mv build build_prev_before_fix`），之后对两份 PYZ 跑同样的命令。

判据示例（2026-09-11 的冻结路径修复）:
  旧 `suvtk_submit` 有 `str(Path(__file__).resolve().parents[1])` → co_names 含 'Path'
  新 `suvtk_submit` 用 `from .config import PLATFORM_ROOT`  → 不含 'Path'，含 'PLATFORM_ROOT'
  旧 `consensus._samtools_exe` 兜底用 `os.path.abspath(__file__)` → 含 'abspath'

注意：**必须递归**看嵌套 code 对象。只看模块级 `co_names` 会漏掉函数内部的改动
（consensus 的改动就在函数里，只看模块级会误判成"两边一样"）。

局限：PYZ 的压缩格式随 PyInstaller 版本变化，本工具只能读**本机安装的
PyInstaller 版本**产出的 PYZ。读别的版本打的包会报
`zlib.error: incorrect header check`（例如 BioAider 的
`_bioaider_re/BioAider.exe_extracted/PYZ-00.pyz` 就解不开）——
那种情况请用对应版本的 PyInstaller 或 pyinstxtractor。
"""
import os
import sys
import types


def walk(code):
    """递归收集 code 及其所有嵌套 code 的 co_names / 字符串常量。"""
    names = set(code.co_names)
    consts = set()
    for c in code.co_consts:
        if isinstance(c, types.CodeType):
            n2, c2 = walk(c)
            names |= n2
            consts |= c2
        elif isinstance(c, str):
            consts.add(c)
    return names, consts


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    pyz, rest = argv[1], argv[2:]

    # exe 形式：把内嵌的 PYZ.pyz 抽出来再读（package.py 跑完会删掉 build/）
    if pyz.lower().endswith('.exe'):
        import tempfile
        from PyInstaller.archive.readers import CArchiveReader
        car = CArchiveReader(pyz)
        blob = car.extract('PYZ.pyz')
        fd, tmp = tempfile.mkstemp(suffix='.pyz', prefix='vp_pyz_')
        with os.fdopen(fd, 'wb') as f:
            f.write(blob)
        print(f'从 exe 抽出内嵌 PYZ -> {tmp}')
        pyz = tmp

    from PyInstaller.archive.readers import ZlibArchiveReader
    z = ZlibArchiveReader(pyz)
    print(f'PYZ: {pyz}（{len(z.toc)} 个条目）')

    if not rest or rest == ['--list']:
        for name in sorted(z.toc):
            print(' ', name)
        return 0

    for name in rest:
        if name not in z.toc:
            print(f'\n✘ {name}: PYZ 里找不到')
            continue
        try:
            code = z.extract(name)
        except Exception as e:      # 版本不匹配 / 条目损坏
            print(f'\n✘ {name}: 解压失败（{type(e).__name__}: {e}）')
            print('   PYZ 格式随 PyInstaller 版本变化，'
                  '请用产出该包的同版本 PyInstaller 运行本工具')
            continue
        names, consts = walk(code)
        print(f'\n=== {name} ===')
        print(f'co_names（{len(names)}）:')
        for n in sorted(names):
            print('   ', n)
        strs = sorted(c for c in consts if c and len(c) < 60)
        print(f'字符串常量（{len(strs)}）:')
        for c in strs:
            print('   ', repr(c))
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
