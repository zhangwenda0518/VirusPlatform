# -*- coding: utf-8 -*-
"""
平台配置：工具路径自动探测 / 手动覆盖、目录布局、线程数。
配置持久化到 <平台根>/platform.json，GUI 修改后立即生效。
"""
import os
import sys
import json
import glob
import shutil
import threading

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')


def _detect_platform_root():
    """平台根目录：PyInstaller 打包后 = exe 所在目录；源码运行 = vp/ 上级目录。"""
    if getattr(sys, 'frozen', False):          # PyInstaller 环境
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


PLATFORM_ROOT = _detect_platform_root()


def engine_cmd(script_abspath, *args):
    """构造「以子进程运行内部引擎脚本」的命令行。

    源码运行: [python, script.py, args...]
    冻结分发: [VirusPlatform.exe, --run-engine, script.py, args...]
    （打包环境无独立 python、无源码脚本路径；app.py 入口识别 --run-engine
    后经 vp/engine_entry.py 进程内执行对应引擎。）
    """
    if getattr(sys, 'frozen', False):
        return [sys.executable, '--run-engine',
                os.path.basename(script_abspath)] + list(args)
    # -u：子进程 stdout 无缓冲（管道默认块缓冲会让任务日志长时间空白）
    return [sys.executable, '-u', script_abspath] + list(args)

# ------------------------------------------------------------------
# 目录布局（全部限定在平台根目录内）
# ------------------------------------------------------------------
DIRS = {
    'databases': os.path.join(PLATFORM_ROOT, 'databases'),   # kunpeng 库根目录
    'taxonomy':  os.path.join(PLATFORM_ROOT, 'databases', 'taxonomy'),
    'host_src':  os.path.join(PLATFORM_ROOT, 'host-db'),     # 宿主源基因组
    'virus_src': os.path.join(PLATFORM_ROOT, 'virus-db'),    # 病毒源参考
    # ---- 运行期数据统一收在 run/ 下（2026-09-10 目录整理）----
    'results':   os.path.join(PLATFORM_ROOT, 'run', 'results'),   # 样品结果
    'tool_runs': os.path.join(PLATFORM_ROOT, 'run', 'tool_runs'),  # 工具运行目录
    'downloads': os.path.join(PLATFORM_ROOT, 'run', 'downloads'),  # 公共数据下载
    'logan':     os.path.join(PLATFORM_ROOT, 'run', 'logan'),     # LOGAN 溯源任务
    'submissions': os.path.join(PLATFORM_ROOT, 'run', 'submissions'),  # NCBI 提交准备
    'meta_search': os.path.join(PLATFORM_ROOT, 'run', 'meta_search'),  # 公共数据检索
    'tasks':     os.path.join(PLATFORM_ROOT, 'run', 'tasks'),     # GUI 任务状态
    'logs':      os.path.join(PLATFORM_ROOT, 'run', 'logs'),      # 全局日志
    'uploads':   os.path.join(PLATFORM_ROOT, 'run', 'uploads'),   # 粘贴/上传中转
    'fastq':     os.path.join(PLATFORM_ROOT, 'run', 'fastq'),     # 流程 FASTQ 中转
    'webapp_static': os.path.join(PLATFORM_ROOT, 'webapp', 'static'),
    # 示例数据根（内置示例 FASTA/GenBank/树）：默认在程序目录内，
    # 但允许外置（打包时「程序 / 数据库 / 示例」三分离）。
    'examples':  os.path.join(PLATFORM_ROOT, 'databases', 'examples'),
}

# 目录整理（2026-09-10）后的新旧顶层目录映射：
#   运行期数据 → run/，外部二进制与第三方 → 3rd/。
# 历史数据/前端/文档里仍可能写旧相对路径（tool_runs/xxx、results/xxx…），
# utils.check_path 会按这张表重定向，保证旧调用与旧记录不失效。
LEGACY_TOP_DIRS = {
    'results': 'run/results',
    'tool_runs': 'run/tool_runs',
    'logs': 'run/logs',
    'tasks': 'run/tasks',
    'uploads': 'run/uploads',
    'submissions': 'run/submissions',
    'meta_search': 'run/meta_search',
    'logan': 'run/logan',
    'fastq': 'run/fastq',
    'downloads': 'run/downloads',
    'tools': '3rd/tools',
    'bin': '3rd/bin',
    'vendor': '3rd/vendor',
    'open-virome': '3rd/open-virome',
}

# ------------------------------------------------------------------
# 数据库分类路径注册表
# ------------------------------------------------------------------
DB_LAYOUT = {
    'virus': {
        'plant': ('virus/plant', 'virus_db'),
        'ref':   ('virus/ref',   'refvirus_db'),
        'rvdb':  ('virus/rvdb',  'rvdb_db'),
    },
    'host': {
        # 宿主**分类库**（kunpeng hash）与病毒/注释库不同：它按物种而异、
        # 单库约 1.5GB，所以不进 databases/ 分发包（package.py --with-db
        # 不再收录它），而与宿主源基因组一起放 host-db/ 下。
        # 两种层级都接受（第三个元素 = base_key，指向 DIRS['host_src']）：
        #   host-db/host/classify   把 databases/host 整体搬过来的结果
        #   host-db/classify        拍平后的位置
        'classify': (['host/classify', 'classify'], 'host_db', 'host_src'),
    },
    'annot': {
        'cdd':  ('annot/cdd',  'cdd'),
        'hmm':  ('annot/hmm',  'hmm'),
        'prot': ('annot/prot', 'viral_prot'),
    },
    'tax': {
        'core': ('tax/core', 'taxonomy'),
        'ictv': ('tax/ictv', 'ictv_db'),
    },
    # 建树参考库（两套口径，由库本身决定宿主范围）
    #   plant : 植物病毒参考（ref_info 45 科 + 补齐 3 科，共 48 科），植物口径
    #   ictv  : 全病毒界参考（ICTV acvirus_db 全量，20,178 条），不过滤宿主
    # old_name 保留 acvirus_db：旧目录若仍在，_db_path 自动回退不报错。
    'tree': {
        'plant': ('tree_db/plant_tree.db', 'acvirus_db'),
        'ictv':  ('tree_db/ictv_tree.db',  'acvirus_db'),
    },
    'misc': {
        'viroids': ('misc/viroids', 'viroids-db'),
        'suvtk':   ('misc/suvtk',   'suvtk_db'),
        'gb':      ('misc/gb',      'gb_collections'),
        'prob':    ('misc/prob',    'host_prob'),
    },
}


def _db_path(new_sub, old_name, base_key='databases'):
    """数据库路径：新分类路径优先，未迁移时回退旧目录。

    new_sub:  相对 base_key 的子路径；可为候选列表（按序取第一个存在的）
    old_name: 旧布局目录名（同样相对 base_key）
    base_key: DIRS 里的根键，默认 'databases'。宿主分类库用 'host_src'
              —— 它按物种而异、体积大，不进 databases/ 分发包，
              与宿主源基因组同放 host-db/ 下。

    候选都不存在时返回第一个候选（供建库落盘用）。
    """
    base = DIRS[base_key]
    subs = new_sub if isinstance(new_sub, (list, tuple)) else [new_sub]
    for s in subs:
        p = os.path.join(base, s)
        if os.path.isdir(p):
            return p
    if old_name:
        old = os.path.join(base, old_name)
        if os.path.isdir(old):
            return old
    return os.path.join(base, subs[0])


def db_path(category, name):
    """按分类取数据库路径（virus/plant、host/classify、annot/cdd 等）。"""
    entry = DB_LAYOUT[category][name]
    sub, old = entry[0], entry[1]
    base_key = entry[2] if len(entry) > 2 else 'databases'
    return _db_path(sub, old, base_key)


# taxonomy 目录也走注册表（新 tax/core 优先，旧 databases/tax/core 兜底），
# 迁移前后 DIRS['taxonomy'] 都能解析到有效路径。
DIRS['taxonomy'] = db_path('tax', 'core')


def host_source_dirs():
    """host-db 下所有宿主源目录（<taxid>_<slug>/ 且含 genome.fa）。"""
    base = DIRS['host_src']
    if not os.path.isdir(base):
        return []
    out = []
    for n in sorted(os.listdir(base)):
        p = os.path.join(base, n)
        if os.path.isdir(p) and os.path.isfile(os.path.join(p, 'genome.fa')):
            out.append(n)
    return out


def current_host_genome():
    """当前宿主源基因组：host-db 下第一个含 genome.fa 的宿主目录。
    兼容旧默认（host-db/genome.fa）。"""
    dirs = host_source_dirs()
    if dirs:
        return os.path.join(DIRS['host_src'], dirs[0], 'genome.fa')
    old = os.path.join(DIRS['host_src'], 'genome.fa')
    return old if os.path.isfile(old) else None


CONFIG_FILE = os.path.join(PLATFORM_ROOT, 'platform.json')
# 配置文件写入互斥（Flask threaded=True，设置页可并发保存）
_SAVE_LOCK = threading.RLock()


# ------------------------------------------------------------------
# 自定义输出根目录：设置后所有产物（样品结果 / 工具运行 / 数据下载 /
# 公共数据检索 / LOGAN / 提交准备 / 日志）按推荐结构写入该目录下的
# 同名子目录（自动创建）；留空 = 平台目录内。
# ------------------------------------------------------------------
OUTPUT_SUBDIRS = ('results', 'tool_runs', 'downloads', 'meta_search',
                  'logan', 'submissions', 'logs')

_OUTPUT_ROOT = ''          # 模块级当前自定义输出根（'' = 默认平台目录）


def apply_output_root(root):
    """设置/切换输出根：原地重写 DIRS 输出类条目并自动创建推荐子目录。

    所有功能在运行时读取 DIRS，因此切换立即对全部模块生效，无需重启。
    """
    global _OUTPUT_ROOT
    root = (root or '').strip()
    if root:
        if not os.path.isabs(root):
            raise ValueError('输出目录需为绝对路径')
        root = os.path.normpath(os.path.abspath(root))
        os.makedirs(root, exist_ok=True)
    _OUTPUT_ROOT = root
    for name in OUTPUT_SUBDIRS:
        target = os.path.join(root, name) if root \
            else os.path.join(PLATFORM_ROOT, name)
        DIRS[name] = target
        os.makedirs(target, exist_ok=True)
    # 同步预建 tool_runs 固定子目录（_archive/_tmp/_scripts/_reports）；
    # 懒导入避免与 tool_runs_admin 循环依赖
    try:
        from .tool_runs_admin import ensure_fixed_dirs
        ensure_fixed_dirs(DIRS['tool_runs'])
    except Exception:
        pass
    return _OUTPUT_ROOT


def get_output_root():
    return _OUTPUT_ROOT


# ------------------------------------------------------------------
# 示例数据根（程序 / 数据库 / 示例 三分离打包时，示例可放在程序目录之外）
# ------------------------------------------------------------------
_EXAMPLES_ROOT = ''


def _default_examples_root():
    return os.path.join(PLATFORM_ROOT, 'databases', 'examples')


def _detect_examples_root():
    """自动探测外置示例目录（无需用户手工配置）。

    探测顺序：
      1) <平台根>/databases/examples（传统内置布局）
      2) <平台根>/../VirusPlatform-Examples/databases/examples
      3) <平台根>/../VirusPlatform-Examples/examples
      4) <平台根>/examples
    找到含 example_viral_contigs.fasta 的目录即采用。
    """
    cands = [
        _default_examples_root(),
        os.path.join(os.path.dirname(PLATFORM_ROOT), 'VirusPlatform-Examples',
                     'databases', 'examples'),
        os.path.join(os.path.dirname(PLATFORM_ROOT), 'VirusPlatform-Examples',
                     'examples'),
        os.path.join(PLATFORM_ROOT, 'examples'),
    ]
    for c in cands:
        if os.path.isfile(os.path.join(c, 'example_viral_contigs.fasta')):
            return c
    return ''


def apply_examples_root(root):
    """设置/切换示例数据根（'' = 自动探测，找不到则用平台内默认路径）。"""
    global _EXAMPLES_ROOT
    root = (root or '').strip()
    if root:
        if not os.path.isabs(root):
            raise ValueError('示例目录需为绝对路径')
        root = os.path.normpath(os.path.abspath(root))
    else:
        root = _detect_examples_root()
    _EXAMPLES_ROOT = root
    DIRS['examples'] = root or _default_examples_root()
    return _EXAMPLES_ROOT


def get_examples_root():
    return _EXAMPLES_ROOT or DIRS['examples']


def write_roots():
    """允许写入的根目录集合：平台根 + 自定义输出/输入/数据库根（若有）。
    check_path(in_platform=True) 据此放行写入类路径。"""
    roots = [PLATFORM_ROOT]
    for r in (_OUTPUT_ROOT, _INPUT_ROOT, _DATABASE_ROOT):
        if r:
            roots.append(r)
    return roots


# 输入根：测序数据 fastq/ 与拖拽上传 uploads/ 的存放位置
INPUT_SUBDIRS = ('fastq', 'uploads')

# 数据库根：kunpeng 库/taxonomy/palmdb 等大数据目录 + 建库源数据
_DATABASE_KEYS = {                       # DIRS 键 → 数据库根下的子路径
    'databases': 'databases',
    # taxonomy 不在此表内：它必须走 DB_LAYOUT（新布局 tax/core，旧布局
    # taxonomy 兜底）。写死 'databases/taxonomy' 会让外部数据库根下的
    # taxonomy 指向空目录（见 apply_database_root）。
    'host_src':  'host-db',
    'virus_src': 'virus-db',
}

_INPUT_ROOT = ''           # 模块级当前自定义输入根（'' = 默认平台目录）
_DATABASE_ROOT = ''        # 模块级当前自定义数据库根（'' = 默认平台目录）


def apply_input_root(root):
    """设置/切换输入根：重写 DIRS['fastq'/'uploads'] 并自动创建。"""
    global _INPUT_ROOT
    root = (root or '').strip()
    if root:
        if not os.path.isabs(root):
            raise ValueError('输入目录需为绝对路径')
        root = os.path.normpath(os.path.abspath(root))
        os.makedirs(root, exist_ok=True)
    _INPUT_ROOT = root
    for name in INPUT_SUBDIRS:
        DIRS[name] = os.path.join(root, name) if root \
            else os.path.join(PLATFORM_ROOT, name)
        os.makedirs(DIRS[name], exist_ok=True)
    return _INPUT_ROOT


def apply_database_root(root):
    """设置/切换数据库根：重写 DIRS 数据库类条目并自动创建。"""
    global _DATABASE_ROOT
    root = (root or '').strip()
    if root:
        if not os.path.isabs(root):
            raise ValueError('数据库目录需为绝对路径')
        root = os.path.normpath(os.path.abspath(root))
        os.makedirs(root, exist_ok=True)
    _DATABASE_ROOT = root
    for key, sub in _DATABASE_KEYS.items():
        DIRS[key] = os.path.join(root, sub) if root \
            else os.path.join(PLATFORM_ROOT, sub)
        os.makedirs(DIRS[key], exist_ok=True)
    # taxonomy 走注册表解析：新布局 <root>/databases/tax/core 优先，
    # 旧布局 <root>/databases/taxonomy 兜底（与平台内 DIRS 初始化口径一致）。
    DIRS['taxonomy'] = db_path('tax', 'core')
    os.makedirs(DIRS['taxonomy'], exist_ok=True)
    _refresh_module_paths()
    return _DATABASE_ROOT


def _refresh_module_paths():
    """通知「import 时快照了 DIRS」的模块重算路径常量。

    否则切换数据库目录后，ictv_db / virus_ref / universal_ref /
    local_search / verify / hmm_annot / orf_annot / suvtk_submit
    仍指向旧库（长驻的 Web 进程尤其明显）。这类失配不会报错，
    只会让功能静默失效（库找不到 → 该层结果为空）。
    用延迟导入避免 config ↔ 这些模块的循环依赖。
    """
    for name in ('ictv_db', 'virus_ref', 'universal_ref', 'local_search',
                 'verify', 'hmm_annot', 'orf_annot', 'suvtk_submit'):
        try:
            mod = __import__(f'vp.{name}', fromlist=['refresh_paths'])
            fn = getattr(mod, 'refresh_paths', None)
            if callable(fn):
                fn()
        except Exception:
            pass


def get_input_root():
    return _INPUT_ROOT


def get_database_root():
    return _DATABASE_ROOT


def _safe_child(path, parent=PLATFORM_ROOT):
    """规范化路径并校验必须位于 parent 目录内，禁止 ../ 逃逸。"""
    norm = os.path.normpath(os.path.abspath(path))
    parent = os.path.normpath(os.path.abspath(parent))
    if norm == parent or norm.startswith(parent + os.sep):
        return norm
    raise ValueError(f"路径越界（仅允许平台目录内）: {path}")


def _first_exist(paths):
    for p in paths:
        if p and os.path.isfile(p):
            return os.path.abspath(p)
    return None


def _glob_first(pattern):
    hits = sorted(glob.glob(pattern))
    return os.path.abspath(hits[0]) if hits else None


def detect_tools():
    """自动探测外部工具路径（仅 PATH 与 3rd/bin、3rd/tools 目录，不访问其他用户目录）。
    3rd/bin/   = 单文件可执行（kunpeng、seqkit、crabz 等）
    3rd/tools/ = 带目录结构的工具套件（Blast、mafft-win、iQtree 等）
    下面各条目里沿用 PLATFORM_ROOT 的候选是「旧版平铺分发」回退（exe 与 app.py
    同级），仍然保留以兼容已分发的 exe 平台。"""
    R = PLATFORM_ROOT
    BIN = os.path.join(R, '3rd', 'bin')
    T = os.path.join(R, '3rd', 'tools')
    which = shutil.which
    cands = {
        'kunpeng': [
            _glob_first(os.path.join(BIN, 'kun_peng-v*-x86_64-pc-windows-msvc.exe')),
            _glob_first(os.path.join(BIN, 'kun_peng*.exe')),
            _glob_first(os.path.join(R, 'kun_peng-v*-x86_64-pc-windows-msvc.exe')),
            _glob_first(os.path.join(R, 'kun_peng*.exe')),
            which('kun_peng'), which('kun_peng.exe'),
        ],
        # 捆绑副本优先于 PATH：分发版始终用随包 SPAdes，不受对方机器已装版本影响
        'spades': [_glob_first(os.path.join(T, 'SPAdes*', 'bin', 'spades.bat')),
                   _glob_first(os.path.join(R, 'SPAdes*', 'bin', 'spades.bat')),
                   which('spades.bat'), which('spades.py')],
        'blastn':      [_glob_first(os.path.join(T, 'Blast', 'bin', 'blastn.exe')),
                        _glob_first(os.path.join(R, 'Blast', 'bin', 'blastn.exe')),      which('blastn')],
        'makeblastdb': [_glob_first(os.path.join(T, 'Blast', 'bin', 'makeblastdb.exe')),
                        _glob_first(os.path.join(R, 'Blast', 'bin', 'makeblastdb.exe')), which('makeblastdb')],
        'blastp':      [_glob_first(os.path.join(T, 'Blast', 'bin', 'blastp.exe')),
                        _glob_first(os.path.join(R, 'Blast', 'bin', 'blastp.exe')),      which('blastp')],
        'blastx':      [_glob_first(os.path.join(T, 'Blast', 'bin', 'blastx.exe')),
                        _glob_first(os.path.join(R, 'Blast', 'bin', 'blastx.exe')),      which('blastx')],
        'mafft':   [which('mafft'), os.path.join(T, 'mafft-win', 'mafft.bat'),
                    _glob_first(os.path.join(T, 'mafft-win', 'mafft*.bat')),
                    os.path.join(R, 'mafft-win', 'mafft.bat'),
                    _glob_first(os.path.join(R, 'mafft-win', 'mafft*.bat'))],
        'fasttree': [which('fasttree'), which('FastTree'),
                     _glob_first(os.path.join(T, 'FastTree', 'FastTree*.exe')),
                     _glob_first(os.path.join(R, 'FastTree', 'FastTree*.exe'))],
        'iqtree2': [which('iqtree2'), which('iqtree2.exe'),
                    _glob_first(os.path.join(T, 'iQtree', '*', 'bin', 'iqtree2.exe')),
                    _glob_first(os.path.join(T, 'iQtree', '*', 'iqtree2*.exe')),
                    _glob_first(os.path.join(R, 'iQtree', '*', 'bin', 'iqtree2.exe')),
                    _glob_first(os.path.join(R, 'iQtree', '*', 'iqtree2*.exe'))],
        'iqtree3': [which('iqtree3'), which('iqtree3.exe'),
                    _glob_first(os.path.join(T, 'iQtree', '*', 'bin', 'iqtree3.exe')),
                    _glob_first(os.path.join(T, 'iQtree', '*', 'iqtree3*.exe')),
                    _glob_first(os.path.join(R, 'iQtree', '*', 'bin', 'iqtree3.exe')),
                    _glob_first(os.path.join(R, 'iQtree', '*', 'iqtree3*.exe'))],
        'trimal':  [which('trimal'), which('trimal.exe'),
                    os.path.join(T, 'trimAl', 'trimal.exe'),
                    _glob_first(os.path.join(T, 'trimAl*', 'bin', 'trimal*.exe')),
                    os.path.join(R, 'trimAl', 'trimal.exe'),
                    _glob_first(os.path.join(R, 'trimAl*', 'bin', 'trimal*.exe'))],
        'gblocks': [which('Gblocks'), which('Gblocks.exe'),
                    os.path.join(T, 'Gblocks', 'Gblocks.exe'),
                    _glob_first(os.path.join(T, 'Gblocks*', 'Gblocks*.exe')),
                    os.path.join(R, 'Gblocks', 'Gblocks.exe'),
                    _glob_first(os.path.join(R, 'Gblocks*', 'Gblocks*.exe'))],
        'clustalw': [os.path.join(BIN, 'clustalw2.exe'),
                     os.path.join(R, 'clustalw2.exe'), which('clustalw2')],
        'muscle':   [_glob_first(os.path.join(BIN, 'muscle*.exe')),
                     _glob_first(os.path.join(R, 'muscle*.exe')), which('muscle')],
        'seqkit':   [which('seqkit'), _glob_first(os.path.join(BIN, 'seqkit*.exe')),
                     _glob_first(os.path.join(R, 'seqkit*.exe'))],
        'crabz':    [which('crabz'), which('crabz.exe'),
                     _glob_first(os.path.join(BIN, 'crabz*.exe')),
                     _glob_first(os.path.join(R, 'crabz*.exe'))],
        'gbdraw':   [which('gbdraw'), which('gbdraw.exe'),
                     os.path.join(os.path.dirname(sys.executable), 'Scripts',
                                  'gbdraw.exe'),
                     _glob_first(os.path.join(BIN, 'gbdraw*', 'gbdraw*.exe')),
                     _glob_first(os.path.join(R, 'gbdraw*', 'gbdraw*.exe'))],
        'orfipy':   [which('orfipy'),
                     # 打包运行时 Scripts 不一定在 PATH：按当前 Python 推断
                     os.path.join(os.path.dirname(sys.executable), 'Scripts', 'orfipy.exe')],
        'diamond':  [os.path.join(T, 'diamond', 'diamond.exe'),
                     os.path.join(R, 'diamond', 'diamond.exe'), which('diamond'),
                     which('diamond.exe')],
        'mmseqs':   [os.path.join(T, 'mmseqs', 'bin', 'mmseqs.exe'),
                     os.path.join(R, 'mmseqs', 'bin', 'mmseqs.exe'),
                     which('mmseqs'), which('mmseqs.exe')],
        'minimap2': [os.path.join(T, 'minimap2', 'minimap2.exe'),
                     os.path.join(T, 'minimap2', 'minimap2'),
                     os.path.join(R, 'minimap2', 'minimap2.exe'),
                     os.path.join(R, 'minimap2', 'minimap2'),
                     which('minimap2'), which('minimap2.exe')],
        # minibwa：minimap2 作者的下一代比对器，与 minimap2 同属单文件工具，
        # 故探测 bin/；随包分发不依赖 PATH。
        'minibwa': [_glob_first(os.path.join(BIN, 'minibwa*.exe')),
                     os.path.join(BIN, 'minibwa.exe'),
                     _glob_first(os.path.join(R, 'minibwa*.exe')),
                     which('minibwa'), which('minibwa.exe')],
        'fastp':    [which('fastp'), which('fastp.exe'),
                     _glob_first(os.path.join(T, 'fastp*', 'fastp.exe')),
                     _glob_first(os.path.join(R, 'fastp*', 'fastp.exe')),
                     _glob_first(os.path.join(R, 'biosoft', 'fastp*', 'fastp.exe')),
                     _glob_first(os.path.join(R, 'fastp*.exe'))],
        'aria2c':   [os.path.join(BIN, 'aria2c.exe'), os.path.join(R, 'aria2c.exe'),
                     which('aria2c'), which('aria2c.exe')],
        'sracha':   [os.path.join(BIN, 'sracha.exe'), os.path.join(R, 'sracha.exe'),
                     which('sracha'), which('sracha.exe')],
        # ---- 以下工具原先不在探测表里，只靠 platform.json 手填绝对路径；
        # 打包版用的是干净配置（tools: {}），于是"已随包"的它们反而探测不到
        # （实测发布版少了 salmon/samtools/table2asn 三个）。这里补齐候选，
        # 让源码模式与发布版行为一致、且不依赖手改配置。
        'samtools': [which('samtools'), which('samtools.exe'),
                     os.path.join(T, 'samtools', 'bin', 'samtools.exe'),
                     os.path.join(BIN, 'samtools.exe'),
                     os.path.join(R, 'samtools.exe')],
        'bcftools': [which('bcftools'), which('bcftools.exe'),
                     os.path.join(T, 'bcftools', 'bin', 'bcftools.exe'),
                     os.path.join(R, 'bcftools.exe')],
        'salmon':   [which('salmon'), which('salmon.exe'),
                     os.path.join(T, 'salmon2', 'salmon.exe'),
                     os.path.join(T, 'salmon', 'bin', 'salmon.exe'),
                     os.path.join(R, 'salmon.exe')],
        'table2asn': [which('table2asn'), which('table2asn.exe'),
                      os.path.join(T, 'table2asn', 'table2asn.exe'),
                      os.path.join(R, 'table2asn.exe')],
        'pandepth': [which('pandepth'), which('pandepth.exe'),
                     _glob_first(os.path.join(T, 'pandepth*', 'pandepth.exe')),
                     os.path.join(R, 'pandepth.exe')],
        'viral_consensus': [
            which('viral_consensus'), which('viral_consensus.exe'),
            _glob_first(os.path.join(T, 'viral_consensus*',
                                     'viral_consensus.exe')),
            os.path.join(R, 'viral_consensus.exe')],
        # 注：snpEff（jar）与 SNPGenie（perl 脚本）不是可直接执行的单文件工具，
        # 由 known_virus_suite 自己按 tools/snpeff/snpEff/snpEff.jar、
        # tools/snpgenie/snpgenie.pl 定位，不放进本探测表（避免"jar 当 exe"）。
    }
    out = {name: _first_exist(lst) for name, lst in cands.items()}
    if getattr(sys, 'frozen', False) and not out.get('gbdraw'):
        out['gbdraw'] = 'bundled:gbdraw'     # 随包 Python 引擎，进程内调用
    return out


class Config:
    """全局配置单例。tools 可被 platform.json 覆盖；未探测到的工具调用时报错。"""

    # 分析默认参数的定义（键 → 类型/默认/中英说明）；设置页据此渲染
    DEFAULT_FIELDS = [
        # key, 类型, 默认, 中文说明, 英文说明[, 选项]
        ('confidence',    'float',  0.0,        '分类置信度（0~1，越大越严格）',
         'Classification confidence (0-1)'),
        ('subsample',     'int',    0,          '默认子采样 reads 对数（0=不截取）',
         'Default subsample pairs (0 = all)'),
        ('fastp_dedup',   'bool',   False,      'Fastp 质控默认去重 (--dedup)',
         'Dedup by default in fastp QC'),
        ('do_fq2fa',      'bool',   True,       '默认 FASTQ→FASTA 预转换（分类提速）',
         'FASTQ to FASTA pre-conversion by default'),
        ('assembly_mode', 'select', 'metaviral', 'SPAdes 组装模式',
         'SPAdes assembly mode',
         ['metaviral', 'rna', 'meta', 'isolate']),
        ('assembly_input','select', 'virus',    '组装输入 reads',
         'Assembly input reads',
         ['virus', 'kept', 'raw']),
        ('memory',        'int',    64,         'SPAdes 内存上限 (GB)',
         'SPAdes memory cap (GB)'),
        ('min_contig_len','int',    200,        '最小 contig 长度 (bp)',
         'Min contig length (bp)'),
        ('min_orf_aa',    'int',    100,        '最小 ORF 长度 (aa)',
         'Min ORF length (aa)'),
        ('top_n_refs',    'int',    10,         '进化分析近缘参考数',
         'Closest references for phylogenetics'),
        ('tree_tool',     'select', 'fasttree', '建树工具',
         'Tree building tool', ['fasttree', 'iqtree']),
        ('tree_sampling', 'select', 'blast',    '建树参考抽样策略',
         'Tree reference sampling', ['blast', 'macro', 'genus', 'lineage']),
        ('primer_mode',   'select', 'conserved', '引物设计模式',
         'Primer design mode', ['conserved', 'plain']),
        ('specificity',   'bool',   False,      '引物宿主特异性检查（首次较慢）',
         'Primer host-specificity check'),
        ('gbdraw_max',    'int',    12,         '基因组图出图上限（条）',
         'Genome plot limit (contigs)'),
        ('plot_engine',   'select', 'auto',     '基因组图引擎',
         'Genome plot engine', ['auto', 'gbdraw', 'dfv']),
        ('force',         'bool',   False,      '默认强制重跑（忽略断点）',
         'Force re-run by default'),
        ('do_trim',       'bool',   True,       '⑦ 建树前用 trimAl 清剪比对',
         'Trim alignment with trimAl before tree building'),
    ]

    def __init__(self):
        self.threads = max(1, (os.cpu_count() or 4) - 1)
        self.tools = detect_tools()
        self.email = ''            # NCBI EUtils 联系邮箱（可选，礼貌性参数）
        self.language = 'zh'       # 界面语言: zh | en
        # 分析默认参数（预填硬编码缺省，platform.json 的已存值在 _load_extras 覆盖）
        self.defaults = {k: v for k, _t, v, *_r in self.DEFAULT_FIELDS}
        self.databases = {
            'host':  db_path('host', 'classify'),
            'virus': db_path('virus', 'plant'),
        }
        self.output_root = ''      # 自定义输出根（'' = 平台目录内）
        self.input_root = ''       # 自定义输入根（fastq / uploads）
        self.database_root = ''    # 自定义数据库根（databases / host-db / virus-db）
        self.examples_root = ''    # 自定义示例数据根（'' = 自动探测）
        self._db_override = {}
        # 使用者登记的外部已构建 kunpeng 病毒库（绝对路径，平台内/数据库根优先）
        self.extra_virus_libs = []
        # 使用者登记的外部病毒鉴定库（minibwa/salmon 比对索引目录，可为平台外）
        self.extra_kv_indexes = []
        self._load()
        for attr, apply_fn in (('input_root', apply_input_root),
                               ('database_root', apply_database_root),
                               ('output_root', apply_output_root)):
            path = getattr(self, attr)
            if path:
                try:
                    setattr(self, attr, apply_fn(path))
                except (OSError, ValueError):
                    setattr(self, attr, '')
        # 示例数据根：显式配置优先，否则自动探测（程序/数据库/示例三分离
        # 打包时示例目录位于程序目录之外，靠这里接上）。
        apply_examples_root(self.examples_root)
        # 数据库实际路径按（可能已迁移的）数据库根重算；
        # platform.json 的 databases 显式覆盖：仅当该路径真实存在时生效
        # （迁移后旧路径不存在则回退注册表解析，自动切到新分类路径）。
        self.databases = {
            'host':  db_path('host', 'classify'),
            'virus': db_path('virus', 'plant'),
        }
        for k, v in (getattr(self, '_db_override', {}) or {}).items():
            if not v:
                continue
            pv = os.path.normpath(os.path.abspath(v))
            if not os.path.isdir(pv):
                continue
            if any(pv == os.path.normpath(r)
                   or pv.startswith(os.path.normpath(r) + os.sep)
                   for r in write_roots()):
                self.databases[k] = pv
        for d in ('databases', 'taxonomy', 'results', 'downloads', 'logan',
                  'submissions', 'meta_search', 'tasks', 'logs'):
            os.makedirs(DIRS[d], exist_ok=True)

    # ---- 持久化 -------------------------------------------------
    def _load(self):
        if not os.path.isfile(CONFIG_FILE):
            return
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
            self._load_extras(data)
            self.output_root = str(data.get('output_root') or '').strip()
            self.input_root = str(data.get('input_root') or '').strip()
            self.database_root = str(data.get('database_root') or '').strip()
            self.examples_root = str(data.get('examples_root') or '').strip()
            # threads: 0 / 缺省 = 自动探测（cpu 核数 - 1，见 __init__）；
            # 显式 >0 才采用——干净发布配置里写 0 不应钳成单线程
            try:
                _t = int(data.get('threads') or 0)
            except (TypeError, ValueError):
                _t = 0
            if _t > 0:
                self.threads = _t
            if data.get('email'):
                self.email = str(data['email'])
            for k, v in data.get('tools', {}).items():
                if not v:
                    continue
                # 相对路径按平台根解析（platform.json 可存 rel 路径，
                # 避免搬动目录后绝对路径失效）
                p = v if os.path.isabs(str(v)) else os.path.join(PLATFORM_ROOT,
                                                                 str(v))
                if os.path.isfile(p):
                    self.tools[k] = os.path.abspath(p)
            # databases 覆盖延后到根目录应用之后再校验（见 __init__）
            self._db_override = {k: str(v).strip()
                                 for k, v in data.get('databases', {}).items()
                                 if v}
            libs = []
            for v in (data.get('extra_virus_libs') or []):
                v = os.path.normpath(os.path.abspath(str(v).strip()))
                if v and os.path.isdir(v):
                    libs.append(v)
            self.extra_virus_libs = libs
            kvi = []
            for v in (data.get('extra_kv_indexes') or []):
                v = os.path.normpath(os.path.abspath(str(v).strip()))
                if v and os.path.isdir(v):
                    kvi.append(v)
            self.extra_kv_indexes = kvi
        except Exception as e:
            # 不要静默吞掉：配置损坏时用户"改了设置不生效"且无从发现。
            sys.stderr.write(f'[vp.config] 读取 platform.json 失败，'
                             f'已回退默认配置: {type(e).__name__}: {e}\n')

    def save(self):
        data = {'threads': self.threads, 'tools': self.tools,
                'databases': self.databases,
                'defaults': self.defaults, 'language': self.language,
                'output_root': self.output_root,
                'input_root': self.input_root,
                'database_root': self.database_root,
                'examples_root': self.examples_root,
                'extra_virus_libs': self.extra_virus_libs,
                'extra_kv_indexes': self.extra_kv_indexes}
        if self.email:
            data['email'] = self.email
        # 原子写：先写临时文件再替换，断电/崩溃不会损坏现有配置。
        # 加锁 + 临时名带 pid/线程 id：Flask 以 threaded=True 运行，设置页
        # 并发保存会共用同一个 platform.json.tmp，交错写入会写出损坏 JSON。
        with _SAVE_LOCK:
            tmp = f'{CONFIG_FILE}.{os.getpid()}.{threading.get_ident()}.tmp'
            try:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                os.replace(tmp, CONFIG_FILE)
            finally:
                if os.path.isfile(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass

    # ---- 语言 ---------------------------------------------------
    @property
    def lang(self):
        return 'en' if self.language == 'en' else 'zh'

    def set_input_root(self, path):
        """设置自定义输入根（'' = 恢复默认平台目录），持久化并立即生效。"""
        path = (path or '').strip()
        if path and not os.path.isabs(path):
            raise ValueError('输入目录需为绝对路径')
        self.input_root = apply_input_root(path)
        self.save()

    def set_database_root(self, path):
        """设置自定义数据库根（'' = 恢复默认平台目录），持久化并立即生效；
        数据库实际路径（host_db/virus_db）按新根重算。"""
        path = (path or '').strip()
        if path and not os.path.isabs(path):
            raise ValueError('数据库目录需为绝对路径')
        self.database_root = apply_database_root(path)
        self.databases = {
            'host':  db_path('host', 'classify'),
            'virus': db_path('virus', 'plant'),
        }
        self.save()

    def set_output_root(self, path):
        """设置自定义输出根（'' = 恢复默认平台目录），持久化并立即生效。"""
        path = (path or '').strip()
        if path and not os.path.isabs(path):
            raise ValueError('输出目录需为绝对路径（如 D:\\我的分析结果）')
        self.output_root = apply_output_root(path)
        self.save()

    def set_examples_root(self, path):
        """设置示例数据根（'' = 自动探测），持久化并立即生效。

        程序 / 数据库 / 示例 三分离打包时，示例目录在程序目录之外，
        这里指定后各工具「✨ 示例」与「示例结果」页立即指向新位置。
        """
        path = (path or '').strip()
        if path and not os.path.isabs(path):
            raise ValueError('示例目录需为绝对路径')
        if path and not os.path.isdir(path):
            raise ValueError(f'示例目录不存在: {path}')
        # 配置里只记用户显式指定的路径；留空 = 自动探测（保持 platform.json
        # 可移植，不要把探测出来的本机绝对路径写回去）
        apply_examples_root(path)
        self.examples_root = path
        self.save()

    def tr(self, zh, en):
        """按当前语言取字符串（后端动态文案用）。"""
        return en if self.lang == 'en' else zh

    def _load_extras(self, data):
        """非路径类配置：界面语言与分析默认参数（值均为标量，逐项校验类型）。"""
        try:
            if data.get('language') in ('zh', 'en'):
                self.language = data['language']
            known = {kk: t for kk, t, *_r in self.DEFAULT_FIELDS}
            for k, v in (data.get('defaults') or {}).items():
                if k not in known or v is None:
                    continue
                kind = known[k]
                try:
                    if kind == 'int':
                        self.defaults[k] = int(v)
                    elif kind == 'float':
                        self.defaults[k] = float(v)
                    elif kind == 'bool':
                        self.defaults[k] = bool(v)
                    else:
                        self.defaults[k] = str(v)
                except (TypeError, ValueError):
                    pass
        except Exception:
            pass

    # ---- 工具 ---------------------------------------------------
    def tool(self, name):
        path = self.tools.get(name)
        if path and path.startswith('bundled:'):
            return path          # 随包 Python 引擎哨兵，由调用方进程内处理
        if not path or not os.path.isfile(path):
            raise FileNotFoundError(
                f"未找到工具 [{name}]。请在平台配置(platform.json 或 GUI 设置页)中手动指定路径。")
        return path

    def tool_status(self):
        """GUI 用：返回各工具探测状态。"""
        return dict(self.tools)

    def ensure_dir(self, key):
        d = DIRS[key]
        os.makedirs(d, exist_ok=True)
        return d


_config = None

def get_config():
    global _config
    if _config is None:
        _config = Config()
    return _config
