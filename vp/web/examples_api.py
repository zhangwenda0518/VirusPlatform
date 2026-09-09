# -*- coding: utf-8 -*-
"""示例结果 API（阶段 C）：只读暴露 databases/examples/results/<模块>/。

与真实结果彻底隔离 —— 不读 tool_runs/ 也不读 results/，只读示例目录；
目录内容由 tests/make_example_results.py 生成并写 manifest.json。

路由：
    GET /api/examples                     清单（含各模块标题与产物文件）
    GET /api/examples/<module>            单模块详情（含可预览文件的文本/尺寸）
    GET /api/examples/<module>/<path>     取单个产物文件（图片/表格/JSON）
"""
import json
import os

from flask import Blueprint, abort, jsonify, send_file

from vp.config import PLATFORM_ROOT
from vp.utils import check_path

bp = Blueprint('examples', __name__)

EXR = os.path.join(PLATFORM_ROOT, 'databases', 'examples', 'results')

# 可内联预览的文本类扩展名（其余按下载/图片处理）
_TEXT_EXT = {'.json', '.tsv', '.csv', '.txt', '.md', '.nwk', '.gff', '.gff3',
             '.fasta', '.fa', '.fna', '.faa', '.ffn', '.aln', '.newick'}
_IMG_EXT = {'.png', '.jpg', '.jpeg', '.svg', '.webp', '.gif', '.pdf'}


def _manifest():
    p = os.path.join(EXR, 'manifest.json')
    if not os.path.isfile(p):
        return {}
    try:
        with open(p, encoding='utf-8') as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _module_dir(module):
    """模块目录（白名单校验，防路径注入）。"""
    import re
    if not re.fullmatch(r'[A-Za-z0-9_\-]{1,40}', str(module)):
        abort(400, '无效的模块名')
    d = os.path.join(EXR, module)
    if not os.path.isdir(d):
        abort(404, f'示例结果不存在: {module}')
    return check_path(d, must_exist=True, in_platform=True)


def _kind(name):
    e = os.path.splitext(name)[1].lower()
    if e in _IMG_EXT:
        return 'image'
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
            if fn == 'manifest.json':
                continue
            rel = os.path.relpath(os.path.join(cur, fn), d).replace('\\', '/')
            size = os.path.getsize(os.path.join(cur, fn))
            files.append({'path': rel, 'size': size, 'kind': _kind(rel)})
    files.sort(key=lambda x: (x['kind'] != 'image', x['path']))
    return jsonify({'module': module, 'title': man.get('title', module),
                    'run': man.get('run', ''),
                    'generated_at': man.get('generated_at', ''),
                    'files': files})


@bp.route('/api/examples/<module>/<path:filename>')
def api_example_file(module, filename):
    """取示例结果的单个产物（只读）。"""
    d = _module_dir(module)
    p = check_path(os.path.join(d, filename), must_exist=True, in_platform=True)
    if not os.path.isfile(p):
        abort(404, '文件不存在')
    return send_file(p)
