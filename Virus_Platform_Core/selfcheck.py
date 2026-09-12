# -*- coding: utf-8 -*-
"""环境自检（结构化版）：模块导入 / 外部工具 / 数据库 / 磁盘空间。

collect() 返回四段结构化结果，供两处共用：
  - web API /api/selfcheck（设置页「环境自检」卡片 + 总览页环境状态条）
  - main.py selfcheck（CLI 控制台版，另带 ⑤样品 / ⑥依赖 两段 CLI 专属检查）

结果按进程缓存（CACHE_TTL 秒内直接复用）：首次收集要递归 import 全部 80+
子模块，实测数秒；此后模块都已进 sys.modules，force=True 重跑也很快。
整体 ok 的口径与 CLI 一致：模块导入与数据库失败才算失败；工具缺失只算
降级（warn），磁盘不足只提示。
"""
import importlib
import shutil
import time

from Virus_Platform_Core.config import DIRS, PLATFORM_ROOT, get_config

CACHE_TTL = 300.0          # 缓存有效期（秒）；设置页按钮走 force=1 强制重跑
DISK_WARN_BYTES = 10e9     # 磁盘剩余低于此值提示（与 CLI 自检同一口径）
_CACHE = {'ts': 0.0, 'data': None}


def iter_platform_modules():
    """枚举 Virus_Platform_Core 下的全部子模块（递归含子包）。

    返回 (模块名列表, 遍历期导入失败的子包名列表)。

    为什么遍历而不是硬编码清单：原先自检只 import 16 个写死的模块，而平台有
    80+ 个。**走子进程调用的引擎不在其中** —— kv 引擎由 kv_stage 以子进程启动
    （`--run-engine`），kv_stage 本身只 import config/utils，于是 kv_filter /
    kv_identify 在模块级的 `import polars` 缺失时，自检完全看不见。
    2026-09-11 就是这个盲区让「已知病毒识别与定量」整段静默失效。

    冻结分发下靠 PyInstaller 的 `pyi_rth_pkgutil` 运行时钩子让 pkgutil 可用，
    打包后同样能遍历。遍历本身若失败（返回空列表），调用方回退到手工清单。
    """
    import pkgutil
    mods, errs = [], []
    try:
        import Virus_Platform_Core as _pkg
        for info in pkgutil.walk_packages(
                _pkg.__path__, _pkg.__name__ + '.',
                onerror=lambda n: errs.append(n)):
            if not info.ispkg:
                mods.append(info.name)
    except Exception as e:
        errs.append(f'<遍历失败: {e!r}>')
    return sorted(set(mods)), errs


# 遍历不可用时的兜底清单（原 CLI 内联清单，保持一致）
FALLBACK_MODULES = [
    'Virus_Platform_Core.config', 'Virus_Platform_Core.utils',
    'Virus_Platform_Core.taxonomy', 'Virus_Platform_Core.kunpeng',
    'Virus_Platform_Core.preprocess',
    'Virus_Platform_Core.host_removal',
    'Virus_Platform_Core.kv_stage', 'Virus_Platform_Core.assembly',
    'Virus_Platform_Core.host_analysis', 'Virus_Platform_Core.orf',
    'Virus_Platform_Core.orf_annot', 'Virus_Platform_Core.phylo',
    'Virus_Platform_Core.primer', 'Virus_Platform_Core.viz',
    'Virus_Platform_Core.pipeline', 'Virus_Platform_Core.msa_view',
]


def _check_modules():
    mods, walk_errs = iter_platform_modules()
    if not mods:
        mods = FALLBACK_MODULES
    total = len(mods) + len(walk_errs)
    t0 = time.time()
    fails = []
    for m in mods:
        try:
            importlib.import_module(m)
        except Exception as e:
            fails.append((m, repr(e)))
    for n in walk_errs:                # 遍历阶段就导不进来的子包（如缺依赖）
        fails.append((n + '.*', '子包导入失败，其下模块未能枚举'))
    return {'id': 'modules', 'title': '模块导入',
            'ok': not fails, 'warn': False,
            'summary': f'{total - len(fails)}/{total}',
            'seconds': round(time.time() - t0, 1),
            # 只列失败明细：86 个模块名全量回传没有信息量
            'items': [{'name': m, 'ok': False, 'detail': e}
                      for m, e in fails]}


def _check_tools():
    cfg = get_config()
    st = cfg.tool_status()
    missing = sorted(k for k, v in st.items() if not v)
    return {'id': 'tools', 'title': '外部工具',
            'ok': not missing, 'warn': bool(missing),
            'summary': f'{len(st) - len(missing)}/{len(st)}',
            'missing': missing}
    # 工具逐项明细不重复给：设置页上方「工具探测」卡片已有同源列表


def _check_databases():
    from Virus_Platform_Core.config import host_db_info
    from Virus_Platform_Core.kunpeng import db_ready
    from Virus_Platform_Core.taxonomy import taxonomy_ready
    cfg = get_config()
    items = [{'name': 'NCBI Taxonomy', 'ok': bool(taxonomy_ready())}]
    for key, label in (('host', '宿主库 host_db'),
                       ('virus', '病毒库 virus_db')):
        ok = bool(db_ready(cfg.databases[key]))
        item = {'name': label, 'ok': ok, 'detail': cfg.databases[key]}
        if key == 'host':
            # 宿主库"是谁"必须可见：库本体不记录物种，历史上出过
            # "目录名是枸杞、库却按 4081 番茄建"的事故，用错宿主是静默的。
            h = host_db_info(cfg.databases[key])
            if h:
                who = (f"{h.get('species')} (taxid={h.get('taxid')})"
                       if h.get('taxid') else '身份未记录')
                item['detail'] = f"{h.get('name')} | 物种 = {who}"
                if h.get('conflicted'):
                    item['detail'] += (' | ⚠ 元数据冲突 '
                                       f"{h.get('taxids_in_map')}")
        items.append(item)
    return {'id': 'databases', 'title': '数据库',
            'ok': all(i['ok'] for i in items), 'warn': False,
            'summary': f"{sum(i['ok'] for i in items)}/{len(items)}",
            'items': items}


def _check_disk():
    items = []
    for key, d in (('平台根', PLATFORM_ROOT), ('结果', DIRS['results'])):
        try:
            free = shutil.disk_usage(d).free
            items.append({'name': key, 'ok': free > DISK_WARN_BYTES,
                          'detail': f'剩余 {free / 1e9:.1f} GB'
                                    + ('' if free > DISK_WARN_BYTES
                                       else '（建议保留 >10GB）')})
        except OSError as e:
            items.append({'name': key, 'ok': False, 'detail': str(e)})
    return {'id': 'disk', 'title': '磁盘空间',
            'ok': all(i['ok'] for i in items),
            'warn': any(not i['ok'] for i in items),
            'summary': f"{sum(i['ok'] for i in items)}/{len(items)}",
            'items': items}


def collect(force=False):
    """跑一遍四段自检并返回结构化 dict；进程内缓存 CACHE_TTL 秒。

    返回形如：{'ok': bool, 'seconds': 3.2, 'cached': False,
               'sections': [ {id,title,ok,warn,summary,items?}, ... ]}
    """
    now = time.time()
    if (not force and _CACHE['data'] is not None
            and now - _CACHE['ts'] < CACHE_TTL):
        data = dict(_CACHE['data'])
        data['cached'] = True
        return data
    t0 = time.time()
    sections = [_check_modules(), _check_tools(),
                _check_databases(), _check_disk()]
    # 整体口径与 CLI 一致：模块导入与数据库失败才算失败（工具缺失=降级、
    # 磁盘不足=提示，都不算失败）
    modules, databases = sections[0], sections[2]
    data = {'ok': bool(modules['ok'] and databases['ok']),
            'seconds': round(time.time() - t0, 1),
            'ts': now, 'cached': False, 'sections': sections}
    _CACHE['ts'], _CACHE['data'] = now, data
    return data
