# -*- coding: utf-8 -*-
"""回归：TreeTime mugration 的**状态代号映射**必须完整（含标点代号）。

背景（2026-09-18 真跑发现）
--------------------------
TreeTime mugration 给每个状态分配**单字符代号**（`GTR.txt` 的
`Character to attribute mapping`）。**状态多于 36 个时代号会跨到标点**
（实测 `[`=Peru、`\\`=Poland、`]`=Russia、`^`=Russia, Institute…）。

我们原来读映射用了 `^([A-Za-z0-9]+)\\s*:\\s*(.*)$` —— **只认字母数字**，
于是标点代号那几条读不到（实测 37 个状态只解析出 32 条）。后果：
`confidence.csv` 的列名**部分**翻译成功，`state_of` 里真地名与未翻译代号混用
（`China → ]` 而不是 `China → Russia`）→ **走廊表上若干区划被标成标点**，
凡按区划名做的下游匹配（地图落点、坐标表、逐区统计）都会漏掉它们。
更隐蔽的是：旧告警条件写的是"**一条都没**映射上才告警"，部分失败**静默通过**。

本测试**不依赖 TreeTime**：用合成的 GTR.txt / confidence.csv 把这条口径钉住。

用法: python tests/_check_gtr_mapping.py
"""
import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from Virus_Platform_Core import treetime_ml as tt          # noqa: E402

WORK = os.path.join(ROOT, 'run', '_check_gtr_mapping')
PASS, FAIL = [], []


def chk(cond, msg):
    (PASS if cond else FAIL).append(msg)
    print(('  ok   ' if cond else '  FAIL ') + msg, flush=True)


# 40 个状态 → 代号必须跨到标点（A..Z 只有 26 个）
CODES = [chr(c) for c in range(65, 65 + 40)]        # A..Z 然后 [ \ ] ^ _ ` a..m
# 按**真跑实测**摆放：`E`=China、`[`=Peru、`\`=Poland、`]`=Russia、`^`=Russia, Khabarovsk
NAMED = {'E': 'China', '[': 'Peru', chr(92): 'Poland', ']': 'Russia',
         '^': 'Russia, Khabarovsk'}
NAMES = [NAMED.get(c, 'Loc%02d' % i) for i, c in enumerate(CODES)]


def build_gtr():
    lines = ['Character to attribute mapping:']
    for c, nm in zip(CODES, NAMES):
        lines.append('  %s: %s' % (c, nm))
    lines.append('')
    lines.append('Substitution rate (mu): 0.5')
    lines.append('')
    lines.append('Equilibrium frequencies (pi_i):')
    for c in CODES:
        lines.append('  %s: %.4f' % (c, 1.0 / len(CODES)))
    return '\n'.join(lines) + '\n'


def build_confidence():
    hdr = '#name, ' + ', '.join(CODES)
    rows = [hdr]
    # 一个叶 + 两个内部节点；内部节点偏向 `]`（Russa）与 `[`（Peru）
    for nm, pick in (('TIP0001', 'E'), ('NODE_0000001', ']'), ('NODE_0000002', '[')):
        vals = []
        for c in CODES:
            vals.append('0.99' if c == pick else '0.0001')
        rows.append('%s, %s' % (nm, ', '.join(vals)))
    return '\n'.join(rows) + '\n'


def main():
    os.makedirs(WORK, exist_ok=True)
    gtr_p = os.path.join(WORK, 'GTR.txt')
    conf_p = os.path.join(WORK, 'confidence.csv')
    io.open(gtr_p, 'w', encoding='utf-8', newline='\n').write(build_gtr())
    io.open(conf_p, 'w', encoding='utf-8', newline='\n').write(build_confidence())

    print('[1] GTR.txt 的代号映射必须**一条不漏**（含标点代号）')
    g = tt.parse_gtr_txt(gtr_p)
    mp = g.get('mapping') or {}
    chk(len(mp) == len(CODES),
        '映射条数 = 状态数（%d/%d）' % (len(mp), len(CODES)))
    for c in ('[', ']', chr(92), '^', '_'):
        chk(c in mp, '标点代号 %r 也被解析（→ %s）' % (c, mp.get(c)))
    chk(mp.get(']') == 'Russia', "`]` 映射成 Russia（真跑实测值）")
    print('  映射样例:', {k: mp[k] for k in list(mp)[24:30]})

    print('\n[2] pi（均衡频率）同样不能漏标点代号')
    # 上面 GTR 里每个代号都写了 pi → 条数应等于状态数
    chk(len(g.get('pi') or {}) == len(CODES),
        'pi 条数 = 状态数（%d/%d）' % (len(g.get('pi') or {}), len(CODES)))

    print('\n[3] confidence.csv 必须**全部**翻译成地名，且未映射数为 0')
    rows, summ = tt.parse_confidence_csv(conf_p, mp)
    chk(summ.get('n_labels_unmapped') == 0,
        '未映射列数 = 0（实际 %s）' % summ.get('n_labels_unmapped'))
    chk(summ.get('confidence_labels_mapped') is True, '整体标记为已映射')
    best = {r['name']: r['best'] for r in rows}
    chk(best.get('NODE_0000001') == 'Russia',
        "内部节点状态是地名而不是代号（%r）" % best.get('NODE_0000001'))
    chk(best.get('NODE_0000002') == 'Peru', "`[` → Peru（%r）" % best.get('NODE_0000002'))
    chk(best.get('TIP0001') == 'China', '叶状态也走同一套映射（%r）' % best.get('TIP0001'))

    print('\n[4] 部分未映射必须**能被报出来**（旧条件只在"全失败"时才告警）')
    rows2, summ2 = tt.parse_confidence_csv(conf_p, {'E': 'China'})   # 只给一条映射
    chk(summ2.get('n_labels_unmapped') == len(CODES) - 1,
        '部分映射时未映射数被如实统计（%s）' % summ2.get('n_labels_unmapped'))
    chk(summ2.get('confidence_labels_unmapped'),
        '并给出未映射代号清单（前 3: %s）'
        % (summ2.get('confidence_labels_unmapped') or [])[:3])
    chk(summ2.get('confidence_labels_mapped') is True,
        '（旧字段仍为 True —— 正因如此才需要新的计数与告警条件）')

    print('\n' + '=' * 52)
    if FAIL:
        print('FAILED: %d 项' % len(FAIL))
        for m in FAIL:
            print('  - ' + m)
        return 1
    print('GTR MAPPING CHECKS PASSED（%d 项）' % len(PASS))
    return 0


if __name__ == '__main__':
    sys.exit(main())
