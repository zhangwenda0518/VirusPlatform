# -*- coding: utf-8 -*-
"""pytest 共享引导：把平台根加进 sys.path，保证 `from Virus_Platform_Core...`
与 `import app` 在任何工作目录下运行 pytest 都能导入。
（tests/ 内既有脚本各自做 sys.path.insert，这里只是给规范的 test_*.py 兜底。）
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
