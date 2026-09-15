# -*- coding: utf-8 -*-
"""Explorer（病毒浏览器）计算层。

移植自服务器部署版 `virus_explorer/app.py`（Dash 应用），剥离 Dash 外壳与
回调装饰器后由 `web/explorer.py` 的 Flask 路由驱动。详见 `engine.py` 模块头。

    paths.py    数据根解析（databases/explorer/，可用 VP_EXPLORER_DATA 外置）
    shim.py     Dash/Mantine 组件的最小 HTML 渲染替身
    engine.py   计算引擎（数据加载 / 比对矩阵 / 图表构建 / 面板聚合）
"""
