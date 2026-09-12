# -*- coding: utf-8 -*-
"""CDS / PEP 提取产物 API（独立模块）。

页面：/cds-export
接口：/api/cds/table · /api/cds/selection/save · /api/cds/export

业务逻辑在 Virus_Platform_Core.cds_export（单向依赖 Virus_Platform_Core.gb_collection 的集合基础设施）。
"""
from flask import Blueprint, abort, jsonify, request

bp = Blueprint('cds_export', __name__)


@bp.route('/api/cds/table')
def api_cds_table():
    """某集合的 CDS 明细表（人工挑选界面用）。

    返回 rows / viruses / families / genera，外加已保存的选择状态。
    """
    name = (request.args.get('name') or '').strip()
    if not name:
        abort(400, '参数不完整（name 必填）')
    from Virus_Platform_Core.cds_export import build_cds_table, load_selection
    try:
        data = build_cds_table(name)
    except FileNotFoundError as e:
        abort(404, str(e))
    data['selection'] = load_selection(name)
    return jsonify(data)


@bp.route('/api/cds/selection/save', methods=['POST'])
def api_cds_selection_save():
    """body: {name, items:[{rid, gene}]} → 保存人工挑选状态。"""
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        abort(400, '参数不完整（name 必填）')
    from Virus_Platform_Core.cds_export import save_selection
    try:
        data = save_selection(name, body.get('items') or [])
    except FileNotFoundError as e:
        abort(404, str(e))
    return jsonify(data)


@bp.route('/api/cds/export', methods=['POST'])
def api_cds_export():
    """body: {name, items:[{rid, gene}], async:bool} → 按基因名归组导出 CDS + PEP。

    async=True（页面用）：导出要重新全量解析集合的每个 .gb 并对缺 translation
    的 CDS 现场翻译，科级集合是分钟级；改后台任务后可在任务中心看进度与取消。
    结果字段少且扁平，直接由任务结果预览带回（n_cds/n_pep/genes/dir/missing
    都是标量或可由前端忽略的列表）。
    """
    body = request.get_json(force=True) or {}
    name = (body.get('name') or '').strip()
    if not name:
        abort(400, '参数不完整（name 必填）')
    items = body.get('items') or []
    from Virus_Platform_Core.cds_export import export_selected, save_selection
    if body.get('async'):
        from Virus_Platform_Core.web.tasks import tm
        from Virus_Platform_Core.web.state import cfg as _cfg

        def job(log, prog, cancel):
            prog('export', 0.02, f'解析集合并导出 {len(items)} 条选中 CDS')
            if log:
                log(f'集合 {name}：选中 {len(items)} 条')
            # export_selected 的 prog 就是 (stage, frac, msg) 三参口径，直接透传
            res = export_selected(name, items, prog=prog)
            if cancel.is_set():
                raise RuntimeError('任务已停止（用户取消）')
            try:
                save_selection(name, items)
            except Exception:
                pass
            prog('done', 1.0, f"导出 {res.get('n_cds', 0)} 条 CDS")
            # 只回标量：结果预览只保留标量字段，且 _persist 会把返回值原样
            # 落进 tasks/<tid>.json——把 genes/missing 列表带进去既没用又涨盘。
            return {'n_cds': res.get('n_cds', 0), 'n_pep': res.get('n_pep', 0),
                    'n_genes': len(res.get('genes') or []),
                    'n_missing': len(res.get('missing') or []),
                    'dir': res.get('dir'), 'tsv': res.get('tsv')}

        tid = tm.start(_cfg.tr(f'CDS/PEP 导出·{name}', f'CDS/PEP export·{name}'),
                       job, weight='light', link='/cds-export')
        return jsonify({'ok': True, 'task': tid})
    try:
        res = export_selected(name, items)
    except FileNotFoundError as e:
        abort(404, str(e))
    except ValueError as e:
        abort(400, str(e))
    try:                      # 导出即落盘选择状态，下次打开可恢复
        save_selection(name, items)
    except Exception:
        pass
    return jsonify(res)
