# -*- coding: utf-8 -*-
"""工具箱：22 个独立分析任务工厂（自 app.py 拆出）。

每个 _tool_job_<name>(ctx) 返回 job(log, prog, cancel) 可调用；
由 Virus_Platform_Core/web/tools_api.py 的 /api/tool/run 取用。
新增工具三步：① 写 _tool_job_<name> ② 注册 TOOL_REGISTRY
（在 tools_api.py）③ webapp/templates/tools.html 加卡片。
"""
import json
import os
import re
import shutil
import subprocess

from flask import abort

from Virus_Platform_Core.config import DIRS, PLATFORM_ROOT
from Virus_Platform_Core.utils import (TaskLogger, check_path, safe_open)
from Virus_Platform_Core.web.state import cfg, tool_runs_root as _tool_runs_root


# 共识模块 reads 未手动指定时的兜底层（contig 分类运行目录下）：
# 去宿主后全量，变异检测无偏。不再提供「病毒筛选后 / 质控后原始」等
# 选项——前者低估变异，后者带宿主污染。
CONSENSUS_FALLBACK_LAYER = '01_host_removal'

# kvsuite 卡的默认阶段：识别/定量（identify）+ 过滤（filter）两段。
# 共识/绘图/变异属于下游模块（t-consensus / t-variant），不在「识别与定量」范围内。
# 字面量与引擎侧 Virus_Platform_Core/known_virus_suite/known_virus_suite.py 的
# DEFAULT_STAGE 必须一致；这里不 import 引擎模块——冻结分发版不打包 kv_filter /
# kv_identify（见 main.py 的 import 白名单说明）。
KV_DEFAULT_STAGE = 'identify+filter'


def _tool_job_convert(ctx):
    """格式转换：.sra→FASTQ/FASTA（sracha）、FASTQ→FASTA（seqkit）。"""
    inp = ctx.req('input', '输入文件')
    target = ctx.p.get('target') or 'fastq'
    if target not in ('fastq', 'fasta'):
        abort(400, '无效的目标格式')
    ilower = str(inp).lower()
    if ilower.endswith('.sra'):
        mode = 'sra'
    elif ilower.endswith(('.fastq', '.fq', '.fastq.gz', '.fq.gz')):
        mode = 'fastq2fasta' if target == 'fasta' else None
    elif ilower.endswith(('.fa', '.fasta', '.fa.gz', '.fasta.gz')):
        abort(400, '输入已是 FASTA，无需转换')
    else:
        abort(400, '无法识别的输入格式（支持 .sra / .fastq[.gz]）')

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        out_files = []
        if mode == 'sra':
            from Virus_Platform_Core.public_data import sra_convert_engine
            engine, exe = sra_convert_engine()
            if engine != 'sracha':
                raise RuntimeError('sracha.exe 不可用，无法转换 .sra')
            threads = ctx.threads or max(2, min((os.cpu_count() or 4) // 2, 8))
            prog('sra', 0.2, f'sracha 解码 .sra → {target.upper()}')
            cmd = [exe, 'fastq', inp, '-O', ctx.run_dir,
                   '-t', str(threads), '-f', '-q']
            if target == 'fasta':
                cmd.append('--fasta')
            import subprocess as _sp
            from Virus_Platform_Core.public_data import _sra_fastq_outputs
            _sp.run(cmd, check=True, timeout=8 * 3600,
                    stdout=_sp.DEVNULL, stderr=_sp.PIPE)
            base = os.path.basename(inp)[:-4]
            # ⚠ 单端 run：sracha 写 `<acc>.fastq.gz`（**无下划线**）；双端才写
            #   `<acc>_1/_2.fastq.gz`。只匹配 `base + '_'` 会把单端产物判成
            #   「无输出」，把已经落盘的 GB 级 FASTQ 丢掉 —— 与下载链
            #   （public_data._convert_sras）同源的历史 bug。这里复用同一份
            #   判定函数，杜绝两处再走偏。
            out_files = [os.path.join(ctx.run_dir, f_) for f_ in
                         _sra_fastq_outputs(
                             ctx.run_dir, base,
                             exts=('.fastq.gz', '.fq.gz',
                                   '.fa.gz', '.fasta.gz'))]
            if not out_files:
                raise RuntimeError('sracha 无输出')
        else:
            seqkit = cfg.tool('seqkit')
            dst = os.path.join(ctx.run_dir,
                               os.path.basename(inp).rsplit('.', 2)[0] + '.fa.gz')
            prog('fq2fa', 0.3, 'seqkit fq2fa 转换中')
            from Virus_Platform_Core.utils import run_cmd
            run_cmd([seqkit, 'fq2fa', '-w', '0',
                     '-j', str(ctx.threads or cfg.threads), inp,
                     '-o', dst], logger=logger)
            out_files = [dst]
        prog('done', 1.0, f'完成：{len(out_files)} 个文件')
        logger.close()
        return {'n_files': len(out_files),
                'files': [os.path.relpath(f, ctx.run_dir).replace(os.sep, '/')
                          for f in out_files]}
    return job


def _tool_job_fastp(ctx):
    """① 质控预处理（fastp，单/双端）。"""
    r1 = ctx.req('r1', 'R1 FASTQ')
    r2 = ctx.opt('r2')

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.preprocess import run_fastp
        prog('fastp', 0.3, 'fastp 质控中')
        res = run_fastp(ctx.run_dir, r1, r2, threads=ctx.threads, logger=logger,
                        force=True, dedup=bool(ctx.p.get('dedup')))
        if not res:
            raise RuntimeError('未检测到 fastp.exe，无法运行质控')
        prog('fastp', 1.0, '完成')
        logger.close()
        return res
    return job


def _tool_job_hostremoval(ctx):
    """宿主去除与序列提取（kunpeng 宿主库分类，独立模块，不依赖样品管道）。

    C 行 = 宿主 read 对，剔除后保留非宿主 reads（kept_R1/R2.fastq.gz）。
    """
    r1 = ctx.req('r1', 'R1 FASTQ')
    r2 = ctx.opt('r2')
    conf = float(ctx.p.get('confidence') or 0)
    db_host = ctx.opt('db') or cfg.databases['host']

    from Virus_Platform_Core.kunpeng import db_ready
    if not db_ready(db_host):
        abort(400, '宿主库未就绪，请先到「数据库构建」页构建宿主库')

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.host_removal import remove_host
        prog('classify', 0.05, 'kunpeng 宿主库分类中')
        res = remove_host(ctx.run_dir, r1, r2, db_host, threads=ctx.threads,
                          confidence=conf, logger=logger, force=True,
                          progress=lambda pct, msg: prog(
                              'classify' if pct < 0.9 else 'filter', pct, msg))
        prog('done', 1.0, '完成')
        logger.close()
        return res
    return job


def _tool_job_hostpredict(ctx):
    """宿主预测（ICTV 级联 + NCBI 元数据交叉），独立模块。

    输入 = 病毒 contig 分类表 TSV：管道③ virus_contigs.tsv 或
    工具④ virus_classification.tsv（列名自动识别，后者归一为 ③ 口径），
    可选配套 viral_contigs.fasta。
    """
    tsv = ctx.req('tsv', '病毒 contig 分类表 TSV')
    fa = ctx.opt('fasta')

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        a_dir = check_path(os.path.join(ctx.run_dir, '03_assembly'),
                           must_exist=False, in_platform=True)
        os.makedirs(a_dir, exist_ok=True)
        prog('prep', 0.05, '整理输入')
        # 统一 11 列口径（含 blast_* 补算），见 host_analysis.normalize_contig_table
        from Virus_Platform_Core.host_analysis import normalize_contig_table, predict_hosts
        normalize_contig_table(tsv, a_dir, fasta=fa, threads=ctx.threads,
                               logger=logger)
        prog('predict', 0.15, 'ICTV 宿主概率级联预测')
        res = predict_hosts(ctx.run_dir, threads=ctx.threads, logger=logger,
                            force=True)
        prog('done', 1.0, f"完成：宿主判定 {res.get('n_contigs', 0)} 条")
        logger.close()
        return res
    return job


def _tool_job_orf(ctx):
    """ORF 预测（pyrodigal / pyrodigal_rv），可选 ⑥b 功能注释。"""
    fasta = ctx.req('fasta', '输入 FASTA（核酸 contigs / 基因组）')
    min_aa = max(1, min(int(ctx.p.get('min_aa') or 100), 5000))
    annotate = bool(ctx.p.get('annotate'))
    orf_tool = (ctx.p.get('orf_tool') or '').strip()
    orf_engine = (ctx.p.get('engine') or '').strip()
    orf_db = (ctx.p.get('db') or '').strip()
    # 功能注释 CDS 模型：pyrodigal_rv（默认）/ pyrodigal
    orf_model = (ctx.p.get('model') or '').strip()
    if orf_model not in ('pyrodigal_rv', 'pyrodigal'):
        orf_model = ''
    # 功能注释层选择：prot（序列同源）/ pfam（HMM）/ cdd（结构域）；空=全部
    orf_libs = ctx.p.get('libs')

    def job(log, prog, cancel):
        import json as _json
        logger = TaskLogger(callback=log)
        a_dir = check_path(os.path.join(ctx.run_dir, '03_assembly'),
                           must_exist=False, in_platform=True)
        os.makedirs(a_dir, exist_ok=True)
        prog('prep', 0.03, '整理输入')
        from Virus_Platform_Core.utils import iter_fasta, write_fasta_record
        ids = []
        vfa = os.path.join(a_dir, 'viral_contigs.fasta')
        cfa = os.path.join(a_dir, 'contigs.filtered.fasta')
        with safe_open(vfa, 'wt') as w, safe_open(cfa, 'wt') as wc:
            for h, s in iter_fasta(fasta):
                cid = h.split()[0]
                ids.append(cid)
                write_fasta_record(w, cid, s)
                write_fasta_record(wc, cid, s)
        if not ids:
            raise RuntimeError('输入 FASTA 中没有序列')
        with safe_open(os.path.join(a_dir, 'summary.json'), 'wt') as f:
            _json.dump({'viral_contigs': ids, 'standalone': True}, f)
        from Virus_Platform_Core.orf import predict_orfs
        prog('orf', 0.08, 'ORF 基因预测')
        res = predict_orfs(ctx.run_dir, min_aa=min_aa, threads=ctx.threads,
                           logger=logger, force=True, tools=orf_tool or None,
                           progress=lambda p, m: prog(
                               'orf', 0.08 + p * 0.6, m))
        res = dict(res)
        if annotate:
            from Virus_Platform_Core.orf_annot import run_orf_annotation
            prog('orfa', 0.72, 'ORF 功能注释')
            res['orfa'] = run_orf_annotation(
                ctx.run_dir, threads=ctx.threads, logger=logger, force=True,
                engine=orf_engine or None, db=orf_db or None,
                model=orf_model or None, libs=orf_libs,
                progress=lambda p, m: prog('orfa', 0.72 + p * 0.26, m))
        prog('done', 1.0, '完成')
        logger.close()
        return res
    return job


def _tool_job_orfa(ctx):
    """功能注释（独立模块）：对已有 orf_ 运行注释，或 FASTA 预测+注释一步完成。"""
    run = (ctx.p.get('run') or '').strip()
    orf_engine = (ctx.p.get('engine') or '').strip()
    orf_db = (ctx.p.get('db') or '').strip()
    # 功能注释 CDS 模型：pyrodigal_rv（默认）/ pyrodigal
    orf_model = (ctx.p.get('model') or '').strip()
    if orf_model not in ('pyrodigal_rv', 'pyrodigal'):
        orf_model = ''
    # 注释层选择：prot（层1 序列同源）/ pfam（层2 HMM）/ cdd（层2 结构域）
    orf_libs = ctx.p.get('libs')
    if run:
        if not re.fullmatch(r'[A-Za-z0-9_]+', run) or not run.startswith('orf_'):
            abort(400, f'无效的 ORF 运行名: {run}')
        target = check_path(os.path.join(_tool_runs_root(), run),
                            must_exist=True, in_platform=True)

        def job(log, prog, cancel):
            logger = TaskLogger(callback=log)
            from Virus_Platform_Core.orf_annot import run_orf_annotation
            prog('orfa', 0.15, f'对运行 {run} 做 ORF 功能注释')
            res = run_orf_annotation(target, threads=ctx.threads, logger=logger,
                                     force=True, engine=orf_engine or None,
                                     db=orf_db or None,
                                     model=orf_model or None, libs=orf_libs,
                                     progress=lambda p, m: prog(
                                         'orfa', 0.15 + p * 0.8, m))
            res = dict(res)
            res['run'] = run
            prog('done', 1.0, '完成')
            logger.close()
            return res
        return job
    # 无 run → FASTA 输入：预测 + 注释一步完成
    ctx.p = dict(ctx.p)
    ctx.p['annotate'] = True
    if not (ctx.p.get('fasta') or '').strip():
        abort(400, '请选择已有 ORF 运行或输入 FASTA')
    return _tool_job_orf(ctx)


def _tool_job_genoplot(ctx):
    """基因组图谱（gbdraw 首选，缺则 DFV 顶上）。

    输入 FASTA（可选配 GFF3 注释）或 GenBank（.gb/.gbk，自带注释）。
    """
    fasta = ctx.opt('fasta')
    ann = ctx.opt('ann')
    if not fasta and not ann:
        abort(400, '请选择 FASTA 或 GenBank 输入')
    if ann and str(ann).lower().endswith(('.gb', '.gbk', '.gbff', '.genbank')):
        fasta = None          # GenBank 自带序列与注释，FASTA 忽略
    max_plots = max(1, min(int(ctx.p.get('max_plots') or 12), 200))
    # 绘图定制参数（透传 gbdraw CLI）：仅收集有值/True 的项
    gb_opts = {}
    for _k, _v in (ctx.p.get('gb_opts') or {}).items():
        if _v is None or _v == '' or _v is False:
            continue
        gb_opts[str(_k)] = _v
    plot_mode = (ctx.p.get('mode') or 'both')   # circular / linear / both

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.gbdraw_plot import run_genome_plots, gbdraw_available
        if not gbdraw_available():
            raise RuntimeError('未检测到 gbdraw（管道不支持 DFV）')
        tag = 'gbdraw'
        prog(tag, 0.05, f'{tag} 出图中')
        res = run_genome_plots(ctx.run_dir, logger=logger, force=True,
                               max_plots=max_plots, fasta_in=fasta, ann_in=ann,
                               opts=gb_opts, mode=plot_mode,
                               progress=lambda p, m: prog(tag, 0.05 + p * 0.9, m))
        if not res.get('plots'):
            raise RuntimeError('未产出任何基因组图（检查输入文件与绘图引擎）')
        res['run'] = os.path.basename(ctx.run_dir)   # 供前端 toolrun 内联展示 SVG
        prog('done', 1.0, f"完成：{len(res.get('plots', []))} 张图")
        logger.close()
        return res
    return job


def _tool_job_primer(ctx):
    """引物设计（primer3）。plain=基因组/contigs 全长分窗；
    conserved=多序列比对 FASTA 保守区（输入需已比对，如 MAFFT aln.fasta）。"""
    fasta = ctx.req('fasta', '输入 FASTA')
    mode = ctx.p.get('mode') or 'plain'
    if mode not in ('conserved', 'plain'):
        abort(400, '无效的引物设计模式')
    num_return = max(1, min(int(ctx.p.get('num_return') or 3), 20))
    specificity = bool(ctx.p.get('specificity'))

    def job(log, prog, cancel):
        import json as _json
        logger = TaskLogger(callback=log)
        if mode == 'conserved':
            p_dir = check_path(os.path.join(ctx.run_dir, '05_phylo'),
                               must_exist=False, in_platform=True)
            os.makedirs(os.path.join(p_dir, 'G1'), exist_ok=True)
            shutil.copyfile(fasta, os.path.join(p_dir, 'G1', 'aln.fasta'))
            with safe_open(os.path.join(p_dir, 'summary.json'), 'wt') as f:
                _json.dump({'groups': [{'group': 'G1', 'dir': 'G1'}]}, f)
        else:
            a_dir = check_path(os.path.join(ctx.run_dir, '03_assembly'),
                               must_exist=False, in_platform=True)
            os.makedirs(a_dir, exist_ok=True)
            shutil.copyfile(fasta, os.path.join(a_dir, 'viral_contigs.fasta'))
        from Virus_Platform_Core.primer import design_primers
        prog('primer', 0.1, f'primer3 引物设计（{mode}）')
        res = design_primers(ctx.run_dir, mode=mode, num_return=num_return,
                             logger=logger, force=True,
                             do_specificity=specificity)
        prog('done', 1.0, f"引物 {res.get('n_primers', 0)} 对")
        logger.close()
        return res
    return job


def _tool_job_identify(ctx):
    """② 病毒鉴定与提取（fastq 双端/单端 或 fasta contigs）。"""
    inp = ctx.req('input', '输入文件')
    itype = ctx.p.get('input_type') or 'pe'
    if itype not in ('pe', 'single', 'fasta'):
        abort(400, '无效的输入类型')
    conf = float(ctx.p.get('confidence') or 0)

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.kunpeng import classify, parse_classify_output
        inputs = [inp]
        if itype == 'pe':
            inputs.append(ctx.req('input2', 'R2 FASTQ'))
        prog('classify', 0.1, 'kunpeng 病毒库分类中')
        res = classify(ctx.db_virus, inputs, os.path.join(ctx.run_dir, 'classify'),
                       paired=(itype == 'pe'), threads=ctx.threads,
                       confidence=conf, logger=logger,
                       progress=lambda pp, mm: prog(
                           'classify', 0.1 + pp * 0.75, mm))
        ids = {}
        if res['kraken']:
            for flag, rid, taxid, _l, mapping in parse_classify_output(res['kraken']):
                if flag != 'C':
                    continue
                # kraken2 口径分值：支持该 taxid 的片段数 / 映射列总片段数
                sup = tot = 0
                for seg in (mapping or '').split():
                    t, _, c = seg.rpartition(':')
                    try:
                        cnt = int(c)
                    except ValueError:
                        continue
                    tot += cnt
                    if t == str(taxid):
                        sup += cnt
                ids[rid] = (taxid, round(sup / tot, 3) if tot else 0)
        prog('extract', 0.9, '提取病毒候选序列')
        n_ext = {}
        if ids:
            for i, s_ in enumerate(inputs, 1):
                tag = '' if len(inputs) == 1 else f'_{i}'
                dst = os.path.join(ctx.run_dir, f'viral_sequences{tag}.fasta')
                n_ext[os.path.basename(dst)] = _extract_records(s_, set(ids), dst)
                logger.log(f'提取病毒序列 {os.path.basename(dst)}: '
                           f'{n_ext[os.path.basename(dst)]} 条')
            with safe_open(os.path.join(ctx.run_dir, 'viral_ids.tsv'), 'wt') as f:
                f.write('seq_id\ttaxid\tscore\n')
                for rid, (tx, sc) in ids.items():
                    f.write(f'{rid}\t{tx}\t{sc}\n')
        prog('extract', 1.0, '完成')
        logger.close()
        # n_extracted 必须是标量：结果预览的统计条只展示标量字段
        return {'n_classified': len(ids), 'n_extracted': sum(n_ext.values()),
                'kreport': res['kreport']}
    return job


def _tool_job_assemble(ctx):
    """③ 病毒组装（SPAdes，可选模式）。"""
    r1 = ctx.req('r1', 'R1 FASTQ')
    r2 = ctx.req('r2', 'R2 FASTQ')
    mode = ctx.p.get('mode') or 'metaviral'
    mem = int(ctx.p.get('memory') or 64)
    min_len = int(ctx.p.get('min_len') or 200)

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.assembly import run_spades, filter_contigs
        out = os.path.join(ctx.run_dir, 'assembly')
        prog('spades', 0.05, 'SPAdes 组装中（耗时主要步骤）')
        spades_out = run_spades(r1, r2, out, mode=mode, threads=ctx.threads,
                                memory_gb=mem, logger=logger,
                                progress=lambda pp, mm: prog(
                                    'spades', 0.05 + pp * 0.85, mm))
        # 组装产物可能是 contigs.fasta（常规/metaviral-meta）或
        # transcripts.fasta（低覆盖自动降级 rna 模式），以 run_spades 实际
        # 返回的路径为准，不能硬编码 contigs.fasta（否则降级时找不到文件）。
        prog('filter', 0.92, 'contig 长度过滤')
        filtered, n_c, total_bp = filter_contigs(
            spades_out,
            os.path.join(ctx.run_dir, 'contigs.filtered.fasta'),
            min_len=min_len, logger=logger)
        prog('filter', 1.0, '完成')
        logger.close()
        return {'n_contigs': n_c, 'total_bp': total_bp,
                'contigs': filtered}
    return job


def _tool_job_contigs(ctx):
    """④ contig 病毒分类与提取（输入 contigs fasta）。"""
    contigs = ctx.req('contigs', 'contigs FASTA')
    min_len = int(ctx.p.get('min_len') or 200)
    conf = float(ctx.p.get('confidence') or 0)

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.assembly import filter_contigs
        from Virus_Platform_Core.kunpeng import classify, parse_classify_output
        from Virus_Platform_Core.contig_annot import classify_rows, genus_avg_map, RANKS

        prog('genus_lens', 0.03, '统计属平均基因组长度（首跑需建缓存）')
        genus_map = genus_avg_map(logger=logger)

        prog('filter', 0.05, 'contig 长度过滤')
        filtered, n_c, _bp = filter_contigs(
            contigs, os.path.join(ctx.run_dir, 'contigs.filtered.fasta'),
            min_len=min_len, logger=logger)
        if n_c == 0:
            raise RuntimeError('过滤后无 contigs（检查最小长度设置）')

        prog('classify', 0.15, 'kunpeng 病毒库分类')
        res = classify(ctx.db_virus, [filtered],
                       os.path.join(ctx.run_dir, 'classify'),
                       paired=False, threads=ctx.threads, confidence=conf,
                       logger=logger,
                       progress=lambda pp, mm: prog(
                           'classify', 0.15 + pp * 0.45, mm))
        ids = {}
        if res['kraken']:
            for flag, _rid, _tx, _l, _pa in parse_classify_output(res['kraken']):
                if flag == 'C':
                    ids[_rid] = _tx

        # metabuli 风格分类表：8 级谱系 + 属平均长度 + 近完整判定
        prog('annot', 0.8, '谱系注释与属长比整理')
        rows = []
        if res['kraken']:
            rows = classify_rows(res['kraken'], genus_map)
        tsv_path = os.path.join(ctx.run_dir, 'virus_classification.tsv')
        header = (['contig', 'taxid', 'taxon'] + RANKS
                  + ['length', 'genus_avg_len', 'ratio', 'near_complete',
                     'score', 'kmer_support', 'kmer_total'])
        with safe_open(tsv_path, 'wt') as f:
            f.write('\t'.join(header) + '\n')
            for r in rows:
                f.write('\t'.join(str(r.get(k, '')) for k in header) + '\n')

        prog('extract', 0.88, '提取病毒 contigs（带谱系 header）')
        n_viral = 0
        viral_fa = None
        if ids:
            viral_fa = os.path.join(ctx.run_dir, 'viral_contigs.fasta')
            seqs = _load_fasta_seqs(filtered)
            with safe_open(viral_fa, 'wt') as f:
                for rid, taxid in ids.items():
                    seq = seqs.get(rid)
                    if seq is None:
                        continue
                    n_viral += 1
                    row = next((r for r in rows if r['contig'] == rid), None)
                    lineage = ';'.join(row[r] for r in RANKS
                                       if row and row.get(r))
                    taxon = (row or {}).get('taxon', '')
                    f.write(f'>{rid} taxid={taxid} taxon='
                            f'{taxon.replace(" ", "_")} '
                            f'lineage={lineage}\n')
                    for i in range(0, len(seq), 70):
                        f.write(seq[i:i + 70] + '\n')

        prog('extract', 1.0, '完成')
        logger.close()
        return {'n_contigs': n_c, 'n_viral': n_viral,
                'kreport': res['kreport'],
                'classification': tsv_path, 'viral_fasta': viral_fa}
    return job


def _tool_job_structcmp(ctx):
    """结构比较：多条序列 MAFFT 全长比对 → 两两 identity 矩阵（SDT 口径）。"""
    seqs_fa = ctx.req('seqs', '序列 FASTA')
    max_n = max(3, min(int(ctx.p.get('max_n') or 30), 200))

    def _short(h, idx):
        name = re.split(r'[\s|]', (h or '').strip())[0][:40]
        name = re.sub(r'[^A-Za-z0-9_\-.]', '_', name)
        return name or f'seq{idx}'

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.phylo import _run_mafft
        from Virus_Platform_Core.utils import iter_fasta

        prog('read', 0.05, '读取与筛选序列')
        recs, seen = [], {}
        for h, s in iter_fasta(seqs_fa):
            name = _short(h, len(recs) + 1)
            if name in seen:
                seen[name] += 1
                name = f'{name}_{seen[name]}'
            else:
                seen[name] = 0
            recs.append((name, s.upper()))
        if len(recs) < 2:
            raise RuntimeError('FASTA 中少于 2 条序列，无法做结构比较')
        recs = recs[:max_n]

        capped_fa = os.path.join(ctx.run_dir, 'input.fasta')
        with safe_open(capped_fa, 'wt') as f:
            for name, s in recs:
                f.write(f'>{name}\n')
                for i in range(0, len(s), 70):
                    f.write(s[i:i + 70] + '\n')

        prog('aln', 0.15, 'MAFFT 全长比对')
        aln = _run_mafft(capped_fa, os.path.join(ctx.run_dir, 'aln.fasta'),
                         threads=ctx.threads, logger=logger)

        prog('matrix', 0.75, '计算两两 identity 矩阵')
        names, cols = [], []
        for h, s in iter_fasta(aln):
            names.append(_short(h, len(names) + 1))
            cols.append(s.upper())
        n = len(names)
        matrix = [[100.0] * n for _ in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                same = comp = 0
                for a, b in zip(cols[i], cols[j]):
                    if a == '-' and b == '-':
                        continue
                    comp += 1
                    if a == b:
                        same += 1
                pid = round(same / comp * 100, 2) if comp else 0.0
                matrix[i][j] = matrix[j][i] = pid

        tsv = os.path.join(ctx.run_dir, 'identity_matrix.tsv')
        with safe_open(tsv, 'wt') as f:
            f.write('\t'.join([''] + names) + '\n')
            for i in range(n):
                f.write('\t'.join([names[i]] +
                                  [f'{matrix[i][j]:.2f}' for j in range(n)]) + '\n')
        data = {'names': names, 'matrix': matrix, 'n': n,
                'aln_cols': len(cols[0]) if cols else 0}
        js = os.path.join(ctx.run_dir, 'identity_matrix.json')
        with safe_open(js, 'wt') as f:
            json.dump(data, f, ensure_ascii=False)

        prog('done', 1.0, '完成')
        logger.close()
        return {'n_seqs': n, 'aln': aln, 'matrix_tsv': tsv,
                'matrix_json': js, 'aln_cols': data['aln_cols']}
    return job


def _tool_job_verify(ctx):
    """候选序列验证（对齐 02b/09b）：宿主筛选 → 长度分流 → 双路过滤。

    输入可选已有 contigs 运行（run）或独立 FASTA（fasta）。
    参数：host（默认 all）、methods（blastx/cdd 组合）、combine（union/intersection）。
    """
    run_ref = (ctx.p.get('run') or '').strip()
    fasta = ctx.opt('fasta') if ctx.p.get('fasta') else None
    host = (ctx.p.get('host') or 'all').strip() or 'all'
    combine = (ctx.p.get('combine') or 'union').strip()
    methods = ctx.p.get('methods') or ['blastx', 'cdd']
    if isinstance(methods, str):
        methods = [m.strip() for m in methods.split(',') if m.strip()]
    methods = [m for m in methods if m in ('blastx', 'cdd')]

    if run_ref and not re.fullmatch(r'[A-Za-z0-9_\-]+', run_ref):
        abort(400, '无效的运行名')
    if combine not in ('union', 'intersection'):
        combine = 'union'

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.verify import verify

        # 输入解析：优先 run（其 viral_contigs.fasta），否则独立 fasta
        run_dir = ctx.run_dir
        if run_ref:
            src_run = check_path(os.path.join(_tool_runs_root(), run_ref),
                                 must_exist=True, in_platform=True)
            vfa = os.path.join(src_run, 'viral_contigs.fasta')
            if not os.path.isfile(vfa):
                raise RuntimeError('该运行无 viral_contigs.fasta（先跑 contig 分类）')
            # 宿主归属依赖源运行的分类表
            for _fn in ('virus_classification.tsv',):
                s = os.path.join(src_run, _fn)
                if os.path.isfile(s):
                    import shutil
                    shutil.copyfile(s, os.path.join(run_dir, _fn))
        else:
            if not fasta:
                abort(400, '请选择 contigs 运行或输入 FASTA')
            vfa = fasta

        summary = verify(run_dir, vfa, host=host, methods=methods,
                         combine=combine, threads=ctx.threads, logger=logger,
                         progress=lambda st, fr, msg: prog(st, fr, msg))
        logger.close()
        return summary
    return job


def _tool_job_consensus(ctx):
    """共识序列与变异分析（验证模块之后）：reads 回贴 → 共识序列 + 变异谱。

    参考三条来源：
      1. kvsuite 运行选参考（virus-fasta/ref_<acc>/）—— 已知病毒基因组
      2. contig 分类运行的 viral_contigs.fasta —— 未知/组装候选
      3. 独立 FASTA
    固定**重新比对**（minibwa map 双位置参数双端回贴），不复用 kvsuite 的
    BAM——那是按参考筛过的 reads 子集，有比对偏好性，会系统性低估变异。
    reads 默认来源（未手动指定时）：
      1. 所选 kvsuite 运行的输入序列（tool_runs/<run>/sample_sheet.tsv，
         即「已知病毒识别与定量」吃进去的 reads）
      2. contig 分类运行目录的 01_host_removal（去宿主后全量，变异无偏）
      3. 都没有 → 报错要求手动指定
    """
    run_ref = (ctx.p.get('run') or '').strip()
    fasta = ctx.opt('fasta') if ctx.p.get('fasta') else None
    kv_run = (ctx.p.get('kv_run') or '').strip()
    kv_refs = [x.strip() for x in (ctx.p.get('kv_refs') or '').split(',') if x.strip()]
    ambig = (ctx.p.get('ambig') or 'N').strip()[:1] or 'N'

    def _num(v, default, cast):
        try:
            return cast(v)
        except (TypeError, ValueError):
            return default

    min_qual = _num(ctx.p.get('min_qual'), 20, int)
    min_depth = _num(ctx.p.get('min_depth'), 10, int)
    min_freq = _num(ctx.p.get('min_freq'), 0.5, float)
    min_mapq = _num(ctx.p.get('min_mapq'), 10, int)
    min_minor_freq = _num(ctx.p.get('min_minor_freq'), 0.02, float)
    min_cov_pct = _num(ctx.p.get('min_cov_pct'), 10.0, float)
    min_qual = max(0, min(min_qual, 60))
    min_depth = max(1, min(min_depth, 100000))
    min_freq = min(1.0, max(0.0, min_freq))

    if run_ref and not re.fullmatch(r'[A-Za-z0-9_\-]+', run_ref):
        abort(400, '无效的运行名')
    if kv_run and not re.fullmatch(r'[A-Za-z0-9_\-]+', kv_run):
        abort(400, '无效的 kvsuite 运行名')
    if kv_refs and not kv_run:
        abort(400, '选了参考序列但未指定 kvsuite 运行')
    for _r in kv_refs:
        if not re.fullmatch(r'[A-Za-z0-9_.\-]+', _r):
            abort(400, '无效的 accession: %s' % _r)

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.consensus import (consensus_and_variants,
                                                   find_read_pairs,
                                                   pair_read_files)

        # ---- 参考 ----
        # 三条来源，优先级：kvsuite 选参考 > contig 运行 > 独立 FASTA
        #   kvsuite：<run>/kvsuite/virus-fasta/ref_<acc>/ref_<acc>.ref.fasta
        #            多选按 accession 合并成临时库（序列名已保证唯一）
        src_run = None
        vfa = None
        if kv_refs:
            kv_base = check_path(os.path.join(_tool_runs_root(), kv_run,
                                              'kvsuite'),
                                 must_exist=True, in_platform=True)
            fa_dir = os.path.join(kv_base, 'virus-fasta')
            parts, missing = [], []
            for acc in kv_refs:
                sub = os.path.join(fa_dir, 'ref_%s' % acc)
                cand = os.path.join(sub, 'ref_%s.ref.fasta' % acc)
                if os.path.isfile(cand) and os.path.getsize(cand) > 0:
                    parts.append((acc, cand))
                    continue
                # 容错：目录在但文件名不同
                found = None
                if os.path.isdir(sub):
                    for fn in sorted(os.listdir(sub)):
                        if fn.endswith(('.fasta', '.fa', '.fna')):
                            found = os.path.join(sub, fn)
                            break
                if found:
                    parts.append((acc, found))
                else:
                    missing.append(acc)
            if not parts:
                raise RuntimeError(
                    '所选参考在 %s 下均无 FASTA（先跑共识段生成 virus-fasta）'
                    % fa_dir)
            if missing:
                log('跳过无 FASTA 的参考: %s' % ', '.join(missing))
            # 写到运行目录，作为本次分析的临时参考
            tmp_ref = os.path.join(ctx.run_dir, 'ref_%s.fasta' % kv_run)
            n_seq = 0
            with open(tmp_ref, 'w', encoding='utf-8', newline='\n') as out:
                for acc, path in parts:
                    with open(path, encoding='utf-8', errors='replace') as fh:
                        for line in fh:
                            if line.startswith('>'):
                                n_seq += 1
                                head = line[1:].strip().split()[0]
                                # accession 唯一化：序列名已一致时保留原样
                                if head == acc:
                                    out.write(line if line.endswith('\n')
                                              else line + '\n')
                                else:
                                    out.write('>%s\n' % acc)
                            else:
                                out.write(line if line.endswith('\n')
                                          else line + '\n')
            log('kvsuite 参考库：%d 条（%d 个 accession）-> %s'
                % (n_seq, len(parts), os.path.basename(tmp_ref)))
            vfa = tmp_ref
        elif run_ref:
            src_run = check_path(os.path.join(_tool_runs_root(), run_ref),
                                 must_exist=True, in_platform=True)
            vfa = os.path.join(src_run, 'viral_contigs.fasta')
            if not os.path.isfile(vfa):
                raise RuntimeError('该运行无 viral_contigs.fasta（先跑 contig 分类）')
        else:
            if not fasta:
                abort(400, '请选择 contigs 运行、kvsuite 参考或输入参考 FASTA')
            vfa = fasta

        # ---- reads ----
        # 固定重新比对。未手动指定时按 docstring 里的默认来源顺序解析；
        # kvsuite 的 bam/virus_reads 已按病毒筛过，不作为来源（低估变异）。
        # 文件 token 先收集再统一配对——R1/R2 拆在两个 token 里也能配上。
        reads = []
        file_toks = []
        for p in (ctx.p.get('reads') or '').split(','):
            p = p.strip()
            if not p:
                continue
            if os.path.isdir(p):
                reads.extend(find_read_pairs(p))
            elif os.path.isfile(p):
                file_toks.append(p)
            else:
                abort(400, 'reads 路径不存在：%s' % p)
        reads.extend(pair_read_files(file_toks))
        if not reads:
            if kv_run:
                # kvsuite 运行的输入序列（含样品与直填测序数据两种来路，
                # 都落在该 run 目录的 sample_sheet.tsv）
                sheet = os.path.join(_tool_runs_root(), kv_run,
                                     'sample_sheet.tsv')
                if not os.path.isfile(sheet):
                    abort(400, 'kvsuite 运行 %s 无 sample_sheet.tsv，'
                               '请手动指定回贴 reads' % kv_run)
                with open(sheet, encoding='utf-8-sig', errors='replace') as fh:
                    hdr = fh.readline().rstrip('\n').split('\t')
                    if 'r1' not in hdr:
                        abort(400, 'sample_sheet.tsv 缺 r1 列：%s' % sheet)
                    i1 = hdr.index('r1')
                    i2 = hdr.index('r2') if 'r2' in hdr else len(hdr)
                    for line in fh:
                        cols = line.rstrip('\n').split('\t')
                        if len(cols) <= i1 or not cols[i1].strip():
                            continue
                        r2 = cols[i2].strip() if len(cols) > i2 else ''
                        reads.append((cols[i1].strip(), r2 or None))
                if not reads:
                    abort(400, 'kvsuite 运行 %s 的 sample_sheet.tsv 没有'
                               '有效 reads，请手动指定' % kv_run)
                log('reads 默认取该 kvsuite 运行的输入序列：'
                    '%d 个样本（sample_sheet.tsv）' % len(reads))
            elif src_run:
                layer = os.path.join(src_run, CONSENSUS_FALLBACK_LAYER)
                reads = find_read_pairs(layer)
                if not reads:
                    raise RuntimeError(
                        '在 %s 下未找到 reads（期望 *_R1/*.fastq(.gz) 配对文件）'
                        % CONSENSUS_FALLBACK_LAYER)
                log('reads 默认取 contig 运行的去宿主后全量（%s）'
                    % CONSENSUS_FALLBACK_LAYER)
            else:
                abort(400, '请直接给出回贴 reads 文件/目录')

        summary = consensus_and_variants(
            ctx.run_dir, vfa, reads, out_subdir='consensus',
            min_qual=min_qual, min_depth=min_depth, min_freq=min_freq,
            ambig=ambig, min_mapq=min_mapq, min_minor_freq=min_minor_freq,
            min_cov_pct=min_cov_pct, preset='sr', threads=ctx.threads,
            logger=logger, progress=lambda st, fr, msg: prog(st, fr, msg))
        logger.close()
        return summary
    return job


def _tool_job_kvsuite(ctx):
    """已知病毒识别与定量（known_virus_suite 五段整合）。

    移植自 D:/桌面/延伸基因组/MMPV-RNA/virome_analysis_pipeline：
      鉴定 → 过滤 → 共识 → 深度绘图 → 变异注释
    引擎分工固定：定量（identify）用 salmon（--writeBam 出映射 BAM），
    共识段内部固定 minibwa 真比对。

    默认只跑**两段**：识别/定量（identify）+ 过滤（filter）——本卡的口径就是
    「识别与定量」；共识序列、深度绘图、变异注释由下游模块各自完成
    （共识序列分析 t-consensus / 病毒变异分析 t-variant），需要在本卡一次跑全时
    前端把 stage 选成 all（或走 t-kvchain 一键全流程，那条链固定 stage=all）。
    与管道阶段 Virus_Platform_Core/kv_stage.py 的口径一致（它也只跑这两段）。

    caller 用 bcftools mpileup+call（freebayes/lofreq/ivar 在 Windows 上均不可得），
    参数与阈值为实测定稿，详见 Virus_Platform_Core/known_virus_suite/POSCOUNTS_REMOVAL_PLAN.md §4.2。
    """
    import json

    # ── 输入：勾选样品 → 临时 sample-sheet TSV(name,r1,r2) ──
    # 变异段（variant）不吃 reads，只需 BAM 或 VCF，因此允许 samples 为空。
    stage = (ctx.p.get('stage') or KV_DEFAULT_STAGE).strip().lower()
    if stage not in ('all', 'index', 'identify', 'filter', KV_DEFAULT_STAGE,
                     'consensus', 'plot', 'variant'):
        stage = KV_DEFAULT_STAGE
    samples_raw = (ctx.p.get('samples') or '').strip()
    sheet_in = (ctx.p.get('sample_sheet') or '').strip()
    reads_raw = (ctx.p.get('reads') or '').strip()
    if sheet_in and reads_raw:
        abort(400, '样本表 TSV 与直接输入测序数据只能二选一')
    if samples_raw and reads_raw:
        abort(400, '样品与直接输入测序数据只能二选一')
    if sheet_in:
        sheet = ctx.req('sample_sheet', '样本表 TSV')
    elif stage == 'variant':
        sheet = None          # 变异段不用样本表
    elif reads_raw:
        # 直接输入测序数据（不必先建样品）：目录/文件 → R1/R2 配对 → 样本表。
        # 样本名取 R1 文件名去掉 _R1 与扩展名，重名自动加后缀；
        # 文件 token 先收集再统一配对——R1/R2 拆在两个 token 里也能配上。
        from Virus_Platform_Core.consensus import (find_read_pairs,
                                                   pair_read_files)
        dir_pairs, file_toks = [], []
        for tok in reads_raw.split(','):
            tok = tok.strip()
            if not tok:
                continue
            if os.path.isdir(tok):
                pairs = find_read_pairs(tok)
                if not pairs:
                    abort(400, '目录下未找到 reads'
                               '（期望 *_R1/*.fastq(.gz)，R2 按 _R2 配对）：%s'
                               % tok)
                dir_pairs.extend(pairs)
            elif os.path.isfile(tok):
                file_toks.append(tok)
            else:
                abort(400, 'reads 路径不存在：%s' % tok)
        rows = []
        used = set()
        for r1, r2 in dir_pairs + pair_read_files(file_toks):
            from Virus_Platform_Core.consensus import R1_RX
            m = R1_RX.match(os.path.basename(r1))
            stem = (m.group(1) if m
                    else re.sub(r'\.(fq|fastq)(\.gz)?$', '',
                                os.path.basename(r1), flags=re.I))
            nm = re.sub(r'[^\w\-.]+', '_', stem).strip('_-.') or 'sample'
            base, k = nm, 2
            while nm in used:
                nm = '%s_%d' % (base, k)
                k += 1
            used.add(nm)
            rows.append((nm, r1, r2 or ''))
        sheet = os.path.join(ctx.run_dir, 'sample_sheet.tsv')
        with open(sheet, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('name\tr1\tr2\n')
            for nm, r1, r2 in rows:
                fh.write(f'{nm}\t{r1}\t{r2}\n')
    else:
        if not samples_raw:
            abort(400, '请选择样品、直接输入测序数据（FASTQ），或提供样本表 TSV')
        names = [s.strip() for s in samples_raw.split(',') if s.strip()]
        if not names:
            abort(400, '未选择有效样品')
        from Virus_Platform_Core.pipeline import load_sample_input
        from Virus_Platform_Core.utils import resolve_sample_name
        rows = []
        for nm in names:
            # 勾选框给的是 /api/samples 返回的真实目录名 → 按磁盘解析后再取输入
            real = resolve_sample_name(nm, DIRS['results'])
            sd = check_path(os.path.join(DIRS['results'], real),
                            must_exist=True, in_platform=True)
            r1, r2, _proj = load_sample_input(sd)
            if not r1 or not os.path.isfile(r1):
                abort(400, f'样品 {nm} 的 R1 不可用: {r1}')
            # sample_sheet 用真实目录名，便于与 results/ 下的产物目录对上
            rows.append((real, r1, r2 or ''))
        sheet = os.path.join(ctx.run_dir, 'sample_sheet.tsv')
        with open(sheet, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write('name\tr1\tr2\n')
            for nm, r1, r2 in rows:
                fh.write(f'{nm}\t{r1}\t{r2}\n')

    # ── 参考序列与注释 ──
    # 缺省参考统一走 kv_stage 的目录解析（重构后的自包含库目录优先，
    # 旧布局散置文件兜底），不再各自硬编码路径。
    from Virus_Platform_Core.kv_stage import (default_ref_info,
                                              default_reference)
    ref = (ctx.p.get('reference') or '').strip()
    if ref:
        ref = ctx.req('reference', '参考序列')
    else:
        ref = default_reference()
        if not ref:
            abort(400, '缺少默认病毒参考：请先在「数据库构建 → 病毒鉴定库」建库')
        ref = check_path(ref, must_exist=True, in_platform=True)
    ref_info = (ctx.p.get('ref_info') or '').strip()
    if ref_info:
        ref_info = ctx.req('ref_info', '参考注释')
    else:
        cand = default_ref_info()
        ref_info = cand if cand and os.path.isfile(cand) else None

    # 定量引擎固定 salmon（共识段内部固定 minibwa，不经此参数）。
    # 旧前端的 engine 值仍接受但一律归一为 salmon。
    engine = 'salmon'
    # 索引复用：① 用户在前端选的「鉴定库」优先（build 页建好的）；
    # ② 默认参考 + 预建索引在位时自动复用（避免每个 run 重建 60 MB 索引）；
    # ③ 都不满足则回退 <out>/index 临时建。
    index_dir = None
    user_idx = (ctx.p.get('index_dir') or '').strip()
    if user_idx:
        index_dir = ctx.req('index_dir', '鉴定库目录')
    else:
        # 预建索引复用（布局判定收敛在 kv_stage.index_dir_for 一处）
        from Virus_Platform_Core.kv_stage import index_dir_for
        index_dir = index_dir_for(ref, engine)

    def _num(v, default, cast, lo=None, hi=None):
        try:
            x = cast(v)
        except (TypeError, ValueError):
            return default
        if lo is not None:
            x = max(lo, x)
        if hi is not None:
            x = min(hi, x)
        return x

    min_cov = _num(ctx.p.get('min_cov'), 10.0, float, 0.0, 100.0)
    min_depth = _num(ctx.p.get('min_depth'), 0.5, float, 0.0)
    min_reads = _num(ctx.p.get('min_reads'), 10, int, 0)
    min_poisson = _num(ctx.p.get('min_poisson'), 0.3, float, 0.0, 1.0)
    variant_qual = _num(ctx.p.get('variant_qual'), 3.5, float, 0.0)
    min_freq = _num(ctx.p.get('min_freq'), 0.05, float, 0.0, 1.0)
    aa_label_cutoff = _num(ctx.p.get('aa_label_cutoff'), 0.50, float, 0.0, 1.01)
    max_aa_labels = _num(ctx.p.get('max_aa_labels'), 40, int, 0)

    def job(log, prog, cancel):
        # 引擎入口统一走 kv_stage.engine_cmd()：源码模式 python -m，
        # 冻结模式 --run-engine（engine_entry 已在进程内注册 kvsuite）
        from Virus_Platform_Core.kv_stage import engine_cmd
        entry_exe, entry_pre = engine_cmd()

        out_dir = os.path.join(ctx.run_dir, 'kvsuite')
        os.makedirs(out_dir, exist_ok=True)
        cmd = [entry_exe] + entry_pre + [stage,
               '--out', out_dir,
               '--reference', ref,
               '--engine', engine,
               '--min-cov', str(min_cov),
               '--min-depth', str(min_depth),
               '--min-reads', str(min_reads),
               '--min-poisson', str(min_poisson),
               '--variant-qual', str(variant_qual),
               '--min-freq', str(min_freq),
               '--aa-label-cutoff', str(aa_label_cutoff),
               '--max-aa-labels', str(max_aa_labels)]
        if sheet:
            cmd += ['--sample-sheet', sheet]
        # 变异段输入：外部 VCF 优先于 BAM 目录（CLI 内也是这个优先级）
        input_vcf = (ctx.p.get('input_vcf') or '').strip()
        if input_vcf:
            cmd += ['--input-vcf', ctx.req('input_vcf', '变异 VCF 文件')]
        bam_dir = (ctx.p.get('bam_dir') or '').strip()
        if bam_dir:
            cmd += ['--bam-dir', ctx.req('bam_dir', 'BAM 目录')]
        if ref_info:
            cmd += ['--ref-info', ref_info]
        if index_dir:
            cmd += ['--index-dir', index_dir]
        if ctx.threads:
            cmd += ['--threads', str(ctx.threads),
                    '--align-threads', str(ctx.threads)]
        if ctx.p.get('ncbi_email'):
            cmd += ['--ncbi-email', str(ctx.p['ncbi_email']).strip()]
        if ctx.p.get('no_genes'):
            cmd.append('--no-genes')
        if ctx.p.get('no_variant_evo'):
            cmd.append('--no-variant-evo')
        if ctx.p.get('all_variants'):
            cmd.append('--all-variants')
        if ctx.p.get('no_snpgenie'):
            cmd.append('--no-snpgenie')

        log('$ ' + ' '.join(cmd))
        env = dict(os.environ)
        env.setdefault('PYTHONIOENCODING', 'utf-8')
        # NCBI API key 走环境变量传递（引擎侧 argparse 以 NCBI_API_KEY 兜底）：
        # 不进 argv → 不出现在上面这行 `$ ...` 任务日志 / run.log / 进程列表里
        _api_key = str(ctx.p.get('ncbi_api_key') or '').strip()
        if _api_key:
            env['NCBI_API_KEY'] = _api_key
        proc = subprocess.Popen(cmd, cwd=PLATFORM_ROOT,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT,
                                text=True, encoding='utf-8',
                                errors='replace', bufsize=1, env=env)
        tail = []
        for line in proc.stdout:
            line = line.rstrip('\n')
            if not line:
                continue
            log(line)
            tail.append(line)
            if len(tail) > 40:
                tail.pop(0)
            # cancel 是 threading.Event（见 TaskServer._run），必须用 is_set()，
            # 直接 cancel() 会报 'Event' object is not callable。
            if cancel is not None and cancel.is_set():
                # taskkill /T 杀整棵进程树：只 kill 引擎本身会留下
                # salmon/samtools 孤儿继续吃 CPU/磁盘
                subprocess.run(['taskkill', '/F', '/T', '/PID', str(proc.pid)],
                               capture_output=True)
                proc.wait()
                raise RuntimeError('用户取消')
        rc = proc.wait()
        if rc != 0:
            raise RuntimeError(f'known_virus_suite 退出码 {rc}；末几行：\n'
                               + '\n'.join(tail[-8:]))

        # ── 汇总产物（供结果面板展示）──
        result = {'stage': stage, 'engine': engine, 'out': out_dir,
                  'reference': ref}
        fsum = os.path.join(out_dir, 'filter', 'filtered.tsv')
        if os.path.isfile(fsum):
            result['filtered_tsv'] = fsum
            try:
                with open(fsum, encoding='utf-8', errors='replace') as fh:
                    result['n_confirmed'] = max(0, sum(1 for _ in fh) - 1)
            except OSError:
                pass
        vsum = os.path.join(out_dir, 'variant_summary.json')
        if os.path.isfile(vsum):
            result['variant_summary'] = vsum
            try:
                with open(vsum, encoding='utf-8') as fh:
                    data = json.load(fh)
                rows = data.get('results') if isinstance(data, dict) else data
                rows = rows or []
                result['n_variant_genomes'] = len(rows)
                result['n_variants'] = sum(int(d.get('n_variants') or 0)
                                           for d in rows)
                if isinstance(data, dict):
                    result['n_variant_skipped'] = int(data.get('n_skipped') or 0)
            except (OSError, ValueError, TypeError):
                pass
        return result
    return job


def _tool_job_quicktree(ctx):
    """快速建树：多条序列 MAFFT 全长比对 → NJ（纯 Python）/ FastTree。

    aligned=True 时输入已是比对好的 FASTA（如序列比对模块的
    aln.fasta / aln.trim.fasta），跳过 MAFFT 直接建树——对已比对序列
    重复比对会破坏列对应关系。
    """
    seqs_fa = ctx.req('seqs', '序列 FASTA')
    method = (ctx.p.get('method') or 'nj').strip().lower()
    if method not in ('nj', 'fasttree'):
        abort(400, '建树方法仅支持 nj / fasttree')
    aligned = str(ctx.p.get('aligned') or '').strip().lower() in (
        '1', 'true', 'yes', 'on')
    max_n = max(3, min(int(ctx.p.get('max_n') or 100), 500))

    def _short(h, idx):
        name = re.split(r'[\s|]', (h or '').strip())[0][:40]
        name = re.sub(r'[^A-Za-z0-9_\-.]', '_', name)
        return name or f'seq{idx}'

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.phylo import _run_mafft, _run_nj, _run_fasttree
        from Virus_Platform_Core.utils import iter_fasta

        prog('read', 0.05, '读取与筛选序列')
        recs, seen = [], {}
        for h, s in iter_fasta(seqs_fa):
            name = _short(h, len(recs) + 1)
            if name in seen:
                seen[name] += 1
                name = f'{name}_{seen[name]}'
            else:
                seen[name] = 0
            recs.append((name, s.upper()))
        if len(recs) < 2:
            raise RuntimeError('FASTA 中少于 2 条序列，无法建树')
        recs = recs[:max_n]

        capped_fa = os.path.join(ctx.run_dir, 'input.fasta')
        with safe_open(capped_fa, 'wt') as f:
            for name, s in recs:
                f.write(f'>{name}\n')
                for i in range(0, len(s), 70):
                    f.write(s[i:i + 70] + '\n')

        prog('aln', 0.2, '输入已比对，跳过 MAFFT' if aligned
             else 'MAFFT 全长比对')
        if aligned:
            aln = capped_fa
        else:
            aln = _run_mafft(capped_fa, os.path.join(ctx.run_dir, 'aln.fasta'),
                             threads=ctx.threads, logger=logger)
        if aligned:
            logger.log('aligned=True：输入视为已完成的多序列比对，'
                       '直接建树（不重复 MAFFT）')

        prog('tree', 0.75, 'NJ 建树' if method == 'nj' else 'FastTree 建树')
        tree_name = 'nj.nwk' if method == 'nj' else 'tree.nwk'
        if method == 'nj':
            _run_nj(aln, os.path.join(ctx.run_dir, tree_name), logger=logger)
        else:
            _run_fasttree(aln, os.path.join(ctx.run_dir, tree_name),
                          logger=logger)

        prog('done', 1.0, '完成')
        logger.close()
        return {'n_seqs': len(recs), 'method': method, 'tree': tree_name,
                'aligned': aligned}
    return job


def _tool_job_align(ctx):
    """序列比对（独立模块）：MAFFT（auto/L-INS-i/fast）→ trimAl 清剪。

    输入 FASTA（核酸或蛋白，自动判别；≥2 条）。可选 seqs_extra：
    第二个 FASTA 文件，与 seqs 合并后一起参与比对（同名序列自动加 _2 后缀）。
    产物：input.fasta / aln.fasta / aln.trim.fasta（trimAl 关闭时无）/
    summary.json，可在「比对查看器」彩色浏览与编辑。
    """
    from Virus_Platform_Core.utils import iter_fasta, write_fasta_record
    seqs_fa = ctx.req('seqs', '序列 FASTA')
    seqs_extra = ctx.opt('seqs_extra')
    strategy = (ctx.p.get('strategy') or 'auto').strip().lower()
    if strategy not in ('auto', 'linsi', 'fast'):
        abort(400, '比对策略仅支持 auto / linsi / fast')
    trimal = (ctx.p.get('trimal') or 'automated1').strip().lower()
    if trimal not in ('automated1', 'gappyout', 'strict', 'none'):
        abort(400, 'trimAl 方法仅支持 automated1 / gappyout / strict / none')
    max_n = max(3, min(int(ctx.p.get('max_n') or 200), 500))

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        from Virus_Platform_Core.phylo import _run_mafft, _run_trimal
        from Virus_Platform_Core.sdt_exact import detect_seqtype
        prog('read', 0.05, '读取与筛选序列')
        recs, seen = [], {}
        _srcs = [seqs_fa] + ([seqs_extra] if seqs_extra else [])
        for _si, _src in enumerate(_srcs):
            for h, s in iter_fasta(_src):
                name = re.split(r'[\s|]', (h or '').strip())[0][:60] or \
                    f'seq{len(recs) + 1}'
                name = re.sub(r'[^A-Za-z0-9_\-.]', '_', name)
                if name in seen:
                    seen[name] += 1
                    name = f'{name}_{seen[name]}'
                else:
                    seen[name] = 0
                recs.append((name, s.upper()))
        if seqs_extra:
            logger.log(f'额外序列文件已合并: {os.path.basename(seqs_extra)}'
                       f'（合并后共 {len(recs)} 条）')
        if len(recs) < 2:
            raise RuntimeError('FASTA 中少于 2 条序列，无法比对')
        recs = recs[:max_n]
        seqtype = detect_seqtype([s for _, s in recs])
        capped = os.path.join(ctx.run_dir, 'input.fasta')
        with safe_open(capped, 'wt') as f:
            for name, s in recs:
                write_fasta_record(f, name, s)
        logger.log(f'序列类型判定: {"蛋白(aa)" if seqtype == "aa" else "核酸(nt)"}'
                   f'，{len(recs)} 条参与比对')
        prog('align', 0.15, f'MAFFT 比对（{strategy}）')
        aln = _run_mafft(capped, os.path.join(ctx.run_dir, 'aln.fasta'),
                         threads=ctx.threads, logger=logger, strategy=strategy)
        trim_info = {'applied': False}
        aln_used = aln
        if trimal != 'none':
            prog('trim', 0.7, f'trimAl 清剪（{trimal}）')
            aln_used, trim_info = _run_trimal(
                aln, os.path.join(ctx.run_dir, 'aln.trim.fasta'),
                logger=logger)
        prog('done', 1.0, '完成')
        logger.close()
        return {'n_seqs': len(recs), 'seqtype': seqtype, 'strategy': strategy,
                'trimal': trimal, 'trim': trim_info,
                'aln': 'aln.fasta',
                'aln_used': os.path.basename(aln_used)}
    return job


def _tool_job_sdt(ctx):
    """SDT 精确分析（纯 Python 复刻 SDTv1.3，替代外部 SDT exe）：
    逐对 MAFFT 独立比对 → Get_Similarity 公式 → 聚类排序热图 + 分布图。
    aligned=True 时输入为已比对 MSA，跳过比对器直接按公式计算；
    seqtype='auto' 自动判别核酸/蛋白（MMPV 双轨口径），蛋白按 AA 同一性。"""
    seqs_fa = ctx.req('seqs', '序列 FASTA')
    max_n = max(3, min(int(ctx.p.get('max_n') or 30), 200))
    orient = bool(ctx.p.get('orient', True))
    seqtype = (ctx.p.get('seqtype') or 'auto').strip().lower()
    if seqtype not in ('auto', 'nt', 'aa'):
        seqtype = 'auto'
    palette = (ctx.p.get('palette') or 'sdt').strip().lower()
    if palette not in ('sdt', 'cividis', 'viridis', 'RdYlBu', 'Spectral',
                       'YlGnBu', 'coolwarm', 'magma'):
        palette = 'sdt'
    aligned = bool(ctx.p.get('aligned'))

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        mafft = cfg.tool('mafft')
        from Virus_Platform_Core.sdt_exact import run_sdt_exact
        prog('sdt', 0.02, 'SDT 精确分析（MAFFT 逐对独立比对，SDT v1.3 口径）')
        res = run_sdt_exact(seqs_fa, ctx.run_dir, mafft, max_n=max_n,
                            orient=orient, threads=ctx.threads,
                            seqtype=seqtype,
                            palette=palette, logger=logger,
                            progress=lambda p, m: prog('sdt', p, m),
                            cancel=cancel, aligned=aligned)
        logger.close()
        return res
    return job


def _tool_job_identity(ctx):
    """核苷酸+氨基酸同一性表（BioAider Sequence Identity Matrix 口径）：
    NT 矩阵 + AA 矩阵（可选输入或最长 ORF 翻译）+ 复合热图（NT 上 /
    AA 下）+ 逐对同一性长表。"""
    nt_fa = ctx.req('nt_seqs', '核苷酸 FASTA')
    aa_fa = ctx.opt('aa_seqs')
    max_n = max(3, min(int(ctx.p.get('max_n') or 30), 200))
    palette = (ctx.p.get('palette') or 'sdt').strip().lower()
    if palette not in ('sdt', 'cividis', 'viridis', 'RdYlBu', 'Spectral',
                       'YlGnBu', 'coolwarm', 'magma'):
        palette = 'sdt'
    aligned = bool(ctx.p.get('aligned'))

    def job(log, prog, cancel):
        logger = TaskLogger(callback=log)
        mafft = cfg.tool('mafft')
        from Virus_Platform_Core.sdt_exact import run_identity_table
        prog('idty', 0.02, '核苷酸+氨基酸同一性表（BioAider 口径）')
        res = run_identity_table(nt_fa, ctx.run_dir, mafft, aa_fasta=aa_fa,
                                 max_n=max_n, aligned=aligned,
                                 threads=ctx.threads, palette=palette,
                                 logger=logger,
                                 progress=lambda p, m: prog('idty', p, m),
                                 cancel=cancel)
        logger.close()
        return res
    return job


def _load_fasta_seqs(path):
    """FASTA → {首 token id: 序列}（单条记录可达 MB 级，仅限小文件用）。"""
    import gzip
    op = gzip.open if str(path).lower().endswith('.gz') else open
    out, name, buf = {}, None, []
    with op(path, 'rt', errors='replace') as f:
        for line in f:
            if line.startswith('>'):
                if name is not None:
                    out[name] = ''.join(buf)
                name = line[1:].split()[0]
                buf = []
            else:
                buf.append(line.strip())
    if name is not None:
        out[name] = ''.join(buf)
    return out


def _find_contig_seq(run_dir, contig):
    """在工具运行目录的各 FASTA 中查找 contig 序列。"""
    for cur, _sub, fns in os.walk(run_dir):
        if os.path.join('analysis') in cur:
            continue
        for fn in fns:
            if not fn.lower().endswith(('.fasta', '.fa', '.fna', '.fas')):
                continue
            try:
                seqs = _load_fasta_seqs(os.path.join(cur, fn))
            except (OSError, ValueError):
                continue
            if contig in seqs:
                return seqs[contig]
    return None


def _extract_records(src, ids, dst):
    """从 FASTA/FASTQ（支持 .gz）提取 header 首 token 命中 ids 的记录。

    kunpeng 报告里的 read ID 经过 seqkit fq2fa 转换，已去掉 Illumina 配对
    后缀 /1、/2，匹配时对原始 header 兼容带/不带后缀两种写法；
    FASTQ 输入统一转成 FASTA 写出（与 .fasta 扩展名一致）。
    返回提取条数；ids 为空集时写出空文件。
    """
    import gzip
    name = str(src).lower()
    is_fq = name.endswith(('.fastq.gz', '.fq.gz', '.fastq', '.fq'))
    op = gzip.open if name.endswith('.gz') else open

    def match(rid):
        """命中返回规范 ID（配对后缀 /1、/2 已去掉，与 kunpeng 报告一致），未命中返回 None。"""
        if rid in ids:
            return rid
        base = rid.rsplit('/', 1)
        if len(base) == 2 and base[1] in ('1', '2') and base[0] in ids:
            return base[0]
        return None

    n = 0
    with op(src, 'rt', errors='replace') as f, safe_open(dst, 'wt') as w:
        if is_fq:
            while True:
                h = f.readline()
                if not h:
                    break
                seq = f.readline().rstrip('\r\n')
                f.readline()
                f.readline()
                tok = h[1:].split()
                mid = match(tok[0]) if tok else None
                if mid:
                    w.write(f'>{mid}\n')
                    for i in range(0, len(seq), 70):
                        w.write(seq[i:i + 70] + '\n')
                    n += 1
        else:
            keep = False
            for line in f:
                if line.startswith('>'):
                    tok = line[1:].split()
                    keep = bool(tok) and match(tok[0]) is not None
                    if keep:
                        n += 1
                if keep:
                    w.write(line)
    return n
