"""为「同属共线性比较」（t-synteny / LoVis4u）生成示例结果。

该卡的输入是 GenBank 集合或 .gb 文件；平台已内置 3 个示例 .gb
（example_synteny_A/B/C.gb，同属不同种），这里直接用内置引擎
（vp.synteny.run_comparison，LoVis4u 不可用时自动回退）跑一遍，
把 compare.html / SVG / PNG / 家族表固化到 databases/examples/results/synteny/。

用法：
    python tests/make_example_synteny.py
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

EX = os.path.join(ROOT, 'databases', 'examples')
OUT = os.path.join(EX, 'results', 'synteny')
WORK = os.path.join(EX, '_work', 'synteny')
GBS = [os.path.join(EX, f'example_synteny_{x}.gb') for x in 'ABC']
KEEP = ('compare.html', 'compare.svg', 'compare.png', 'gene_clusters.tsv',
        'genome_similarity.tsv', 'summary.json')


def main() -> int:
    missing = [p for p in GBS if not os.path.isfile(p)]
    if missing:
        print('缺少示例 .gb：' + ', '.join(missing))
        return 2
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)

    from vp.synteny import run_comparison

    def prog(stage, pct, msg):
        print(f'  [{stage}] {int(pct * 100)}% {msg}', flush=True)

    print(f'对 {len(GBS)} 个示例 GenBank 跑同属比较 …', flush=True)
    res = run_comparison(files=GBS, out_dir=WORK, min_ident=0.30,
                         min_cov=0.50, lovis4u_pdf=False, prog=prog)
    print(f'完成：{res["n_genomes"]} 基因组 · {res["n_genes"]} 基因 · '
          f'{res["n_clusters"]} 家族', flush=True)

    os.makedirs(OUT, exist_ok=True)
    copied = []
    for name in KEEP:
        src = os.path.join(WORK, name)
        if os.path.isfile(src):
            shutil.copy2(src, os.path.join(OUT, name))
            copied.append(name)
            print(f'  → results/synteny/{name}  '
                  f'({os.path.getsize(src) / 1024:.1f} KB)', flush=True)

    # 顺带建一个示例 GenBank 集合（t-seqprep「参考序列获取」的产物示例，
    # 也是 t-synteny / t-treebuild 选集合时的现成输入）
    try:
        from vp.gb_collection import import_local_gb, list_gb_collections
        names = {c['name'] for c in list_gb_collections()}
        if 'EXAMPLE_SET' not in names:
            import_local_gb('EXAMPLE_SET', GBS)
            print('  → GenBank 集合 EXAMPLE_SET（3 条记录）', flush=True)
        else:
            print('  → GenBank 集合 EXAMPLE_SET 已存在', flush=True)
    except Exception as e:                           # noqa: BLE001
        print(f'  ! 示例集合创建失败（不影响共线性示例）: {e}', flush=True)

    mp = os.path.join(EX, 'results', 'manifest.json')
    man = json.load(io.open(mp, encoding='utf-8')) if os.path.isfile(mp) else {}
    man['synteny'] = {
        'title': '同属共线性比较（LoVis4u / 内置引擎）',
        'files': sorted(copied),
        'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
        'source': 'databases/examples/example_synteny_{A,B,C}.gb',
        'note': (f'示例 3 个同属 GenBank：{res["n_genes"]} 基因 → '
                 f'{res["n_clusters"]} 个家族'),
    }
    with io.open(mp, 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'manifest 已更新：{len(man)} 个模块', flush=True)
    return 0


if __name__ == '__main__':
    sys.exit(main())
