# -*- mode: python ; coding: utf-8 -*-
# spec 位于 dev_tools/，平台根目录 = SPECPATH 的上级（由 dev_tools/package.py 调用）
import os
ROOT = os.path.abspath(os.path.join(SPECPATH, '..'))

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [(os.path.join(ROOT, 'webapp'), 'webapp'),
         (os.path.join(ROOT, 'README.md'), '.')]
datas += collect_data_files('plotly')
datas += collect_data_files('pycirclize')
datas += collect_data_files('gbdraw')
# pyrodigal_rv 的病毒 metagenomic 模型库是纯数据（meta.json），不带会被
# 运行时的 FileNotFoundError 挡住 —— 同样会被 orf.py 当"未安装"静默跳过。
datas += collect_data_files('pyrodigal_rv', includes=['meta.json'])

# 包内**非 .py 数据文件**不会被 PyInstaller 自动收集（PYZ 里只装代码，
# 包目录本身不会出现在 dist/ 下）。凡是模块用 `__file__` 相对路径定位的
# 资源，都必须显式登记，且**目标路径要与包结构一致**：
#   冻结后模块的 `__file__` = <_MEIPASS>/Virus_Platform_Core/<子包>/<模块>.pyc，
#   于是 `Path(__file__).parent / 'templates'` 会落到
#   <_MEIPASS>/Virus_Platform_Core/ncbi_submit/templates —— 只要把资源
#   按同名相对路径投放到那里即可命中，**不需要改业务代码**。
# 已实测会出问题的两处（均属「提交准备」页）：
#   - ncbi_submit/templates/submission_report.html
#       report_html.py 用 jinja2 FileSystemLoader 加载 → 缺失抛
#       jinja2.exceptions.TemplateNotFound（生成提交报告时）
#   - ncbi_submit/samples/sample_{public,selfseq}.csv
#       store._sample_dir() 定位 → 缺失时 list_samples() 静默返回空列表、
#       用样例新建提交项目则 FileNotFoundError
# 注：kv_config.yaml / _test_logs/*.log 等无人读取，故意不收。
datas += [
    (os.path.join(ROOT, 'Virus_Platform_Core', 'ncbi_submit', 'templates'),
     'Virus_Platform_Core/ncbi_submit/templates'),
    (os.path.join(ROOT, 'Virus_Platform_Core', 'ncbi_submit', 'samples'),
     'Virus_Platform_Core/ncbi_submit/samples'),
]

# pyrodigal 的 CPU 内核（avx2/avx512/sse2/generic/swar64）在
# `pyrodigal/impl/` 下，那是个**没有 __init__.py 的命名空间包**：
# PyInstaller 的静态分析看不到，`collect_submodules('pyrodigal')` 也不返回它们
# （实测只返回 pyrodigal / .cli / .lib / .tests.*）。漏掉则运行时 `import pyrodigal`
# 抛 `ModuleNotFoundError: No module named 'pyrodigal.impl'`，而 orf.py 把它当作
# "未安装"静默跳过 → 阶段④ ORF 预测整段失效，且日志只写"未安装"，极难排查。
# 按目录下实际存在的扩展模块动态登记，换 pyrodigal 版本/平台都不用改这里。
_pyro_impl = []
try:
    import glob as _glob
    import pyrodigal as _pd
    _impl_dir = os.path.join(os.path.dirname(_pd.__file__), 'impl')
    for _f in (_glob.glob(os.path.join(_impl_dir, '*.pyd'))
               + _glob.glob(os.path.join(_impl_dir, '*.so'))):
        _name = os.path.basename(_f).split('.')[0]      # avx2.cp312-win_amd64.pyd → avx2
        _pyro_impl.append('pyrodigal.impl.' + _name)
    _pyro_impl = sorted(set(_pyro_impl))
except Exception:
    pass

# pywebview 原生窗口壳（app.py 窗口模式；未安装 pywebview 的构建环境自动跳过，
# 运行时回退浏览器）。WebView2/WinForms 后端是 pywebview 运行时按平台动态
# import 的（importlib），静态分析看不到，必须显式登记，否则 exe 一启动就
# WebViewError 回退浏览器，窗口壳形同虚设。WebView2Loader.dll 等 lib 数据
# 文件不用管 —— hooks-contrib 的 hook-webview 会自动收集。
_webview_hidden = []
try:
    import webview as _wv  # noqa: F401
    _webview_hidden = ['webview.platforms.winforms',
                       'webview.platforms.edgechromium']
except Exception:
    pass


a = Analysis(
    [os.path.join(ROOT, 'app.py')],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['Virus_Platform_Core.public_meta.search_engine',
                   'Virus_Platform_Core.public_meta.info_engine',
                   'Virus_Platform_Core.logan_submit', 'Virus_Platform_Core.lovis4u_run',
                   'Virus_Platform_Core.ncbi_submit.unified_metadata', 'Virus_Platform_Core.engine_entry',
                   # 已知病毒引擎（2026-09-10 由顶层 engines/ 并入包内子包；
                   # 用相对导入后 PyInstaller 静态分析不到，须显式登记）
                   'Virus_Platform_Core.known_virus_suite.kv_common',
                   'Virus_Platform_Core.known_virus_suite.kv_engines',
                   'Virus_Platform_Core.known_virus_suite.kv_identify',
                   'Virus_Platform_Core.known_virus_suite.kv_filter',
                   'Virus_Platform_Core.known_virus_suite.kv_consensus',
                   'Virus_Platform_Core.known_virus_suite.kv_plot',
                   'Virus_Platform_Core.known_virus_suite.kv_variant',
                   'Virus_Platform_Core.known_virus_suite.kv_variant_plot',
                   'Virus_Platform_Core.known_virus_suite.kv_variant_evo',
                   'Virus_Platform_Core.known_virus_suite.known_virus_suite',
                   'Virus_Platform_Core.kv_stage',
                   'main',            # exe --cli <子命令> 用（打包后自检）
                   'gbdraw', 'Virus_Platform_Core.public_meta.landscape_plot', 'seaborn']
                   + collect_submodules('gbdraw')
                   + _pyro_impl
                   + _webview_hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # 体积治理：以下模块平台自身从不 import（2026-09-11 已逐项 grep 复核
    # Virus_Platform_Core/ + app.py + main.py，均 0 命中），只是被
    # pandas/plotly/gbdraw 的依赖链顺带拖进来。实测首版打包 2.05GB，
    # 其中 _internal 834MB（llvmlite 115MB / pyarrow 79MB / bokeh 21MB /
    # botocore 18MB …）。注意不要排除 selenium（LOGAN 批量提交必需）。
    #
    # ⚠️ 不要把 polars / _polars_runtime_32 加回来（2026-09-11 实测踩坑）：
    #   known_virus_suite/kv_filter.py 与 kv_identify.py 在**模块级**
    #   `import polars as pl`，缺失时 `raise SystemExit("需要 polars")`；
    #   而 known_virus_suite.py 又在模块级 import 这两个模块 —— 一旦排除，
    #   「已知病毒识别与定量」整段引擎在打包版里**完全失效且完全静默**。
    #   （当时还被 engine_entry.run_engine 吞成 return 0，双重静默；
    #    engine_entry 已修，但依赖本身仍必须打进包。）
    #   polars 本体仅 8.1MB，但 polars/_plr.py 硬依赖 _polars_runtime_32
    #   （174MB 的 .pyd，就是它的核心运行时，无回退），两者必须同进同出，
    #   合计约 +183MB —— 这是该功能的必要成本。
    excludes=['pytest', '_pytest', 'IPython', 'jedi', 'parso', 'tkinter',
              '_tkinter', 'numba', 'llvmlite',
              'pyarrow', 'bokeh', 'botocore', 'boto3', 's3fs', 'sqlalchemy',
              'sympy', 'duckdb', 'kaleido', 'reportlab', 'docutils', 'sphinx',
              'matplotlib.tests', 'numpy.testing',
              'pandas.tests', 'scipy.io.tests'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='VirusPlatform',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='VirusPlatform',
)
