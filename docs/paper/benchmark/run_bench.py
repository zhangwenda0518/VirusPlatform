# -*- coding: utf-8 -*-
"""评测驱动：逐实验拉起 run_one.py，psutil 监控进程树峰值内存，汇总 results.json。

用法: python run_bench.py [runs_root]
默认 runs_root = C:/vp_srna_test/bench
"""
import json
import os
import subprocess
import sys
import time

import psutil

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, '..', '..', '..'))
VM = r'E:\谷歌下载\测试数据验证'
BARI = os.path.join(VM, 'Raw-data-Bari.Workshop')
RUNS = sys.argv[1] if len(sys.argv) > 1 else r'C:\vp_srna_test\bench'

EXPS = []
# —— VIROMOCK 人工数据集 D11-D18（150bp 双端纯病毒 reads，常规路线）——
for d in range(11, 19):
    EXPS.append({
        'type': 'kv', 'name': f'D{d}',
        'r1': os.path.join(VM, f'Dataset_{d}_R1.fastq.gz'),
        'r2': os.path.join(VM, f'Dataset_{d}_R2.fastq.gz'),
        'out': os.path.join(RUNS, f'vm_d{d}'),
    })
# —— Bari 小RNA（250K，21-24nt）× 方法矩阵 ——
for s, fq in (('S3', 'Sample_3.fastq'), ('S9', 'Sample_9.fastq')):
    EXPS.append({'type': 'kv', 'name': s,
                 'r1': os.path.join(BARI, fq), 'out': os.path.join(RUNS, f'bari_{s.lower()}_k15')})
for s, fq in (('S3', 'Sample_3.fastq'), ('S9', 'Sample_9.fastq')):
    EXPS.append({'type': 'asm', 'name': s,
                 'r1': os.path.join(BARI, fq), 'out': os.path.join(RUNS, f'bari_{s.lower()}_asm')})
EXPS.append({'type': 'ctrl_salmon_k31', 'name': 'S3',
             'r1': r'C:\vp_srna_test\in1.fastq',
             'index': r'C:\vp_srna_test\idx_k31',
             'out': os.path.join(RUNS, 'ctrl_s3_k31')})
EXPS.append({'type': 'ctrl_bwa', 'name': 'S3',
             'r1': r'C:\vp_srna_test\in1.fastq',
             'out': os.path.join(RUNS, 'ctrl_s3_bwa')})

# —— 第二轮扩充：双引擎 + 半人工集 + 深度稀释 + 全链路 ——
# D1-D10 半人工/真实集：salmon 与 minibwa 双引擎
for d in range(1, 11):
    single = d in (5, 6, 10)          # 50bp/75bp 单端
    r1 = os.path.join(VM, f'Dataset_{d}.fastq.gz') if single else \
        os.path.join(VM, f'Dataset_{d}_R1.fastq.gz')
    r2 = None if single else os.path.join(VM, f'Dataset_{d}_R2.fastq.gz')
    EXPS.append({'type': 'kv', 'name': f'D{d}', 'r1': r1, 'r2': r2,
                 'out': os.path.join(RUNS, f'vm_d{d}')})
    EXPS.append({'type': 'kv', 'name': f'D{d}', 'r1': r1, 'r2': r2,
                 'engine': 'minibwa', 'out': os.path.join(RUNS, f'vm_d{d}_bwa')})
# D11-D18 补 minibwa 引擎
for d in range(11, 19):
    EXPS.append({'type': 'kv', 'name': f'D{d}',
                 'r1': os.path.join(VM, f'Dataset_{d}_R1.fastq.gz'),
                 'r2': os.path.join(VM, f'Dataset_{d}_R2.fastq.gz'),
                 'engine': 'minibwa', 'out': os.path.join(RUNS, f'vm_d{d}_bwa')})
# Bari 50K 深度稀释（salmon k15）
for s, fq in (('S3', 'Sample_3.fastq'), ('S9', 'Sample_9.fastq')):
    EXPS.append({'type': 'kv', 'name': f'{s}_50K', 'subsample': 50000,
                 'r1': os.path.join(BARI, fq),
                 'out': os.path.join(RUNS, f'bari_{s.lower()}_50k')})
# sRNA 全链路（fastp→鉴定→组装）
for s, fq in (('S3', 'Sample_3.fastq'), ('S9', 'Sample_9.fastq')):
    EXPS.append({'type': 'chain', 'name': s,
                 'r1': os.path.join(BARI, fq),
                 'out': os.path.join(RUNS, f'chain_{s.lower()}')})


def monitor(proc, timeout_s=900):
    """轮询进程树 RSS；超时强杀整棵树。返回 (峰值字节, 是否超时)。"""
    peak = 0
    p = psutil.Process(proc.pid)
    t0 = time.time()
    while proc.poll() is None:
        try:
            total = p.memory_info().rss
            for c in p.children(recursive=True):
                try:
                    total += c.memory_info().rss
                except (psutil.Error, OSError):
                    pass
            peak = max(peak, total)
        except (psutil.Error, OSError):
            # WinError 1455（页面文件太小）等系统级错误：跳过本轮采样，
            # 不让监控自身把评测打死
            pass
        if time.time() - t0 > timeout_s:
            try:
                for c in p.children(recursive=True):
                    c.kill()
                p.kill()
            except psutil.Error:
                pass
            return peak, True
        time.sleep(1.0)
    return peak, False


def cleanup_dir(out_dir, keep=('driver_stdout.txt',)):
    """删除实验目录里的中间产物（结果已提取进 results.json，冗余落盘
    只占空间）：quant/align/stats/batches/identify/logs 等全部清掉。"""
    for entry in os.listdir(out_dir):
        if entry in keep:
            continue
        p = os.path.join(out_dir, entry)
        try:
            if os.path.isdir(p):
                import shutil
                shutil.rmtree(p, ignore_errors=True)
            else:
                os.remove(p)
        except OSError:
            pass


def main():
    os.makedirs(RUNS, exist_ok=True)
    results = []
    res_path = os.path.join(RUNS, 'results.json')
    if os.path.isfile(res_path):          # 断点续跑：已完成且有效的实验跳过
        results = json.load(open(res_path, encoding='utf-8'))
    done = {r['exp'] for r in results if not r.get('error')}
    for name in done:                     # 已完成实验：回溯清理中间产物
        d = os.path.join(RUNS, name)
        if os.path.isdir(d):
            cleanup_dir(d)
    todo = [e for e in EXPS if os.path.basename(e['out']) not in done]
    print(f'共 {len(EXPS)} 实验，已完成 {len(results) - sum(1 for r in results if r.get("error"))}，'
          f'待跑 {len(todo)}', flush=True)
    for i, exp in enumerate(todo):
        # minibwa 真比对在大数据集上可能很久：限时 20 分钟，超时中断记
        # 「timed_out」继续下一个；其余实验 15 分钟兜底
        timeout = 1200 if exp.get('engine') == 'minibwa' else 900
        spec = dict(exp)
        spec_path = os.path.join(exp['out'] + '.spec.json')
        os.makedirs(exp['out'], exist_ok=True)
        with open(spec_path, 'w', encoding='utf-8') as f:
            json.dump(spec, f, ensure_ascii=False)
        print(f"[{i + 1}/{len(EXPS)}] {exp['name']} ({exp['type']}) ...",
              flush=True)
        t0 = time.time()
        # stdout/stderr 落文件而非管道：Windows 下孙进程（salmon 等）继承
        # 管道句柄会让 read() 永久等 EOF，评测直接挂死——文件没有这个问题
        out_path = os.path.join(exp['out'], 'driver_stdout.txt')
        with open(out_path, 'w', encoding='utf-8') as tf:
            proc = subprocess.Popen(
                [sys.executable, os.path.join(HERE, 'run_one.py'), spec_path],
                stdout=tf, stderr=subprocess.STDOUT, cwd=REPO)
        peak, timed_out = monitor(proc, timeout_s=timeout)
        wall = time.time() - t0
        out = open(out_path, encoding='utf-8', errors='replace').read()
        res = {}
        for ln in out.splitlines():
            if ln.startswith('RESULT:'):
                res = json.loads(ln[7:])
                break
        if not res:
            res = {'type': exp['type'], 'name': exp['name'],
                   'error': ('超时被强杀(>%ds)' % timeout if timed_out
                             else out[-800:])}
        res['exp'] = os.path.basename(exp['out'])
        res['driver_wall_s'] = round(wall, 1)
        res['peak_rss_mb'] = round(peak / 1048576, 1)
        if timed_out:
            res['timed_out'] = True
        results.append(res)
        cleanup_dir(exp['out'])
        print(f"    -> {json.dumps({k: res.get(k) for k in ('wall_s', 'peak_rss_mb', 'mapped', 'rejected', 'error') if k in res}, ensure_ascii=False)}",
              flush=True)
        with open(os.path.join(RUNS, 'results.json'), 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\n完成 {len(results)} 个实验 → {os.path.join(RUNS, 'results.json')}")


if __name__ == '__main__':
    main()
