# -*- coding: utf-8 -*-
"""kvsuite 基准：直接驱动已知病毒识别+定量，测时间与进程树峰值内存。"""
import json
import os
import sys
import time
import threading

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
PLATFORM = r'D:\桌面\植物病毒分析平台'
sys.path.insert(0, PLATFORM)
DATA = r'E:\谷歌下载\测试数据验证'
OUT_ROOT = os.path.join(PLATFORM, '_bench_kvs')


def _safe_path(base, *parts):
    """规范化并确保落在 base 目录内（防拼接越界）。"""
    base = os.path.normpath(base)
    p = os.path.normpath(os.path.join(base, *parts))
    if os.path.commonpath([base, p]) != base:
        raise ValueError(f'路径越界: {p}')
    return p


DATASETS = [
    ('Dataset_1', os.path.join(DATA, 'Dataset_1_R1.fastq.gz'),
     os.path.join(DATA, 'Dataset_1_R2.fastq.gz'), 'PE 2x150'),
    ('Dataset_2', os.path.join(DATA, 'Dataset_2_R1.fastq.gz'),
     os.path.join(DATA, 'Dataset_2_R2.fastq.gz'), 'PE 2x150'),
    ('Dataset_3', os.path.join(DATA, 'Dataset_3_R1.fastq.gz'),
     os.path.join(DATA, 'Dataset_3_R2.fastq.gz'), 'PE 2x150'),
]


def tree_snapshot(root_proc):
    """返回 (进程树RSS总和, 树内最大单进程RSS)。字节。"""
    procs = [root_proc]
    try:
        procs += root_proc.children(recursive=True)
    except Exception:
        pass
    total = single = 0
    for p in procs:
        try:
            rss = p.memory_info().rss
            total += rss
            single = max(single, rss)
        except Exception:
            pass
    return total, single


def run_one(name, r1, r2, dtype):
    import psutil
    from Virus_Platform_Core.kv_stage import run_kvsuite_stage

    out_dir = _safe_path(OUT_ROOT, name)
    os.makedirs(out_dir, exist_ok=True)
    print(f'\n========== {name} ({dtype}) ==========', flush=True)
    print(f'R1: {r1}', flush=True)

    peak_total = peak_single = 0
    stop = threading.Event()
    me = psutil.Process()

    def monitor():
        nonlocal peak_total, peak_single
        while not stop.is_set():
            t, s = tree_snapshot(me)
            peak_total = max(peak_total, t)
            peak_single = max(peak_single, s)
            stop.wait(1.0)

    t0 = time.time()
    mon = threading.Thread(target=monitor, daemon=True)
    mon.start()
    err = None
    try:
        res = run_kvsuite_stage(
            out_dir, r1, r2, sample=name.lower(),
            threads=19, engine='salmon', force=True, need_viral_reads=True,
            logger=type('L', (), {'log': lambda self, *a: print('  [kv]', *a, flush=True)})(),
            progress=lambda *a: print(f'  [{a[-2]*100:4.0f}%] {a[-1]}', flush=True))
    except Exception as e:
        err = repr(e)
        res = None
    stop.set()
    mon.join(timeout=3)
    wall = time.time() - t0

    result = {
        'dataset': name, 'dtype': dtype,
        'wall_sec': round(wall, 1),
        'peak_tree_rss_gb': round(peak_total / 2**30, 2),
        'peak_single_rss_gb': round(peak_single / 2**30, 2),
        'error': err,
    }
    if res:
        result.update({
            'stage_elapsed_sec': res.get('elapsed_sec'),
            'species_detected': len(res.get('species_detected') or []),
            'viral_reads': res.get('viral_reads'),
            'viral_pairs': res.get('viral_pairs'),
            'passed': res.get('passed'),
            'rejected': res.get('rejected'),
        })
    with open(os.path.join(out_dir, 'bench.json'), 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f'>>> {name} 完成: 墙钟 {wall/60:.1f} min | 树峰值 {peak_total/2**30:.2f} GB'
          f' | 单进程峰值 {peak_single/2**30:.2f} GB'
          + (f' | 错误: {err}' if err else ''), flush=True)
    return result


def main():
    only = sys.argv[1:] or None
    os.makedirs(OUT_ROOT, exist_ok=True)
    results = []
    for name, r1, r2, dtype in DATASETS:
        if only and not any(o in name for o in only):
            continue
        results.append(run_one(name, r1, r2, dtype))
    print('\n========== 汇总 ==========', flush=True)
    for r in results:
        print(json.dumps(r, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
