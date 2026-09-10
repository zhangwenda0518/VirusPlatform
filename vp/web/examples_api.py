# -*- coding: utf-8 -*-
"""示例结果 API（阶段 C）：只读暴露 <示例根>/results/<模块>/。

与真实结果彻底隔离 —— 不读 tool_runs/ 也不读 results/，只读示例目录；
目录内容由 tests/make_example_results.py 生成并写 manifest.json。

示例根来自 `DIRS['examples']`（vp/config.py）：默认 <程序>/examples，
可用 platform.json 的 examples_root 指向程序目录之外（程序 / 数据库 / 示例
三分离打包），启动时也会自动探测同级的 VirusPlatform-Examples/。

路由：
    GET /api/examples                     清单（含各模块标题与产物文件）
    GET /api/examples/<module>            单模块详情（含可预览文件的文本/尺寸）
    GET /api/examples/<module>/<path>     取单个产物文件（图片/表格/JSON）
    GET /api/example_input/<path:name>    取示例输入文件（只读）
    GET /api/example_paths                示例输入的**绝对路径**表（前端填框用）
"""
import json
import os

from flask import Blueprint, abort, jsonify, send_file

from vp.config import DIRS, PLATFORM_ROOT

bp = Blueprint('examples', __name__)


def _exr():
    """示例结果根（每次读取，支持运行期切换示例根）。"""
    return os.path.join(DIRS.get('examples') or
                        os.path.join(PLATFORM_ROOT, 'examples'),
                        'results')


def _ex_in():
    return DIRS.get('examples') or os.path.join(PLATFORM_ROOT, 'databases',
                                                'examples')

# 可内联预览的文本类扩展名（其余按下载/图片处理）
_TEXT_EXT = {'.json', '.tsv', '.csv', '.txt', '.md', '.nwk', '.gff', '.gff3',
             '.fasta', '.fa', '.fna', '.faa', '.ffn', '.aln', '.newick',
             '.vcf', '.log', '.kreport2'}
_IMG_EXT = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif'}
# 可 iframe 内联渲染的报告类（LOGAN 溯源报告等）
_HTML_EXT = {'.html', '.htm'}
# PDF 不能当 <img> 渲染（浏览器把它当 0×0 → 显示裂图）；单列一类走内嵌查看器
_PDF_EXT = {'.pdf'}


def _manifest():
    p = os.path.join(_exr(), 'manifest.json')
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _within(root, path):
    """path 是否位于 root 内（示例根可能在平台目录之外，故不能只用
    check_path(in_platform=True)）。"""
    root = os.path.normpath(os.path.abspath(root))
    p = os.path.normpath(os.path.abspath(path))
    return p == root or p.startswith(root + os.sep)


def _module_dir(module):
    """模块目录（白名单校验，防路径注入）。"""
    import re
    if not re.fullmatch(r'[A-Za-z0-9_\-]{1,40}', str(module)):
        abort(400, '无效的模块名')
    root = _exr()
    d = os.path.join(root, module)
    if not os.path.isdir(d) or not _within(root, d):
        abort(404, f'示例结果不存在: {module}')
    return os.path.normpath(os.path.abspath(d))


def _kind(name):
    e = os.path.splitext(name)[1].lower()
    if e in _IMG_EXT:
        return 'image'
    if e in _PDF_EXT:
        return 'pdf'
    if e in _HTML_EXT:
        return 'html'
    if e in _TEXT_EXT:
        return 'text'
    return 'other'


@bp.route('/api/examples')
def api_examples():
    """示例结果清单：{module: {title, run, files, ...}}。"""
    man = _manifest()
    out = []
    for module in sorted(man):
        e = man[module]
        out.append({'module': module, 'title': e.get('title', module),
                    'run': e.get('run', ''), 'n_files': len(e.get('files', [])),
                    'generated_at': e.get('generated_at', '')})
    return jsonify(out)


@bp.route('/api/examples/<module>')
def api_example(module):
    """单模块详情：产物文件清单 + 文本类内容（截断）与图片尺寸。"""
    d = _module_dir(module)
    man = _manifest().get(module) or {}
    files = []
    for cur, _dirs, fs in os.walk(d):
        for fn in sorted(fs):
            if fn == 'manifest.json' or fn.startswith('.'):
                continue
            rel = os.path.relpath(os.path.join(cur, fn), d).replace('\\', '/')
            size = os.path.getsize(os.path.join(cur, fn))
            files.append({'path': rel, 'size': size, 'kind': _kind(rel)})
    _order = {'image': 0, 'pdf': 1, 'html': 2, 'text': 3, 'other': 4}
    files.sort(key=lambda x: (_order.get(x['kind'], 9), x['path']))
    return jsonify({'module': module, 'title': man.get('title', module),
                    'run': man.get('run', ''),
                    'generated_at': man.get('generated_at', ''),
                    'files': files})


@bp.route('/api/example_input/<path:name>')
def api_example_input(name):
    """取示例**输入**文件（<示例根>/ 下，只读）。

    前端「✨ 示例」需要把示例 FASTA 正文填进 textarea（CDD / BLAST 走粘贴入口、
    LOGAN 粘贴框），而 databases/ 不经 HTTP 暴露，故单开只读路由。
    """
    root = _ex_in()
    p = os.path.join(root, name)
    # 示例根可能位于平台目录之外，故用「根内前缀」校验而非
    # check_path(in_platform=True)（后者只认平台/输出根）。
    if not _within(root, p) or not os.path.isfile(p):
        abort(404, '示例输入不存在')
    return send_file(os.path.normpath(os.path.abspath(p)))


@bp.route('/api/example_paths')
def api_example_paths():
    """示例输入文件的绝对路径表：{文件名: 绝对路径}。

    前端「✨ 示例」按钮填的是**路径字符串**，后端再按它取文件。示例目录
    可能位于程序目录之外（三分离打包），相对路径 `examples/x`
    就不成立了，故由服务端给出真实绝对路径。
    """
    root = _ex_in()
    out = {}
    if os.path.isdir(root):
        for fn in sorted(os.listdir(root)):
            p = os.path.join(root, fn)
            if os.path.isfile(p):
                out[fn] = p
    return jsonify({'root': root, 'files': out})


@bp.route('/api/examples/<module>/<path:filename>')
def api_example_file(module, filename):
    """取示例结果的单个产物（只读）。"""
    d = _module_dir(module)
    p = os.path.join(d, filename)
    if not _within(d, p) or not os.path.isfile(p):
        abort(404, '文件不存在')
    return send_file(os.path.normpath(os.path.abspath(p)))
