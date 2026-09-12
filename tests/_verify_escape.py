# -*- coding: utf-8 -*-
"""验证 HTML 转义修复（报告注入）。"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Virus_Platform_Core.ncbi_submit.report_html import table_html
from Virus_Platform_Core.logan_trace import _esc_html, parse_result_table

evil = '<script>alert(1)</script>'
th, body = table_html(['col'], [[evil]])
print('report_html:', body.strip())
assert '<script>' not in body and '&lt;script&gt;' in body
print('logan:', _esc_html(evil + ' & "q"'))
assert '<script>' not in _esc_html(evil)
raw = ('Run Accession,Organism,Location\n'
       'SRR1,"' + evil + '","A & B"\n').encode('utf-8')
rows, _ = parse_result_table(raw)
print('parsed organism:', rows[0]['organism'])
assert rows[0]['organism'] == evil
print('转义 OK')
