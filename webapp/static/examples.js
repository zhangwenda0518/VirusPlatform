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
    't-identify':  { i_type: 'fastq', i_input: 'R1', i_input2: 'R2' },
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

  /* ---------- 「✨ 示例」按钮注入 ---------- */
  function injectButtons() {
    document.querySelectorAll('section.card[id^="t-"]').forEach(function (sec) {
      if (sec.querySelector('.vp-ex-btn')) return;
      if (!MAP[sec.id] && sec.id !== 't-kvsuite' && sec.id !== 't-kvchain') return;
      var h2 = sec.querySelector('h2');
      if (!h2) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'btn small vp-ex-btn';
      b.style.marginLeft = '8px';
      b.textContent = '✨ 示例';
      b.title = '一键填入内置示例数据（databases/examples/）';
      b.addEventListener('click', function (ev) {
        ev.preventDefault();
        var n = applyFor(sec);
        if (typeof toast === 'function') {
          toast(n ? '已填入示例数据' : '该模块暂未配置示例', '', { ttl: 2200 });
        }
      });
      h2.appendChild(b);
    });
    /* 独立页面：在页面主标题旁注入 */
    if (PAGE_MAP[location.pathname] && !document.querySelector('.vp-ex-btn')) {
      var h = document.querySelector('main h2, .card h2');
      if (h) {
        var b2 = document.createElement('button');
        b2.type = 'button';
        b2.className = 'btn small vp-ex-btn';
        b2.style.marginLeft = '8px';
        b2.textContent = '✨ 示例';
        b2.title = '一键填入内置示例数据';
        b2.addEventListener('click', function (ev) {
          ev.preventDefault();
          var n = applyFor('page');
          if (typeof toast === 'function') {
            toast(n ? '已填入示例数据' : '该模块暂未配置示例', '', { ttl: 2200 });
          }
        });
        h.appendChild(b2);
      }
    }
  }

  /* ---------- 首次打开自动填充（Phase C） ---------- */
  function autoFill() {
    var off = false;
    try { off = localStorage.getItem(AUTO_KEY) === '0'; } catch (e) {}
    if (off) return;
    var sec = document.querySelector('section.card[id^="t-"]:not([style*="display: none"])');
    if (sec) { applyFor(sec); return; }
    applyFor('page');
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
    apply: applyFor, inject: injectButtons, autofillKey: AUTO_KEY
  };
})();
