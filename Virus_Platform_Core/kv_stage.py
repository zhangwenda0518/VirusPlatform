# -*- coding: utf-8 -*-
"""②b 已知病毒识别与定量（kvsuite）——管道阶段的封装。

取代原 ② 病毒筛查与提取（kunpeng/kraken2 分类）：把 reads 用 **salmon**
比对到**已知病毒参考索引**（定量唯一引擎；salmon --writeBam 同步产出映射
BAM），产出「识别 + 定量」（`identify/` + `filter/`），并用 samtools 把
比对上的病毒 reads 抽成 `viral_R1/R2.fastq.gz` 供 ③组装
（`assembly_input='virus'`）。共识段（③c）内部固定 minibwa，与此处无关。

产物（<sample_dir>/02b_kvsuite/）：
    summary.json           本阶段摘要（卡片状态与 GUI 用）
    identify/              识别结果（all_viruses*.tsv）
    filter/filtered.tsv    二次过滤后的结果表（定量口径）
    align/*.sorted.bam     salmon 映射 BAM（含 .bai 与 pandepth 深度）
    viral_R1/R2.fastq.gz   比对上的病毒 reads（PE）；SE 只有 viral_R1
    kvsuite.log            引擎原始日志

为什么只跑 identify + filter：consensus / 变异注释属于 ③c 共识序列与变异
阶段（`consensus`），不在 ②b 的"识别与定量"范围内。
"""
import json
import os
import sys
import time

from .config import DIRS, get_config
from .utils import check_path, run_cmd, run_cmd_redirect

STAGE_DIR = '02b_kvsuite'
SUMMARY = 'summary.json'
VIRAL_R1 = 'viral_R1.fastq.gz'
VIRAL_R2 = 'viral_R2.fastq.gz'
_ENGINE_MOD = 'Virus_Platform_Core.known_virus_suite.known_virus_suite'
_ENGINE_SCRIPT = 'known_virus_suite.py'


def engine_cmd():
    """引擎入口：(可执行, 前置参数)。

    源码模式 `python -m <模块>`；冻结分发（exe）走 `--run-engine <脚本名>`
    （由 Virus_Platform_Core/engine_entry.py 在进程内执行）。
    """
    if getattr(sys, 'frozen', False):
        return sys.executable, ['--run-engine', _ENGINE_SCRIPT]
    return sys.executable, ['-m', _ENGINE_MOD]


def _kv_lib_dir():
    """默认鉴定库目录（参考病毒目录 databases/virusref_db/ 下的 kv_index）。"""
    return os.path.join(DIRS['virus_src'], 'kv_index')


def default_reference():
    """平台默认病毒参考。

    参考病毒目录重构后每个库自包含：<库>/reference.fasta +
    <库>/reference.ref_info.tsv + <库>/salmon_k31/。解析顺序：
    ① 默认库目录内的 reference.fasta；
    ② 库 manifest.json 登记的 reference（外部来源参考）；
    ③ 旧布局根目录散置的 final.cluster.ref.fasta（未迁移安装的兼容回退）。
    """
    p = os.path.join(_kv_lib_dir(), 'reference.fasta')
    if os.path.isfile(p):
        return p
    try:
        with open(os.path.join(_kv_lib_dir(), 'manifest.json'),
                  encoding='utf-8') as fh:
            ref = (json.load(fh) or {}).get('reference') or ''
        if ref and os.path.isfile(ref):
            return ref
    except (OSError, ValueError):
        pass
    p = os.path.join(DIRS['virus_src'], 'final.cluster.ref.fasta')
    return p if os.path.isfile(p) else None


def default_ref_info():
    """默认参考注释 TSV（新布局在库目录内，旧布局在 virusref_db 根下）。"""
    for p in (os.path.join(_kv_lib_dir(), 'reference.ref_info.tsv'),
              os.path.join(DIRS['virus_src'], 'final.cluster.ref_info.tsv')):
        if os.path.isfile(p):
            return p
    return None


def index_dir_for(ref, engine='salmon'):
    """预建索引目录（命中才返回）：与平台「鉴定库」同一套布局。

    定量唯一引擎是 salmon：<库>/salmon_k31/info.json。
    （共识段的 minibwa 索引由共识段在运行目录内自建自用，不在这里复用。）
    """
    kv = os.path.join(DIRS['virus_src'], 'kv_index')
    if engine != 'salmon':
        return None
    hits = (os.path.join(kv, 'salmon_k31', 'info.json'),)
    if not any(os.path.isfile(h) for h in hits):
        return None
    default_ref = default_reference()
    if default_ref and os.path.abspath(ref) != os.path.abspath(default_ref):
        return None            # 自定义参考 → 索引不匹配，让引擎自建
    return kv


_DTYPES = {'String', 'Int64', 'Int32', 'Float64', 'Float32', 'Boolean',
           'Utf8', 'Null', 'Object', 'Date', 'Datetime'}


def _read_tsv_rows(path):
    """读 TSV → (表头 list, 数据行 list)。跳过 polars 误写出的 dtype 行。"""
    if not os.path.isfile(path):
        return [], []
    with open(path, encoding='utf-8', errors='replace') as fh:
        lines = [ln.rstrip('\n') for ln in fh if ln.strip()]
    if not lines:
        return [], []
    head = lines[0].split('\t')
    rows = []
    for ln in lines[1:]:
        cols = ln.split('\t')
        if cols and all((c or '').strip() in _DTYPES for c in cols[:3]):
            continue                      # dtype 行（历史 bug 产物），不算数据
        rows.append(cols)
    return head, rows


def _col(head, *names):
    lut = {h.strip().lower(): i for i, h in enumerate(head)}
    for n in names:
        i = lut.get(n.strip().lower())
        if i is not None:
            return i
    return None


def _summarize(out_dir):
    """识别/定量结果 → {species, reads, passed, rejected, filtered_tsv}。

    识别与定量口径：
      * 物种与 reads 取 `identify/all_viruses.summary.tsv`（识别段全量结果）；
      * 通过/剔除条数取 `filter/filtered.tsv` 与 `filter/discarded.tsv`
        （二次过滤 = 定量口径；多段物种会被节段完整性规则剔除）。
    """
    ident = os.path.join(out_dir, 'identify', 'all_viruses.summary.tsv')
    head, rows = _read_tsv_rows(ident)
    sp_i = _col(head, 'Species', 'Accession', 'Virus')
    rd_i = _col(head, 'Uniq_Reads', 'EM_Reads', 'Reads')
    species, reads = [], 0
    for cols in rows:
        if sp_i is not None and sp_i < len(cols) and cols[sp_i].strip():
            name = cols[sp_i].strip()
            if name not in species:
                species.append(name)
        if rd_i is not None and rd_i < len(cols):
            try:
                reads += int(float(cols[rd_i]))
            except ValueError:
                pass
    filtered = os.path.join(out_dir, 'filter', 'filtered.tsv')
    discarded = os.path.join(out_dir, 'filter', 'discarded.tsv')
    # 比对失败的样本：引擎在 identify/（旧布局在阶段根目录）落
    # failed_samples.json。失败样本与真阴性绝不可混同——不读这个文件，
    # salmon 崩掉的样本就会以「检出 0 物种」的假阴性面孔混进汇总。
    failed = []
    for cand in (os.path.join(out_dir, 'identify', 'failed_samples.json'),
                 os.path.join(out_dir, 'failed_samples.json')):
        if os.path.isfile(cand):
            try:
                with open(cand, encoding='utf-8') as fh:
                    failed = json.load(fh) or []
            except (OSError, ValueError):
                failed = []
            break
    return {
        'species_detected': species,
        'viral_reads': reads,
        'passed': len(_read_tsv_rows(filtered)[1]),
        'rejected': len(_read_tsv_rows(discarded)[1]),
        'failed_samples': failed,
        'filtered_tsv': filtered if os.path.isfile(filtered) else '',
        'identify_tsv': ident if os.path.isfile(ident) else '',
    }


def _samtools():
    exe = get_config().tool('samtools')
    if not exe:
        raise FileNotFoundError('未找到 samtools（抽病毒 reads 需要）')
    return exe


def _input_fingerprint(path):
    """输入文件指纹（路径 + size + mtime）：断点复用前核对，防「换了输入
    重跑却拿到旧结果」。读不到 stat（文件刚被替换/网络抖动）时 size/mtime
    记 None——只有路径也一致才算命中。"""
    p = os.path.abspath(str(path))
    try:
        st = os.stat(p)
        return [p, st.st_size, st.st_mtime]
    except OSError:
        return [p, None, None]


def _extract_viral_reads(out_dir, bam, r2, threads, logger=None):
    """按名字排序后抽 fastq：比对上的 reads → viral_R1/R2（PE）或 viral_R1（SE）。"""
    st_exe = _samtools()
    name_sorted = os.path.join(out_dir, 'align', 'viral.namesort.bam')
    cmd1 = [st_exe, 'sort', '-n', f'-@{threads}', '-o', name_sorted, bam]
    cmd2 = [st_exe, 'fastq', f'-@{threads}',
            '-1', os.path.join(out_dir, VIRAL_R1)]
    if r2:
        cmd2 += ['-2', os.path.join(out_dir, VIRAL_R2)]
    else:
        cmd2 += ['-0', os.path.join(out_dir, VIRAL_R1)]
    cmd2 += [name_sorted]
    # 走 run_cmd（非裸 subprocess）：进任务取消注册表（「停止」能杀掉进程树）
    # + 默认超时看门狗，samtools 挂死不再拖死整个任务
    for cmd in (cmd1, cmd2):
        run_cmd(cmd, logger=logger)
        if logger:
            logger.log(f'  抽病毒 reads: samtools {cmd[1]} 完成')
    try:
        os.remove(name_sorted)
    except OSError:
        pass
    r1_out = os.path.join(out_dir, VIRAL_R1)
    r2_out = os.path.join(out_dir, VIRAL_R2)
    return (r1_out, r2_out if (r2 and os.path.isfile(r2_out)) else None)


def run_kvsuite_stage(out_dir, r1, r2=None, sample=None, threads=8,
                      engine='salmon', force=False, need_viral_reads=True,
                      logger=None, progress=None):
    """跑 ②b 识别+定量，返回结果字典（同时落 summary.json）。

    引擎固定 salmon（定量唯一引擎；--writeBam 同步出映射 BAM 供抽病毒
    reads）。断点续跑：summary.json 已存在、不是 force、且输入指纹
    （r1/r2/参考的 路径+size+mtime）与上次完全一致时才直接复用——
    换了 FASTQ 或换了鉴定库重跑会真正重跑，绝不拿旧结果冒充新结果。
    """
    out_dir = check_path(out_dir, must_exist=False, in_platform=True)
    os.makedirs(out_dir, exist_ok=True)
    summary_p = os.path.join(out_dir, SUMMARY)
    ref = default_reference()
    if not ref:
        raise FileNotFoundError(
            '缺少病毒参考：请先在「数据库构建 → 病毒鉴定库」建库'
            '（databases/virusref_db/kv_index/）')
    if os.path.isfile(summary_p) and not force:
        done = None
        try:
            with open(summary_p, encoding='utf-8') as fh:
                done = json.load(fh)
        except (OSError, ValueError):
            pass
        want_fp = {
            'r1': _input_fingerprint(r1),
            'r2': _input_fingerprint(r2) if r2 else None,
            'reference': _input_fingerprint(ref),
        }
        if done and done.get('inputs_fp') == want_fp:
            if logger:
                logger.log(f'②b 已知病毒识别与定量已完成且输入未变化，'
                           f'跳过（{summary_p}）')
            return done
        if logger:
            logger.log('②b 存在历史断点，但输入已变化或缺少输入指纹——'
                       '重跑本阶段（不复用旧结果）')

    sample = sample or os.path.basename(os.path.dirname(out_dir.rstrip(os.sep)))
    entry_exe, entry_pre = engine_cmd()
    log_p = os.path.join(out_dir, 'kvsuite.log')
    t0 = time.time()

    def _run(sub, extra):
        cmd = [entry_exe] + entry_pre + [sub, '--out', out_dir,
                                         '--reference', ref,
                                         '--engine', engine,
                                         '--threads', str(threads),
                                         '--align-threads', str(threads),
                                         '--sample-name', sample]
        if sub != 'filter':                       # filter 只用已有结果表
            cmd += ['-1', r1]
            if r2:
                cmd += ['-2', r2]
        ri = default_ref_info()
        if ri:
            cmd += ['--ref-info', ri]
        idx = index_dir_for(ref, engine)
        if idx:
            cmd += ['--index-dir', idx]
        cmd += list(extra)
        if logger:
            logger.log(f'  ②b kvsuite {sub}: {" ".join(cmd[1 + len(entry_pre):])}')
        with open(log_p, 'a', encoding='utf-8') as fl:
            fl.write(f'\n===== {sub} =====\n')
        # 走 run_cmd_redirect（非裸 subprocess.run）：引擎进程进任务取消
        # 注册表（「停止」可杀整棵进程树，salmon/samtools 不再成为孤儿），
        # 且带默认超时看门狗；输出继续追加进 kvsuite.log
        try:
            run_cmd_redirect(cmd, log_p, append=True)
        except RuntimeError as e:
            tail = ''
            try:
                with open(log_p, encoding='utf-8', errors='replace') as fl:
                    tail = ''.join(fl.readlines()[-8:])
            except OSError:
                pass
            raise RuntimeError(f'kvsuite {sub} 失败：{tail or e}') from e

    _run('identify', [])
    if progress:
        progress(0.7, '识别完成，二次过滤（定量）')
    _run('filter', [])

    stats = _summarize(out_dir)
    bam = os.path.join(out_dir, 'align', f'{sample}_pandepth.sorted.bam')
    if not os.path.isfile(bam):
        bam = os.path.join(out_dir, 'align', f'{sample}.sorted.bam')
    viral_r1 = viral_r2 = None
    if need_viral_reads and os.path.isfile(bam):
        if progress:
            progress(0.9, '抽病毒 reads（供 ③组装）')
        viral_r1, viral_r2 = _extract_viral_reads(out_dir, bam, r2, threads,
                                                  logger=logger)

    reads = stats['viral_reads']
    result = {
        'stage': 'kvsuite',
        'sample': sample,
        'engine': engine,
        'reference': ref,
        'index_dir': index_dir_for(ref, engine) or '',
        'identify_tsv': stats['identify_tsv'],
        'filtered_tsv': stats['filtered_tsv'],
        'bam': bam if os.path.isfile(bam) else '',
        'species_detected': stats['species_detected'],
        'viral_reads': reads,
        'viral_pairs': reads // 2 if r2 else reads,
        'passed': stats['passed'],
        'rejected': stats['rejected'],
        'viral_r1': viral_r1 or '',
        'viral_r2': viral_r2 or '',
        'failed_samples': stats.get('failed_samples', []),
        'elapsed_sec': round(time.time() - t0, 1),
        # 输入指纹：下次断点续跑时核对，输入变了就重跑而不是复用旧结果
        'inputs_fp': {
            'r1': _input_fingerprint(r1),
            'r2': _input_fingerprint(r2) if r2 else None,
            'reference': _input_fingerprint(ref),
        },
    }
    with open(summary_p, 'w', encoding='utf-8') as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    if logger:
        _fail_tip = ''
        if stats.get('failed_samples'):
            _fail_tip = (f'，⚠ {len(stats["failed_samples"])} 个样本比对失败'
                         '（未计入结果，勿当作阴性！详见 failed_samples.json）')
        logger.log(f'②b 已知病毒识别与定量完成：检出 '
                   f'{len(result["species_detected"])} 个物种（通过 '
                   f'{result["passed"]} / 剔除 {result["rejected"]}），'
                   f'病毒 reads {result["viral_reads"]}{_fail_tip}，'
                   f'用时 {result["elapsed_sec"]}s')
    return result
