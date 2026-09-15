/* 植物病毒分析平台 · 病毒浏览器 Explorer 前端
 *
 * 从 webapp/templates/vexplorer.html 的内联 <script> 抽出并扩展
 * （2026-09-15）。抽出原因：加入「宿主范围 / 媒介传播 / 全基因组变异」三个
 * 面板后脚本超过 700 行，留在模板里既难维护也让模板失去可读性。
 *
 * 依赖（由模板按序引入）：i18n.js（t）、app.js（$ / esc / toast）、
 * plotly.min.js、examples.js。全部为全局函数，无模块封装 —— 与平台其余
 * static/*.js 的写法一致（它们都靠 onclick="fn()" 触发）。
 *
 * 页签：概览与导出 / 宿主范围 / 媒介传播 / 全基因组变异
 */
'use strict';

/* ==================================================================
 * 通用
 * ================================================================== */
function val(id) { return ($(id)?.value || '').trim(); }

function vxShowErr(boxId, e) {
  const b = $(boxId);
  if (b) b.innerHTML = '<p class="err">' + esc(e && e.message ? e.message : e) + '</p>';
}

/* 页签切换：只切显示，不销毁已渲染的图（Plotly 图切回来不用重画） */
function vxTab(name) {
  document.querySelectorAll('.vx-pane').forEach(p => {
    p.style.display = (p.id === 'vxPane-' + name) ? '' : 'none';
  });
  document.querySelectorAll('.vx-tab').forEach(b => {
    b.classList.toggle('active', b.dataset.tab === name);
  });
  try { localStorage.setItem('vx_tab', name); } catch (e) {}
  // 首次进入某面板时才拉数据，避免开页面就打四个接口
  if (name === 'host' && !VX_LOADED.host) { VX_LOADED.host = 1; vxHostLoad(); }
  if (name === 'vec' && !VX_LOADED.vec) { VX_LOADED.vec = 1; vxVecInit(); }
  if (name === 'var' && !VX_LOADED.var) { VX_LOADED.var = 1; vxVarInit(); }
  // 图表在隐藏容器里渲染会得到 0 宽，切回来补一次 resize
  setTimeout(() => {
    ['vxChartYear', 'vxChartGeo', 'vxChartFamily', 'vxChartHost',
     'vxChartMol', 'vxChartMap', 'vxHostChart', 'vxVecSankey',
     'vxVarCons', 'vxVarWin', 'vxVarHeat'].forEach(id => {
      const gd = document.getElementById(id);
      if (gd && gd.data) { try { Plotly.Plots.resize(gd); } catch (e) {} }
    });
  }, 60);
}

const VX_LOADED = { host: 0, vec: 0, var: 0 };

/* ==================================================================
 * ① 概览与导出（原有逻辑，逐字保留）
 * ================================================================== */
const VX_PER = 50;
let VX_PAGE = 1, VX_TOTAL = 0;

async function vxLoadFacets() {
  for (const [field, sel] of [
    ['Family', 'f_Family'], ['Molecule_type', 'f_Molecule_type'],
    ['Sequence_Type', 'f_Sequence_Type'], ['Segment_std', 'f_Segment'],
    ['Nuc_Completeness', 'f_Nuc_Completeness']]) {
    try {
      const d = await (await fetch('/api/vexplorer/facets?field=' + field)).json();
      $(sel).innerHTML = '<option value="">全部</option>' +
        (d.values || []).map(v => {
          const label = v.value === '__none__'
            ? t('vx.noneSeg', '（未标注 / 单片段）') : v.value;
          return `<option value="${esc(v.value)}">${esc(label)}（${v.count}）</option>`;
        }).join('');
    } catch (e) {}
  }
}

function vxParams() {
  const p = new URLSearchParams();
  const bal = val('vxBalance');
  if (bal) p.set('geo_balance', bal);
  const fields = [['f_Family', 'Family'], ['f_Segment', 'Segment_std'],
    ['f_Molecule_type', 'Molecule_type'], ['f_Sequence_Type', 'Sequence_Type'],
    ['f_Nuc_Completeness', 'Nuc_Completeness'], ['f_species', 'species'],
    ['f_host', 'host'], ['f_geo', 'geo'], ['f_q', 'q'],
    ['f_len_min', 'len_min'], ['f_len_max', 'len_max'],
    ['f_date_from', 'date_from'], ['f_date_to', 'date_to']];
  for (const [id, k] of fields) {
    const v = val(id);
    if (v) p.set(k, v);
  }
  return p;
}

async function vxQuery(page) {
  VX_PAGE = page || 1;
  const p = vxParams();
  p.set('page', VX_PAGE); p.set('per', VX_PER);
  const r = await fetch('/api/vexplorer/query?' + p.toString());
  if (!r.ok) { $('vxWrap').innerHTML = '<p class="err">' + esc((await r.json()).error || '') + '</p>'; return; }
  const d = await r.json();
  VX_TOTAL = d.total;
  $('vxInfo').textContent = t('vx.total', '命中 {n} 条').replace('{n}', d.total);
  $('vxPage').textContent = t('vx.pageN', '第 {p} 页').replace('{p}', d.page);
  // 查询联动图表
  vxRenderCharts(p);
  const heads = ['vx.thAcc|Accession', 'vx.thSpecies|物种', 'vx.thFamily|科',
    'vx.thMol|分子', 'vx.thLen|长度', 'vx.thComp|完整度', 'vx.thGeo|地理',
    'vx.thHost|宿主', 'vx.thDate|年份'].map(x => {
      const [k, dft] = x.split('|');
      return '<th>' + t(k, dft) + '</th>';
    }).join('');
  const body = d.rows.map(r =>
    '<tr><td><input type="checkbox" class="vx-pick" value="' + esc(r.Accession) +
    '" style="width:auto"></td>' +
    `<td class="mono"><a href="#" onclick="vxFasta('${esc(r.Accession)}');return false">${esc(r.Accession)}</a></td>` +
    `<td>${esc(r.Species_ICTV)}</td><td>${esc(r.Family)}</td>` +
    `<td>${esc(r.Molecule_type)}</td><td>${r.Length}</td>` +
    `<td>${esc(r.Nuc_Completeness)}</td><td>${esc(r.Geo_Location)}</td>` +
    `<td>${esc(r.Host)}</td><td>${esc(r.Collection_Date)}</td></tr>`).join('');
  $('vxWrap').innerHTML =
    '<table id="vxTable"><thead><tr><th style="width:30px"></th>' + heads +
    '</tr></thead><tbody>' + body + '</tbody></table>';
  document.querySelectorAll('.vx-pick').forEach(c =>
    c.addEventListener('change', vxCount));
  vxCount();
}

function vxSelNames() {
  return [...document.querySelectorAll('.vx-pick:checked')].map(c => c.value);
}

function vxCount() {
  $('vxSel').textContent =
    t('vx.selected', '已选 {n} 条').replace('{n}', vxSelNames().length);
}

function vxAll(on) {
  document.querySelectorAll('.vx-pick').forEach(c => { c.checked = !!on; });
  vxCount();
}

function vxPage(dir) {
  const maxPage = Math.max(1, Math.ceil(VX_TOTAL / VX_PER));
  vxQuery(Math.min(maxPage, Math.max(1, VX_PAGE + dir)));
}

function vxDownloadChart(divId, filename) {
  const gd = document.getElementById(divId);
  if (!gd || !gd.data) return;
  Plotly.downloadImage(gd, { format: 'png', width: 1200, height: 700,
                             filename: filename || divId, scale: 2 });
}

function vxDownloadAllCharts() {
  const charts = [
    ['vxChartYear', '时间分布'], ['vxChartGeo', '地理分布'],
    ['vxChartFamily', '科分布'], ['vxChartHost', '宿主分布'],
    ['vxChartMol', '分子类型'],
  ];
  let delay = 0;
  for (const [id, name] of charts) {
    const gd = document.getElementById(id);
    if (gd && gd.data) {
      setTimeout(() => {
        Plotly.downloadImage(gd, { format: 'png', width: 1200, height: 700,
                                   filename: name, scale: 2 });
      }, delay);
      delay += 500;
    }
  }
}

async function vxRenderCharts(params) {
  try {
    const st = await (await fetch('/api/vexplorer/filtered_stats?' + params.toString())).json();
    // ① 时间分布折线
    const yrs = st.by_year || [];
    if (yrs.length) {
      Plotly.newPlot('vxChartYear', [{
        x: yrs.map(v => v.year), y: yrs.map(v => v.count),
        mode: 'lines', type: 'scatter', line: { color: '#2e86c1' },
        fill: 'tozeroy', fillcolor: 'rgba(46,134,193,.15)',
      }], { margin: { l: 50, r: 10, t: 28, b: 34 },
            title: { text: t('vx.chYearT', '时间分布'), font: { size: 13 } },
            xaxis: { title: '年份' }, yaxis: { title: '序列数' },
            showlegend: false }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge('vxChartYear'); }
    // ② 地理分布条形
    const geo = (st.by_geo || []).slice(0, 12);
    if (geo.length) {
      Plotly.newPlot('vxChartGeo', [{
        x: geo.map(v => v.count).reverse(),
        y: geo.map(v => v.geo).reverse(),
        type: 'bar', orientation: 'h', marker: { color: '#27ae60' },
      }], { margin: { l: 110, r: 16, t: 28, b: 30 },
            title: { text: t('vx.chGeoT', '地理分布 Top12'), font: { size: 13 } },
            showlegend: false }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge('vxChartGeo'); }
    // ③ 科分布
    const fam = (st.by_family || []).slice(0, 12);
    if (fam.length) {
      Plotly.newPlot('vxChartFamily', [{
        x: fam.map(v => v.count).reverse(),
        y: fam.map(v => v.name).reverse(),
        type: 'bar', orientation: 'h', marker: { color: '#8e44ad' },
      }], { margin: { l: 130, r: 16, t: 28, b: 30 },
            title: { text: t('vx.chFamT', '科分布'), font: { size: 13 } },
            showlegend: false }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge('vxChartFamily'); }
    // ④ 宿主分布
    const host = (st.by_host || []).slice(0, 12);
    if (host.length) {
      Plotly.newPlot('vxChartHost', [{
        x: host.map(v => v.count).reverse(),
        y: host.map(v => v.name).reverse(),
        type: 'bar', orientation: 'h', marker: { color: '#e67e22' },
      }], { margin: { l: 130, r: 16, t: 28, b: 30 },
            title: { text: t('vx.chHostT', '宿主分布'), font: { size: 13 } },
            showlegend: false }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge('vxChartHost'); }
    // ⑤ 分子类型饼图
    const mol = (st.by_molecule || []);
    if (mol.length) {
      Plotly.newPlot('vxChartMol', [{
        labels: mol.map(v => v.name), values: mol.map(v => v.count),
        type: 'pie', hole: .4,
      }], { margin: { l: 10, r: 10, t: 28, b: 10 },
            title: { text: t('vx.chMolT', '分子类型'), font: { size: 13 } },
            showlegend: true }, { displayModeBar: false, responsive: true });
    } else { Plotly.purge('vxChartMol'); }
    // ⑥ 地理地图
    const geoAll = (st.by_geo || []);
    if (geoAll.length && typeof Plotly !== 'undefined') {
      Plotly.newPlot('vxChartMap', [{
        type: 'choropleth',
        locationmode: 'country names',
        locations: geoAll.map(v => v.geo),
        z: geoAll.map(v => v.count),
        text: geoAll.map(v => v.geo + ': ' + v.count),
        colorscale: 'Greens',
        marker: { line: { color: '#fff', width: 0.5 } },
        hovertemplate: '%{text}<extra></extra>',
      }], {
        geo: { projection: { type: 'natural earth' }, showframe: false,
               showcoastlines: false, bgcolor: 'rgba(0,0,0,0)' },
        margin: { l: 0, r: 0, t: 28, b: 0 },
        title: { text: t('vx.chMapT', '全球分布'), font: { size: 13 } },
      }, { displayModeBar: false, responsive: true });
    }
  } catch (e) {}
}

async function vxLoadStats() {
  try {
    const d = await (await fetch('/api/vexplorer/stats')).json();
    $('kpiTotal').textContent = (d.total || 0).toLocaleString();
    $('kpiSpecies').textContent = (d.n_species || 0).toLocaleString();
    $('kpiFam').textContent = (d.n_families || 0).toLocaleString();
    const yrs = d.by_year || [];
    if (yrs.length && typeof Plotly !== 'undefined') {
      Plotly.newPlot('chartYear', [{
        x: yrs.map(v => v.year), y: yrs.map(v => v.count),
        mode: 'lines', type: 'scatter', line: { color: '#2e86c1' },
        fill: 'tozeroy', fillcolor: 'rgba(46,134,193,.15)',
      }], { margin: { l: 46, r: 10, t: 26, b: 34 },
            title: { text: t('vx.chYear', '逐年序列数'), font: { size: 13 } },
            showlegend: false }, { displayModeBar: false, responsive: true });
    }
    const geo = (d.by_geo || []).slice(0, 12);
    if (geo.length && typeof Plotly !== 'undefined') {
      Plotly.newPlot('chartGeo', [{
        x: geo.map(v => v.count).reverse(),
        y: geo.map(v => v.geo).reverse(),
        type: 'bar', orientation: 'h',
        marker: { color: '#27ae60' },
      }], { margin: { l: 110, r: 16, t: 26, b: 30 },
            title: { text: t('vx.chGeo', '地理分布 Top12（国家/地区）'),
                     font: { size: 13 } },
            showlegend: false }, { displayModeBar: false, responsive: true });
    }
  } catch (e) {}
}

function vxTableCsv() {
  const p = vxParams();
  const a = document.createElement('a');
  a.href = '/api/vexplorer/table.csv?' + p.toString();
  a.download = 'vexplorer_table.csv';
  a.click();
}

function vxReset() {
  ['#f_Family', '#f_Molecule_type', '#f_Sequence_Type', '#f_Nuc_Completeness']
    .forEach(id => { if ($(id)) $(id).value = ''; });
  ['f_species', 'f_host', 'f_geo', 'f_q', 'f_len_min', 'f_len_max',
   'f_date_from', 'f_date_to'].forEach(id => { if ($(id)) $(id).value = ''; });
  vxQuery(1);
}

async function vxFasta(acc) {
  const box = $('vxFasta');
  box.style.display = '';
  box.textContent = '…';
  try {
    box.textContent = await (await fetch('/api/vexplorer/fasta?acc=' +
      encodeURIComponent(acc))).text();
  } catch (e) { box.textContent = '读取失败: ' + e; }
}

async function vxSendPhylodyn(btn) {
  const names = vxSelNames();
  const p = vxParams();
  let body, url = '/api/vexplorer/send_to_phylodyn';
  if (names.length) {
    body = JSON.stringify({ accessions: names });
  } else {
    if (!p.toString()) { alert(t('vx.needFilter', '请先筛选，或勾选具体序列')); return; }
    /* 未勾选时按当前筛选条件导出。筛选参数必须走 query string：
       后端 _apply_filters() 只读 request.args，放 body 里会被静默忽略，
       结果是"不加筛选"的全库命中 → 必然撞 5000 上限报错。
       此处与 vxExport() 保持同一口径。 */
    body = null; url += '?' + p.toString();
  }
  if (btn) { btn.disabled = true; }
  try {
    const r = await fetch(url, body ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body
    } : { method: 'POST' });
    if (!r.ok) { alert((await r.json()).error || '送入失败'); return; }
    const d = await r.json();
    // 跨页交接：平台 prefill 机制
    sessionStorage.setItem('vp_prefill', JSON.stringify({
      page: 'phylodyn', ts: Date.now(), fa: d.path, n: d.n_seqs }));
    location.href = '/tools?g=phylodyn#t-rdp';
  } catch (e) { alert('送入失败: ' + e); }
  finally { if (btn) { btn.disabled = false; } }
}

async function vxExport(btn) {
  const names = vxSelNames();
  const p = vxParams();
  let body, url = '/api/vexplorer/export';
  if (names.length) {
    body = JSON.stringify({ accessions: names });
  } else {
    if (!p.toString()) { alert(t('vx.needFilter', '请先筛选，或勾选具体序列')); return; }
    body = null; url += '?' + p.toString();
  }
  if (btn) { btn.disabled = true; }
  try {
    const r = await fetch(url, body ? {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body
    } : {});
    if (!r.ok) { alert((await r.json()).error || '导出失败'); return; }
    const blob = await r.blob();
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'vexplorer_export.fa';
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) { alert('导出失败: ' + e); }
  finally { if (btn) { btn.disabled = false; } }
}

/* ==================================================================
 * ② 宿主范围（属 → 种 下钻）
 * ================================================================== */
let VX_HOST_LEVEL = 'genus';
let VX_HOST_DRILL = '';      // 非空 = 正在看该属下的宿主种

async function vxHostLoad(level, drill) {
  if (level) VX_HOST_LEVEL = level;
  if (drill !== undefined) VX_HOST_DRILL = drill;
  const box = $('vxHostInfo');
  const f = vxParams();
  // 复用概览页的筛选（科/物种），保证两个面板口径一致
  const p = new URLSearchParams();
  ['Family', 'species'].forEach(k => {
    const v = new URLSearchParams(f).get(k === 'Family' ? 'Family' : 'species');
    if (v) p.set(k === 'Family' ? 'family' : 'species', v);
  });
  p.set('level', VX_HOST_LEVEL);
  p.set('limit', '20');
  if (VX_HOST_DRILL) p.set('host', VX_HOST_DRILL);
  if (box) box.textContent = t('c.loading', '加载中…');
  try {
    const d = await (await fetch('/api/vexplorer/host/levels?' + p.toString())).json();
    if (d.error) throw new Error(d.error);
    vxHostRender(d);
  } catch (e) { vxShowErr('vxHostInfo', e); }
}

function vxHostRender(d) {
  const st = d.stats || {};
  const crumbs = [];
  crumbs.push(`<a href="#" onclick="vxHostLoad('genus','');return false">`
    + t('vx.hostAll', '全部宿主属') + '</a>');
  if (VX_HOST_LEVEL === 'species') {
    crumbs.push('<span>›</span><b>' + esc(VX_HOST_DRILL || t('vx.hostUndef', '未定')) + '</b>');
  }
  $('vxHostCrumb').innerHTML = crumbs.join(' ');
  $('vxHostInfo').innerHTML =
    t('vx.hostStats', '命中 {n} 条 · 宿主记录 {r} 条 · 宿主种 {s} · 宿主属 {g}')
      .replace('{n}', (st.total || 0).toLocaleString())
      .replace('{r}', (st.n_host_records || 0).toLocaleString())
      .replace('{s}', (st.n_host_taxa || 0).toLocaleString())
      .replace('{g}', (st.n_genus || 0).toLocaleString());

  const rows = d.rows || [];
  const y = rows.map(r => r.name).reverse();
  const x = rows.map(r => r.count).reverse();
  const extra = rows.map(r => r.species_n).reverse();
  if (y.length) {
    Plotly.newPlot('vxHostChart', [{
      x, y, type: 'bar', orientation: 'h',
      marker: { color: VX_HOST_LEVEL === 'genus' ? '#e67e22' : '#16a085' },
      customdata: extra,
      hovertemplate: VX_HOST_LEVEL === 'genus'
        ? '%{y}<br>序列 %{x}<br>宿主种 %{customdata}<extra></extra>'
        : '%{y}<br>序列 %{x}<extra></extra>',
    }], {
      margin: { l: 150, r: 20, t: 30, b: 40 },
      title: { text: VX_HOST_LEVEL === 'genus'
        ? t('vx.hostTopGenus', '宿主属分布 Top20')
        : t('vx.hostTopSp', '宿主种分布 Top20'), font: { size: 13 } },
      xaxis: { title: t('vx.hostSeqN', '序列数') },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });
    // 属级点击 → 下钻到该属的宿主种
    if (VX_HOST_LEVEL === 'genus') {
      const gd = $('vxHostChart');
      if (gd && !gd.__vxBound) {
        gd.__vxBound = 1;
        gd.on('plotly_click', ev => {
          const pt = ev.points && ev.points[0];
          if (pt && pt.y) vxHostLoad('species', pt.y);
        });
      }
    }
  } else { Plotly.purge('vxHostChart'); }

  // 明细表（属级带「宿主种数」，种级带计数）
  const head = VX_HOST_LEVEL === 'genus'
    ? `<th>${t('vx.hostGenus', '宿主属')}</th><th>${t('vx.hostSeqN', '序列数')}</th><th>${t('vx.hostSpN', '宿主种数')}</th><th></th>`
    : `<th>${t('vx.hostSp', '宿主种')}</th><th>${t('vx.hostSeqN', '序列数')}</th>`;
  const body = rows.map(r => VX_HOST_LEVEL === 'genus'
    ? `<tr><td>${esc(r.name)}</td><td>${r.count}</td><td>${r.species_n}</td>`
      + `<td><button class="btn small" onclick="vxHostLoad('species','${esc(r.name)}')">`
      + t('vx.drill', '下钻') + '</button></td></tr>'
    : `<tr><td>${esc(r.name)}</td><td>${r.count}</td></tr>`).join('');
  $('vxHostTable').innerHTML =
    `<table id="vxTable"><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table>`;
}

/* ==================================================================
 * ③ 媒介传播网络（多层 Sankey）
 * ================================================================== */
let VX_VEC_PAGE = 1, VX_VEC_TOTAL = 0, VX_VEC_DEPTH = 6;

async function vxVecInit() {
  try {
    const d = await (await fetch('/api/vexplorer/vector/facets')).json();
    if (d.error) throw new Error(d.error);
    for (const [field, sel] of [
      ['Virus Family', 'vf_family'], ['Virus Genus', 'vf_genus'],
      ['Vector Order', 'vf_order'], ['Virus Transmission Mode', 'vf_mode']]) {
      const opts = (d.facets[field] || []).map(v =>
        `<option value="${esc(v.value)}">${esc(v.value)}（${v.count}）</option>`).join('');
      const el = $(sel);
      if (el) el.innerHTML = '<option value="">全部</option>' + opts;
    }
    // 层深选择器
    const dep = $('vf_depth');
    if (dep) {
      dep.innerHTML = (d.layers || []).slice(2).map((l, i) =>
        `<option value="${i + 2}"${i + 2 === VX_VEC_DEPTH ? ' selected' : ''}>`
        + (i + 2) + ' 层</option>').join('');
    }
    vxVecRender();
  } catch (e) { vxShowErr('vxVecInfo', e); }
}

function vxVecParams() {
  const p = new URLSearchParams();
  [['vf_family', 'family'], ['vf_genus', 'genus'],
   ['vf_order', 'vector_order'], ['vf_mode', 'transmission']].forEach(([id, k]) => {
    const v = val(id);
    if (v) p.set(k, v);
  });
  return p;
}

async function vxVecRender() {
  const depth = val('vf_depth') || VX_VEC_DEPTH;
  VX_VEC_DEPTH = parseInt(depth, 10) || 6;
  const p = vxVecParams();
  p.set('depth', VX_VEC_DEPTH);
  if ($('vxVecInfo')) $('vxVecInfo').textContent = t('c.loading', '加载中…');
  try {
    const d = await (await fetch('/api/vexplorer/vector/graph?' + p.toString())).json();
    if (d.error) throw new Error(d.error);
    const nodes = d.nodes || [], links = d.links || [];
    if (!nodes.length) {
      Plotly.purge('vxVecSankey');
      $('vxVecInfo').textContent = t('vx.vecEmpty', '当前筛选无媒介关系记录');
    } else {
      // 层色：让同一层的节点同色，读者才能一眼分辨层序
      const palette = ['#2e86c1', '#8e44ad', '#16a085', '#e67e22',
                       '#c0392b', '#7f8c8d', '#2c3e50', '#d35400', '#27ae60'];
      const colors = (d.layer_of || []).map(i => palette[i % palette.length]);
      // 层标题：Plotly 的 Sankey 不画列名，6 层图上读者无法分辨
      // 「媒介目」与「媒介科」——必须自己按层序补 annotation。
      // 层在图上等距分布（x: 0→1），第 i 层即 i/(depth-1)。
      const depth = d.depth || VX_VEC_DEPTH;
      const names = d.layer_names || [];
      const annots = names.map((nm, i) => ({
        text: nm, showarrow: false, xref: 'paper', yref: 'paper',
        x: depth > 1 ? i / (depth - 1) : 0.5, y: 1.04,
        xanchor: 'center', yanchor: 'bottom',
        font: { size: 11, color: '#888' },
      }));
      Plotly.newPlot('vxVecSankey', [{
        type: 'sankey', orientation: 'h',
        node: { label: nodes, color: colors, pad: 8, thickness: 14,
                line: { color: 'rgba(0,0,0,.25)', width: .5 },
                hovertemplate: '%{label}<br>流向总量 %{value}<extra></extra>' },
        link: { source: links.map(l => l.source), target: links.map(l => l.target),
                value: links.map(l => l.value),
                color: links.map(l => colors[l.source] + '55'),
                hovertemplate: '%{source.label} → %{target.label}<br>%{value}<extra></extra>' },
      }], {
        margin: { l: 8, r: 8, t: 34, b: 8 },
        font: { size: 11 },
        annotations: annots,
      }, { displayModeBar: false, responsive: true });
      $('vxVecInfo').innerHTML =
        t('vx.vecStats', '关系记录 {f} / {t} 条 · 节点 {n} · 链路 {k} · {d} 层')
          .replace('{f}', (d.n_filtered || 0).toLocaleString())
          .replace('{t}', (d.n_total || 0).toLocaleString())
          .replace('{n}', nodes.length).replace('{k}', links.length)
          .replace('{d}', d.depth || VX_VEC_DEPTH);
    }
  } catch (e) { vxShowErr('vxVecInfo', e); }
  vxVecTable(1);
}

/* 媒介表列名 → i18n 键。刻意写成静态映射而不是「前缀 + 列名」拼接：
 * 数据列名含空格（'Virus Family'），拼出来的键既不在审计正则的字符集内，
 * 也没法在 i18n.js 里稳定维护。静态映射让每个键都能被
 * tests/_audit_contract.py 的中英键一致性检查覆盖。 */
const VX_VC_KEYS = {
  'Virus Family': 'vx.vcFamily',
  'Virus Genus': 'vx.vcGenus',
  'Virus Name': 'vx.vcName',
  'Vector': 'vx.vcVector',
  'Vector Order': 'vx.vcOrder',
  'Vector Family': 'vx.vcVectorFamily',
  'Virus Transmission Mode': 'vx.vcMode',
  'Virus Host': 'vx.vcHost',
};

async function vxVecTable(page) {
  VX_VEC_PAGE = page || 1;
  const p = vxVecParams();
  p.set('page', VX_VEC_PAGE); p.set('per', '25');
  try {
    const d = await (await fetch('/api/vexplorer/vector/table?' + p.toString())).json();
    if (d.error) throw new Error(d.error);
    VX_VEC_TOTAL = d.total;
    const cols = d.columns || [];
    const heads = cols.map(c =>
      '<th>' + esc(VX_VC_KEYS[c] ? t(VX_VC_KEYS[c], c) : c) + '</th>').join('');
    const body = (d.rows || []).map(r =>
      '<tr>' + cols.map(c => `<td>${esc(r[c])}</td>`).join('') + '</tr>').join('');
    $('vxVecTable').innerHTML =
      `<table id="vxTable"><thead><tr>${heads}</tr></thead><tbody>${body}</tbody></table>`;
    const maxPage = Math.max(1, Math.ceil(VX_VEC_TOTAL / 25));
    $('vxVecPage').textContent = t('vx.vecPage', '第 {p}/{m} 页 · 共 {n} 条')
      .replace('{p}', VX_VEC_PAGE).replace('{m}', maxPage)
      .replace('{n}', VX_VEC_TOTAL.toLocaleString());
  } catch (e) { vxShowErr('vxVecTable', e); }
}

function vxVecPage(dir) {
  const maxPage = Math.max(1, Math.ceil(VX_VEC_TOTAL / 25));
  const np = Math.min(maxPage, Math.max(1, VX_VEC_PAGE + dir));
  if (np !== VX_VEC_PAGE) vxVecTable(np);
}

/* ==================================================================
 * ④ 全基因组变异
 * ================================================================== */
let VX_VAR_DATA = null;

async function vxVarInit() {
  // 物种候选：用 facets 填 datalist，省得用户记学名
  try {
    const d = await (await fetch('/api/vexplorer/facets?field=Species_ICTV&limit=400')).json();
    const dl = $('vxVarSpeciesList');
    if (dl) {
      dl.innerHTML = (d.values || [])
        .filter(v => v.value && v.value !== '__none__')
        .map(v => `<option value="${esc(v.value)}">${v.count} 条</option>`)
        .join('');
    }
  } catch (e) {}
}

async function vxVarRun(btn) {
  const sp = val('vxVarSpecies');
  if (!sp) { alert(t('vx.varNeedSp', '请先填写病毒物种（可用下拉候选）')); return; }
  const p = new URLSearchParams();
  p.set('species', sp);
  const seg = val('vxVarSegment');
  if (seg) p.set('segment', seg);
  const ms = val('vxVarMaxSeqs');
  if (ms) p.set('max_seqs', ms);
  if ($('vxVarRefresh') && $('vxVarRefresh').checked) p.set('refresh', '1');
  if (btn) btn.disabled = true;
  $('vxVarInfo').textContent = t('vx.varRunning', '比对中…（首次需数秒，结果会缓存）');
  try {
    const r = await fetch('/api/vexplorer/variation?' + p.toString());
    const d = await r.json();
    if (d.error) throw new Error(d.error);
    VX_VAR_DATA = d;
    vxVarRender(d);
  } catch (e) { vxShowErr('vxVarInfo', e); }
  finally { if (btn) btn.disabled = false; }
}

function vxVarRender(d) {
  // 片段切换器：分段病毒必须逐段看，这里把可用片段列全
  const segs = d.segments || [];
  const sel = $('vxVarSegment');
  if (sel) {
    sel.innerHTML = '<option value="">' + t('vx.varAutoSeg', '自动（最大片段）') + '</option>'
      + segs.map(s => `<option value="${esc(s.segment)}"${s.segment === d.segment ? ' selected' : ''}>`
        + esc(s.segment === '__none__' ? t('vx.varNoSeg', '未标注 / 单片段') : s.segment)
        + `（${s.count}）</option>`).join('');
  }
  const li = d.length_info || {};
  $('vxVarInfo').innerHTML =
    t('vx.varStats', '物种 <b>{sp}</b> · 片段 <b>{seg}</b> · 比对 {n} 条 × {c} 位点'
      + ' · 平均同一性 <b>{id}%</b> · 整体变异率 <b>{vr}</b>')
      .replace('{sp}', esc(d.species || ''))
      .replace('{seg}', esc(d.segment === '__none__' ? t('vx.varNoSeg', '未标注 / 单片段') : d.segment || ''))
      .replace('{n}', d.n_seq).replace('{c}', d.n_col)
      .replace('{id}', d.mean_identity ?? '—')
      .replace('{vr}', ((d.overall_var_rate || 0) * 100).toFixed(2) + '%')
    + `<br><span class="hint">`
    + t('vx.varLenNote', '长度口径：取长度 {lo}–{hi} bp 的可比全长簇（该簇 {n} 条，自动排除片段与离群）')
        .replace('{lo}', li.length_min ?? '—').replace('{hi}', li.length_max ?? '—')
        .replace('{n}', li.cluster_n ?? '—')
    + (d.cached ? ' · ' + t('vx.varCached', '命中缓存') : '')
    + `</span>`;

  const pos = d.positions || [];
  // ① 保守度曲线（面积）
  if (pos.length) {
    Plotly.newPlot('vxVarCons', [{
      x: pos, y: d.conservation, mode: 'lines', type: 'scatter',
      line: { color: '#2e86c1', width: 1 },
      fill: 'tozeroy', fillcolor: 'rgba(46,134,193,.18)',
    }], {
      margin: { l: 46, r: 12, t: 30, b: 36 },
      title: { text: t('vx.varConsT', '位点保守度（1−归一化熵）'), font: { size: 13 } },
      xaxis: { title: t('vx.varPos', '比对位点') }, yaxis: { title: '1 − H/Hmax', range: [0, 1.02] },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });

    // ② 滑动窗口变异率
    const w = d.window || [];
    Plotly.newPlot('vxVarWin', [{
      x: w.map(v => v.pos), y: w.map(v => +(v.rate * 100).toFixed(3)),
      mode: 'lines', type: 'scatter', line: { color: '#c0392b', width: 1.4 },
    }], {
      margin: { l: 50, r: 12, t: 30, b: 36 },
      title: { text: t('vx.varWinT', '滑动窗口变异率（窗 {w}）').replace('{w}', d.window_size || 50),
               font: { size: 13 } },
      xaxis: { title: t('vx.varPos', '比对位点') }, yaxis: { title: '变异率 %' },
      showlegend: false,
    }, { displayModeBar: false, responsive: true });

    // ③ 位点矩阵热图：0 gap / 1 A / 2 C / 3 G / 4 T / 5 N
    const zt = ['gap', 'A', 'C', 'G', 'T', 'N'];
    Plotly.newPlot('vxVarHeat', [{
      z: d.matrix, x: d.matrix_cols, y: d.names || [],
      type: 'heatmap', zmin: 0, zmax: 5,
      colorscale: [[0, '#d9d9d9'], [0.2, '#2ecc71'], [0.4, '#3498db'],
                   [0.6, '#f1c40f'], [0.8, '#e74c3c'], [1, '#7f8c8d']],
      colorbar: { title: '', tickvals: [0, 1, 2, 3, 4, 5], ticktext: zt,
                  len: .8, thickness: 12 },
      hovertemplate: t('vx.varHeatHover', '位点 %{x}<br>%{y}<br>碱基 %{z}<extra></extra>'),
    }], {
      margin: { l: 130, r: 10, t: 30, b: 40 },
      title: { text: t('vx.varHeatT', '比对热图（{n} 条 × {c} 位点，抽稀显示）')
                 .replace('{n}', d.n_seq).replace('{c}', (d.matrix_cols || []).length),
               font: { size: 13 } },
      xaxis: { title: t('vx.varPos', '比对位点') },
    }, { displayModeBar: false, responsive: true });
  }

  // ④ 热点表
  const hs = d.hotspots || [];
  $('vxVarHot').innerHTML = hs.length
    ? `<table id="vxTable"><thead><tr>
         <th>${t('vx.hsStart', '起始')}</th><th>${t('vx.hsEnd', '终止')}</th>
         <th>${t('vx.hsLen', '长度')}</th><th>${t('vx.hsMean', '平均变异率')}</th>
         <th>${t('vx.hsMax', '峰值变异率')}</th></tr></thead><tbody>`
      + hs.map(h => `<tr><td>${h.start}</td><td>${h.end}</td><td>${h.len}</td>`
        + `<td>${(h.mean_rate * 100).toFixed(2)}%</td>`
        + `<td>${(h.max_rate * 100).toFixed(2)}%</td></tr>`).join('')
      + '</tbody></table>'
    : `<p class="hint">${t('vx.hsNone', '未检出变异位点（该组序列高度保守）')}</p>`;
}

/* ==================================================================
 * 启动
 * ================================================================== */
vxLoadFacets();
vxLoadStats();
vxQuery(1);
// 恢复上次停留的页签
try {
  const last = localStorage.getItem('vx_tab');
  if (last && document.getElementById('vxPane-' + last)) vxTab(last);
} catch (e) {}
