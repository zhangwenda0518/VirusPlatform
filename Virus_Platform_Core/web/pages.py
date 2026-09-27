# -*- coding: utf-8 -*-
"""页面路由与全局上下文（自 app.py 拆出）。

含：NAV_GROUPS 导航单一数据源、模板上下文处理器、统一错误处理、
19 个页面端点与报告静态文件服务。"""
import os
import sys
import time

from werkzeug.exceptions import HTTPException

from flask import (Blueprint, current_app, jsonify, render_template,
                   request, send_file)

from Virus_Platform_Core.config import DIRS, PLATFORM_ROOT
from Virus_Platform_Core.utils import (check_path, safe_open)
from Virus_Platform_Core.web.common import _safe_sample
from Virus_Platform_Core.web.state import (  # noqa: F401
    _WWW, cfg, tool_runs_root as _tool_runs_root)

bp = Blueprint('pages', __name__)


@bp.app_context_processor
def _inject_lang():
    """所有模板可用 {{ lang }}（服务端配置语言，前端 i18n.js 据此初始化）。"""
    return {'lang': cfg.lang}


def _asset_version():
    """静态资源版本号（static/ 下全部 .js/.css 的 mtime 最大值），模板引用带
    ?v= 破缓存。

    每次请求都重算（一次 listdir + 每文件一次 getmtime，微秒级）：若缓存，
    运行中改了前端资源后浏览器仍拿旧 ?v= 而命中自身缓存，必须重启服务才能生效。

    为什么是**全目录扫描**而不是列举文件名：此前写死
    ('app.js','i18n.js','app.css','examples.js')，于是 app-batch.js /
    app-browse.js / app-compare.js / app-jobs.js / app-runhistory.js /
    app-storage.js / app-vexplorer.js 这 7 个按页拆分的脚本全部漏网 ——
    改了它们，?v= 不变，浏览器继续用旧缓存，只能靠硬刷新才能看到新代码。
    按目录扫则新增脚本自动纳入，不会再漏。
    """
    mt = 0.0
    try:
        names = os.listdir(os.path.join(_WWW, 'static'))
    except OSError:
        return '1'
    for _f in names:
        if not _f.endswith(('.js', '.css')):
            continue
        try:
            mt = max(mt, os.path.getmtime(os.path.join(_WWW, 'static', _f)))
        except OSError:
            pass
    return str(int(mt)) if mt else '1'


@bp.app_context_processor
def _inject_asset_v():
    return {'asset_v': _asset_version()}


NAV_GROUPS = [
    {'id': 'resource', 'label': '数据资源', 'path': '数据资源', 'items': [
        {'href': '/meta', 'title': '公共数据检索', 'desc': '检索公共样本 / 元数据'},
        # 病毒浏览器（/explorer）已于 2026-09-27 彻底归档
        # （archive/_retire_20260927/explorer/），路由与页面均已下线。
        {'href': '/virome', 'title': 'Open-Virome', 'desc': '公共病毒组浏览 / 导出'},
        {'href': '/build', 'title': '数据库构建', 'desc': 'Taxonomy / 宿主库 / 病毒库'},
    ]},
    {'id': 'sample', 'label': '样本处理', 'path': '样本处理', 'items': [
        # 2026-09-20：一键前处理（prepchain）置顶 —— 与定量/识别两组的 ⚡ 卡
        # 同构的文件级子链：转换 → 质控 → 转换(FASTA) → 宿主去除。
        {'id': 't-prepchain', 'title': '⚡ 一键前处理',
         'desc': 'SRA / FASTQ 自适应：转换 → 质控 → 转换(FASTA) → 宿主去除；'
                 '宿主库未就绪自动跳过宿主去除，kept reads 可直喂 ②→③→④ 一键'},
        {'href': '/download', 'title': '公共数据下载', 'desc': 'Run / URL / SRA → FASTQ，衔接样品与模块'},
        {'href': '/samples', 'title': '样品创建 / 批量导入', 'desc': '样品名 + R1/R2 / TSV 批量'},
        {'id': 't-convert', 'title': '格式转换', 'desc': 'sra2fastq / sra2fasta / fastq2fasta'},
        {'id': 't-fastp', 'title': '序列质控', 'desc': 'fastp 去接头 / 过滤 / 去重'},
        {'href': '/hostremoval', 'title': '宿主去除与序列提取', 'desc': 'kunpeng 宿主库分类'},
    ]},
    {'id': 'kvsuite', 'label': '病毒定量与共识', 'path': '病毒定量与共识', 'items': [
        {'id': 't-kvchain', 'title': '⚡ 一键分析（全流程）',
         'desc': '鉴定 → 过滤 → 共识 → 深度绘图 → 变异注释，一次跑完，产物收拢到汇总目录'},
        {'id': 't-kvsuite', 'title': '已知病毒识别与定量',
         'desc': 'minibwa 比对病毒库 → 鉴定/定量 + 过滤（默认两段；共识/绘图/变异归下游模块）'},
        {'id': 't-consensus', 'title': '共识序列分析',
         'desc': '比对到参考 → 共识序列构建（minibwa + viral_consensus）'},
        {'id': 't-variant', 'title': '病毒变异分析',
         'desc': 'BAM / VCF 直入 → bcftools caller（可选）→ SnpEff 注释 → 8 张变异图 + SNPGenie'},
    ]},
    {'id': 'virus', 'label': '病毒识别和分类分析', 'path': '病毒识别和分类分析', 'items': [
        {'id': 't-virchain', 'title': '⚡ 一键分析（②→③→④）',
         'desc': '提取序列组装 → 组装结果再鉴定 → 候选序列验证，可选先跑①提取病毒序列'},
        {'id': 't-identify', 'title': '病毒识别分类与提取', 'desc': 'FASTQ / FASTA / 去宿主 → 分类 + 病毒序列提取'},
        {'id': 't-assemble', 'title': '提取序列组装', 'desc': 'SPAdes rnaviral / contigs 过滤'},
        {'id': 't-contigs', 'title': '组装结果再鉴定', 'desc': 'contig 二次分类 + 谱系注释'},
        {'id': 't-verify', 'title': '候选序列验证', 'desc': '宿主筛选 → 长度分流 → blastx/CDD 过滤 + 类病毒 blastn'},
    ]},
    {'id': 'annotate', 'label': '病毒注释分析', 'path': '病毒注释分析', 'items': [
        # 2026-09-21：注释三连（annochain）置顶 —— 与定量/识别/样本三组的 ⚡ 卡
        # 同构的文件级子链：ORF 预测 → 功能注释 → 基因组图谱，跑完即可在
        # 「数据提交」页关联生成 featuretable。
        {'id': 't-annochain', 'title': '⚡ 注释三连（ORF→功能→图谱）',
         'desc': '输入 FASTA：ORF 预测 → 功能注释 → 基因组图谱，一键跑完；'
                 '注释产物可在「数据提交」页一键关联、直接生成 featuretable'},
        {'href': '/orf', 'title': 'ORF 预测',
         'desc': 'pyrodigal / pyrodigal-rv 基因预测（独立模块）'},
        {'href': '/annotation', 'title': '功能注释',
         'desc': 'DIAMOND / MMseqs2 / blastp 对照 RefSeq 病毒蛋白库 + 类别投票 + ICTV 映射（独立模块）'},
        {'id': 't-cdd', 'title': '保守域与功能元件注释（CDD）',
         'desc': 'NCBI CDD 保守域搜索（6-frame 翻译取最长 ORF ≥50aa）：结构域位置 / 边界，服务于基因组图谱与功能注释'},
        {'id': 't-hom', 'title': '同源比对（BLASTN · BLASTX）',
         'desc': 'NCBI nt / nr 同源比对（限病毒）：为 GenBank 提交注释提供依据'},
        {'href': '/genome', 'title': '基因组图谱',
         'desc': 'gbdraw / DFV 圈图 + 线图（独立模块）'},
    ]},
    # 2026-09-18：引物设计 / dsRNA 设计从「病毒注释分析」拆出，独立成组。
    # 判定口径（用户提出后核过一遍）：注释组回答的是「这条序列是什么」——
    # ORF / 数据库比对 / 保守域 / 图谱，产物都是**对序列的描述**；
    # 而引物设计回答「怎么把它检出来」（产物是引物对，服务 PCR/qPCR 检测），
    # dsRNA 设计回答「怎么把它防住」（产物是 RNAi 分子，服务防治），
    # 两者产物都是**可下单的实验材料**，且必须真做湿实验才能闭环，
    # 与注释不是同一条业务线 —— 故并列成组，不再挂在注释组下。
    {'id': 'detect', 'label': '检测与防治', 'path': '检测与防治', 'items': [
        {'href': '/primer', 'title': '引物设计',
         'desc': 'primer3 全长分窗 / 保守区设计（独立模块）；面向 PCR / qPCR 检测'},
        {'id': 't-dsrna', 'title': 'dsRNA 设计',
         'desc': '全链路：dsRNAmax 确定性选窗（maximin 多候选）→ dsRIP 效价 → '
                 '面板脱靶扫描（致死基因加权 + 0 错配一票否决）→ T7 引物（限定最优窗）'
                 '→ 成品扩增子 QC（脱靶面板 FASTA 放入 databases/dsrna/panel/ 即启用）'},
        # 2026-09-18：PAmiRDB（12.pamirdb）7 文件移植 → Virus_Platform_Core/mirna_target/。
        # 归入本组的口径与 dsRNA 相同：miRNA 介导的宿主抗病毒沉默是「天然防治线索」，
        # 产物回答「宿主哪些 miRNA 能靶向这条病毒基因组、位点在哪」，不是序列描述。
        {'id': 't-mirna', 'title': '🧬 miRNA 靶标预测（PAmiRDB）',
         'desc': '输入 miRNA × 病毒序列 → Smith-Waterman 比对 + psRNATarget/RNAhybrid '
                 '复刻引擎共识投票（完整模式含 RNA22/TAPIR/psRobot）→ 结合位点 / 彩色比对 / '
                 '双链 SVG / 二级结构弧图；纯 Python 无外部依赖，线上参照 pamirdb'},
    ]},
    # 2026-09-17：恢复比较基因组分组。09-15 拆分时把它和「进化动力学分析」
    # 当成同一件事一起移出了导航，这是错的 —— 两者是不同的业务对象：
    # 比较基因组 = **不同病毒之间**的比较（跨科/属取参考序列 → 比对 → 建树 / SDT
    # 同一性）；进化动力学 = **同一个基因/序列集内部**的时间与地理信号。
    # 09-16 恢复 phylodyn 时用的是「覆盖」而不是「并列」，等于顺手把 compare 的
    # 一级导航位吞了（有组、有卡、有路由，但界面上到不了）。
    {'id': 'compare', 'label': '比较基因组分析', 'path': '比较基因组分析', 'items': [
        {'id': 't-seqprep', 'title': '参考序列获取', 'desc': 'ICTV 科/属选择 或 accession / 检索式 → 下载整科整属序列（GenBank 集合 + FASTA 参考集）'},
        {'href': '/cds-export', 'title': 'CDS / PEP 提取产物',
         'desc': '集合内 CDS 明细 → 人工挑选 / 改名 → 按基因名归组导出 CDS + PEP（独立模块）'},
        {'id': 't-align', 'title': '序列比对（MAFFT + trimAl）', 'desc': 'MAFFT 比对 + trimAl 清剪；彩色比对查看器支持查看与编辑，结果直接送建树 / SDT'},
        {'id': 't-treebuild', 'title': '进化树构建（科/属级）', 'desc': 'GenBank 集合（全基因组 / CDS / PEP）或 FASTA → MAFFT 比对 + NJ / FastTree / IQ-TREE 建树；页内树查看'},
        {'id': 't-sdt', 'title': 'SDT 同一性分析（属级）', 'desc': '逐对 MAFFT 精确比对 → identity 矩阵 / 热图 / 分布图；NT+AA 模式同一性表 + 复合热图'},
    ]},
    # 2026-09-16：本站移植了裁剪版系统地理能力（距离三分类 / MOTP / 权重分带 /
    # 迁移 GIF，见 docs/主平台同步_裁剪移植_20260916.md），故恢复一个最小分组
    # 让这三张卡可达。BEAST 产物导入 / 自研贝叶斯 ASR / T3 时间树 / LTT / skyline
    # 仍只在进化平台。
    # 2026-09-17：补充 VirPhyKit（Yin et al. 2025）方法学对齐的 12 张卡
    # （数据接入三来源 + SeqIDRenamer/SeqGrouper/VirSpaceTime/GeoSubsampler/
    #   RRT/TempMig/BSP-Viz/RSPP-Viz/TreeTime-RTT/TreeDater-LTT/MJRM），
    # 代码全部自研（GPL-3.0 红线：只对齐方法与 I/O 契约，不复制代码），
    # 见 Virus_Platform_Core/phylodyn_kit.py / phylodyn_trees.py。
    # label 与一级导航 `nav.g.phylodyn`、进化平台同名组保持一致（同一业务线一个名字）。
    {'id': 'phylodyn', 'label': '进化动力学分析', 'path': '进化动力学分析', 'items': [
        {'id': 't-pdprep', 'title': '🧬 进化动力学数据接入',
         'desc': '三种来源建标准数据集（比对 FASTA + 元数据）：**文件对**（两份文件直喂）/ 手动输入（时间地点同检）/ 在线下载；元数据列名自动识别并择优（Collection_Date↔Release_Date、Geo_Location↔Country）。附时间轴·地点分布·地图汇总'},
        {'id': 't-rdp', 'title': '🔁 RDP5 重组分析',
         'desc': 'RDP5 九方法检测，逐方法 p 值；可导出掩蔽重组区后的干净比对'},
        {'id': 't-rtt', 'title': '⏱ 时间信号与定年',
         'desc': '根到尾回归：R² 高＝时间信号强，斜率＝每位点每年替换数'},
        {'id': 't-phylogeo', 'title': '🌍 系统地理分析',
         'desc': 'Fitch 迁移重构 + 距离三分类（haversine）/ MOTP 时间分箱 / 权重分带 / 迁移 GIF 导出'},
        # 2026-09-21 归档 t-pdrename / t-pdgroup 两卡（导航/section/job 注册已同摘，
        # 底层 phylodyn_kit 函数保留）：
        #   🏷 重命名 → 已接进「时间与地理推断·本地全链」可选前置（t-phylodyn 卡的
        #     「🏷 重命名映射」字段，A0 之前 FASTA/元数据/树 tip 三处同改）；
        #   🧩 分组 → 属导入/收集阶段职责（online 阶段自动跑，产物进 report）。
        {'id': 't-phylodyn', 'title': '⚡ 一键分析（定年 → 地理迁移 → 汇总溯源）',
         'desc': 'A0 数据准备 → A1 定年 → A2 地理迁移 → A3 天际线 → A4 祖先序列 → A5 汇总溯源；可一键全跑，也可只跑单阶段或从上一轮产物续跑。全程本地、不跑 MCMC'},
    ]},
    {'id': 'result', 'label': '结果中心', 'path': '结果中心', 'items': [
        {'href': '/results', 'title': '样品结果 / 专项结果',
         'desc': '报告 / 专项运行 / SDT / MSA / 进化树 / 序列查看'},
    ]},
    {'id': 'trace', 'label': '溯源与提交', 'path': '溯源与提交', 'items': [
        {'href': '/logan', 'title': 'LOGAN 溯源 / 批量提交', 'desc': '公共样本追踪'},
        {'href': '/submit', 'title': '数据提交', 'desc': 'NCBI 提交准备'},
    ]},
]


# 2026-09-15：/explorer 已随病毒浏览器迁出（2026-09-27 彻底归档，
# archive/_retire_20260927/explorer/），不再映射到本站的导航组。
# 2026-09-17：/cds-export 是 compare 组的子页，映射随 compare 组一起恢复。
# 2026-09-18：/primer 随「检测与防治」组从 annotate 迁到 detect —— 这行不改，
# 引物页侧栏仍显示注释组的 7 项、dsRNA 卡入口也会指错组（_group_nav.html 用
# current_group 拼 `/tools?g=<组id>#<卡id>`）。
_PATH_TO_GROUP = {'/meta': 'resource', '/virome': 'resource',
                  '/download': 'sample', '/build': 'resource',
                  '/hostremoval': 'sample', '/samples': 'sample',
                  '/orf': 'annotate', '/annotation': 'annotate',
                  '/genome': 'annotate', '/primer': 'detect',
                  '/cds-export': 'compare',
                  '/logan': 'trace', '/submit': 'trace'}


@bp.app_context_processor
def _inject_group_nav():
    """组导航数据 + 当前组：子页侧栏与 tools 工作台共用同一数据源。"""
    gid = None
    if request.path == '/tools':
        gid = request.args.get('g')
    if gid not in {g['id'] for g in NAV_GROUPS}:
        gid = _PATH_TO_GROUP.get(request.path)
    group = next((g for g in NAV_GROUPS if g['id'] == gid), None)
    return {'nav_groups': NAV_GROUPS, 'current_group': group}


@bp.app_errorhandler(ValueError)
@bp.app_errorhandler(FileNotFoundError)
def _bad_request(e):
    """路径非法/不存在 → 400（含路径穿越拦截）。"""
    return jsonify({'error': str(e)}), 400


@bp.app_errorhandler(PermissionError)
def _forbidden(e):
    return jsonify({'error': str(e)}), 403


@bp.app_errorhandler(HTTPException)
def _http_err(e):
    """所有 HTTP 错误统一 JSON 返回（abort(400, msg) 等）。"""
    return jsonify({'error': e.description}), e.code


@bp.app_errorhandler(Exception)
def _unhandled(e):
    """兜底：未捕获异常也返回 JSON，避免前端 `await r.json()` 解析 HTML 失败。

    否则前端只会显示「无法连接平台服务 / SyntaxError」，把服务端参数错误
    误报成网络故障（app.js 的 fetch 包装就是按 r.json() 解析的）。
    """
    import traceback as _tb
    current_app.logger.exception('未处理异常: %s', e)
    if request.path.startswith('/api/') or request.is_json:
        detail = _tb.format_exc(limit=3)
        # traceback 里的本机绝对路径（含用户名）不必回显给前端，日志里已有
        try:
            from Virus_Platform_Core.config import PLATFORM_ROOT
            import tempfile as _tf
            detail = detail.replace(str(PLATFORM_ROOT), '<platform>')
            detail = detail.replace(os.path.abspath(_tf.gettempdir()), '<temp>')
        except Exception:
            pass
        return jsonify({'error': f'服务端异常: {e.__class__.__name__}: {e}',
                        'detail': detail}), 500
    raise e


@bp.route('/')
def page_index():
    return render_template('home.html')


@bp.route('/pipeline')
def page_pipeline():
    return render_template('pipeline.html')


@bp.route('/hostremoval')
def page_host_removal():
    return render_template('host_removal.html')


@bp.route('/samples')
def page_samples():
    return render_template('samples.html')


@bp.route('/orf')
def page_orf():
    return render_template('orf.html')


@bp.route('/annotation')
def page_annotation():
    return render_template('annotation.html')


@bp.route('/genome')
def page_genome():
    return render_template('genome.html')


@bp.route('/primer')
def page_primer():
    return render_template('primer.html')


@bp.route('/cds-export')
def page_cds_export():
    return render_template('cds_export.html')


@bp.route('/build')
def page_build():
    return render_template('build.html')


@bp.route('/tasks')
def page_tasks():
    """全局任务中心：运行中监测 / 日志折叠 / 停止 / 重启 / 删除 / 历史归档。"""
    return render_template('tasks.html')


@bp.route('/results')
def page_results():
    samples, archived = [], []
    res_root = check_path(DIRS['results'], must_exist=True, in_platform=True)
    for name in sorted(os.listdir(res_root)):
        if name.startswith('_'):
            # _archive 归档样品单独收集；其余内部目录不展示
            if name == '_archive':
                arch = os.path.join(res_root, '_archive')
                for an in sorted(os.listdir(arch)):
                    ad = os.path.join(arch, an)
                    if not os.path.isdir(ad):
                        continue
                    archived.append({
                        'name': an,
                        'report': os.path.isfile(
                            os.path.join(ad, '07_report', 'report.html')),
                        'mtime': time.strftime(
                            '%Y-%m-%d %H:%M',
                            time.localtime(os.path.getmtime(ad)))})
            continue
        d = check_path(os.path.join(res_root, name), must_exist=False,
                       in_platform=True)
        if not os.path.isdir(d):
            continue
        rpt = check_path(os.path.join(d, '07_report', 'report.html'),
                         must_exist=False, in_platform=True)
        samples.append({'name': name, 'report': os.path.isfile(rpt),
                        'project': _sample_project(d),
                        'mtime': time.strftime(
                            '%Y-%m-%d %H:%M',
                            time.localtime(os.path.getmtime(d)))})
    return render_template('results.html', samples=samples, archived=archived)


def _sample_project(sample_dir):
    """样品所属项目名（与 /api/samples 同口径：input.json 优先，清单兜底）。

    全局项目筛选器要在结果中心也生效，所以这里必须把 project 一并带进模板；
    读不到（老样品/档案损坏）返回空串，由前端归入「未分组」。
    """
    try:
        from Virus_Platform_Core.pipeline import (load_project_manifest,
                                                  load_sample_input)
        _r1, _r2, proj = load_sample_input(sample_dir)
        if proj:
            return str(proj)
        return str(load_project_manifest(sample_dir).get('project') or '')
    except Exception:
        return ''


@bp.route('/report/<sample>/')
def page_report(sample):
    safe = _safe_sample(sample)
    rpt = check_path(os.path.join(DIRS['results'], safe, '07_report', 'report.html'),
                     must_exist=True, in_platform=True)
    return send_file(check_path(rpt, must_exist=True, in_platform=True))


@bp.route('/report/<sample>/<path:filename>')
def page_report_file(sample, filename):
    """报告目录内静态文件（plotly.min.js 等；尾斜杠路由使相对引用可解析）。"""
    safe = _safe_sample(sample)
    p = check_path(os.path.join(DIRS['results'], safe, '07_report', filename),
                   must_exist=True, in_platform=True)
    return send_file(check_path(p, must_exist=True, in_platform=True))


@bp.route('/archive_report/<sample>/')
def page_archive_report(sample):
    """归档样品报告（results/_archive/<sample>/）。"""
    # 归档目录名不在 results/ 下，解析基准要指到 _archive
    safe = _safe_sample(sample, base=os.path.join(DIRS['results'], '_archive'))
    rpt = check_path(os.path.join(DIRS['results'], '_archive', safe,
                                  '07_report', 'report.html'),
                     must_exist=True, in_platform=True)
    return send_file(check_path(rpt, must_exist=True, in_platform=True))


@bp.route('/help')
def page_help():
    """浏览器内阅读使用手册（不依赖系统 .md 文件关联）。"""
    cands = [os.path.join(PLATFORM_ROOT, 'README.md')]
    if getattr(sys, '_MEIPASS', None):
        cands.append(os.path.join(sys._MEIPASS, 'README.md'))
    text = ''
    for p in cands:
        if os.path.isfile(p):
            try:
                with safe_open(p) as f:
                    text = f.read()
            except OSError:
                pass
            break
    return render_template('help.html', text=text)
