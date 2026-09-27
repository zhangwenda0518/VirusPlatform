# -*- coding: utf-8 -*-
"""Web 层共用小工具（多 blueprint 共享，自 app.py 拆出）。"""
import json
import os

# 「进化树 + 基因组叠加」数据约定：叠加 JSON 与树文件**同目录同名**
# （tree.nwk → tree.overlay.json），内容见 archaeopteryx.js 的 genomeOverlay：
# {tracks:[{name, acc?, genus?, length?, genes:[{id?, start, end, strand?,
#  product?, cid?}]}], links:[{q, t, ident?}]}（ident 0-1 或 0-100 均可）。
# 树查看器只认这一个位置，缺文件即"没有叠加"，树照常渲染。
TREE_OVERLAY_EXT = '.overlay.json'
_TREE_OVERLAY_MAX_BYTES = 16 * 1024 * 1024


def tree_overlay_for(nwk_path):
    """树文件 → 叠加数据 dict；缺失/损坏/过大一律返回 None（绝不让树打不开）。

    叠加 JSON 是**可选**产物：读不动就当没有，界面上少一层轨道图，
    而不是把整个树查看卡变成报错。
    """
    p = os.path.splitext(str(nwk_path))[0] + TREE_OVERLAY_EXT
    try:
        if not os.path.isfile(p) or os.path.getsize(p) > _TREE_OVERLAY_MAX_BYTES:
            return None
        with open(p, encoding='utf-8') as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get('tracks'):
        return None
    return data


def _safe_sample(sample, base=None):
    """把请求里的样品名解析为磁盘上真实存在的样品目录名。

    历史问题：本函数原先只做"逐字符替换非法字符"，而建目录走
    pipeline._safe_sample_name（连续非法字符折叠成一个 '_'、去首尾、截断 50）。
    两套口径对中文/连续特殊字符/超长名不一致：样品名「样品A」建成目录 `A`，
    读路径却去找 `__A` → 读不到自己刚建的样品。

    现在统一委托 utils.resolve_sample_name：以磁盘真实目录名为准
    （原名命中就原样用，兼容手工创建/历史遗留/中文目录），
    未命中才退回规范名。路径越界仍由 check_path(in_platform=True) 兜底。

    base: 样品目录的父目录，缺省为 results/。
          归档样品报告要传 results/_archive（那里的目录名不在 results/ 下）。
    """
    from Virus_Platform_Core.utils import resolve_sample_name
    return resolve_sample_name(sample, base=base)
