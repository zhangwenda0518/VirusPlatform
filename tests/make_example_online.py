"""为「在线」工具卡（t-cdd / t-hom）生成示例结果。

这两张卡走 NCBI 在线接口（Batch CD-Search / BLAST URL API），结果不落在
tool_runs/<run>/ 里，而是缓存成 tool_runs/_seq_input/<contig>_<md5>/analysis/
<contig>_<action>.json。本脚本用示例 contig 真跑一遍，把 JSON 固化到
databases/examples/results/{cdd,hom}/，与真实数据隔离。

用法（需平台已在 http://127.0.0.1:8765 运行）：
    python tests/make_example_online.py
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = os.environ.get('VP_BASE', 'http://127.0.0.1:8765')
EX = os.path.join(ROOT, 'databases', 'examples')
OUT = os.path.join(EX, 'results')
CONTIGS = os.path.join(EX, 'example_viral_contigs.fasta')


def _post(path: str, payload: dict) -> dict:
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode('utf-8'),
        headers={'Content-Type': 'application/json'}, method='POST')
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def _get(path: str):
    with urllib.request.urlopen(BASE + path, timeout=60) as r:
        return json.loads(r.read().decode('utf-8'))


def first_record(path: str) -> tuple[str, str]:
    name, buf = None, []
    for ln in io.open(path, encoding='utf-8'):
        ln = ln.strip()
        if ln.startswith('>'):
            if name:
                break
            name = ln[1:].split()[0]
        elif name:
            buf.append(ln)
    return name, ''.join(buf)


def run_one(contig: str, seq: str, action: str) -> str:
    """提交在线分析并等待完成，返回缓存 JSON 的路径。"""
    d = _post('/api/tool/analyze',
              {'run': '_seq_input', 'contig': contig, 'action': action,
               'seq': seq})
    if d.get('error'):
        raise RuntimeError(f'{action}: 启动失败 {d["error"]}')
    tid = d.get('task')
    if not tid:
        print(f'    {action}: 已有缓存，跳过运行')
    else:
        t0 = time.time()
        while True:
            snap = _get('/api/task/' + tid)
            st = snap.get('status')
            if st == 'done':
                break
            if st in ('failed', 'cancelled'):
                raise RuntimeError(f'{action}: 任务 {st} {snap.get("error")}')
            if time.time() - t0 > 900:
                raise RuntimeError(f'{action}: 超时')
            time.sleep(3)
        print(f'    {action}: 完成（{time.time() - t0:.0f}s）')
    key = hashlib.md5((contig + '|' + seq).encode('utf-8')).hexdigest()[:12]
    safe = re.sub(r'[^A-Za-z0-9_\-.]', '_', contig)[:30]
    p = os.path.join(ROOT, 'tool_runs', '_seq_input', f'{safe}_{key}',
                     'analysis', f'{safe}_{key}_{action}.json')
    if not os.path.isfile(p):
        raise RuntimeError(f'{action}: 缓存文件不存在 {p}')
    return p


def main() -> int:
    if not os.path.isfile(CONTIGS):
        print(f'缺少示例 contig 文件: {CONTIGS}')
        return 2
    contig, seq = first_record(CONTIGS)
    print(f'示例 contig: {contig} ({len(seq)} bp)')
    jobs = [('cdd', 'cdd'), ('blastn', 'hom'), ('blastx', 'hom')]
    made: dict[str, list[str]] = {}
    for action, module in jobs:
        try:
            src = run_one(contig, seq, action)
        except Exception as e:                       # noqa: BLE001
            print(f'  ! {action} 失败: {e}')
            continue
        dst_dir = os.path.join(OUT, module)
        os.makedirs(dst_dir, exist_ok=True)
        dst = os.path.join(dst_dir, f'{contig}_{action}.json')
        shutil.copy2(src, dst)
        made.setdefault(module, []).append(os.path.basename(dst))
        print(f'  → databases/examples/results/{module}/{os.path.basename(dst)}'
              f'  ({os.path.getsize(dst) / 1024:.1f} KB)')

    # 更新/写入 manifest 条目
    mp = os.path.join(OUT, 'manifest.json')
    man = json.load(io.open(mp, encoding='utf-8')) if os.path.isfile(mp) else {}
    titles = {'cdd': '保守域与功能元件注释（CDD · NCBI 在线）',
              'hom': '同源比对（BLASTN / BLASTX · NCBI 在线）'}
    for module, files in made.items():
        d = os.path.join(OUT, module)
        allf = []
        for dirpath, _dirs, names in os.walk(d):
            for n in names:
                allf.append(os.path.relpath(os.path.join(dirpath, n), d)
                            .replace('\\', '/'))
        man[module] = {
            'title': titles.get(module, module),
            'files': sorted(allf),
            'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'databases/examples/',
            'note': 'NCBI 在线分析（示例 contig），结果已固化',
        }
    with io.open(mp, 'w', encoding='utf-8') as f:
        json.dump(man, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'manifest 已更新：{len(man)} 个模块')
    return 0


if __name__ == '__main__':
    sys.exit(main())
