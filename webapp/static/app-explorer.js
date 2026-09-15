/* 病毒浏览器 Explorer —— 前端。
 *
 * 配套后端：Virus_Platform_Core/web/explorer.py（服务器版 13 个 Dash 回调的 Flask 化）
 * 计算：Virus_Platform_Core/explorer/engine.py（服务器代码原样搬运）
 *
 * 两个渲染职责要分清：
 *   · 主图表（时空三图 / 变异两图）—— 接口回 plotly 的 JSON，本文件 Plotly.newPlot
 *   · 面板内容（引物 / 宿主 / 媒介 / 病毒档案）—— 接口回**服务端渲染好的 HTML 片段**，
 *     片段里 shim.py 已经把图塞进 .vx-plot 的 data-vx-fig 属性，insertAdjacentHTML 之后
 *     再统一由 renderPlots() 把图画出来（innerHTML 插入的 <script> 不会执行，故不走脚本）。
 */
(function () {
  'use strict';

  var $ = function (id) { return document.getElementById(id); };
  /* i18n：i18n.js 以普通脚本加载，其顶层 t() 在全局脚本作用域可见。
     取不到就退回中文原字面量，保证单文件也能跑。 */
  function T(key, fallback) {
    try { return (typeof t === 'function') ? t(key, fallback) : fallback; }
    catch (e) { return fallback; }
  }
  function Tf(key, vars, fallback) {
    var s = T(key, fallback);
    Object.keys(vars || {}).forEach(function (k) {
      s = s.split('{' + k + '}').join(vars[k]);
    });
    return s;
  }

  var state = {
    table: [],            // 当前筛选结果（≤5000 行，无 Sequence 列）
    page: 1,
    pageSize: 50,
    sortBy: null,
    sortAsc: true,
    query: '',
    tab: 'trends',
    loadedTabs: {},       // 面板懒加载标记
    preset: null
  };

  // ------------------------------------------------------------------ 工具
  function qs(sel) {
    var el = $(sel);
    if (!el) return [];
    var out = [];
    for (var i = 0; i < el.options.length; i++) {
      if (el.options[i].selected) out.push(el.options[i].value);
    }
    return out;
  }

  function setOptions(sel, items, selected, labelKey) {
    var el = $(sel);
    if (!el) return;
    el.innerHTML = '';
    (items || []).forEach(function (it) {
      var o = document.createElement('option');
      o.value = it.value;
      o.textContent = labelKey && it[labelKey] ? it[labelKey] : it.label;
      el.appendChild(o);
    });
    var want = selected || [];
    for (var i = 0; i < el.options.length; i++) {
      el.options[i].selected = want.indexOf(el.options[i].value) >= 0;
    }
  }

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function api(url, opts) {
    return fetch(url, opts).then(function (r) {
      if (!r.ok) {
        return r.json().catch(function () { return {}; }).then(function (j) {
          throw new Error(j.error || ('HTTP ' + r.status));
        });
      }
      return r.json();
    });
  }

  function filters() {
    return {
      host: qs('exHost'),
      country: qs('exCountry'),
      family: qs('exFamily'),
      virus: qs('exVirus'),
      category: qs('exCategory'),
      completeness: qs('exCompleteness'),
      year_range: [$('exYearMin').value || 0, $('exYearMax').value || 0],
      year_source: $('exYearSource').value,
      filter_na: $('exFilterNa').checked,
      table: state.table
    };
  }

  function post(url, body) {
    return api(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    });
  }

  /* 文本模式的 POST：给那些**返回服务端渲染 HTML 片段**的面板接口用。
     不能走 post() —— api() 里无脑 r.json()，在 HTML 上会抛
     `Unexpected token '<'`，面板就永远停在「加载中…」。 */
  function postText(url, body) {
    return fetch(url, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)
    }).then(function (r) {
      return r.text().then(function (txt) {
        if (!r.ok) {
          var msg = txt;
          try { msg = JSON.parse(txt).error || msg; } catch (e) { /* 保持原文 */ }
          throw new Error(msg || ('HTTP ' + r.status));
        }
        return txt;
      });
    });
  }

  /* 把服务端片段里 shim 生成的 .vx-plot 画出来。
     Plotly JSON 在 data-vx-fig 属性里（属性值已实体转义，dataset 读出来就是原文）。 */
  function renderPlots(root) {
    var nodes = (root || document).querySelectorAll('.vx-plot');
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      if (el.dataset.vxDone === '1') continue;
      var raw = el.dataset.vxFig;
      if (!raw) continue;
      var fig;
      try { fig = JSON.parse(raw); } catch (e) { el.textContent = '图表数据解析失败'; continue; }
      var cfg;
      try { cfg = JSON.parse(el.dataset.vxCfg || '{}'); } catch (e2) { cfg = {}; }
      var layout = fig.layout || {};
      // 跟随页面主题：plotly 默认白底，在暗色主题下会刺眼
      var dark = document.documentElement.getAttribute('data-theme') === 'dark';
      layout.paper_bgcolor = 'rgba(0,0,0,0)';
      layout.plot_bgcolor = 'rgba(0,0,0,0)';
      layout.font = Object.assign({}, layout.font,
        { color: dark ? '#c3cfdc' : '#2c3a4b' });
      cfg.responsive = true;
      try {
        Plotly.newPlot(el, fig.data || [], layout, cfg);
        el.dataset.vxDone = '1';
      } catch (e3) {
        el.textContent = '图表渲染失败: ' + e3.message;
      }
    }
  }

  function showFig(boxId, fig) {
    var el = $(boxId);
    if (!el) return;
    if (!fig) { el.innerHTML = '<div class="loading">' + esc(T('ex.noData', '暂无数据')) + '</div>'; return; }
    var layout = fig.layout || {};
    var dark = document.documentElement.getAttribute('data-theme') === 'dark';
    layout.paper_bgcolor = 'rgba(0,0,0,0)';
    layout.plot_bgcolor = 'rgba(0,0,0,0)';
    layout.font = Object.assign({}, layout.font, { color: dark ? '#c3dfcf' : '#2c3a4b' });
    el.dataset.vxDone = '1';
    Plotly.newPlot(el, fig.data || [], layout, { responsive: true, displayModeBar: true });
  }

  // ------------------------------------------------------------------ 初始化
  function loadStatus() {
    return api('/api/explorer/status').then(function (s) {
      var rec = $('exRecCount');
      if (s.missing && s.missing.length) {
        rec.textContent = '数据缺失';
        var box = $('exMissing');
        box.style.display = '';
        box.innerHTML = '<b>Explorer 数据不完整，页面无法工作。</b><br>' +
          '缺少：<code>' + s.missing.map(esc).join('</code>、<code>') + '</code><br>' +
          '期望目录：<code>' + esc(s.data_root) + '</code><br>' +
          '请把服务器上 <code>plant_virus_db_pipeline/docs/data/</code> 与 ' +
          '<code>genome_annotations/</code> 同步过来；也可用环境变量 ' +
          '<code>VP_EXPLORER_DATA</code> 指向别处的数据根。' +
          (s.load_error ? '<br>最近一次加载错误：<code>' + esc(s.load_error) + '</code>' : '');
        $('exLoadState').textContent = T('ex.notReady', '不可用');
        return false;
      }
      if (s.loaded) {
        rec.textContent = (s.n_records || 0).toLocaleString() + ' 条 / ' +
          (s.n_species || 0).toLocaleString() + ' 物种';
        $('exLoadState').textContent = T('ex.ready', '已就绪');
      } else {
        rec.textContent = '待首次加载';
        $('exLoadState').textContent = '首次查询会解析全量数据（约 10–60 秒）';
      }
      return true;
    }).catch(function (e) {
      $('exRecCount').textContent = '状态获取失败';
      $('exLoadState').textContent = e.message;
      return false;
    });
  }

  function loadInit() {
    var search = window.location.search || '';
    return api('/api/explorer/init' + (search ? '?search=' + encodeURIComponent(search) : ''))
      .then(function (d) {
        if (!d.ok) throw new Error(d.error || '初始化失败');
        state.preset = d.preset;
        setOptions('exHost', d.host_options, d.preset.host ? [d.preset.host] : []);
        setOptions('exCountry', d.country_options, d.preset.country);
        setOptions('exFamily', d.family_options, d.preset.family);
        setOptions('exCategory', d.category_options, d.preset.category, 'label_count');
        setOptions('exCompleteness', d.completeness_options, ['complete'], 'label_count');
        setOptions('exVirus', d.virus_options, d.preset.virus || d.virus_default, 'label_count');
        setOptions('exMutationVirus',
          (d.virus_options || []).map(function (o) { return { value: o.value, label: o.label }; }),
          d.virus_default);
        $('exYearMin').value = d.preset.year_range[0];
        $('exYearMax').value = d.preset.year_range[1];
        $('exYearMin').min = $('exYearMax').min = d.year_bounds[0];
        $('exYearMin').max = $('exYearMax').max = d.year_bounds[1];
        $('exRecCount').textContent = (d.stats_badge.sequences || 0).toLocaleString() +
          ' 条 / ' + (d.stats_badge.species || 0).toLocaleString() + ' 物种';
        renderPlots(document);
        return d;
      });
  }

  // ------------------------------------------------------------------ 主查询
  function runQuery() {
    var btn = $('exApply');
    btn.disabled = true;
    var oldText = btn.textContent;
    btn.textContent = '查询中…';
    return post('/api/explorer/query', filters()).then(function (d) {
      if (!d.ok) throw new Error(d.error || '查询失败');
      state.table = d.table || [];
      state.page = 1;
      state.query = '';
      $('exTblSearch').value = '';
      var st = d.stats || {};
      $('exKpiTotal').textContent = st.total || '0';
      $('exKpiSpecies').textContent = st.n_species || '0';
      $('exKpiCommon').textContent = st.common_virus || '—';
      $('exKpiCommon').title = st.common_virus || '';
      $('exKpiCountry').textContent = st.top_country || '—';
      $('exVpLink').href = (d.vp_link && d.vp_link.href) || '#';
      $('exVpLink').textContent = (d.vp_link && d.vp_link.label) || '📋 Virus Profiles';

      var note = $('exTblNote');
      if (d.table_truncated) {
        note.style.display = '';
        note.textContent = Tf('ex.truncWarn',
          {n: (d.rows_total || 0).toLocaleString(),
           cap: (d.table_cap || 5000).toLocaleString()},
          '⚠️ 结果共 {n} 行，表格与图表只取前 {cap} 行（与服务器版同一取数口径）。');
      } else { note.style.display = 'none'; }

      setOptions('exMutationVirus', d.mutation_options || [],
        d.default_virus ? [d.default_virus] : []);
      setOptions('exProfileSel', d.profile_options || [], []);

      renderTable();
      $('exTrendNote').innerHTML = '';
      return loadCharts();
    }).catch(function (e) {
      $('exKpiTotal').textContent = '错误';
      $('exKpiCommon').textContent = e.message;
      $('exKpiCommon').title = e.message;
    }).then(function () {
      btn.disabled = false;
      btn.textContent = oldText;
    });
  }

  function loadCharts() {
    return post('/api/explorer/charts', { table: state.table }).then(function (d) {
      if (!d.ok) throw new Error(d.error || '图表失败');
      showFig('exFigTime', d.figures[0]);
      showFig('exFigCountry', d.figures[1]);
      showFig('exFigMap', d.figures[2]);
    }).catch(function (e) {
      $('exTrendNote').innerHTML = '<div class="ex-note">图表加载失败：' + esc(e.message) + '</div>';
    });
  }

  // ------------------------------------------------------------------ 数据浏览表
  function filteredRows() {
    if (!state.query) return state.table;
    var q = state.query.toLowerCase();
    return state.table.filter(function (r) {
      for (var k in r) {
        if (r[k] != null && String(r[k]).toLowerCase().indexOf(q) >= 0) return true;
      }
      return false;
    });
  }

  function sortedRows(rows) {
    if (!state.sortBy) return rows;
    var k = state.sortBy, asc = state.sortAsc ? 1 : -1;
    return rows.slice().sort(function (a, b) {
      var x = a[k], y = b[k];
      if (x == null) return 1;
      if (y == null) return -1;
      var nx = parseFloat(x), ny = parseFloat(y);
      if (!isNaN(nx) && !isNaN(ny) && String(x).trim() !== '' && String(y).trim() !== '') {
        return (nx - ny) * asc;
      }
      return String(x).localeCompare(String(y)) * asc;
    });
  }

  function renderTable() {
    var tbl = $('exTable');
    var rows = filteredRows();
    var total = rows.length;
    var maxPage = Math.max(1, Math.ceil(total / state.pageSize));
    if (state.page > maxPage) state.page = maxPage;
    var start = (state.page - 1) * state.pageSize;
    var slice = sortedRows(rows).slice(start, start + state.pageSize);

    var cols = state.table.length ? Object.keys(state.table[0]) : [];
    var thead = '<tr>';
    cols.forEach(function (c) {
      var cls = state.sortBy === c ? ('sorted' + (state.sortAsc ? ' asc' : '')) : '';
      thead += '<th class="' + cls + '" data-col="' + esc(c) + '">' + esc(c) + '</th>';
    });
    thead += '</tr>';
    tbl.querySelector('thead').innerHTML = thead;

    var body = '';
    slice.forEach(function (r) {
      body += '<tr>';
      cols.forEach(function (c) {
        var v = r[c];
        body += '<td title="' + esc(v) + '">' + esc(v) + '</td>';
      });
      body += '</tr>';
    });
    tbl.querySelector('tbody').innerHTML = body ||
      '<tr><td colspan="' + (cols.length || 1) + '" style="color:var(--ink-400)">无匹配行</td></tr>';

    $('exPageInfo').textContent = Tf('ex.pageInfo', {p: state.page, t: maxPage}, '第 {p} / {t} 页');
    $('exPageRows').textContent = Tf('ex.searchCols', {n: total.toLocaleString()}, '共 {n} 行');
    $('exPagePrev').disabled = state.page <= 1;
    $('exPageNext').disabled = state.page >= maxPage;

    Array.prototype.forEach.call(tbl.querySelectorAll('th[data-col]'), function (th) {
      th.onclick = function () {
        var c = th.dataset.col;
        if (state.sortBy === c) state.sortAsc = !state.sortAsc;
        else { state.sortBy = c; state.sortAsc = true; }
        renderTable();
      };
    });
  }

  // ------------------------------------------------------------------ 面板
  function loadPanel(name) {
    if (state.loadedTabs[name]) return Promise.resolve();
    var virus = (qs('exVirus')[0]) || '';
    var box = { primers: 'exPrimers', host: 'exHostPanel', vector: 'exVector' }[name];
    if (!box) return Promise.resolve();
    $(box).innerHTML = '<div class="loading">' + esc(T('ex.loading', '加载中…')) + '</div>';
    // 三个面板接口都返回**服务端渲染好的 HTML 片段**：
    //   引物 / 宿主 —— GET  ?virus=<第一个选中物种>
    //   媒介       —— POST 当前完整筛选（要按筛选结果算媒介-宿主三元组，
    //                  只传 virus 会丢掉 family/country 等条件）
    var req = (name === 'vector')
      ? postText('/api/explorer/vector', filters())
      : fetch('/api/explorer/' + name + '?virus=' + encodeURIComponent(virus))
        .then(function (r) { return r.text(); });
    return Promise.resolve(req).then(function (html) {
      $(box).innerHTML = html;
      renderPlots($(box));
      state.loadedTabs[name] = true;
    }).catch(function (e) {
      $(box).innerHTML = '<div class="ex-note">加载失败：' + esc(e.message) + '</div>';
    });
  }

  function loadProfile() {
    var name = $('exProfileSel').value;
    if (!name) { $('exProfile').innerHTML = '<div class="loading">' + esc(T('ex.speciesPlaceholder', '选择物种后加载…')) + '</div>'; return; }
    $('exProfile').innerHTML = '<div class="loading">' + esc(T('ex.loading', '加载中…')) + '</div>';
    fetch('/api/explorer/profile?name=' + encodeURIComponent(name))
      .then(function (r) { return r.text(); })
      .then(function (html) {
        $('exProfile').innerHTML = html;
        renderPlots($('exProfile'));
      })
      .catch(function (e) {
        $('exProfile').innerHTML = '<div class="ex-note">加载失败：' + esc(e.message) + '</div>';
      });
  }

  function runVariation() {
    var v = $('exMutationVirus').value;
    if (!v) { $('exVarMsg').textContent = '请先选择物种'; return; }
    $('exVarMsg').textContent = '比对中…（序列多时需数十秒）';
    post('/api/explorer/variation', { table: state.table, virus: v }).then(function (d) {
      if (!d.ok) throw new Error(d.error || '分析失败');
      if (d.empty) {
        $('exVarMsg').textContent = d.error || '没有可用序列';
        $('exFigHeat').innerHTML = ''; $('exFigVar').innerHTML = '';
        return;
      }
      $('exVarMsg').textContent = '';
      showFig('exFigHeat', d.figures[0]);
      showFig('exFigVar', d.figures[1]);
    }).catch(function (e) { $('exVarMsg').textContent = '失败：' + e.message; });
  }

  function download(url, body) {
    return post(url, body).then(function () { /* 下载走表单提交，见下 */ })
      .catch(function () { });
  }

  /* 导出用隐藏表单提交：避免把 5000 行 JSON 再回传一次，
     但仍复用同一套筛选（后端无 table 时会自己重跑管道）。 */
  function submitForm(url, extra) {
    var f = document.createElement('form');
    f.method = 'POST';
    f.action = url;
    f.style.display = 'none';
    var payload = Object.assign({}, filters(), extra || {});
    // 表格数据太大不放表单里；后端会用筛选条件重跑
    delete payload.table;
    var input = document.createElement('input');
    input.type = 'hidden';
    input.name = 'payload';
    input.value = JSON.stringify(payload);
    f.appendChild(input);
    document.body.appendChild(f);
    f.submit();
    setTimeout(function () { f.remove(); }, 1000);
  }

  // ------------------------------------------------------------------ 事件绑定
  function bind() {
    $('exApply').onclick = runQuery;
    $('exReset').onclick = function () {
      location.href = '/explorer';
    };
    $('exFamily').onchange = function () {
      var fam = qs('exFamily'), cat = qs('exCategory');
      var q = '/api/explorer/virus_options?' +
        'family=' + encodeURIComponent(fam.join(',')) +
        '&category=' + encodeURIComponent(cat.join(','));
      api(q).then(function (d) {
        if (d.ok) setOptions('exVirus', d.options, d.default, 'label_count');
      });
    };

    Array.prototype.forEach.call($('exTabs').querySelectorAll('.ex-tab'), function (btn) {
      btn.onclick = function () {
        var name = btn.dataset.tab;
        state.tab = name;
        Array.prototype.forEach.call($('exTabs').querySelectorAll('.ex-tab'), function (b) {
          b.classList.toggle('active', b === btn);
        });
        Array.prototype.forEach.call(document.querySelectorAll('.ex-pane'), function (p) {
          p.classList.toggle('active', p.dataset.pane === name);
        });
        if (name === 'primers' || name === 'host' || name === 'vector') loadPanel(name);
        if (name === 'mutation') renderPlots(document);
        // 页签切换后 plotly 需要一次 resize 才知道容器尺寸
        if (window.Plotly) {
          Array.prototype.forEach.call(
            document.querySelectorAll('.ex-pane.active .js-plotly-plot'),
            function (p) { try { Plotly.Plots.resize(p); } catch (e) { } });
        }
      };
    });

    $('exTblSearch').oninput = function () { state.query = this.value; state.page = 1; renderTable(); };
    $('exPagePrev').onclick = function () { state.page--; renderTable(); };
    $('exPageNext').onclick = function () { state.page++; renderTable(); };
    $('exExportCsv').onclick = function () { submitForm('/api/explorer/export/csv'); };
    $('exExportFasta').onclick = function () { submitForm('/api/explorer/export/fasta'); };
    $('exRunVar').onclick = runVariation;
    $('exProfileSel').onchange = loadProfile;
  }

  // ------------------------------------------------------------------ 启动
  document.addEventListener('DOMContentLoaded', function () {
    bind();
    loadStatus().then(function (ready) {
      if (!ready) return;
      return loadInit().then(runQuery);
    });
  });
})();
