# -*- coding: utf-8 -*-
"""冻结分发专用：进程启动最早点预载 ViennaRNA(RNA)。

为什么需要（2026-09-18 排查结论）：
  RNA 包的 __init__ 用 `except: raise ImportError(...)` 掩盖真实错误；
  经探针逐层复现，在完整应用里 _RNA.pyd 的 DllMain 会报「初始化例程失败」
  —— 依赖解析全部正常（MSVCP140 已随包，见 spec 的 _binaries），失败与
  **加载时机**相关：dsrna_* 在 web 全栈导入之后才首次 import RNA 就会挂，
  在进程最早期 import 则必成功（多轮 PyInstaller 探针实证）。
  因此用 runtime hook 在引导期预载，绕开时机问题。源码模式不需要本钩子
  （System32 的运行库无冲突）。若未来 RNA 包修复或换版本，可重测后移除。
"""

import RNA  # noqa: F401
