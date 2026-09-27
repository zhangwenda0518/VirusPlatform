# -*- coding: utf-8 -*-
"""植物病毒分析平台 - 本地 Web GUI（组合根）。

启动（两种模式，可显式选）:
    python app.py            或 双击 启动平台-桌面窗口.bat → 默认独立桌面窗口
    python app.py --gui      或 双击 启动平台-桌面窗口.bat → 强制桌面窗口
    python app.py --web      或 双击 启动平台-网页.bat     → 强制系统浏览器
  桌面窗口由 pywebview(WebView2) 壳住本地页面，无地址栏，观感即本地应用；
  未安装 pywebview / 缺 WebView2 / 窗口启动失败时**自动回退**浏览器。
  兼容旧写法：环境变量 VP_GUI=browser|web 等价于 --web，VP_GUI=gui 等价于 --gui；
  命令行参数优先于环境变量。打包版同理：VirusPlatform.exe --web 即浏览器模式。
  仅监听本机回环地址；长任务在后台线程执行，页面实时轮询进度。
  所有文件写入经由 utils.safe_open（路径校验+限平台内），os.startfile 前一律 check_path。

本文件只做「组装」——创建 Flask 应用、注册 blueprint、启动服务。
业务逻辑分两层：
  - Virus_Platform_Core/        计算与流程（pipeline / kunpeng / phylo / orf_annot …）
  - Virus_Platform_Core/web/    HTTP 边界与任务工厂（各 blueprint）
**请勿在 app.py 新增路由**；新路由写进 Virus_Platform_Core/web/ 对应模块，在此登记 blueprint。
"""
import os
import sys
import threading
import time
import webbrowser
# Windows 注册表把 .svg 关联成 MIME 类型 "image/svg"，而标准类型是
# "image/svg+xml"；Python 的 mimetypes 会照搬注册表，Flask 便以 image/svg
# 发出去，Chromium 直接拒绝解码（<img> 拿到 naturalWidth=0 的裂图）。
# 这里在造 Flask app 之前显式注册，全站 SVG 才能当图片显示
# （首页封面主视觉、⑨ 基因组图、示例结果都用 <img> 引 SVG）。
import mimetypes
mimetypes.add_type('image/svg+xml', '.svg')

from flask import Flask, abort, request
from flask.json.provider import DefaultJSONProvider

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

# 冻结分发下 multiprocessing（SDT 精确矩阵的 ProcessPoolExecutor 等）子进程
# 会重新启动 exe，必须在任何业务代码前调用 freeze_support 拦截子进程引导；
# 非冻结环境是空操作
if __name__ == '__main__':
    import multiprocessing
    multiprocessing.freeze_support()

# 冻结分发：primer3-py 的 pyd 在非 ASCII 安装路径下构造 ThermoAnalysis 会
# 直接段错误（同 sitecustomize 的镜像机制口径：源码模式把包镜像到
# %ALLUSERSPROFILE%\VirusPlatformPrimer3）。程序包自带 primer3_pkg/primer3
# 副本，启动时镜像到纯 ASCII 的用户公共目录并插入 sys.path——必须在任何
# 业务模块可能触发 primer3 导入之前完成。镜像失败仅影响引物热力学功能。
# ⚠️ 位置必须在下方 --run-engine / --cli 派发之前：--run-engine 跑 dsRNA T7
# 引物、--cli importprobe 子进程探测 primer3，两者都依赖镜像路径已入 sys.path。
if getattr(sys, 'frozen', False):
    try:
        _p3_src = os.path.join(os.path.dirname(sys.executable),
                               'primer3_pkg', 'primer3')
        if os.path.isdir(_p3_src):
            import shutil as _sh
            _p3_base = os.path.join(os.environ.get('ALLUSERSPROFILE',
                                                   r'C:\ProgramData'),
                                    'VirusPlatformPrimer3App')
            _p3_dst = os.path.join(_p3_base, 'primer3')
            _ver_src = os.path.join(os.path.dirname(_p3_src), 'VERSION.txt')
            _ver_dst = os.path.join(_p3_base, 'VERSION.txt')
            _need = not os.path.isdir(_p3_dst)
            # 旧版程序包漏带 primer3_config（热力学参数表）时镜像会完整但
            # 段错误 —— 检测到配置目录缺失也强制重镜像（自愈升级路径）
            if not _need and not os.path.isdir(
                    os.path.join(_p3_dst, 'src', 'libprimer3',
                                 'primer3_config')):
                _need = True
            try:
                if os.path.isfile(_ver_src) and os.path.isfile(_ver_dst) and \
                   open(_ver_src, 'rb').read() != open(_ver_dst, 'rb').read():
                    _need = True
            except OSError:
                pass
            if _need:
                _sh.rmtree(_p3_dst, ignore_errors=True)
                os.makedirs(_p3_base, exist_ok=True)
                _sh.copytree(_p3_src, _p3_dst)
                if os.path.isfile(_ver_src):
                    _sh.copyfile(_ver_src, _ver_dst)
            if _p3_base not in sys.path:
                sys.path.insert(0, _p3_base)
    except Exception:
        pass  # 镜像失败仅引物热力学功能降级，平台其余功能不受影响

# 冻结分发：`VirusPlatform.exe --run-engine <脚本名> [args...]` → 进程内执行引擎
if getattr(sys, 'frozen', False) and len(sys.argv) > 2 and sys.argv[1] == '--run-engine':
    from Virus_Platform_Core.engine_entry import run_engine
    raise SystemExit(run_engine(sys.argv[2]))

# 冻结分发：`VirusPlatform.exe --cli <子命令> [args...]` → 进程内跑 CLI
# （打包后没有 python，无法 `python main.py selfcheck`；这条给打包验证和
#  用户自检用，例如 `VirusPlatform.exe --cli selfcheck`）
if getattr(sys, 'frozen', False) and len(sys.argv) > 2 and sys.argv[1] == '--cli':
    import main as _cli
    sys.argv = ['main.py'] + sys.argv[2:]
    _cli.main()
    raise SystemExit(0)

# webapp 目录 / 配置单例 / tool_runs 根统一由 Virus_Platform_Core/web/state.py 提供，
# 各 blueprint 也从那里取，避免 app ↔ blueprint 循环导入。
from Virus_Platform_Core.web.state import _WWW  # noqa: E402

app = Flask(__name__, template_folder=os.path.join(_WWW, 'templates'),
            static_folder=os.path.join(_WWW, 'static'))
app.config['JSON_AS_ASCII'] = False
# 模板热重载：debug=False 下 Jinja2 默认缓存模板，改 .html 后需重启才生效；
# 打开后每次请求按 mtime 检测，本地平台开销可忽略，改模板即刷新可见。
app.config['TEMPLATES_AUTO_RELOAD'] = True

# NaN/±Inf 清洗的唯一实现（原随病毒浏览器归档，现收编进 utils.py）；
# 非 JSON 出口（/tool_runs 原样发文件）的落盘清洗见 web/tool_jobs._dump_json。
from Virus_Platform_Core.utils import nan_to_null as _nan_to_null  # noqa: E402


class _CleanJSONProvider(DefaultJSONProvider):
    """全局 JSON 出口：清洗 NaN/±Inf 后再序列化（平台 JSON 铁律）。

    Flask 默认放行裸 `NaN`（`allow_nan=True`）——那是**非法 JSON**：
    Python 端 json.loads 能容忍（本地自测假通过），浏览器 JSON.parse 直接
    报错、整份响应被丢弃。来源多为空集合求均值/占比（pandas 聚合）。
    这里统一把 NaN/±Inf 换成 null，并以 `allow_nan=False` 兜底：若还有
    漏网之鱼会带类型报错，而不是静默产出非法 JSON。
    """

    ensure_ascii = False

    def default(self, o):
        try:
            return super().default(o)
        except TypeError:
            if hasattr(o, 'tolist'):        # numpy 数组
                return o.tolist()
            if hasattr(o, 'item'):          # numpy 标量
                return o.item()
            raise

    def dumps(self, obj, **kwargs):
        kwargs.setdefault('allow_nan', False)
        return super().dumps(_nan_to_null(obj), **kwargs)


app.json = _CleanJSONProvider(app)


# ------------------------------------------------------------------
# 本地 CSRF / DNS-rebinding 防护
# 服务只监听 127.0.0.1，但这挡不住两类远程攻击：
#   1) CSRF：用户浏览器里的任意恶意网页可静默 POST http://127.0.0.1:<port>
#      （删样品、全局重置、改设置…），响应虽不可读，破坏已经生效；
#   2) DNS rebinding：攻击者域名解析到 127.0.0.1 后，同源策略即被绕过，
#      恶意页面可读取响应（任意文件浏览/序列查看 → 数据外泄）。
# 两道校验（对每个请求，纯头部判断，开销可忽略）：
#   ① Host 必须是回环主机名 —— rebinding 时 Host 是攻击者域名，直接 403；
#   ② 带 Origin/Referer 的请求必须同源 —— 浏览器跨站 POST 必带 Origin，
#      恶意网页驱动不了任何端点。非浏览器客户端（curl/本机脚本）不带
#      Origin/Referer，正常放行。
# ------------------------------------------------------------------
_LOOPBACK_HOSTS = {'127.0.0.1', 'localhost', '::1'}


def _url_hostname(v):
    try:
        from urllib.parse import urlparse
        return (urlparse(v).hostname or '').lower()
    except ValueError:
        return ''


@app.before_request
def _guard_local_origin():
    host_hdr = (request.host or '') if request else ''
    if host_hdr:
        hostname = host_hdr.rsplit(':', 1)[0].strip('[]').lower()
        if hostname and hostname not in _LOOPBACK_HOSTS:
            abort(403, '仅允许通过本机回环地址访问平台')
    origin = request.headers.get('Origin') or ''
    if origin:
        # 浏览器对同源 POST 也带 Origin（与 Host 同源则放行）
        if _url_hostname(origin) not in _LOOPBACK_HOSTS:
            abort(403, '已拦截跨站请求（Origin 校验失败）')
    else:
        referer = request.headers.get('Referer') or ''
        if referer and _url_hostname(referer) not in _LOOPBACK_HOSTS:
            abort(403, '已拦截跨站请求（Referer 校验失败）')

# ------------------------------------------------------------------
# Blueprint 注册
# 路由清单守卫：python tests/_route_inventory.py
#（锁定 179 条 rule + methods，拆分/新增后必须零差异）
# ------------------------------------------------------------------
from Virus_Platform_Core.web import (  # noqa: E402
    build as _bp_build,
    cds_export as _bp_cds_export,
    download as _bp_download,
    examples_api as _bp_examples,
    io_api as _bp_io,
    logan as _bp_logan,
    meta as _bp_meta,
    pages as _bp_pages,
    refs as _bp_refs,
    samples as _bp_samples,
    settings as _bp_settings,
    submit as _bp_submit,
    tasks_api as _bp_tasks,
    tool_results as _bp_tool_results,
    tools_api as _bp_tools,
    virome as _bp_virome,
)

# 顺序与拆分前的 app.py 区块顺序一致（便于对照回溯）
#
# 2026-09-17：病毒浏览器（explorer）蓝图停止挂载 —— 平台不再提供 /explorer
# 页面与 /api/explorer/* 接口。
# 2026-09-27：**彻底归档** —— 引擎（Virus_Platform_Core/explorer/）、蓝图
# （web/explorer.py）、页面（explorer.html / app-explorer.js）、专属测试与
# 运行数据（run/explorer_exports、run/explorer_variation）全部移入
# archive/_retire_20260927/explorer/，代码与数据在本仓不再保留活动副本。
# 注意：app.py 的 JSON 清洗器原从 web/explorer.py 借 _nan_to_null（每个
# JSON 响应都走它）——现已内联为本文件顶部的 _nan_to_null，无外部依赖。
for _bp in (_bp_pages, _bp_tool_results, _bp_refs, _bp_logan, _bp_io,
            _bp_samples, _bp_download, _bp_submit, _bp_meta,
            _bp_settings, _bp_virome, _bp_tools, _bp_tasks, _bp_build,
            _bp_examples, _bp_cds_export):
    app.register_blueprint(_bp.bp)
del _bp


# 把不带 TaskManager 执行的子系统接进任务中心（统一列表/进度/停止/前往）：
# 下载批次（DownloadManager 自建线程）。执行仍归各自子系统，这里只是
# 注册 provider 回调做状态镜像；详见 web/download.py:bind_downloads。
from Virus_Platform_Core.web.download import bind_downloads as _bind_downloads  # noqa: E402
_bind_downloads()


# ------------------------------------------------------------------
# 兼容别名：app.py 拆分到 Virus_Platform_Core/web/ 之前，这些名字挂在 app 模块上，
# 仓库内测试（tests/_it_*.py、test_logan_trace.py）与外部脚本仍按老写法
# 引用（app.tm / app._KEEP_TOTAL / app._resolve_virus_db）。
# 这里只做转发，真实定义仍在各自模块，避免复制状态。
# ------------------------------------------------------------------
from Virus_Platform_Core.web.tasks import tm as tm  # noqa: E402,F401
from Virus_Platform_Core.web.tasks import _KEEP_TOTAL as _KEEP_TOTAL  # noqa: E402,F401
from Virus_Platform_Core.web.tools_api import _resolve_virus_db as _resolve_virus_db  # noqa: E402,F401


# ------------------------------------------------------------------
# 启动
# ------------------------------------------------------------------
def _pick_port():
    """选择可绑定的端口。

    Windows 上 Hyper-V/WSL 会动态保留端口段（netsh 可见），
    固定端口可能被系统排除导致 bind 被拒（访问权限不允许），
    因此逐个探测候选端口，全部失败再随机尝试。
    """
    import socket
    candidates = [8765, 8900, 8989, 9600, 8888, 5050, 5000]
    for p in candidates:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                return p
        except OSError:
            continue
    import random
    for _ in range(30):
        p = random.randint(10000, 19999)
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(('127.0.0.1', p))
                return p
        except OSError:
            continue
    raise RuntimeError('未找到可用的本地端口，请关闭占用端口的程序后重试')


def _open_browser(url):
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def _start_server(port):
    """在后台线程起 Flask，返回已绑定端口的 server 句柄。

    为什么不用 app.run：它会阻塞主线程，而 pywebview 的窗口必须开在主线程；
    换到后台线程后主线程才能建窗口，且拿到 server 句柄，窗口关闭时可停机。
    make_server 同步完成 bind，返回即意味着地址可访问，窗口首开不会白屏。
    """
    from werkzeug.serving import make_server
    srv = make_server('127.0.0.1', port, app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _gui_mode():
    """启动模式：'gui'（独立桌面窗口）| 'web'（系统浏览器）。

    优先级：命令行 `--web`/`--browser` 或 `--gui` > 环境变量 VP_GUI > 默认 gui。
    为什么要有命令行开关：原先只能用 `set VP_GUI=browser` 切模式，双击 .bat
    的人没有入口；打包后的 exe 也一样（`VirusPlatform.exe --web` 即可）。
    gui 模式下若 pywebview/WebView2 不可用，仍会自动回退浏览器（见 _open_window）。
    """
    for raw in sys.argv[1:]:
        a = raw.strip().lower()
        if a in ('--web', '--browser', '--no-gui'):
            return 'web'
        if a in ('--gui', '--window', '--webview'):
            return 'gui'
    v = os.environ.get('VP_GUI', '').strip().lower()
    if v in ('browser', 'web'):
        return 'web'
    if v in ('gui', 'window', 'webview'):
        return 'gui'
    return 'gui'


def _open_window(url, mode='gui'):
    """pywebview 独立桌面窗口（壳住本地页面，无浏览器地址栏）。

    返回 True=窗口已开过并关闭（进程应退出）；False=pywebview 不可用或
    指定了网页模式，调用方回退浏览器。Windows 固定 edgechromium 后端：
    系统缺 WebView2 运行时就走回退，绝不静默掉到老旧的 mshtml
    （IE 内核渲染会烂）。
    """
    if mode == 'web':
        return False
    try:
        import webview
    except Exception:
        print('  [提示] 未安装 pywebview，回退浏览器模式'
              '（pip install pywebview 后即为独立窗口）')
        return False
    try:
        webview.create_window('植物病毒分析平台', url,
                              width=1440, height=900, min_size=(1080, 700))
        webview.start(gui='edgechromium' if sys.platform == 'win32' else None)
        return True
    except Exception as e:
        print(f'  [提示] 桌面窗口启动失败（{type(e).__name__}: {e}），'
              f'回退浏览器模式')
        return False


def main():
    mode = _gui_mode()
    try:
        port = _pick_port()
    except RuntimeError as e:
        print(f'  [错误] {e}')
        input('按回车键退出...')
        return
    url = f'http://127.0.0.1:{port}'
    print('=' * 56)
    print('  植物病毒分析平台 启动中...'
          f'（模式: {"独立桌面窗口" if mode == "gui" else "系统浏览器"}）')
    print(f'  本机地址: {url}')
    if port != 8765:
        print(f'  （默认端口 8765 被系统占用/保留，已自动改用 {port}）')
    print('  关闭窗口/控制台即退出平台'
          if mode == 'gui' else
          '  平台在本控制台窗口内运行，关闭它即退出')
    print('=' * 56)
    try:
        srv = _start_server(port)
    except OSError as e:
        print(f'\n  [错误] 端口 {port} 监听失败: {e}')
        print('  可在管理员 PowerShell 运行以下命令查看被系统保留的端口段:')
        print('     netsh interface ipv4 show excludedportrange protocol=tcp')
        input('按回车键退出...')
        return
    try:
        if _open_window(url, mode):
            print('  桌面窗口已关闭，平台退出。')
            return
        # 浏览器模式：显式 --web / VP_GUI=browser，或 gui 模式但窗口不可用时回退
        if mode == 'gui':
            print('  （已回退浏览器模式；如需固定用网页模式，'
                  '下次用 启动平台-网页.bat 或 python app.py --web）')
        threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
        while True:
            time.sleep(3600)    # 关闭本控制台窗口即退出（守护线程随之终止）
    except KeyboardInterrupt:
        print('\n  收到退出信号，平台关闭。')
    finally:
        try:
            srv.shutdown()
        except Exception:
            pass


if __name__ == '__main__':
    main()
