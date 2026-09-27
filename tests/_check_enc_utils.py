# -*- coding: utf-8 -*-
"""编码统一工具回归：decode_output / to_utf8_file（2026-09-27 日志编码闭环）。

覆盖四类真实场景：
  1. 纯 GBK 产物（RAxML-NG/LSD2 把含中文路径的行按系统 ANSI 写盘）→ 转写为 UTF-8；
  2. 纯 UTF-8/ASCII 产物 → 原样保留（字节级不变，幂等）；
  3. 混编码文件（cmd 重定向：UTF-8 框线 + GBK 报错逐行共存）→ 逐行无损规范化；
  4. 文件不存在 → 静默 False，不抛异常。
外加 decode_output 的 utf-8 优先 / GBK 兜底 / 不可解 replace 三分支。
全程离线，秒级。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Virus_Platform_Core.utils import decode_output, to_utf8_file  # noqa: E402
from Virus_Platform_Core.config import DIRS  # noqa: E402

OUT = os.path.join(DIRS['tool_runs'], '_enc_check')


def check(cond, msg):
    print(('  ok ' if cond else '  FAIL ') + msg, flush=True)
    assert cond, msg


def main():
    os.makedirs(OUT, exist_ok=True)

    # ---- decode_output 三分支 ----
    check(decode_output('已是字符串') == '已是字符串', 'str 输入原样返回')
    check(decode_output('中文路径'.encode('gbk')) == '中文路径', 'GBK 字节按 GBK 解')
    check(decode_output('utf8 中文'.encode('utf-8')) == 'utf8 中文', 'UTF-8 字节按 UTF-8 解')
    check(decode_output(b'\xff\xfe\x00') .count('\ufffd') >= 1, '不可解字节退 replace')

    # ---- to_utf8_file 场景 1：纯 GBK（RAxML-NG 日志形态）----
    p1 = os.path.join(OUT, 'a.raxml.log')
    raw1 = 'RAxML-NG started, alignment: D:/桌面/数据/aln.fasta'.encode('gbk')
    with open(p1, 'wb') as f:
        f.write(raw1)
    check(to_utf8_file(p1) is True, '纯 GBK 文件被转写')
    with open(p1, 'rb') as f:
        got = f.read()
    check(got.decode('utf-8') == raw1.decode('gbk'), '转写后内容逐字符一致')
    check(to_utf8_file(p1) is False, '已是 UTF-8 的文件幂等跳过')

    # ---- 场景 2：纯 ASCII/UTF-8（LSD2 .result 数值形态）----
    p2 = os.path.join(OUT, 'b.result')
    raw2 = b'rate 0.0032 tMRCA 1978.4\n'
    with open(p2, 'wb') as f:
        f.write(raw2)
    check(to_utf8_file(p2) is False, '纯 ASCII 不改写')
    with open(p2, 'rb') as f:
        check(f.read() == raw2, '纯 ASCII 字节级不变')

    # ---- 场景 3：混编码（cmd 重定向形态：UTF-8 框线 + GBK 报错）----
    p3 = os.path.join(OUT, 'c_mixed.log')
    raw3 = ('╔══╗'.encode('utf-8') + b'\r\n'
            + "'" .encode('gbk') + '不是内部或外部命令'.encode('gbk') + b'\r\n')
    with open(p3, 'wb') as f:
        f.write(raw3)
    check(to_utf8_file(p3) is True, '混编码文件被逐行规范化')
    with open(p3, 'rb') as f:
        txt = f.read().decode('utf-8')
    check('╔══╗' in txt and '不是内部或外部命令' in txt, 'UTF-8 行与 GBK 行均无损保留')

    # ---- 场景 4：文件不存在 ----
    check(to_utf8_file(os.path.join(OUT, 'nope.log')) is False, '缺失文件静默 False')

    print('ENC UTILS CHECKS PASSED')


if __name__ == '__main__':
    main()
