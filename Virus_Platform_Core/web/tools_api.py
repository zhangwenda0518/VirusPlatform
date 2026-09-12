# -*- coding: utf-8 -*-
"""工具箱 HTTP 边界：运行目录、任务提交、结果读取（自 app.py 拆出）。

Blueprint 名 tools，路由 /tools 与 /api/tool/*。
任务工厂本体在 Virus_Platform_Core/web/tool_jobs.py，链式在 Virus_Platform_Core/web/chains.py。
"""
import json
import os
import re
import time
import uuid

from flask import abort, jsonify, render_template, request, send_file

from Virus_Platform_Core.config import DIRS, PLATFORM_ROOT, db_path
from Virus_Platform_Core.utils import (check_path, fmt_size, safe_open)
from Virus_Platform_Core.web.state import cfg, tool_runs_root as _tool_runs_root
from flask import Blueprint

from Virus_Platform_Core.web.tool_jobs import (
    _tool_job_convert,
    _tool_job_fastp,
    _tool_job_hostremoval,
    _tool_job_hostpredict,
    _tool_job_orf,
    _tool_job_orfa,
    _tool_job_genoplot,
    _tool_job_primer,
    _tool_job_identify,
    _tool_job_assemble,
    _tool_job_contigs,
    _tool_job_structcmp,
    _tool_job_verify,
    _tool_job_consensus,
    _tool_job_kvsuite,
    _tool_job_quicktree,
    _tool_job_align,
    _tool_job_sdt,
    _tool_job_identity,
)
from Virus_Platform_Core.web.chains import (
    _tool_job_virchain,
    _tool_job_kvchain,
)
from Virus_Platform_Core.web.tasks import tm

bp = Blueprint('tools', __name__)


TOOL_REGISTRY = {
    'convert':  {'title': '格式转换', 'title_en': 'Format convert',
                 'need_db': False, 'job': _tool_job_convert},
    'fastp':    {'title': '质控预处理', 'title_en': 'QC preprocess',
                 'need_db': False, 'job': _tool_job_fastp},
    'hostremoval': {'title': '宿主去除与序列提取', 'title_en': 'Host removal',
                    'need_db': False, 'job': _tool_job_hostremoval},
    'hostpredict': {'title': '宿主预测', 'title_en': 'Host prediction',
                    'need_db': False, 'job': _tool_job_hostpredict},
    'orf':         {'title': 'ORF 预测', 'title_en': 'ORF predict',
                    'need_db': False, 'job': _tool_job_orf},
    'orfa':        {'title': '功能注释', 'title_en': 'ORF annotate',
                    'need_db': False, 'job': _tool_job_orfa},
    'genoplot':    {'title': '基因组图谱', 'title_en': 'Genome plots',
                    'need_db': False, 'job': _tool_job_genoplot},
    'primer':      {'title': '引物设计', 'title_en': 'Primer design',
                    'need_db': False, 'job': _tool_job_primer},
    'identify': {'title': '病毒鉴定', 'title_en': 'Virus identify',
                 'need_db': True, 'job': _tool_job_identify},
    'assemble': {'title': '病毒组装', 'title_en': 'Virus assembly',
                 'need_db': False, 'job': _tool_job_assemble},
    'contigs':  {'title': 'contig分类', 'title_en': 'Contig classify',
                 'need_db': True, 'job': _tool_job_contigs},
    'sdt':      {'title': 'SDT 精确分析', 'title_en': 'SDT exact',
                 'need_db': False, 'job': _tool_job_sdt},
    'identity': {'title': 'NT+AA 同一性表', 'title_en': 'NT+AA identity',
                 'need_db': False, 'job': _tool_job_identity},
    'structcmp': {'title': '结构比较', 'title_en': 'Structure compare',
                  'need_db': False, 'job': _tool_job_structcmp},
    'verify':   {'title': '候选序列验证', 'title_en': 'Candidate verify',
                 'need_db': False, 'job': _tool_job_verify},
    'consensus': {'title': '共识序列与变异', 'title_en': 'Consensus & variants',
                  'need_db': False, 'job': _tool_job_consensus},
    'kvsuite':  {'title': '已知病毒识别与定量', 'title_en': 'Known virus suite',
                 'need_db': False, 'job': _tool_job_kvsuite},
    'align':    {'title': '序列比对', 'title_en': 'Alignment',
                 'need_db': False, 'job': _tool_job_align},
    'quicktree': {'title': '快速建树', 'title_en': 'Quick tree',
                  'need_db': False, 'job': _tool_job_quicktree},
    'virchain': {'title': '病毒识别分类·一键', 'title_en': 'Virus chain',
                 'need_db': True, 'job': _tool_job_virchain},
    'kvchain':  {'title': '病毒定量与共识·一键', 'title_en': 'KV chain',
                 'need_db': False, 'job': _tool_job_kvchain},
}


LIGHT_TOOLS = {'convert', 'genoplot', 'primer'}


# 工具②/④的病毒库内置键名。RVDB（databases/virus/rvdb）已于本会话移除，
# 保留键名只会让 /api/dbs 的“可用内置库”提示与“库未就绪”报错指向不存在的目录。
VIRUS_DB_PRESETS = {'virus': ('virus', 'plant'),
                    'refvirus': ('virus', 'ref'),
                    'k2viral': None}


@bp.route('/tools')
def page_tools():
    return render_template('tools.html')


@bp.route('/tool_runs/<run>/<path:filename>')
def page_tool_run_file(run, filename):
    """工具运行目录内文件的下载/预览（严格限制在该运行目录内）。"""
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', run) or '..' in filename:
        abort(400, '无效的运行名')
    p = check_path(os.path.join(_tool_runs_root(), run, filename),
                   must_exist=True, in_platform=True)
    resp = send_file(p)
    # .svg 必须在浏览器内联渲染：send_file 在此环境把 .svg 推断成了
    # 非标准的 image/svg（浏览器会拒绝渲染 → broken image），改回标准 MIME。
    if str(filename).lower().endswith('.svg'):
        resp.mimetype = 'image/svg+xml'
    if request.args.get('dl'):          # 显式 ?dl=1 才强制下载；
        import urllib.parse as _up      # 不带时内联渲染（report iframe 需要）
        resp.headers['Content-Disposition'] = (
            "attachment; filename*=UTF-8''"
            + _up.quote(os.path.basename(filename)))
    return resp


# 最近运行列表缓存：{signature: (ts, payload)}
# 本接口对最近 30 个运行目录做整棵 os.walk + 逐个 getsize，装了大组装/MSA
# 的运行目录动辄数千文件；而工具页与「结果恢复」都会反复拉它。签名取
# (运行名, 目录 mtime) 列表 —— 新增/删除运行或顶层变动立刻失效，嵌套变动
# 由 _RUNS_TTL 兜底。
_RUNS_CACHE = {}
_RUNS_TTL = 4.0


def _runs_signature(root):
    try:
        names = [n for n in os.listdir(root)
                 if not n.startswith('_')
                 and os.path.isdir(os.path.join(root, n))]
    except OSError:
        return None, []
    sig = []
    for n in names:
        try:
            sig.append((n, os.path.getmtime(os.path.join(root, n))))
        except OSError:
            sig.append((n, 0))
    sig.sort(key=lambda x: x[1], reverse=True)
    return tuple(sig), [n for n, _ in sig]


@bp.route('/api/tool/runs')
def api_tool_runs():
    """最近的工具运行列表（按运行目录修改时间倒序，30 条）。

    按目录名排序会让字母序靠前的前缀（contigs/genoplot…）挤掉真正
    最新的运行，这里以 mtime 为准。

    结果按「(运行名, 目录 mtime) 签名 + 短 TTL」缓存：整棵 os.walk 是本
    接口的主要开销，而它会被工具页反复轮询。
    """
    import time as _time
    root = _tool_runs_root()
    sig, names = _runs_signature(root)
    if sig is None:
        return jsonify([])
    hit = _RUNS_CACHE.get(sig[0][0] if sig else '')
    now = _time.time()
    if hit and hit[0] == sig and now - hit[1] < _RUNS_TTL:
        return jsonify(hit[2])
    out = []
    for name in names[:30]:
        d = check_path(os.path.join(root, name), must_exist=False,
                       in_platform=True)
        if not os.path.isdir(d):
            continue
        files = []
        for cur, _sub, fns in os.walk(d):
            rel = os.path.relpath(cur, d)
            for fn in fns:
                p = os.path.join(cur, fn)
                try:
                    size = os.path.getsize(p)
                except OSError:
                    # MMseqs2 临时库等系统级特殊文件 stat 不到（WinError
                    # 1920），跳过大小即可，不让整个列表接口 500
                    continue
                files.append({
                    'path': fn if rel == '.' else os.path.join(rel, fn),
                    'size': fmt_size(size)})
        out.append({'name': name, 'out_dir': d, 'files': files[:40]})
    _RUNS_CACHE.clear()                     # 只保留最新签名一份，防内存增长
    _RUNS_CACHE[sig[0][0] if sig else ''] = (sig, now, out)
    return jsonify(out)


@bp.route('/api/tool/runs/<run>/delete', methods=['POST'])
def api_tool_run_delete(run):
    """删除一个工具运行目录（模块历史区的 🗑；运行名校验 + 平台内限定）。"""
    if not re.fullmatch(r'[A-Za-z0-9_\-]+', run):
        abort(400, '无效的运行名')
    p = check_path(os.path.join(_tool_runs_root(), run),
                   must_exist=True, in_platform=True)
    import shutil as _sh
    _sh.rmtree(p, ignore_errors=True)
    _RUNS_CACHE.clear()                 # 删了运行，最近运行列表立刻失效
    return jsonify({'ok': True, 'run': run})


@bp.route('/api/tool/open', methods=['POST'])
def api_tool_open():
    """在资源管理器中打开某次工具运行的目录。"""
    body = request.get_json(force=True) or {}
    name = body.get('name') or ''
    if not name or '/' in name or '\\' in name or '..' in name:
        abort(400, '无效的运行名')
    d = check_path(os.path.join(_tool_runs_root(), name), must_exist=True,
                   in_platform=True)
    os.startfile(d)
    return jsonify({'ok': True})


@bp.route('/api/tool/genoplot_preview', methods=['POST'])
def api_tool_genoplot_preview():
    """基因组图谱交互预览：接收输入 + 绘图参数，出图到临时目录，返回 SVG 内容。

    不写 tool_runs/、不建运行目录（交互模式下仅预览不落盘）。
    参数：fasta / ann（.gb/.gff）+ gb_opts（dict，透传 gbdraw CLI）。
    返回：{ok, svg, mode}（svg 为 circular SVG 文本；失败抛 400/500）。
    """
    import tempfile
    body = request.get_json(force=True) or {}
    fasta = (body.get('fasta') or '').strip()
    ann = (body.get('ann') or '').strip()
    gb_opts = body.get('gb_opts') or {}
    if not fasta and not ann:
        abort(400, '请提供 FASTA 或 GenBank 输入')
    def _pabs(v):
        v = v.strip() if v else ''
        return check_path(v if os.path.isabs(v)
                          else os.path.join(PLATFORM_ROOT, v),
                          must_exist=True)
    fasta_abs = _pabs(fasta) if fasta else None
    ann_abs = _pabs(ann) if ann else None
    if ann_abs and str(ann_abs).lower().endswith(
            ('.gb', '.gbk', '.gbff', '.genbank')):
        fasta_abs = None
    # 过滤 opts（去空/False/None）。预览只出 SVG，排除仅保存时生效的格式/多记录。
    _PREVIEW_SKIP = {'format', 'multi_record_canvas'}
    opts = {str(k): v for k, v in gb_opts.items()
            if v not in (None, '', False) and k not in _PREVIEW_SKIP}
    tmp = tempfile.mkdtemp(prefix='vp_genoplot_preview_')
    try:
        # 用本次请求专属的 ascii 临时目录（gbdraw 需 ascii 路径）。
        # 原先用固定路径 %TEMP%\vp_geno_preview\preview.svg 且从不清理：
        # 两个并发预览会互相覆盖，先返回的请求可能拿到后者的图。
        import shutil as _sh
        tmp_ascii = os.path.join(tmp, 'geno')
        os.makedirs(tmp_ascii, exist_ok=True)
        from Virus_Platform_Core.gbdraw_plot import _run_gbdraw
        fasta_p, gff_p, gbk_p = None, None, None
        if ann_abs and str(ann_abs).lower().endswith(
                ('.gb', '.gbk', '.gbff', '.genbank')):
            gbk_p = ann_abs
        else:
            fasta_p = fasta_abs
            # 可选 GFF：若 ann 是 .gff 且 fasta 也给了 → 配对
            if ann_abs and str(ann_abs).lower().endswith(('.gff', '.gff3')):
                gff_p = ann_abs
        made = _run_gbdraw(fasta=fasta_p, gff=gff_p, gbk=gbk_p,
                           out_prefix=os.path.join(tmp_ascii, 'preview'),
                           mode=body.get('mode') or 'circular', opts=opts)
        if not made:
            abort(400, 'gbdraw 未产出预览图')
        svg_path = made[0]
        with safe_open(svg_path) as f:
            svg = f.read()
        return jsonify({'ok': True, 'mode': 'circular', 'svg': svg})
    finally:
        _sh.rmtree(tmp, ignore_errors=True)


@bp.route('/api/tool/run', methods=['POST'])
def api_tool_run():
    """运行独立工具。body: {tool, threads, params{...}}；返回 {task, run}。"""
    from types import SimpleNamespace
    body = request.get_json(force=True) or {}
    tool = body.get('tool')
    threads = body.get('threads') or None
    p = body.get('params') or {}

    spec = TOOL_REGISTRY.get(tool)
    if not spec:
        abort(400, '未知工具')

    def _input_abs(v):
        """输入数据文件：相对路径按平台根解析；绝对路径允许电脑任意位置
        （只读）。输出产物仍限制在平台目录内。"""
        return check_path(v if os.path.isabs(v)
                          else os.path.join(PLATFORM_ROOT, v),
                          must_exist=True)

    def _req(key, what):
        v = (p.get(key) or '').strip()
        if not v:
            abort(400, f'请选择{what}')
        return _input_abs(v)

    def _opt(key):
        v = (p.get(key) or '').strip()
        return _input_abs(v) if v else None

    db_virus = _resolve_virus_db(p.get('db_virus'))
    if spec['need_db']:
        from Virus_Platform_Core.kunpeng import db_ready
        if not db_ready(db_virus):
            abort(400, f'所选病毒库未就绪: {db_virus}'
                       '（先到「数据库构建」页构建，或换选其他病毒库）')

    ts = time.strftime('%Y%m%d_%H%M%S')
    # 秒级时间戳会撞车：同一秒两次同工具运行（双击/多标签页）会复用同一
    # 目录并互相覆盖产物。追加 6 位随机后缀。
    run_dir = check_path(os.path.join(_tool_runs_root(),
                                      f'{tool}_{ts}_{uuid.uuid4().hex[:6]}'),
                         must_exist=False, in_platform=True)
    os.makedirs(run_dir, exist_ok=True)
    # 数字参数钳制：负数/异常大值不直接传给外部工具
    if threads is not None:
        threads = max(1, min(int(threads), (os.cpu_count() or 4) * 4))

    ctx = SimpleNamespace(p=p, run_dir=run_dir, threads=threads,
                          db_virus=db_virus, req=_req, opt=_opt)
    try:
        job = spec['job'](ctx)
    except Exception:
        # 工厂期 abort（缺必填参数）不该留下空运行目录
        import shutil as _sh
        _sh.rmtree(run_dir, ignore_errors=True)
        raise

    name = cfg.tr(f"工具·{spec['title']} {ts}", f"Tool·{spec['title_en']} {ts}")
    run_name = os.path.basename(run_dir)

    def _job_with_run(log, prog, cancel):
        """包一层：结果 dict 注入 run 名与输出目录，供结果面板列出产物、
        明示「结果输出在哪」。"""
        res = job(log, prog, cancel)
        if isinstance(res, dict):
            res.setdefault('run', run_name)
            res['out_dir'] = str(run_dir)
        return res

    tid = tm.start(name, _job_with_run,
                   log_file=os.path.join(run_dir, 'run.log'),
                   weight=('light' if tool in LIGHT_TOOLS else 'heavy'),
                   out_dir=str(run_dir))
    return jsonify({'task': tid, 'run': run_name, 'out_dir': str(run_dir)})


@bp.route('/api/tool/chain_result')
def api_tool_chain_result():
    """一键流程汇总目录：返回 _chain.json 内容 + 链接清单。

    chain = virchain / kvchain；run 为汇总目录名（留空取最新一次）。
    """
    chain = (request.args.get('chain') or '').strip()
    if chain not in ('virchain', 'kvchain'):
        abort(400, '无效的链式运行类型')
    run = (request.args.get('run') or '').strip()
    root = _tool_runs_root()
    if run:
        if not re.fullmatch(r'[A-Za-z0-9_\-]+', run):
            abort(400, '无效的运行名')
        if not run.startswith(chain + '_'):
            abort(400, '运行名与链式类型不匹配')
    else:
        cands = []
        if os.path.isdir(root):
            for d in os.listdir(root):
                if d.startswith(chain + '_') and os.path.isfile(
                        os.path.join(root, d, '_chain.json')):
                    cands.append(d)
        if not cands:
            return jsonify({'run': None, 'out_dir': None, 'meta': None,
                            'entries': []})
        run = sorted(cands)[-1]
    cdir = check_path(os.path.join(root, run), must_exist=False,
                      in_platform=True)
    meta = None
    cj = os.path.join(cdir, '_chain.json')
    if os.path.isfile(cj):
        try:
            with safe_open(cj) as f:
                meta = json.load(f)
        except (OSError, ValueError):
            meta = None
    entries = []
    if os.path.isdir(cdir):
        for name in sorted(os.listdir(cdir)):
            if name == '_chain.json':
                continue
            full = os.path.join(cdir, name)
            entries.append({'name': name,
                            'is_dir': os.path.isdir(full),
                            'is_link': os.path.islink(full),
                            'size': (None if os.path.isdir(full)
                                     else fmt_size(os.path.getsize(full))
                                     if os.path.exists(full) else None)})
    return jsonify({'run': run, 'out_dir': cdir, 'meta': meta,
                    'entries': entries})


def _resolve_virus_db(v=None):
    """工具②/④的病毒库选择：内置键名、平台相对路径或本机绝对路径。

    缺省用平台主病毒库（cfg.databases['virus']）。返回库目录绝对路径；
    键名不识别且路径不存在时 abort(400)。
    """
    if not v:
        return cfg.databases['virus']
    v = str(v).strip()
    if v in VIRUS_DB_PRESETS:
        mapping = VIRUS_DB_PRESETS[v]
        if mapping:
            return db_path(*mapping)
        return os.path.join(DIRS['databases'], 'k2viral_db')
    if os.path.isabs(v):
        d = v
    else:
        d = os.path.join(PLATFORM_ROOT, v)
        # 兼容旧前端：'databases/<rel>' 的语义是**相对数据库根**，不是相对
        # 平台根。/api/dbs 早期就是这么输出的，而「数据库包与程序目录分离」
        # 的分发版下两者不同（DIRS['databases'] = <数据库包>\databases），
        # 按平台根解析会指向不存在的 <程序目录>\databases\...。
        rel = v.replace('\\', '/')
        if rel.startswith('databases/'):
            alt = os.path.join(DIRS['databases'], rel[len('databases/'):])
            if os.path.exists(alt):
                d = alt
    try:
        return check_path(d, must_exist=True)
    except (ValueError, FileNotFoundError):
        abort(400, f'病毒库不存在: {v}（可用内置库: '
                   f'{", ".join(VIRUS_DB_PRESETS)} 或填库目录路径）')
