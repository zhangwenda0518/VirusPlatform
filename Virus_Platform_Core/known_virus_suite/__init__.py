# -*- coding: utf-8 -*-
"""known_virus_suite — 已知病毒识别与定量引擎（五段整合）。

由 MMPV-RNA virome_analysis_pipeline 复制改造，作为 Virus_Platform_Core
的子包（2026-09-10 由顶层 engines/known_virus_suite/ 迁入，见 commit）。

五段流程（可单独调用，也可一键全跑）：
  鉴定 → 过滤 → 共识 → 变异 → 绘图

入口：
  - 命令行 : python -m Virus_Platform_Core.known_virus_suite.known_virus_suite
             （原 `python known_virus_suite.py`；包内改用相对导入后
              直接跑脚本文件不再可行，请用 -m 形式）
  - Web 端 : Virus_Platform_Core/web/build.py 从本子包导入

引擎分工固定：定量（identify）只用 salmon（kv_engines.py 的 SalmonEngine，
--writeBam 出映射位点）；共识段内部固定 minibwa 真比对（kv_consensus.py）。
"""
