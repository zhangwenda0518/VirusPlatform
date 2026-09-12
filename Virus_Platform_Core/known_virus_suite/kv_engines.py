#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kv_engines.py — 引擎抽象层
=========================
定量（identify）唯一引擎是 salmon：quant.sf 出 EM 定量，--writeBam 出映射
位点（排序 BAM + pandepth 覆盖度/深度，与旧 minibwa 路径同一后端与命名）。
真比对只存在于共识段内部——kv_consensus 直接调 minibwa，不经本工厂
（用户口径：定量用 salmon，共识用 minibwa，互不混用）。

接口契约见 DESIGN.md 第三节。

设计来源: virome_analysis_pipeline/batch_virus_depth.py 的
build_index / process_sample_pseudo / process_sample_traditional
（复制后重构为引擎类，原文件不动）
"""

import gzip
import os
import re
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AlignResult:
    """一次比对的统一返回结构"""
    sam_path: Path = None            # 比对记录（salmon 为排序后的映射 BAM）
    quant_path: Path = None          # 定量文件（salmon quant.sf）
    reads: dict = field(default_factory=dict)      # {accession: 定量 reads}
    refstats: dict = field(default_factory=dict)   # {accession: {Coverage(%), MeanDepth, Mapped_Reads, Covered_Bases}}
    mapped: int = 0                  # 实际比对上的记录数/片段数
    total: int = 0                   # 输入总片段数
    elapsed: float = 0.0
    has_positions: bool = False      # 是否含真实比对位点（决定共识段可用性）


class VirusEngine:
    """引擎基类。子类实现 build_index / align。"""
    name = 'base'
    supports_consensus = False

    def __init__(self, exe, threads=8, logger=None, min_mapq=10):
        self.exe = exe
        self.threads = threads
        self.logger = logger
        self.min_mapq = min_mapq

    def log(self, msg, level='info'):
        if self.logger:
            getattr(self.logger, level)(f"[{self.name}] {msg}")

    def build_index(self, ref_fasta, index_dir, threads=None):
        raise NotImplementedError

    def align(self, index_path, sample, out_dir, threads=None):
        raise NotImplementedError


# ══════════════════════════════════════════════════════════
# salmon —— 定量引擎（伪比对定量 + --writeBam 映射位点）
# ══════════════════════════════════════════════════════════
class SalmonEngine(VirusEngine):
    name = 'salmon'
    supports_consensus = False   # 映射 CIGAR 是伪的（无缺口）、无 NM/QUAL——
                                 # 共识/变异的真实位点仍由共识段内部的 minibwa 提供

    def __init__(self, exe, threads=8, logger=None, min_mapq=10,
                 samtools=None, pandepth=None, coverage_tool='pandepth'):
        super().__init__(exe, threads=threads, logger=logger, min_mapq=min_mapq)
        # 覆盖度后端：默认 pandepth（与原 minibwa 路径同一口径：view -F 0x04
        # 建 BAM + pandepth -a 无 -q）。两者齐全才出真实覆盖度/深度与比对 BAM，
        # 缺失时退回「reads×读长」估算（引擎仍可用）。
        self.samtools = samtools
        self.pandepth = pandepth
        self.coverage_tool = (coverage_tool or 'pandepth').lower()

    def build_index(self, ref_fasta, index_dir, threads=None):
        threads = threads or self.threads
        index_dir = Path(index_dir)
        idx_path = index_dir / 'salmon_k31'
        if idx_path.is_dir() and (idx_path / 'info.json').exists():
            self.log(f"复用已有索引 -> {idx_path}")
            return idx_path

        index_dir.mkdir(parents=True, exist_ok=True)
        self.log(f"构建索引 (k=31) -> {idx_path}")
        t0 = time.time()
        cmd = [self.exe, 'index', '-t', str(ref_fasta), '-i', str(idx_path),
               '-k', '31', '-p', str(threads)]
        with open(index_dir / 'salmon_index.log', 'w', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)
        self.log(f"索引完成 {time.time()-t0:.1f}s")
        return idx_path

    def align(self, index_path, sample, out_dir, threads=None):
        threads = threads or self.threads
        out_dir = Path(out_dir)
        sname = sample['name']
        quant_dir = out_dir / 'quant' / sname
        quant_dir.mkdir(parents=True, exist_ok=True)

        # --writeBam：映射记录直接落 BAM（SEQ 为真、CIGAR 伪无缺口、无 QUAL）。
        # 只含 mapped 记录（salmon 只写 per-mapping 记录，unmapped 不落盘）。
        bam_raw = quant_dir / 'mappings.bam'
        cmd = [self.exe, 'quant', '-i', str(index_path), '-p', str(threads),
               '-l', 'A', '-o', str(quant_dir), '--writeBam', str(bam_raw)]
        if sample.get('r2'):
            cmd += ['-1', sample['r1'], '-2', sample['r2']]
        else:
            cmd += ['-r', sample['r1']]

        t0 = time.time()
        logf = out_dir / 'logs' / f'align_{sname}.log'
        logf.parent.mkdir(parents=True, exist_ok=True)
        with open(logf, 'w', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)
        elapsed = time.time() - t0

        res = AlignResult(quant_path=quant_dir / 'quant.sf', elapsed=elapsed,
                          has_positions=True)

        # quant.sf → EM 定量（salmon 的核心口径：多映射 reads 经 EM 分摊）
        qf = res.quant_path
        if qf.exists():
            with open(qf, 'r', encoding='utf-8') as f:
                header = f.readline().rstrip('\n').split('\t')
                ci = {h: i for i, h in enumerate(header)}
                for line in f:
                    p = line.rstrip('\n').split('\t')
                    if len(p) <= ci.get('NumReads', 1):
                        continue
                    acc = p[ci['Name']]
                    n = float(p[ci['NumReads']])
                    if n > 0:
                        res.reads[acc] = n

        # 覆盖度/深度/逐位点深度表：与原 minibwa 路径同一后端（pandepth），
        # 产物命名保持 <样本>_pandepth.* —— kv_plot 的深度表查找
        # （<样本>_pandepth.pandepth.SiteDepth.gz）与管道②b 抽病毒 reads 的
        # BAM 拾取（align/<样本>_pandepth.sorted.bam）都依赖这套名字。
        if not (self.samtools and self.pandepth):
            self.log('samtools/pandepth 不可用：不产出比对 BAM，覆盖度/深度退到'
                     '「reads×读长」估算', level='warning')
            res.total, res.mapped = self._parse_counts(logf, res.reads)
            res.has_positions = False
            try:
                bam_raw.unlink()     # 不会再用；GB 级原始 BAM 不留盘
            except OSError:
                pass
            return res

        try:
            backend = BamCoverageBackend(self.samtools, self.pandepth,
                                         threads=max(1, min(threads, 8)),
                                         logger=self.logger)
            align_dir = out_dir / 'align'
            name = f'{sname}_pandepth'
            sorted_bam = backend.to_bam(bam_raw, align_dir, name=name,
                                        strict_orig=True)
            if self.coverage_tool == 'pandepth':
                refstats = backend.coverage_pandepth(sorted_bam, align_dir,
                                                     name=name)
            else:
                refstats = backend.coverage_samtools(sorted_bam, align_dir,
                                                     name=name)
            mapped_reads = backend.count_mapped_by_ref(sorted_bam)
        finally:
            # 原始未排序映射 BAM 无论成败都不留盘：成功则已转换，
            # 失败则重跑本段会重新产出，残留在盘只会吃掉几十 GB
            try:
                bam_raw.unlink()
            except OSError:
                pass

        for acc, st in refstats.items():
            st['Mapped_Reads'] = mapped_reads.get(acc, 0)

        res.sam_path = sorted_bam
        res.refstats = refstats
        res.mapped = sum(mapped_reads.values())
        res.total = backend.count_records(sorted_bam)
        return res

    def _parse_counts(self, logf, reads):
        """salmon 的比对统计口径：num_processed / num_mapped

        返回 (total, mapped)。日志里解析不到这两个数时退到 reads 总和，
        但记 warning——否则日志会显示成 100% 比对率，误导排查。
        （仅 samtools/pandepth 缺失、无 BAM 可统计时的兜底路径。）
        """
        total = mapped = 0
        try:
            txt = Path(logf).read_text(encoding='utf-8', errors='replace')
            m = re.search(r'(\d+)\s+fragments?\s+from\s+intermediate\s+RAD,\s+(\d+)\s+quantified', txt)
            if m:
                total, mapped = int(m.group(1)), int(m.group(2))
            else:
                m = re.search(r'mapped\s+(\d+)\s*/\s*(\d+)\s+fragments', txt)
                if m:
                    mapped, total = int(m.group(1)), int(m.group(2))
        except Exception as e:  # noqa: BLE001
            self.log(f'salmon 日志解析异常（{e}），比对统计改用 reads 总和',
                     level='warning')
        if total == 0:
            s = int(sum(reads.values()))
            self.log(f'未从 {Path(logf).name} 解析到比对统计，'
                     f'total/mapped 退到 reads 总和 {s}', level='warning')
            total = s or 1
            mapped = s
        return total, mapped


# ══════════════════════════════════════════════════════════
# 覆盖度/深度：只走外部工具，严格照原管线
# ══════════════════════════════════════════════════════════
# 说明：模块内曾有一个自研的 SAM/CIGAR 解析器（parse_sam_coverage），已删除。
# 原管线（virome_analysis_pipeline/batch_virus_depth.py）的覆盖度与深度
# 只有一条来源：pandepth 的 <prefix>.chr.stat.gz（第 5/6 列），
# 全文没有任何 CIGAR 运算。自研实现属于平行口径，即使对拍一致也制造
# 静默分歧风险（尤其 D/N 处理、secondary/supplementary 取舍这类边界）。
# 工具缺失时直接 fail-fast，不降级。


# ══════════════════════════════════════════════════════════
# 外部覆盖度后端：pandepth（原管线口径）
# ══════════════════════════════════════════════════════════
class BamCoverageBackend:
    """
    SAM -> BAM -> sort -> index，然后交给 samtools coverage 或 pandepth 统计。

    ★ pandepth 路径严格照抄原管线（virome_analysis_pipeline/batch_virus_depth.py
      L372-404 pseudo 分支 / L493-503 traditional 分支）：
        samtools view -b -F 0x04   （只去 unmapped，不过滤 MAPQ）
        samtools sort -@ N
        pysam.index(bam)           （本地用 samtools index 等价替代）
        pandepth -a -i bam -o prefix -t N    ← **无 -q**（min MAPQ = 0）
        读 <prefix>.chr.stat.gz，第 5 列 Coverage(%)、第 6 列 MeanDepth

    口径要点：
      * 原管线不传 -q，所以 MAPQ 0 起算；本模块的 min_mapq 只作用于
        builtin / samtools 后端，pandepth 后端照原管线为 0。
      * pandepth -x 默认 1796，排除 0x4|0x100|0x200|0x800。
      * -a 语义是 "output all the site depth"，额外产逐位点文件，
        不改变统计口径。实测 truth30 / q06 均 5.5s。

    三条口径已在 truth30/truth3/q06 上对拍一致（差异仅小数位）：
      samtools coverage / pandepth / 内置 parse_sam_coverage
    """

    def __init__(self, samtools_exe, pandepth_exe=None, threads=4, logger=None):
        self.samtools = samtools_exe
        self.pandepth = pandepth_exe
        self.threads = threads
        self.logger = logger

    def log(self, msg, level='info'):
        if self.logger:
            getattr(self.logger, level)(f"[bam] {msg}")

    def to_bam(self, sam_path, out_dir, name='coverage', min_mapq=10,
               strict_orig=True):
        """SAM -> 排序后的 BAM + 索引。返回 bam_path

        strict_orig=True（默认）照原管线：samtools view -b -F 0x04
          只剔除 unmapped，不做 MAPQ 过滤。
        strict_orig=False 启用 min_mapq 过滤。
        """
        sam_path = Path(sam_path)
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        bam = out_dir / f'{name}.bam'
        logf = out_dir / f'{name}_samtools.log'

        if strict_orig:
            cmd = [self.samtools, 'view', '-b', '-F', '0x04',
                   '-o', str(bam), str(sam_path)]
        else:
            cmd = [self.samtools, 'view', '-b', '-q', str(min_mapq),
                   '-o', str(bam), str(sam_path)]
        with open(logf, 'w', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)

        sorted_bam = out_dir / f'{name}.sorted.bam'
        cmd = [self.samtools, 'sort', '-@', str(self.threads), '-o', str(sorted_bam), str(bam)]
        with open(logf, 'a', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)

        cmd = [self.samtools, 'index', str(sorted_bam)]
        with open(logf, 'a', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)

        try:
            bam.unlink()
        except OSError:
            pass
        return sorted_bam

    def count_mapped_by_ref(self, sorted_bam):
        """每个参考的比对记录数（samtools idxstats）

        pandepth 的 .chr.stat.gz 只有 Coverage(%)/MeanDepth，没有读数；
        原管线在 traditional 分支用 samtools view -c 拿总记录数，
        这里按参考细分，同一工具、同一口径。

        实现：用 samtools idxstats 一次调用拿全部参考的映射数（第 3 列）。
        实测与逐参考 `samtools view -F 0x4 -F 0x100 -c <bam> <ref>`
        数值完全一致（本平台病毒库 8464 条参考对拍，含 0 值与非 0 值）。
        旧实现对 8464 条参考逐条启动 samtools（一次进程几十毫秒），
        单样本要多花几分钟；idxstats 是毫秒级。
        """
        r = subprocess.run([self.samtools, 'idxstats', str(sorted_bam)],
                           capture_output=True, text=True,
                           encoding='utf-8', errors='replace')
        counts = {}
        for line in r.stdout.splitlines():
            p = line.split('\t')
            if len(p) >= 4 and p[0] != '*':
                counts[p[0]] = int(p[2])
        return counts

    def count_records(self, sorted_bam):
        """比对上的记录总数（去 unmapped / secondary）"""
        r = subprocess.run(
            [self.samtools, 'view', '-F', '0x4', '-F', '0x100', '-c',
             str(sorted_bam)],
            capture_output=True, text=True,
            encoding='utf-8', errors='replace')
        return int((r.stdout or '0').strip() or 0)

    def coverage_samtools(self, sorted_bam, out_dir, name='coverage'):
        """samtools coverage -> refstats 格式"""
        out_dir = Path(out_dir)
        raw = out_dir / f'{name}.samtools_cov.tsv'
        cmd = [self.samtools, 'coverage', str(sorted_bam)]
        with open(raw, 'w', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True)

        refstats = {}
        with open(raw, 'r', encoding='utf-8') as f:
            header = f.readline().rstrip('\n').split('\t')
            ci = {h.lstrip('#'): i for i, h in enumerate(header)}
            for line in f:
                p = line.rstrip('\n').split('\t')
                if len(p) < len(header):
                    continue
                rname = p[ci['rname']]
                refstats[rname] = {
                    'Length': _to_int(p[ci['endpos']]) - _to_int(p[ci['startpos']]) + 1,
                    'Mapped_Reads': _to_int(p[ci['numreads']]),
                    'Covered_Bases': _to_int(p[ci['covbases']]),
                    'Coverage(%)': _to_float(p[ci['coverage']]),
                    'MeanDepth': _to_float(p[ci['meandepth']]),
                }
        return refstats

    def coverage_pandepth(self, sorted_bam, out_dir, name='coverage',
                          min_mapq=None):
        """pandepth -> refstats 格式（严格照原管线，无 -q）

        min_mapq=None 时不传 -q（原管线行为，MAPQ 0 起算）。

        pandepth 的 hts-3.dll 还有传递依赖（libcrypto/libcurl 等），
        这些 DLL 在 samtools\bin 里，所以调用时必须把该目录注入子进程 PATH。
        """
        out_dir = Path(out_dir)
        prefix = out_dir / f'{name}.pandepth'
        logf = out_dir / f'{name}_pandepth.log'
        cmd = [self.pandepth, '-a', '-i', str(sorted_bam), '-o', str(prefix),
               '-t', str(self.threads)]
        if min_mapq is not None:
            cmd += ['-q', str(min_mapq)]
        env = dict(os.environ)
        st_bin = str(Path(self.samtools).resolve().parent)
        pd_bin = str(Path(self.pandepth).resolve().parent)
        env['PATH'] = os.pathsep.join(
            [pd_bin, st_bin] + [env.get('PATH', '')])
        with open(logf, 'w', encoding='utf-8') as fl:
            subprocess.run(cmd, stdout=fl, stderr=subprocess.STDOUT, check=True,
                           env=env)

        stat_gz = Path(str(prefix) + '.chr.stat.gz')
        if not stat_gz.exists():
            raise RuntimeError(f"pandepth 未产生 {stat_gz}")

        # 原管线解析：跳过 # 行，取第 5 列 Cov / 第 6 列 Dep
        refstats = {}
        with gzip.open(stat_gz, 'rt', encoding='utf-8') as f:
            for line in f:
                if line.startswith('#'):
                    continue
                p = line.rstrip('\n').split('\t')
                if len(p) >= 6:
                    refstats[p[0].strip()] = {
                        'Length': _to_int(p[1]),
                        'Covered_Bases': _to_int(p[2]),
                        'Coverage(%)': _to_float(p[4]),
                        'MeanDepth': _to_float(p[5]),
                    }
        return refstats


def _to_int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def make_engine(name, tools, threads=8, logger=None, min_mapq=10,
                coverage_tool='pandepth'):
    """
    按名字构造引擎。tools 是 ToolRegistry。

    定量引擎只有 salmon：quant.sf 出 EM 定量，--writeBam 出映射位点，
    排序 BAM 交给 BamCoverageBackend（pandepth，默认）出覆盖度/深度。
    真比对只在共识段内部直接调 minibwa（kv_consensus），不经本工厂；
    这里再传 minibwa 直接报错，避免两条比对链路被混用。

    coverage_tool: pandepth | samtools（覆盖度/深度统计后端，默认 pandepth，
      严格照原管线：samtools view -F 0x04 建 BAM + pandepth -a，无 -q）。
      samtools 仅供快速对拍；两条路径共用同一份 BAM。
    """
    name = (name or '').lower()
    if name != 'salmon':
        raise ValueError(
            f"不支持的引擎: {name}（定量引擎仅 salmon；共识段内部固定 minibwa，"
            "不经本工厂）")
    tools.require('salmon')
    tool = (coverage_tool or 'pandepth').lower()
    if tool not in ('pandepth', 'samtools'):
        raise ValueError(f"不支持的覆盖度后端: {tool}（可选 pandepth / samtools）")
    samtools = tools.paths.get('samtools')
    pandepth = tools.paths.get('pandepth') if tool == 'pandepth' else None
    if not samtools or (tool == 'pandepth' and not pandepth):
        # 覆盖度后端缺件不阻断定量：SalmonEngine 退回估算口径并记 warning
        if logger:
            logger.warning(
                "覆盖度后端缺件（samtools=%s pandepth=%s），定量照跑，"
                "覆盖度/深度退到估算且无比对 BAM",
                '有' if samtools else '缺', '有' if pandepth else '缺')
    return SalmonEngine(tools.paths['salmon'], threads=threads, logger=logger,
                        min_mapq=min_mapq, samtools=samtools,
                        pandepth=pandepth, coverage_tool=tool)
