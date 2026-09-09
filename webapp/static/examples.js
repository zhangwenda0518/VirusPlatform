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
    't-cdd':       { cddSeqIn: 'CONTIGS' },
    't-hom':       { homSeqIn: 'CONTIGS' },
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
    '/logan':       { pasteSeq: 'TMV_TEXT' }   /* 文本域：填序列内容 */
  };

  var AUTO_KEY = 'vp_example_autofill';
  var _tmvText = null;

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
      if (setField(id, map[id])) n++;
    }
    return n;
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
    fetch('/' + F.TMV).then(function (r) { return r.text(); }).then(function (t) {
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

  function autoFill() {
    var off = false;
    try { off = localStorage.getItem(AUTO_KEY) === '0'; } catch (e) {}
    if (off) return;
    var sec = document.querySelector('section.card[id^="t-"]:not([style*="display: none"])');
    var mod = null;
    if (sec) {
      applyFor(sec);
      mod = resultModule(sec.id);
    } else {
      applyFor('page');
      mod = resultModule(location.pathname);
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
    '/hostpredict': 'hostpredict'
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
            (f.path.endsWith('.svg')
              ? '<img src="' + url + '" style="max-width:460px;max-height:320px;display:block">'
              : '<img src="' + url + '" style="max-width:460px;max-height:320px;display:block">') +
            '</div>';
        });
        html += '</div>';
      }
      body.innerHTML = html + '<div id="vpExTexts"></div>';
      var textsBox = body.querySelector('#vpExTexts');
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
            if (ext === 'json') box.innerHTML = prettyJson(t);
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
})();
