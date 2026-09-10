# -*- coding: utf-8 -*-
"""阶段 B：跑一遍各模块，把产物固化到 databases/examples/results/<模块>/。

做法：用平台自己的 /api/tool/run 提交任务（与用户点击「运行」完全同一条
链路），轮询到完成后把 tool_runs/<run>/ 复制到示例结果目录，并写
manifest.json 供前端「👁 示例结果」读取。与真实数据完全隔离。

用法:
    python tests/make_example_results.py                # 跑全部（跳过已存在）
    python tests/make_example_results.py --only identify,orf
    python tests/make_example_results.py --force        # 重跑覆盖
"""
import argparse
import io
import json
import os
import shutil
import sys
import time

ROOT = r'D:\桌面\植物病毒分析平台'
sys.path.insert(0, ROOT)

EX = 'databases/examples/'
EXR = os.path.join(ROOT, 'databases', 'examples', 'results')

# (模块名, 工具键, 标题, 参数)  —— 参数键名取自各 _tool_job_* 的 ctx.req/ctx.p
JOBS = [
    ('identify', 'identify', '病毒识别分类与提取', {
        'input': EX + 'example_R1.fastq.gz',
        'input2': EX + 'example_R2.fastq.gz',
        'input_type': 'pe',
        'db_virus': 'databases/virus/plant'}),
    ('hostremoval', 'hostremoval', '宿主去除与序列提取', {
        'r1': EX + 'example_R1.fastq.gz',
        'r2': EX + 'example_R2.fastq.gz',
        'db': 'host-db/host/classify'}),
    ('fastp', 'fastp', '序列质控（fastp）', {
        'r1': EX + 'example_R1.fastq.gz',
        'r2': EX + 'example_R2.fastq.gz'}),
    ('convert', 'convert', '格式转换（FASTQ→FASTA）', {
        'input': EX + 'example_R1.fastq.gz', 'target': 'fasta'}),
    ('orf', 'orf', 'ORF 预测', {'fasta': EX + 'example_viral_contigs.fasta'}),
    ('genoplot', 'genoplot', '基因组图谱', {
        'ann': EX + 'example_genome.gb', 'mode': 'both', 'max_plots': 2,
        'gb_opts': {'labels': 'out'}}),
    ('primer', 'primer', '引物设计（保守区）', {
        'fasta': EX + 'example_conserved_set.fasta', 'mode': 'conserved'}),
    ('align', 'align', '序列比对（MAFFT + trimAl）', {
        'seqs': EX + 'example_virus_set.fasta'}),
    ('quicktree', 'quicktree', '进化树构建（快速）', {
        'seqs': EX + 'example_virus_set.fasta', 'method': 'fasttree'}),
    ('sdt', 'sdt', 'SDT 同一性分析', {
        'seqs': EX + 'example_virus_set.fasta'}),
    ('structcmp', 'structcmp', '结构比较', {
        'seqs': EX + 'example_virus_set.fasta'}),
    ('identity', 'identity', 'NT+AA 同一性表', {
        'nt_seqs': EX + 'example_virus_set.fasta'}),
    ('assemble', 'assemble', '提取序列组装（SPAdes）', {
        'r1': EX + 'example_R1.fastq.gz',
        'r2': EX + 'example_R2.fastq.gz', 'mode': 'metaviral'}),
    ('contigs', 'contigs', 'contig 分类（组装结果再鉴定）', {
        'contigs': EX + 'example_viral_contigs.fasta',
        'db_virus': 'databases/virus/plant'}),
    ('orfa', 'orfa', 'ORF 功能注释', {
        'fasta': EX + 'example_viral_contigs.fasta'}),
    ('verify', 'verify', '候选序列验证', {
        'fasta': EX + 'example_viral_contigs.fasta'}),
    ('hostpredict', 'hostpredict', '宿主预测（ICTV 级联）', {
        'tsv': EX + 'example_contig_classification.tsv',
        'fasta': EX + 'example_viral_contigs.fasta'}),
    ('consensus', 'consensus', '共识序列与变异', {
        'fasta': EX + 'example_viral_contigs.fasta',
        'reads': EX + 'example_R1.fastq.gz'}),
    ('kvsuite', 'kvsuite', '已知病毒识别与定量', 'KVSUITE'),
    ('variant', 'kvsuite', '病毒变异分析', 'VARIANT'),
    ('virchain', 'virchain', '病毒识别分类·一键（②→③→④）', {
        'input': EX + 'example_R1.fastq.gz',
        'input2': EX + 'example_R2.fastq.gz',
        'run_identify': True, 'do_verify': True,
        'mode': 'metaviral', 'memory': 32}),
    ('kvchain', 'kvchain', '病毒定量与共识·一键（全流程）', 'KVCHAIN'),
]

# 复制产物时排除的中间目录/大文件（体积大且对示例无价值）
# mmseqs_tmp 里含 Windows 无法 stat 的 latest 符号链接（遍历会抛 WinError 1920）
SKIP_DIRS = {'_chunk', 'spades', 'mmseqs_tmp', '__pycache__', '_fq2fa'}
# kunpeng 原始输出（每 read 一行，几百 KB，仅中间产物；kreport/汇总表才是结果）
# plotly.min.js 是报告内嵌的前端库副本（4.6MB），不进示例结果
SKIP_NAMES = {'.done', 'run.log', 'output_1.txt', 'output_2.txt',
              'output_1-2.txt', 'plotly.min.js'}
SKIP_SUFFIX = ('.fastq.gz', '.fq.gz', '.fasta.gz', '.tmp', '.k2', '.bam',
               '.sam', '.sorted.bam', '.bai')


def _kvsuite_params():
    """kvsuite 需要样品表：临时生成一份指向示例 reads 的 TSV（不建真样品，
    避免示例数据混进用户的样品列表）。"""
    d = os.path.join(ROOT, 'run', 'tool_runs', '_example_inputs')
    os.makedirs(d, exist_ok=True)
    sheet = os.path.join(d, 'example_sample_sheet.tsv')
    r1 = os.path.join(ROOT, 'databases', 'examples', 'example_R1.fastq.gz')
    r2 = os.path.join(ROOT, 'databases', 'examples', 'example_R2.fastq.gz')
    with io.open(sheet, 'w', encoding='utf-8', newline='\n') as f:
        f.write('name\tr1\tr2\nEXAMPLE\t' + r1 + '\t' + r2 + '\n')
    return {'sample_sheet': sheet, 'stage': 'all'}


def _variant_params():
    """变异段（kvsuite stage=variant）不跑 reads，只吃上游 BAM/VCF。
    取最近一次 kvsuite 示例运行的 bam 目录。"""
    import glob
    cands = sorted(glob.glob(os.path.join(ROOT, 'run', 'tool_runs', 'kvsuite_*',
                                          'kvsuite', 'bam')),
                   key=os.path.getmtime, reverse=True)
    for d in cands:
        if glob.glob(os.path.join(d, '*.bam')):
            return {'stage': 'variant', 'bam_dir': d}
    raise RuntimeError('未找到上游 BAM（先跑 kvsuite 示例）')


def run_one(client, tool, params, timeout=3600):
    r = client.post('/api/tool/run',
                    json={'tool': tool, 'threads': 8, 'params': params})
    if r.status_code != 200:
        raise RuntimeError(f'提交失败 HTTP {r.status_code}: '
                           f'{r.get_data(as_text=True)[:200]}')
    d = r.get_json() or {}
    tid, run = d.get('task'), d.get('run')
    t0 = time.time()
    while time.time() - t0 < timeout:
        time.sleep(2)
        j = client.get(f'/api/task/{tid}').get_json() or {}
        st = j.get('status')
        if st == 'done':
            return run, j.get('result'), time.time() - t0
        if st in ('failed', 'cancelled'):
            raise RuntimeError(f'任务{st}: {(j.get("error") or "")[:200]}')
    raise RuntimeError(f'超时 {timeout}s')


def collect(run, module, title, meta):
    src = os.path.join(ROOT, 'run', 'tool_runs', run)
    dst = os.path.join(EXR, module)
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    os.makedirs(dst, exist_ok=True)
    files = []
    for cur, dirs, fs in os.walk(src):
        dirs[:] = [d for d in dirs
                   if d not in SKIP_DIRS and not d.endswith('.mmseqs_tmp')]
        rel = os.path.relpath(cur, src)
        for fn in fs:
            if fn in SKIP_NAMES or fn.endswith(SKIP_SUFFIX):
                continue
            s = os.path.join(cur, fn)
            try:
                if os.path.islink(s):        # mmseqs 的 latest 等符号链接
                    continue
                if os.path.getsize(s) > 8 * 1024 * 1024:
                    continue
            except OSError:
                continue
            d = os.path.join(dst, rel) if rel != '.' else dst
            os.makedirs(d, exist_ok=True)
            shutil.copy2(s, os.path.join(d, fn))
            files.append(os.path.relpath(os.path.join(d, fn), dst).replace('\\', '/'))
    return {'module': module, 'title': title, 'run': run,
            'files': sorted(files), 'generated_at': time.strftime('%Y-%m-%d %H:%M:%S'),
            'source': 'databases/examples/', **(meta or {})}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', default='')
    ap.add_argument('--force', action='store_true')
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(',') if x.strip()}

    os.makedirs(EXR, exist_ok=True)
    import app as appmod
    client = appmod.app.test_client()

    manifest_path = os.path.join(EXR, 'manifest.json')
    manifest = {}
    if os.path.isfile(manifest_path):
        try:
            with io.open(manifest_path, encoding='utf-8') as f:
                manifest = json.load(f)
        except ValueError:
            manifest = {}

    ok, fail = [], []
    for module, tool, title, params in JOBS:
        if only and module not in only:
            continue
        if not args.force and os.path.isdir(os.path.join(EXR, module)):
            print(f'  [跳过] {module}（已存在）', flush=True)
            ok.append(module)
            continue
        print(f'  [运行] {module} <- {tool} …', flush=True)
        try:
            if params in ('KVSUITE', 'KVCHAIN'):
                params = _kvsuite_params()
            elif params == 'VARIANT':
                params = _variant_params()
            run, result, dt = run_one(client, tool, params)
            meta = result if isinstance(result, dict) else {}
            manifest[module] = collect(run, module, title, meta)
            n = len(manifest[module]['files'])
            print(f'         ✓ {dt:.0f}s  产物 {n} 个 -> {run}', flush=True)
            ok.append(module)
        except Exception as e:
            print(f'         ✗ 失败: {e}', flush=True)
            fail.append((module, str(e)[:160]))

    with io.open(manifest_path, 'w', encoding='utf-8', newline='\n') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1, sort_keys=True)
    print(f'\n  完成 {len(ok)} 个，失败 {len(fail)} 个')
    for m, e in fail:
        print(f'    ✗ {m}: {e}')
    print(f'  manifest -> {os.path.relpath(manifest_path, ROOT)}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
