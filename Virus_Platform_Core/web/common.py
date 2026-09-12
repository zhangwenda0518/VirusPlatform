# -*- coding: utf-8 -*-
"""Web 层共用小工具（多 blueprint 共享，自 app.py 拆出）。"""


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
