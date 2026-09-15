# -*- coding: utf-8 -*-
"""Dash / Mantine 组件的最小 HTML 渲染替身（shim）。

## 为什么需要它

服务器版 Explorer 是 Dash 应用，面板回调返回的是 **组件树**：

    dmc.Paper(withBorder=True, p="md", children=[dmc.Title(...), dcc.Graph(figure=fig)])

平台是 Flask，没有 Dash 运行时。与其把这 ~1000 行面板代码逐行手抄成 HTML 字符串
（既慢又容易抄错，且以后无法与服务器同步），不如**保留组件树的写法**，用一个
只覆盖实际用到的那十几个组件的小替身把它渲染成 HTML。

这样 `engine.py` 里从服务器搬来的面板 / 病毒档案代码可以**一字不改**。

## 覆盖面

只实现服务器代码真正用到的组件（已按 610-795 与 1703-1963 两段实测盘点）：

    dmc   Title Paper Text Anchor Group Button Badge Alert Space Card
    html  Div Span A
    dcc   Graph Link
    dash_table  DataTable

未实现的属性一律**静默忽略**（Dash 的 prop 体系太宽，逐个校验只会徒增维护成本）；
但未实现的**组件**会直接 AttributeError —— 这是故意的，避免悄悄少渲染一块内容。

## 图表

`dcc.Graph(figure=fig)` 渲染成占位 div + 把 plotly 图的 JSON 塞进 `data-vx-fig`
属性，由前端 `app-explorer.js` 取出来 `Plotly.newPlot()`。
属性值经 `html.escape(quote=True)`，浏览器读 `dataset` 时已自动反转义。
"""
from __future__ import annotations

import html as _html
import json
from typing import Any, Iterable

__all__ = ['dmc', 'dcc', 'dash_table', 'to_html', 'Record']


# --------------------------------------------------------------------------
# 样式换算：Mantine 的设计 token → 内联 CSS
# --------------------------------------------------------------------------
_SPACE = {          # Mantine spacing scale
    'xs': '8px', 'sm': '12px', 'md': '16px', 'lg': '24px', 'xl': '32px',
    None: '0',
}
_SIZE = {           # Mantine font-size scale（Text/Anchor 的 size=）
    'xs': '12px', 'sm': '13px', 'md': '14px', 'lg': '16px', 'xl': '18px',
}
_HEIGHT = {'xs': '20px', 'sm': '28px', 'md': '34px', 'lg': '42px', 'xl': '50px'}

_COLOR = {          # Mantine 调色板的近似值（够用；不与线上逐像素比对）
    'dimmed': '#868e96', 'gray': '#868e96', 'grey': '#868e96',
    'blue': '#228be6', 'indigo': '#4c6ef5', 'teal': '#12b886',
    'red': '#fa5252', 'green': '#40c057', 'yellow': '#fab005',
    'orange': '#fd7e14', 'pink': '#e64980', 'violet': '#7950f2',
    'grape': '#be4bdb', 'cyan': '#15aabf', 'lime': '#82c91e',
    'dark': '#212529',
}
_ALERT_BG = {
    'yellow': ('#fff9db', '#f0c000'), 'red': ('#fff5f5', '#fa5252'),
    'blue': ('#e7f5ff', '#228be6'), 'green': ('#ebfbee', '#40c057'),
    'teal': ('#e6fcf5', '#12b886'), 'gray': ('#f8f9fa', '#adb5bd'),
    'indigo': ('#edf2ff', '#4c6ef5'),
}


def _style_of(kw: dict) -> str:
    """把 Mantine 风格的 kwargs 折成一条内联 style。"""
    s = []

    # 外边距 / 内边距
    for prop, css in (('mt', 'margin-top'), ('mb', 'margin-bottom'),
                      ('ml', 'margin-left'), ('mr', 'margin-right'),
                      ('m', 'margin'), ('p', 'padding'),
                      ('px', 'padding-left'), ('py', 'padding-top')):
        if prop in kw and kw[prop] is not None:
            v = _SPACE.get(kw[prop], kw[prop])
            s.append(f'{css}:{v}')
    if kw.get('px') is not None and kw.get('py') is not None:
        s.append(f"padding-right:{_SPACE.get(kw['px'], kw['px'])}")
        s.append(f"padding-bottom:{_SPACE.get(kw['py'], kw['py'])}")
    if 'my' in kw and kw['my'] is not None:
        v = _SPACE.get(kw['my'], kw['my'])
        s += [f'margin-top:{v}', f'margin-bottom:{v}']

    # 字体
    if kw.get('fw') is not None:
        w = kw['fw']
        s.append(f'font-weight:{"bold" if w in (700, "bold") else w}')
    if kw.get('size') is not None and kw.get('flex') is None:
        v = _SIZE.get(kw['size'], kw['size'])
        if str(v).endswith('px') or str(v).endswith('rem') or str(v).endswith('%'):
            s.append(f'font-size:{v}')
    if kw.get('fz') is not None:
        s.append(f"font-size:{kw['fz']}")
    if kw.get('c') is not None:
        s.append(f"color:{_COLOR.get(kw['c'], kw['c'])}")
    if kw.get('tt') is not None:
        s.append(f"text-transform:{kw['tt']}")
    if kw.get('ta') is not None:
        s.append(f"text-align:{kw['ta']}")

    # 盒子
    if kw.get('radius') is not None:
        r = _SPACE.get(kw['radius'], kw['radius'])
        s.append(f'border-radius:{r}')
    if kw.get('shadow') is not None or kw.get('withBorder'):
        s.append('box-shadow:0 1px 3px rgba(0,0,0,.06)')
    if kw.get('h') is not None:
        s.append(f"height:{_HEIGHT.get(kw['h'], kw['h'])}")

    # flex 容器
    if kw.get('gap') is not None:
        s.append(f"gap:{_SPACE.get(kw['gap'], kw['gap'])}")
    if kw.get('justify') is not None:
        s.append(f"justify-content:{_flex(kw['justify'])}")
    if kw.get('align') is not None:
        s.append(f"align-items:{_flex(kw['align'])}")
    if kw.get('wrap') is not None:
        s.append('flex-wrap:wrap' if kw['wrap'] else 'flex-wrap:nowrap')

    # 其余直接透传（调用方写的 style 字典优先，见 _Comp.to_html）
    return ';'.join(s)


def _flex(v: Any) -> str:
    return {'apart': 'space-between', 'center': 'center',
            'start': 'flex-start', 'end': 'flex-end'}.get(v, str(v))


# --------------------------------------------------------------------------
# 组件基类
# --------------------------------------------------------------------------
class _Comp:
    """一个可渲染成 HTML 的节点。"""

    tag = 'div'
    base_class = ''

    def __init__(self, *children: Any, **kw: Any):
        # ⚠️ Mantine 两种写法都有：`dmc.Paper([...])` 与 `dmc.Paper(children=[...])`。
        # 服务器版代码里 `children=` 关键字形式占多数，必须在这里合流，
        # 否则组件会渲染成空壳（实测踩过一次：病毒档案 8 个 Paper 全空、
        # 媒介面板的统计卡全空）。
        kw_children = kw.pop('children', None)
        if kw_children is not None:
            if isinstance(kw_children, (list, tuple)):
                children = children + tuple(kw_children)
            else:
                children = children + (kw_children,)
        self._children = children
        self._kw = kw

    # -- 渲染 ---------------------------------------------------------------
    def to_html(self) -> str:
        inline = _style_of(self._kw)
        extra = self._kw.get('style') or {}
        if isinstance(extra, dict):
            inline = ';'.join(
                [inline] + [f'{k}:{v}' for k, v in extra.items() if v is not None])
        attrs = self.render_attrs()
        cls = ' '.join(x for x in (self.base_class, self._kw.get('className')) if x)
        if cls:
            attrs += f' class="{_html.escape(cls)}"'
        if inline:
            attrs += f' style="{_html.escape(inline, quote=True)}"'
        if self.tag in ('img', 'br', 'hr', 'input'):
            return f'<{self.tag}{attrs}>'
        return f'<{self.tag}{attrs}>{self.render_inner()}</{self.tag}>'

    def render_attrs(self) -> str:
        return ''

    def render_inner(self) -> str:
        return render_children(self._children)

    # -- 让 str()/f-string/Jinja 都能直接用 -------------------------------
    def __html__(self) -> str:
        return self.to_html()

    def __str__(self) -> str:
        return self.to_html()

    def __repr__(self) -> str:
        return f'<{type(self).__name__} {self.to_html()[:60]}...>'


def render_children(children: Iterable[Any]) -> str:
    """递归渲染子节点；list/tuple 展开，None 跳过，其余 str() 化。"""
    out = []
    for ch in children:
        if ch is None or ch is False:
            continue
        if isinstance(ch, (list, tuple)):
            out.append(render_children(ch))
        elif isinstance(ch, _Comp):
            out.append(ch.to_html())
        elif isinstance(ch, str):
            out.append(ch)                       # 允许调用方直接塞 HTML
        else:
            out.append(_html.escape(str(ch)))
    return ''.join(out)


class Record(dict):
    """dash_table.DataTable 里的 data 行；允许属性式访问，便于搬运代码。"""

    def __getattr__(self, item):
        try:
            return self[item]
        except KeyError as e:
            raise AttributeError(item) from e


# --------------------------------------------------------------------------
# dmc —— Mantine 子集
# --------------------------------------------------------------------------
class _Text(_Comp):
    tag = 'div'
    base_class = 'vx-text'

    def __init__(self, children=None, **kw):
        kw.setdefault('size', 'sm')
        super().__init__(children, **kw)


class _Title(_Comp):
    base_class = 'vx-title'

    def __init__(self, children=None, order=3, **kw):
        self.tag = f'h{max(1, min(6, int(order)))}'
        super().__init__(children, **kw)


class _Anchor(_Comp):
    tag = 'a'

    def __init__(self, children=None, **kw):
        kw.setdefault('size', 'sm')
        super().__init__(children, **kw)

    def render_attrs(self) -> str:
        href = self._kw.get('href') or '#'
        attrs = f' href="{_html.escape(str(href), quote=True)}"'
        if self._kw.get('target'):
            attrs += f' target="{_html.escape(str(self._kw["target"]), quote=True)}"'
            if self._kw['target'] == '_blank':
                attrs += ' rel="noopener noreferrer"'
        return attrs


class _Group(_Comp):
    base_class = 'vx-group'


class _Card(_Comp):
    base_class = 'vx-card'


class _Paper(_Comp):
    base_class = 'vx-paper'


class _Badge(_Comp):
    tag = 'span'
    base_class = 'vx-badge'

    def __init__(self, children=None, **kw):
        kw.setdefault('variant', 'light')
        super().__init__(children, **kw)


class _Button(_Comp):
    tag = 'button'
    base_class = 'vx-btn'

    def __init__(self, children=None, **kw):
        kw.setdefault('variant', 'filled')
        super().__init__(children, **kw)

    def render_attrs(self) -> str:
        attrs = ' type="button"'
        if self._kw.get('id'):
            attrs += f' id="{_html.escape(str(self._kw["id"]), quote=True)}"'
        if self._kw.get('disabled'):
            attrs += ' disabled'
        return attrs


class _Alert(_Comp):
    base_class = 'vx-alert'

    def __init__(self, children=None, color='blue', title=None, **kw):
        self._color = color
        self._title = title
        super().__init__(children, **kw)

    def to_html(self) -> str:
        bg, bd = _ALERT_BG.get(self._color, _ALERT_BG['blue'])
        head = f'<div class="vx-alert-t">{_html.escape(str(self._title))}</div>' \
            if self._title else ''
        return (f'<div class="{self.base_class}" style="background:{bg};'
                f'border-left:3px solid {bd}">{head}{self.render_inner()}</div>')


class _Space(_Comp):
    def to_html(self) -> str:
        return f'<div style="height:{_SPACE.get(self._kw.get("h"), "16px")}"></div>'


class _Divider(_Comp):
    tag = 'hr'
    base_class = 'vx-divider'


class _Unsupported(_Comp):
    """占位：库里提供了组件但本页用不到，渲染成一个可见的提示而不是静默吞掉。"""

    def __init__(self, *a, **kw):
        name = type(self).__name__
        super().__init__(f'[未支持的组件 {name}]', **kw)


class _dmc:
    Text = _Text
    Title = _Title
    Anchor = _Anchor
    Group = _Group
    Card = _Card
    Paper = _Paper
    Badge = _Badge
    Button = _Button
    Alert = _Alert
    Space = _Space
    Divider = _Divider


# --------------------------------------------------------------------------
# html —— 直接用真 html 模块的名字，省一层
# --------------------------------------------------------------------------
class _html_ns:
    class Div(_Comp):
        tag = 'div'

    class Span(_Comp):
        tag = 'span'

    class A(_Anchor):
        pass

    class Hr(_Comp):
        tag = 'hr'

    class Br(_Comp):
        tag = 'br'


# --------------------------------------------------------------------------
# dcc —— Dash 核心组件子集
# --------------------------------------------------------------------------
class _Graph(_Comp):
    """Plotly 图占位：JSON 塞 data-vx-fig，前端 Plotly.newPlot。"""

    base_class = 'vx-plot'

    def __init__(self, figure=None, config=None, **kw):
        self._figure = figure
        self._config = config or {}
        super().__init__(**kw)

    def to_html(self) -> str:
        fig = self._figure
        if fig is None:
            payload = '{"data":[],"layout":{}}'
        elif hasattr(fig, 'to_json'):
            payload = fig.to_json()                 # plotly Figure
        else:
            payload = json.dumps(fig, default=str)
        h = self._kw.get('style', {}).get('height') if isinstance(self._kw.get('style'), dict) else None
        style = f'height:{h};' if h else 'height:340px;'
        cfg = json.dumps(self._config, default=str)
        return (f'<div class="{self.base_class}" style="{style}width:100%" '
                f'data-vx-fig="{_html.escape(payload, quote=True)}" '
                f'data-vx-cfg="{_html.escape(cfg, quote=True)}"></div>')


class _Link(_Comp):
    tag = 'a'
    base_class = 'vx-link'

    def render_attrs(self) -> str:
        return f' href="{_html.escape(str(self._kw.get("href") or "#"), quote=True)}"'


class _dcc:
    Graph = _Graph
    Link = _Link


# --------------------------------------------------------------------------
# dash_table.DataTable —— 渲染成普通 <table>
# --------------------------------------------------------------------------
class _DataTable(_Comp):
    """服务端渲染的静态表格。

    服务器版靠 Dash 的前端分页/排序/筛选；这里渲染成完整 HTML 表格，
    分页与排序交给前端 `app-explorer.js`（面板里的表都很小，最多的引物表也只有 100 行）。
    """

    base_class = 'vx-table'

    def __init__(self, data=None, columns=None, page_size=10, **kw):
        self._data = list(data or [])
        self._columns = list(columns or [])
        self._page_size = page_size
        kw.pop('children', None)
        self._kw = kw

    def to_html(self) -> str:
        if not self._columns and self._data:
            self._columns = [{'name': k, 'id': k} for k in self._data[0].keys()]
        if not self._columns:
            return '<div class="vx-table vx-table-empty">（无数据）</div>'

        sortable = self._kw.get('sort_action') == 'native'
        filterable = self._kw.get('filter_action') == 'native'

        head = []
        for c in self._columns:
            cid = c.get('id', c.get('name', ''))
            mark = ' data-sortable="1"' if sortable else ''
            head.append(f'<th data-col="{_html.escape(str(cid), quote=True)}"{mark}>'
                        f'{_html.escape(str(c.get("name", cid)))}</th>')
        head = '<tr>' + ''.join(head) + '</tr>'

        body = []
        for row in self._data:
            tds = []
            for c in self._columns:
                cid = c.get('id', c.get('name', ''))
                val = row.get(cid) if isinstance(row, dict) else None
                cell = '' if val is None else str(val)
                if c.get('presentation') == 'markdown':
                    cell = _md_link(cell)
                else:
                    cell = _html.escape(cell)
                tds.append(f'<td>{cell}</td>')
            body.append('<tr>' + ''.join(tds) + '</tr>')
        body = ''.join(body)

        cls = self.base_class + (' vx-sortable' if sortable else '') \
            + (' vx-filterable' if filterable else '')
        page = f' data-page-size="{int(self._page_size)}"' if self._page_size else ''
        return (f'<div class="vx-table-wrap"><table class="{cls}"{page}>'
                f'<thead>{head}</thead><tbody>{body}</tbody></table></div>')


_MD_LINK = None


def _md_link(text: str) -> str:
    """把 markdown 的 [label](href) 转成真链接（服务器用 presentation="markdown"）。"""
    import re
    def repl(m):
        label, href = m.group(1), m.group(2)
        return (f'<a href="{_html.escape(href, quote=True)}" target="_blank" '
                f'rel="noopener noreferrer">{_html.escape(label)}</a>')
    return re.sub(r'\[([^\]]+)\]\(([^)]+)\)', repl, _html.escape(text))


class _dash_table:
    DataTable = _DataTable


# --------------------------------------------------------------------------
# 导出
# --------------------------------------------------------------------------
dmc = _dmc
dcc = _dcc
dash_table = _dash_table

# html.* 用真模块名（engine.py 里 from .shim import html）
html = _html_ns


def to_html(node: Any) -> str:
    """任意组件 / 组件列表 → HTML 字符串。"""
    if node is None:
        return ''
    if isinstance(node, _Comp):
        return node.to_html()
    if isinstance(node, (list, tuple)):
        return render_children(node)
    return str(node)
