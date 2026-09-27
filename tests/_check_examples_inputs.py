# -*- coding: utf-8 -*-
"""示例**输入 fixture** 的自洽性守卫（此前没有任何测试覆盖，2026-09-18 踩过）。

背景（真实事故）
----------------
一个检查脚本的补丁把"读取示例"和"写入子集"改成了同一个路径，
**把 `examples/example_phylogeo.fasta` 覆盖成了 200 条 GenBank 病毒序列**。
后果不轻：A0 全链的 e2e 与示例按钮全废，报"超过半数的序列拿不到区划"——
而当时**没有任何测试会红**（`_check_examples_manifest.py` 只看 `examples/results/**`）。

本测试钉住「示例输入必须自洽」这条不变量：
  1. 存在、条数够、名字与随附元数据**逐条对得上**（A0 的硬要求）；
  2. 不是"病毒库转储"（不许出现 `NC_/PQ/OM…` 这类 GenBank 登录号当叶名）；
  3. 序列是**等长比对**（A0/建树要求）——示例如果不能直接喂 A0 就没有意义。

用法: python tests/_check_examples_inputs.py
"""
import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EX = os.path.join(ROOT, 'examples')
PASS, FAIL = [], []


def chk(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)


def read_fasta(path):
    seqs, name = [], None
    for ln in io.open(path, encoding='utf-8', errors='replace'):
        if ln.startswith('>'):
            name = ln[1:].strip().split()[0]
            seqs.append([name, ''])
        elif seqs:
            seqs[-1][1] += ln.strip()
    return seqs


def main():
    print('[1] example_phylogeo.fasta ↔ example_phylogeo.meta.csv（A0 全链的示例）')
    fa = os.path.join(EX, 'example_phylogeo.fasta')
    mt = os.path.join(EX, 'example_phylogeo.meta.csv')
    chk(os.path.isfile(fa), '示例 FASTA 存在')
    chk(os.path.isfile(mt), '示例元数据存在')
    if not (os.path.isfile(fa) and os.path.isfile(mt)):
        return 1
    seqs = read_fasta(fa)
    chk(len(seqs) >= 5, f'条数够用（{len(seqs)} 条；A0 至少 3 条）')
    lens = {len(s) for _n, s in seqs}
    chk(len(lens) == 1, f'是**等长比对**（唯一长度 {sorted(lens)}）—— A0 硬前置')

    # 不是"病毒库转储"：叶名不许是 GenBank 登录号
    acc = re.compile(r'^(NC_|NM_|NZ_|PQ\d|OM\d|OK\d|ON\d|MZ\d|LC\d|MN\d)')
    dumped = [n for n, _s in seqs if acc.match(n)]
    chk(not dumped,
        f'不是 GenBank 转储（登录号叶名 {len(dumped)} 个'
        f'{"，例：" + "、".join(dumped[:3]) if dumped else ""}）')

    # 名字与元数据对得上 —— 口径同 A0：**首词**精确，否则前缀/包含兜底。
    # ⚠️ 示例 FASTA 头是 `名称|区划|年份`（A0 的左约定之一），所以不能用严格相等。
    rows = [l.rstrip('\n').split(',') for l in
            io.open(mt, encoding='utf-8-sig')][1:]
    names_in_meta = {r[0].strip() for r in rows if r and r[0].strip()}

    def matches(n):
        return any(k == n or n.startswith(k) or (k and k in n)
                   for k in names_in_meta)

    miss = sorted(n for n, _s in seqs if not matches(n))
    chk(not miss,
        f'FASTA 叶名**逐条**能被元数据匹配（缺 {len(miss)} 个'
        f'{"：" + "、".join(miss[:4]) if miss else ""}）—— 这正是 A0 报'
        f'"超过半数拿不到区划"的根因')
    used = {k for k in names_in_meta if any(matches(n) and (k == n or n.startswith(k)
                                                           or k in n)
                                            for n, _s in seqs)}
    chk(len(used) == len(names_in_meta),
        f'元数据没有用不上的行（未用上 {len(names_in_meta - used)} 条）')

    print('\n[2] 其余示例输入（.fasta/.csv 成对的都查一遍名字对得上）')
    others = [f for f in sorted(os.listdir(EX))
              if f.endswith(('.fasta', '.fa', '.fas')) and f != 'example_phylogeo.fasta']
    for f in others:
        p = os.path.join(EX, f)
        try:
            ss = read_fasta(p)
        except OSError:
            continue
        chk(len(ss) > 0, f'{f} 可读（{len(ss)} 条）')
    if not others:
        print('  （没有其它 fasta 示例）')

    print('\n[3] 平台侧引用一致性（卡片「✨示例」填的路径必须真实存在）')
    import json
    consts = {}
    for fn in sorted(os.listdir(os.path.join(ROOT, 'webapp', 'static'))):
        if not fn.endswith('.js') or fn.endswith('.min.js') or '.bak' in fn:
            continue
        s = io.open(os.path.join(ROOT, 'webapp', 'static', fn),
                    encoding='utf-8', errors='replace').read()
        for m in re.finditer(r"const\s+(EXAMPLE_[A-Z0-9_]+)\s*=\s*'([^']+)'", s):
            consts[m.group(1)] = m.group(2)
    for k, v in sorted(consts.items()):
        # ⚠️ 有些常量是**逗号分隔的多文件**（如 EXAMPLE_GB_TRIO 三个 .gb）
        for rel in [x.strip() for x in v.split(',') if x.strip()]:
            rel = rel.split('?')[0]
            p = rel if os.path.isabs(rel) else os.path.join(ROOT, rel)
            chk(os.path.exists(p), f'{k} → {rel} 存在')

    print('\n' + '=' * 52)
    if FAIL:
        print(f'FAILED: {len(FAIL)} 项')
        for m in FAIL:
            print('  - ' + m)
        return 1
    print(f'EXAMPLE INPUT CHECKS PASSED（{len(PASS)} 项）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
