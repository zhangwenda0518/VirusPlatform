# -*- coding: utf-8 -*-
"""拖拽代理 —— 桌面悬浮窗：把资源管理器拖入的文件路径直送平台输入框。

浏览器安全模型拿不到拖拽文件的本机路径（只会复制内容到 run/uploads/）；
这个小代理补上这一环：从资源管理器拖文件到悬浮窗 → 真实路径经本机
HTTP 直送平台 → 平台自动填入「最后点过的输入框」（零拷贝，不复制文件）。

用法：
  python scripts/drag_proxy.py [--port 8765] [--host 127.0.0.1]

依赖：pip install tkinterdnd2（一次性；平台 requirements 可加）
启动：随平台手动启动，或双击「启动拖拽代理.bat」。
"""

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from tkinter import Tk, Label, Listbox, StringVar, END

try:
    from tkinterdnd2 import DND_FILES, TkinterDnD
except ImportError:
    print('缺少 tkinterdnd2：python -m pip install tkinterdnd2')
    sys.exit(1)


def parse_dnd(data):
    """tkinterdnd2 的 Files 数据 → 路径列表（带空格的路径包在 {} 里）。"""
    out = []
    for m in re.finditer(r'\{([^}]+)\}|(\S+)', data):
        out.append((m.group(1) or m.group(2)).replace('/', os.sep))
    return out


def find_platform(port):
    """在候选端口上探测平台（/api/dropped_paths/last 存在即命中）。"""
    candidates = [port] + [p for p in range(8760, 8790) if p != port]
    for p in candidates:
        try:
            with urllib.request.urlopen(
                    f'http://127.0.0.1:{p}/api/dropped_paths/last?since=0',
                    timeout=2) as r:
                j = json.loads(r.read().decode())
                if 'fresh' in j:
                    return p
        except (urllib.error.URLError, urllib.error.HTTPError,
                json.JSONDecodeError, OSError):
            continue
    return None


def send(port, paths):
    req = urllib.request.Request(
        f'http://127.0.0.1:{port}/api/dropped_paths', method='POST',
        data=json.dumps({'paths': paths}).encode())
    req.add_header('Content-Type', 'application/json')
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8765, help='平台端口')
    args = ap.parse_args()

    root = TkinterDnD.Tk()
    root.title('拖拽代理 → 植物病毒分析平台')
    root.attributes('-topmost', True)
    root.geometry('420x260')

    port_var = StringVar(value='探测平台中…')
    Label(root, text='把文件从资源管理器拖到这里', font=('Microsoft YaHei', 12)
          ).pack(pady=(12, 2))
    Label(root, text='真实路径直送平台，自动填入最后点过的输入框',
          fg='#666').pack()
    Label(root, textvariable=port_var, fg='#2e86c1').pack(pady=(4, 6))

    plist = Listbox(root, height=8)
    plist.pack(fill='both', expand=True, padx=12, pady=6)

    def log(msg):
        plist.insert(END, msg)
        plist.see(END)

    platform_port = find_platform(args.port)
    if not platform_port:
        log('✘ 未发现平台服务——请先启动平台（网页或桌面窗口）')
        port_var.set('未连接')
    else:
        args.port = platform_port
        port_var.set(f'已连接平台 :{platform_port}')
        log(f'✔ 平台端口 {platform_port}')

    def on_drop(event):
        if not platform_port:
            log('✘ 平台未连接，先启动平台')
            return
        paths = parse_dnd(event.data)
        if not paths:
            return
        try:
            send(platform_port, paths)
            for p in paths:
                log('→ ' + p)
        except Exception as e:
            log(f'✘ 发送失败: {e}')

    root.drop_target_register(DND_FILES)
    root.dnd_bind('<<Drop>>', on_drop)
    root.mainloop()
    return 0


if __name__ == '__main__':
    sys.exit(main())
