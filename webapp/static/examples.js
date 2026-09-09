/* ============================================================
 * 内置示例数据 · 统一入口（webapp/static/examples.js）
 * ------------------------------------------------------------
 * 目的：任何模块都不需要用户先准备数据 —— 点「✨ 示例」即填好该模块
 *       所需输入；页面首次打开且输入为空时也会自动填入（可在设置关闭）。
 *
 * 数据文件全部在 databases/examples/，由 tests/make_example_reads.py 与
 * tests/make_examples.py 生成（确定性、可重跑）：
 *   example_R1/R2.fastq.gz      3 种植物病毒模拟双端 reads（~60x）
 *   example_viral_contigs.fasta 2 条病毒 contig（含 Pepper yellows virus）
 *   example_virus_set.fasta     6 条同属近缘基因组（比对/建树/SDT）
 *   example_conserved_set.fasta 5 条同种近缘序列（保守区引物）
 *   example_genome.gb           带 CDS 注释的 GenBank（基因组图谱）
 *   example_tree.nwk            示例树
 *   example_synteny_A/B/C.gb    同属共线性三件套
 *   example_tmv/pvy/cmv/pstvd/mix.fasta  Metabuli 示例病毒
 *
 * 新增模块只改下面的 MAP / PAGE_MAP 两个表，不要在页面里散写示例路径。
 * ============================================================ */
(function () {
  'use strict';

  var DIR = 'databases/examples/';
  var F = {
    R1: DIR + 'example_R1.fastq.gz',
    R2: DIR + 'example_R2.fastq.gz',
    CONTIGS: DIR + 'example_viral_contigs.fasta',
    CONTIG1: DIR + 'example_contig_1.fasta',
    SET: DIR + 'example_virus_set.fasta',
    CONSERVED: DIR + 'example_conserved_set.fasta',
    GENOME: DIR + 'example_genome.gb',
    TMV: DIR + 'example_tmv.fasta',
    MIX: DIR + 'example_mix.fasta',
    TREE: DIR + 'example_tree.nwk',
    SYNTENY: DIR + 'example_synteny_A.gb,' + DIR + 'example_synteny_B.gb,' +
             DIR + 'example_synteny_C.gb'
  };

  /* 工具卡（tools.html 里 <section class="card" id="t-xxx">）→ 字段映射。
     值写成 F 的键（示例文件）或字面量；select 会按 option value 匹配。 */
  var MAP = {
    't-convert':   { cv_input: 'R1', cv_target: 'fasta' },
    't-fastp':     { f_r1: 'R1', f_r2: 'R2' },
    't-identify':  { i_type: 'pe', i_input: 'R1', i_input2: 'R2' },
    't-assemble':  { a_r1: 'R1', a_r2: 'R2' },
    't-contigs':   { c_fa: 'CONTIGS' },
    't-verify':    { vf_fa: 'CONTIGS' },
    't-virchain':  { vc_input: 'R1', vc_input2: 'R2' },
    't-cdd':       { cddSeqText: 'CONTIGS_TEXT' },
    't-hom':       { homSeqText: 'CONTIGS_TEXT' },
    't-consensus': { cs_fa: 'CONTIGS', cs_reads: 'R1' },
    't-variant':   { vr_ref: 'CONTIGS' },
    't-seqprep':   null,      /* 已有自带示例按钮，保持原样 */
    't-synteny':   null,
    't-align':     null,
    't-treebuild': null,
    't-sdt':       null,
    't-kvsuite':   null       /* 用样品名而非文件，见 fillKvsuiteExample */
  };

  /* 独立页面（按 location.pathname 匹配）→ 字段映射 */
  var PAGE_MAP = {
    '/hostremoval': { hr_r1: 'R1', hr_r2: 'R2' },
    '/hostpredict': { hp_fa: 'CONTIGS' },
    '/orf':         { of_fa: 'CONTIGS' },
    '/annotation':  { oa_fa: 'CONTIGS' },
    '/genome':      { gp_ann: 'GENOME' },
    '/primer':      { pr_fa: 'CONSERVED' },
    '/logan':       { pasteSeq: 'TMV_TEXT' },  /* 文本域：填序列内容 */
    '/samples':     { sample: 'example_reads', r1: 'R1', r2: 'R2' },
    '/meta':        { mtSpecies: 'Tobacco mosaic virus', mtSource: 'All' }
  };

  var AUTO_KEY = 'vp_example_autofill';
  var _tmvText = null;

  /* 文本域示例：字段值写成 '<KEY>_TEXT' → 取该示例文件的内容填进 textarea。
     CDD / BLASTN·BLASTX 两张卡走「粘贴序列」入口，需要的是序列正文而非路径。 */
  var TEXT_SRC = { CONTIGS_TEXT: 'CONTIG1', TMV_TEXT: 'TMV' };

  function $(id) { return document.getElementById(id); }

  function setField(id, raw) {
    var el = $(id);
    if (!el) return false;
    var val = (raw in F) ? F[raw] : raw;
    if (val === 'TMV_TEXT') return false;          /* 由专用逻辑处理 */
    if (el.tagName === 'SELECT') {
      var ok = false;
      for (var i = 0; i < el.options.length; i++) {
        if (el.options[i].value === String(val)) { el.value = String(val); ok = true; break; }
      }
      if (!ok) return false;
    } else {
      el.value = val;
    }
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return true;
  }

  function fillMap(map) {
    var n = 0;
    for (var id in map) {
      var v = map[id];
      if (typeof v === 'string' && TEXT_SRC[v]) {
        if (fillTextFromFile(id, TEXT_SRC[v])) n++;
        continue;
      }
      if (setField(id, v)) n++;
    }
    return n;
  }

  /* 取示例文件正文填入 textarea（FASTA 全文，含 >header）。
     databases/ 不经 HTTP 暴露 → 走只读路由 /api/example_input/<文件名>。 */
  function fillTextFromFile(id, fileKey) {
    var ta = $(id);
    if (!ta) return false;
    var rel = (fileKey in F) ? F[fileKey] : fileKey;
    var path = '/api/example_input/' + encodeURIComponent(
      rel.indexOf(DIR) === 0 ? rel.slice(DIR.length) : rel.split('/').pop());
    fetch(path).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.text();
    }).then(function (t) {
      ta.value = t;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      ta.dispatchEvent(new Event('change', { bubbles: true }));
    }).catch(function (e) {
      if (typeof toast === 'function') toast('示例加载失败: ' + e.message, '', { ttl: 3000 });
    });
    return true;
  }

  /* kvsuite / kvchain 要的是样品名而不是文件路径：用示例 reads 建一个样品 */
  function fillKvsuiteExample() {
    var el = $('kv_samples');
    if (!el) return 0;
    el.value = 'EXAMPLE';
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    return 1;
  }

  /* 取 example_tmv.fasta 的序列内容（logan 粘贴框用） */
  function fillLoganExample() {
    var ta = $('pasteSeq');
    if (!ta) return 0;
    if (_tmvText) {
      ta.value = _tmvText;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
      return 1;
    }
    fetch('/api/example_input/' + encodeURIComponent(F.TMV.slice(DIR.length)))
      .then(function (r) { return r.text(); }).then(function (t) {
      _tmvText = t;
      ta.value = t;
      ta.dispatchEvent(new Event('input', { bubbles: true }));
    }).catch(function () {});
    return 1;
  }

  function applyFor(el) {
    /* el = 卡片 section 或 页面标识 */
    if (el === 'page') {
      var pm = PAGE_MAP[location.pathname];
      if (!pm) return 0;
      if (pm.pasteSeq === 'TMV_TEXT') return fillLoganExample();
      return fillMap(pm);
    }
    var id = el.id;
    if (id === 't-kvsuite' || id === 't-kvchain') return fillKvsuiteExample();
    var m = MAP[id];
    return m ? fillMap(m) : 0;
  }

  /* ---------- 「✨ 示例」/「👁 示例结果」按钮注入 ---------- */
  function mkBtn(label, title, handler) {
    var b = document.createElement('button');
    b.type = 'button';
    b.className = 'btn small vp-ex-btn';
    b.style.marginLeft = '8px';
    b.textContent = label;
    b.title = title;
    b.addEventListener('click', function (ev) { ev.preventDefault(); handler(); });
    return b;
  }

  function injectButtons() {
    document.querySelectorAll('section.card[id^="t-"]').forEach(function (sec) {
      if (sec.querySelector('.vp-ex-btn')) return;
      var hasFill = !!MAP[sec.id] || sec.id === 't-kvsuite' ||
                    sec.id === 't-kvchain';
      var mod = resultModule(sec.id);
      if (!hasFill && !mod) return;
      var h2 = sec.querySelector('h2');
      if (!h2) return;
      if (hasFill) {
        h2.appendChild(mkBtn('✨ 示例', '一键填入内置示例数据（databases/examples/）',
          function () {
            var n = applyFor(sec);
            if (typeof toast === 'function') {
              toast(n ? '已填入示例数据' : '该模块暂未配置示例', '', { ttl: 2200 });
            }
          }));
      }
      if (mod) {
        h2.appendChild(mkBtn('👁 示例结果', '查看内置示例的运行结果（只读）',
          function () { showExampleResult(mod); }));
      }
    });
    /* 独立页面：在页面主标题旁注入 */
    var pm = PAGE_MAP[location.pathname];
    var pmod = resultModule(location.pathname);
    if ((pm || pmod) && !document.querySelector('.vp-ex-btn')) {
      var h = document.querySelector('main h2, .card h2');
      if (h) {
        if (pm) {
          h.appendChild(mkBtn('✨ 示例', '一键填入内置示例数据', function () {
            var n = applyFor('page');
            if (typeof toast === 'function') {
              toast(n ? '已填入示例数据' : '该模块暂未配置示例', '', { ttl: 2200 });
            }
          }));
        }
        if (pmod) {
          h.appendChild(mkBtn('👁 示例结果', '查看内置示例的运行结果（只读）',
            function () { showExampleResult(pmod); }));
        }
      }
    }
  }

  /* ---------- 首次打开自动填充 + 自动展示示例结果（Phase C） ---------- */
  var SEEN_KEY = 'vp_example_seen';

  function autoFill(tries) {
    var off = false;
    try { off = localStorage.getItem(AUTO_KEY) === '0'; } catch (e) {}
    if (off) return;
    var sec = document.querySelector('section.card[id^="t-"]:not([style*="display: none"])');
    var mod = null;
    if (sec) {
      applyFor(sec);
      mod = resultModule(sec.id);
    } else if (PAGE_MAP[location.pathname]) {
      applyFor('page');
      mod = resultModule(location.pathname);
    } else if ((tries || 0) < 8) {
      /* /tools 的模块卡由 renderModuleTree() 按 ?g=#hash 异步渲染，
         可能晚于本函数首次执行；重试几轮等卡片出现再填。 */
      setTimeout(function () { autoFill((tries || 0) + 1); }, 400);
      return;
    }
    /* 首次访问：直接把示例结果摊开给用户看（之后不再自动弹，可点按钮再看） */
    var seen = false;
    try { seen = localStorage.getItem(SEEN_KEY) === '1'; } catch (e) {}
    if (mod && !seen) {
      try { localStorage.setItem(SEEN_KEY, '1'); } catch (e) {}
      setTimeout(function () { showExampleResult(mod); }, 600);
    }
  }

  function boot() {
    injectButtons();
    injectIndexButton();
    setTimeout(autoFill, 400);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }

  /* 供其它脚本/调试使用 */
  window.VPExamples = {
    files: F, map: MAP, pageMap: PAGE_MAP,
    apply: applyFor, inject: injectButtons, autofillKey: AUTO_KEY,
    showResult: showExampleResult
  };

  /* ============================================================
   * 示例结果查看器（阶段 C）
   * 读 /api/examples/<模块>（只读 databases/examples/results/，与真实结果隔离）
   * 图片内联、TSV/CSV 转表格、JSON 格式化、其余给下载链接。
   * ============================================================ */
  var RESULT_MAP = {
    't-convert': 'convert', 't-fastp': 'fastp', 't-identify': 'identify',
    't-assemble': 'assemble', 't-contigs': 'contigs', 't-verify': 'verify',
    't-align': 'align', 't-treebuild': 'quicktree', 't-sdt': 'sdt',
    't-virchain': 'virchain', 't-kvchain': 'kvchain',
    't-kvsuite': 'kvsuite', 't-consensus': 'consensus', 't-variant': 'variant',
    '/orf': 'orf', '/annotation': 'orfa', '/genome': 'genoplot',
    '/primer': 'primer', '/hostremoval': 'hostremoval',
    '/hostpredict': 'hostpredict',
    't-cdd': 'cdd', 't-hom': 'hom', '/logan': 'logan',
    't-synteny': 'synteny'
  };

  function resultModule(idOrPath) {
    return RESULT_MAP[idOrPath] || null;
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"]/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c];
    });
  }

  function tableHtml(text, maxRows) {
    var lines = text.replace(/\r/g, '').split('\n').filter(function (x) {
      return x.trim();
    });
    if (!lines.length) return '<p class="hint">（空文件）</p>';
    var sep = lines[0].indexOf('\t') >= 0 ? '\t' : ',';
    var rows = lines.slice(0, maxRows || 50).map(function (ln) {
      return ln.split(sep);
    });
    var h = '<div class="scroll-lg"><table class="tbl" style="font-size:11.5px">';
    h += '<tr>' + rows[0].map(function (c) {
      return '<th>' + esc(c) + '</th>';
    }).join('') + '</tr>';
    for (var i = 1; i < rows.length; i++) {
      h += '<tr>' + rows[i].map(function (c) {
        return '<td>' + esc(c) + '</td>';
      }).join('') + '</tr>';
    }
    h += '</table></div>';
    if (lines.length > rows.length) {
      h += '<p class="hint">仅显示前 ' + rows.length + ' 行，共 ' +
           lines.length + ' 行</p>';
    }
    return h;
  }

  function prettyJson(text) {
    try { return '<pre style="font-size:11.5px;max-height:340px;overflow:auto">' +
                 esc(JSON.stringify(JSON.parse(text), null, 1)) + '</pre>'; }
    catch (e) { return '<pre style="font-size:11.5px">' + esc(text) + '</pre>'; }
  }

  /* CDD / BLAST 的在线结果 JSON → 命中表（比裸 JSON 好看得多） */
  var HIT_COLS = {
    cdd: ['query', 'hit_type', 'accession', 'short_name', 'evalue',
          'from', 'to', 'superfamily'],
    hom: ['accession', 'title', 'sciname', 'identity', 'align_len',
          'evalue', 'bit_score']
  };
  var HIT_LABEL = {
    query: '查询', hit_type: '类型', accession: '登录号', short_name: '结构域',
    evalue: 'E-value', from: '起始', to: '终止', superfamily: '超家族',
    title: '描述', sciname: '物种', identity: '同一性(%)',
    align_len: '比对长度', bit_score: 'bit score'
  };

  function hitsHtml(text, module) {
    var d;
    try { d = JSON.parse(text); } catch (e) { return prettyJson(text); }
    if (!d || !d.hits || !d.hits.length) {
      return '<p class="hint">该示例未命中任何条目。</p>' + prettyJson(text);
    }
    var cols = HIT_COLS[module] || HIT_COLS.hom;
    var h = '<p class="hint">contig ' + esc(d.contig || '-') +
      (d.orf_len_aa ? ' · 最长 ORF ' + esc(d.orf_len_aa) + ' aa' : '') +
      (d.rid ? ' · NCBI RID ' + esc(d.rid) : '') +
      ' · 命中 ' + d.hits.length + ' 条</p>' +
      '<div class="scroll-lg"><table class="tbl" style="font-size:11.5px"><tr>';
    cols.forEach(function (c) { h += '<th>' + esc(HIT_LABEL[c] || c) + '</th>'; });
    h += '</tr>';
    d.hits.slice(0, 50).forEach(function (hit) {
      h += '<tr>' + cols.map(function (c) {
        return '<td>' + esc(hit[c]) + '</td>';
      }).join('') + '</tr>';
    });
    h += '</table></div>';
    if (d.hits.length > 50) {
      h += '<p class="hint">仅显示前 50 条，共 ' + d.hits.length + ' 条</p>';
    }
    return h;
  }

  /* ---------- 交互热图（可切换配色 / 悬浮看值） ---------- */
  /* 哪些模块有矩阵数据、数据在哪个文件、含哪些序列类型 */
  var MATRIX_SOURCES = {
    sdt:      { file: 'sdt_matrix.json',      seqtypes: ['nt'],  label: 'SDT 同一性（NT）' },
    identity: { file: 'identity.json',        seqtypes: ['nt', 'aa'], label: '同一性（NT+AA）' }
  };
  var COLORSCALES = [
    ['默认', 'YlGnBu'], ['Viridis', 'Viridis'], ['Plasma', 'Plasma'],
    ['RdYlBu', 'RdYlBu'], ['Inferno', 'Inferno'], ['Cividis', 'Cividis'],
    ['Blues', 'Blues'], ['Reds', 'Reds'], ['Greens', 'Greens'], ['PuOr', 'PuOr']
  ];

  function ensurePlotly() {
    if (window.Plotly) return Promise.resolve();
    if (window.__plotlyLoading) return window.__plotlyLoading;
    window.__plotlyLoading = new Promise(function (resolve, reject) {
      var s = document.createElement('script');
      s.src = '/static/plotly.min.js';
      s.onload = resolve;
      s.onerror = function () {
        delete window.__plotlyLoading;
        reject(new Error('Plotly 加载失败'));
      };
      document.head.appendChild(s);
    });
    return window.__plotlyLoading;
  }

  /* 按 module/key 取矩阵数据并重排（sdt 的 order 字段） */
  function loadMatrixData(module, src) {
    var url = '/api/examples/' + encodeURIComponent(module) + '/' + src.file;
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (d) {
      var mat = (d.matrix != null) ? d.matrix : (d.nt || null);
      var aa = d.aa || null;
      var names = d.names || [];
      if (d.order && d.order.length) {
        names = d.order.map(function (i) { return names[i]; });
        mat = mat.map(function (_, r) {
          return d.order.map(function (c) { return mat[d.order[r]][c]; });
        });
      }
      return { names: names, nt: d.matrix != null ? mat : (d.nt || mat),
               aa: aa, seqtype: d.seqtype || 'nt', n: d.n || names.length };
    });
  }

  function renderHeatmap(el, data, colorscale, seqtype) {
    var z = seqtype === 'aa' ? data.aa : data.nt;
    if (!z || !z.length) return;
    var m = data.names || [];
    var unit = seqtype === 'aa' ? 'AA 同一性(%)' : 'NT 同一性(%)';
    var trace = {
      z: z, x: m, y: m, type: 'heatmap', colorscale: colorscale,
      zmin: 0, zmax: 100,
      hovertemplate: '<b>%{x}</b><br>%{y}<br>' + unit + ': %{z:.1f}<extra></extra>',
      colorbar: { title: { text: unit, side: 'right' }, thickness: 14, len: 0.85 }
    };
    var layout = {
      margin: { l: Math.max(150, (m[0] || '').length * 7.2), r: 16, t: 44, b: 120 },
      xaxis: { tickangle: 45, automargin: true, showgrid: false },
      yaxis: { automargin: true, showgrid: false, autorange: 'reversed' },
      height: Math.max(380, m.length * 46 + 160),
      paper_bgcolor: '#fff', plot_bgcolor: '#fff'
    };
    Plotly.newPlot(el, [trace], layout, { responsive: true, displayModeBar: true });
  }

  function renderMatrixHeatmapPanel(module, box) {
    var src = MATRIX_SOURCES[module];
    if (!src || !box) return;
    loadMatrixData(module, src).then(function (mdata) {
      if (!box.isConnected) return;
      var stype = src.seqtypes[0];
      box.innerHTML = '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;' +
        'margin:8px 0"><b style="font-size:12.5px;color:#1a5276">🗺 交互热图（' +
        esc(src.label) + '）</b>' +
        '<span style="margin-left:auto;display:flex;gap:6px;align-items:center">' +
        (src.seqtypes.length > 1
          ? '<span class="hint">类型</span><select id="vpMatrixSt" style="padding:2px 6px">' +
            src.seqtypes.map(function (t) { return '<option value="' + t + '">' +
              (t === 'aa' ? 'AA' : 'NT') + '</option>'; }).join('') + '</select>' : '') +
        '<span class="hint">配色</span><select id="vpMatrixCs" style="padding:2px 6px">' +
        COLORSCALES.map(function (c) { return '<option value="' + c[0] + '">' +
          c[0] + '</option>'; }).join('') + '</select>' +
        '<span class="hint">悬浮看值 · 可缩放 · 可下载</span></div></div>' +
        '<div id="vpMatrixEl" style="width:100%;overflow:auto"><p class="hint">⏳ 渲染中…</p></div>';
      function rendercs() {
        var key = box.querySelector('#vpMatrixCs').value;
        var cs = COLORSCALES.filter(function (c) { return c[0] === key; })[0] ||
                 COLORSCALES[0];
        var st = (box.querySelector('#vpMatrixSt') || {}).value || stype;
        renderHeatmap(box.querySelector('#vpMatrixEl'), mdata, cs[1], st);
      }
      box.querySelector('#vpMatrixCs').addEventListener('change', rendercs);
      var stsel = box.querySelector('#vpMatrixSt');
      if (stsel) stsel.addEventListener('change', rendercs);
      rendercs();
    }).catch(function (e) {
      if (box && box.isConnected) {
        box.innerHTML = '<p class="hint">交互热图不可用: ' + esc(e.message || e) + '</p>';
      }
    });
  }

  function showExampleResult(module) {
    if (!module) {
      if (typeof toast === 'function') toast('该模块暂无示例结果', '', { ttl: 2200 });
      return;
    }
    var mask = document.createElement('div');
    mask.className = 'dlgmask';
    mask.style.zIndex = 320;
    mask.innerHTML = '<div class="dlg" style="width:min(1120px,95vw);max-height:90vh;' +
      'display:flex;flex-direction:column">' +
      '<div class="dlghead"><b id="vpExTitle">👁 示例结果</b>' +
      '<button class="btn small" id="vpExClose">✕</button></div>' +
      '<div id="vpExBody" style="overflow:auto;padding:12px 16px;flex:1 1 auto">' +
      '<p class="hint">⏳ 加载中…</p></div></div>';
    document.body.appendChild(mask);
    mask.querySelector('#vpExClose').addEventListener('click', function () {
      mask.remove();
    });
    mask.addEventListener('click', function (e) {
      if (e.target === mask) mask.remove();
    });
    var body = mask.querySelector('#vpExBody');
    fetch('/api/examples/' + encodeURIComponent(module)).then(function (r) {
      if (!r.ok) throw new Error('HTTP ' + r.status);
      return r.json();
    }).then(function (d) {
      mask.querySelector('#vpExTitle').textContent =
        '👁 示例结果 · ' + (d.title || module) + '（' + d.files.length + ' 个产物）';
      var imgs = d.files.filter(function (f) { return f.kind === 'image'; });
      var pdfs = d.files.filter(function (f) { return f.kind === 'pdf'; });
      var htmls = d.files.filter(function (f) { return f.kind === 'html'; });
      var texts = d.files.filter(function (f) { return f.kind === 'text'; });
      var others = d.files.filter(function (f) { return f.kind === 'other'; });
      var html = '<p class="hint">生成于 ' + esc(d.generated_at || '-') +
        ' · 目录 databases/examples/results/' + esc(module) +
        '/（只读，与真实结果隔离）</p>';
      if (imgs.length) {
        html += '<div style="display:flex;flex-wrap:wrap;gap:10px;margin:10px 0">';
        imgs.forEach(function (f) {
          var url = '/api/examples/' + encodeURIComponent(module) + '/' + f.path;
          html += '<div style="border:1px solid var(--line-200,#e3e3e3);border-radius:8px;padding:6px;background:#fff">' +
            '<div class="hint" style="margin:0 0 4px">' + esc(f.path) + '</div>' +
            '<img src="' + url + '" style="max-width:460px;max-height:320px;display:block">' +
            '</div>';
        });
        html += '</div>';
      }
      body.innerHTML = html + '<div id="vpExMatrix"></div><div id="vpExTexts"></div>';
      var textsBox = body.querySelector('#vpExTexts');
      /* 有矩阵数据的模块：渲染交互热图（可切配色 / NT-AA），无矩阵则忽略 */
      if (MATRIX_SOURCES[module]) {
        ensurePlotly().then(function () {
          renderMatrixHeatmapPanel(module, body.querySelector('#vpExMatrix'));
        }).catch(function (e) {
          var mb = body.querySelector('#vpExMatrix');
          if (mb) mb.innerHTML = '<p class="hint">交互热图不可用: ' +
            esc(e.message || e) + '</p>';
        });
      }
      /* PDF：不能当 <img>（会显示裂图），用同源 iframe 内嵌查看器预览 */
      if (pdfs.length) {
        var pd = document.createElement('div');
        pd.style.marginTop = '10px';
        pd.innerHTML = '<p class="hint">📄 PDF（内嵌预览）：</p>';
        pdfs.forEach(function (f) {
          var url = '/api/examples/' + encodeURIComponent(module) + '/' + f.path;
          var bx = document.createElement('details');
          bx.className = 'rpt-sec';
          bx.open = pdfs.length === 1;
          bx.style.marginTop = '6px';
          bx.innerHTML = '<summary>' + esc(f.path) + ' <span class="hint">(' +
            (f.size / 1024).toFixed(1) + ' KB · 内嵌预览)</span></summary>' +
            '<div style="margin-top:6px"><iframe src="' + url +
            '" type="application/pdf" style="width:100%;height:64vh;border:1px solid ' +
            'var(--line-200,#e3e3e3);border-radius:8px;background:#fff"></iframe></div>' +
            '<p class="hint" style="margin:4px 0 0"><a href="' + url +
            '" target="_blank">在新标签页打开 ↗</a></p>';
          pd.appendChild(bx);
        });
        textsBox.appendChild(pd);
      }
      /* 报告类（.html）：同源 iframe 内联渲染（LOGAN 溯源报告等） */
      htmls.forEach(function (f) {
        var url = '/api/examples/' + encodeURIComponent(module) + '/' + f.path;
        var box = document.createElement('details');
        box.className = 'rpt-sec';
        box.open = htmls.length === 1;
        box.style.marginTop = '8px';
        box.innerHTML = '<summary>' + esc(f.path) + ' <span class="hint">(' +
          (f.size / 1024).toFixed(1) + ' KB · 在线预览)</span></summary>' +
          '<div style="margin-top:6px"><iframe src="' + url +
          '" style="width:100%;height:70vh;border:1px solid var(--line-200,#e3e3e3);' +
          'border-radius:8px;background:#fff"></iframe></div>' +
          '<p class="hint" style="margin:4px 0 0"><a href="' + url +
          '" target="_blank">在新标签页打开 ↗</a></p>';
        textsBox.appendChild(box);
      });
      texts.forEach(function (f) {
        var url = '/api/examples/' + encodeURIComponent(module) + '/' + f.path;
        var card = document.createElement('details');
        card.className = 'rpt-sec';
        card.style.marginTop = '8px';
        card.innerHTML = '<summary>' + esc(f.path) + ' <span class="hint">(' +
          (f.size / 1024).toFixed(1) + ' KB)</span></summary>' +
          '<div class="rpt-sec-body" data-url="' + url + '"><p class="hint">展开后加载…</p></div>';
        card.addEventListener('toggle', function () {
          if (!card.open || card.dataset.loaded) return;
          card.dataset.loaded = '1';
          var box = card.querySelector('.rpt-sec-body');
          fetch(url).then(function (r) { return r.text(); }).then(function (t) {
            var ext = f.path.split('.').pop().toLowerCase();
            if (ext === 'json' && HIT_COLS[module]) box.innerHTML = hitsHtml(t, module);
            else if (ext === 'json') box.innerHTML = prettyJson(t);
            else if (ext === 'tsv' || ext === 'csv') box.innerHTML = tableHtml(t);
            else box.innerHTML = '<pre style="font-size:11.5px;max-height:300px;overflow:auto">' +
              esc(t.slice(0, 20000)) + (t.length > 20000 ? '\n…（已截断）' : '') + '</pre>';
          }).catch(function () { box.innerHTML = '<p class="hint">加载失败</p>'; });
        });
        textsBox.appendChild(card);
      });
      if (others.length) {
        var o = document.createElement('div');
        o.style.marginTop = '10px';
        o.innerHTML = '<p class="hint">其它产物：</p>' + others.map(function (f) {
          var url = '/api/examples/' + encodeURIComponent(module) + '/' + f.path;
          return '<a class="btn small" style="margin:2px" href="' + url + '" download>' +
                 esc(f.path) + '</a>';
        }).join('');
        textsBox.appendChild(o);
      }
    }).catch(function (e) {
      body.innerHTML = '<p class="hint">示例结果加载失败: ' + esc(e.message || e) + '</p>';
    });
  }

  /* ---------- 全局「示例结果总览」：一次看全部模块（含无卡片的 API 工具） ---------- */
  function showExamplesIndex() {
    var mask = document.createElement('div');
    mask.className = 'dlgmask';
    mask.style.zIndex = 330;
    mask.innerHTML = '<div class="dlg" style="width:min(900px,95vw);max-height:85vh;' +
      'display:flex;flex-direction:column">' +
      '<div class="dlghead"><b>👁 内置示例结果总览</b>' +
      '<button class="btn small" id="vpIdxClose">✕</button></div>' +
      '<div id="vpIdxBody" style="overflow:auto;padding:12px 16px;flex:1 1 auto">' +
      '<p class="hint">⏳ 加载中…</p></div></div>';
    document.body.appendChild(mask);
    mask.querySelector('#vpIdxClose').addEventListener('click', function () {
      mask.remove();
    });
    mask.addEventListener('click', function (e) {
      if (e.target === mask) mask.remove();
    });
    var box = mask.querySelector('#vpIdxBody');
    fetch('/api/examples').then(function (r) { return r.json(); }).then(function (list) {
      var h = '<p class="hint">全部产物固化在 <code>databases/examples/results/</code>' +
        '（只读，与真实运行结果隔离），共 ' + list.length + ' 个模块。</p>' +
        '<table class="tbl" style="font-size:12px"><tr><th>模块</th><th>说明</th>' +
        '<th>产物</th><th>生成时间</th><th></th></tr>';
      list.forEach(function (m) {
        h += '<tr><td><code>' + esc(m.module) + '</code></td><td>' + esc(m.title) +
          '</td><td>' + m.n_files + '</td><td>' + esc(m.generated_at) + '</td>' +
          '<td><button class="btn small" data-mod="' + esc(m.module) +
          '">👁 查看</button></td></tr>';
      });
      box.innerHTML = h + '</table>';
      box.querySelectorAll('button[data-mod]').forEach(function (b) {
        b.addEventListener('click', function () { showExampleResult(b.dataset.mod); });
      });
    }).catch(function (e) {
      box.innerHTML = '<p class="hint">加载失败: ' + esc(e.message || e) + '</p>';
    });
  }

  function injectIndexButton() {
    if (document.getElementById('vpExIdxBtn')) return;
    var b = document.createElement('button');
    b.id = 'vpExIdxBtn';
    b.type = 'button';
    b.className = 'btn small';
    b.textContent = '👁 示例结果';
    b.title = '查看全部内置示例结果（只读，与真实结果隔离）';
    b.style.cssText = 'position:fixed;right:14px;bottom:14px;z-index:300;opacity:.92;' +
      'box-shadow:0 4px 14px rgba(0,0,0,.18)';
    b.addEventListener('click', showExamplesIndex);
    document.body.appendChild(b);
  }
})();
