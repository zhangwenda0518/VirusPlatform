// ---------------- 管道卡片 / 批量导入 + 批处理队列 ----------------
// 2026-09-13 自 app.js 拆出。普通 script 共享全局作用域：本文件在
// app.js 之后加载，可直接使用 $/esc/t/toast/jfetch 等核心工具；页面
// 内联脚本与其它 app-*.js 里的同名调用按全局解析（加载顺序见模板）。
// 注意：本块内引用的其它 app-*.js 函数均为调用期解析（事件/回调触发），
// 不存在加载期交叉依赖。
// ---------------- 批量导入 + 批处理队列 ----------------
async function batchCreate(btn) {
  return withBtn(btn, async () => {
    const errBox = $('bErr');
    errBox.textContent = '';
    const project = ($('batchProject')?.value || '').trim();
    const lines = ($('batchText')?.value || '').split(/\r?\n/)
      .map(l => l.trim()).filter(l => l && !l.startsWith('#'));
    if (!lines.length) { errBox.textContent = t('pp.needRows', '请至少粘贴一行样品信息'); return; }
    const created = [];
    const adjusted = [];
    for (const line of lines) {
      const parts = line.split(/\t| {2,}|,/).map(s => s.trim());
      const [sample, r1, r2] = parts;
      if (!sample || !r1) { errBox.textContent = `${t('pp.badRow', '格式错误（需要 样品名+R1）')}: ${line}`; return; }
      const res = await apiCreateSample({ sample, r1, r2: r2 || null, project });
      if (!res.ok) {
        if (res.conn) setConnBanner(true);
        errBox.textContent = `${sample}: ${res.error}`; return;
      }
      // 用后端返回的**实际**目录名入队/展示，不用 TSV 里的原始写法
      created.push(res.data.sample);
      if (res.data.note) adjusted.push(sample + ' → ' + res.data.sample);
    }
    $('batchText').value = '';
    toast(t('pp.batchCreate'), `${created.length} ${t('dl.samples')}`, {ttl: 4000});
    if (adjusted.length) {
      errBox.textContent = t('pp.nameAdjustedN', '')
        .replace('{n}', adjusted.length) + '：' + adjusted.join('，');
    }
    loadSamples();
    if ($('batchEnq')?.checked && created.length) {
      try {
        const r = await fetch('/api/queue/add', {
          method: 'POST', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({ samples: created, project })});
        if (!r.ok) {
          const d = await r.json().catch(() => ({}));
          toast(t('pp.qAddFail', '加入队列失败'), d.error || (r.status + ''), {kind: 'failed', ttl: 12000});
        }
      } catch (e) {
        toast(t('pp.qAddFail', '加入队列失败'), String(e), {kind: 'failed', ttl: 12000});
      }
      loadQueue();
    }
  }, '⏳ 批量创建中…');
}

const Q_ST = { queued: '排队中', running: '运行中', done: '已完成',
               failed: '失败', cancelled: '已取消' };
async function loadQueue() {
  const box = $('queueBox');
  if (!box) return;
  try {
    const q = await (await fetch('/api/queue')).json();
    if (!q.items || !q.items.length) {
      box.innerHTML = `<p class="hint">${t('pp.queueEmpty')}</p>`;
      return;
    }
    box.innerHTML = '<table class="tbl dl-mini"><tr>' +
      `<th>${t('pp.qSample')}</th><th>${t('pp.qStatus')}</th><th>${t('pp.qOps')}</th></tr>` +
      q.items.map(it => {
        const st = Q_ST[it.status] || it.status;
        const statCls = it.status === 'done' ? 'done'
          : it.status === 'failed' ? 'failed'
          : it.status === 'running' ? 'running' : 'queued';
        return `<tr><td><b>${esc(it.sample)}</b>` +
          (it.project ? ` <span class="hint" style="margin:0">🏷 ${esc(it.project)}</span>` : '') +
          `</td><td><span class="tstat ${statCls}">${st}</span>` +
          (it.error ? `<div class="hint" style="color:#b03a2e;margin:2px 0 0">${esc(it.error)}</div>` : '') +
          `</td><td>${it.status === 'queued'
            ? `<button class="btn small danger" onclick="queueRemove('${esc(it.id)}')">✖</button>` : ''}</td></tr>`;
      }).join('') + '</table>';
  } catch (e) { /* 静默，下一次轮询重试 */ }
}

async function queueRemove(id) {
  try {
    const r = await fetch(`/api/queue/${encodeURIComponent(id)}/remove`, {method: 'POST'});
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      toast(t('pp.qRemoveFail', '移除条目失败'), d.error || (r.status + ''), {kind: 'failed', ttl: 12000});
    }
  } catch (e) {
    toast(t('pp.qRemoveFail', '移除条目失败'), String(e), {kind: 'failed', ttl: 12000});
  }
  loadQueue();
}

async function queueClear() {
  try {
    const r = await fetch('/api/queue/clear_finished', {method: 'POST'});
    if (!r.ok) {
      const d = await r.json().catch(() => ({}));
      toast(t('pp.qClearFail', '清除已完成条目失败'), d.error || (r.status + ''), {kind: 'failed', ttl: 12000});
    }
  } catch (e) {
    toast(t('pp.qClearFail', '清除已完成条目失败'), String(e), {kind: 'failed', ttl: 12000});
  }
  loadQueue();
}

async function selectSample(name) {
  curSample = name;
  // 写进全局上下文（跨模块共享）；取代原来只写不读的 vp_last_sample
  VP_CTX.setSample(name || '');
  loadSamples();
  try {
    const r = await fetch('/api/pipeline/' + encodeURIComponent(name) +
                          '?lang=' + encodeURIComponent(VP_LANG));
    if (!r.ok) { alert(t('c.loadFail', '读取失败')); return; }
    renderPipe(await r.json());
  } catch (e) { setConnBanner(true); }
}

/* 管道 DAG 视图：③组装后的下游分支互不依赖（依赖关系见 Virus_Platform_Core/pipeline.py STAGE_REGISTRY），
   并排展示为紧凑节点，点击节点展开完整卡片（参数/产物/日志） */
const PIPE_FANOUT = ['verify', 'consensus', 'hostana', 'orf', 'orfa', 'phylo', 'primer', 'gbdraw'];

/* 分析模板：一键按预设组合运行（stages=null 表示全部可用阶段；
   exclude 表示「全部可用阶段里剔除这些」） */
const PIPE_TEMPLATES = [
  { id: 'fast', label: '⚡ 快速筛查',
    tip: '质控 → 宿主去除 → 已知病毒识别与定量 → 报告（最快出结果）',
    stages: ['fastp', 'host', 'kvsuite', 'report'] },
  { id: 'std',  label: '🎯 标准分析',
    tip: '质控 → 转换 → 宿主去除 → 已知病毒识别与定量 → 组装 → 验证 → ORF → 进化树 → 报告',
    stages: ['fastp', 'fq2fa', 'host', 'kvsuite', 'assembly', 'verify', 'orf', 'phylo', 'report'] },
  { id: 'full', label: '🔬 完整注释',
    tip: '全部可用阶段（含宿主预测 / 功能注释 / 引物设计 / 基因组图），不含子采样',
    stages: null, exclude: ['subsample'] },
];

function runTemplate(sample, id) {
  const tpl = PIPE_TEMPLATES.find(x => x.id === id);
  if (!tpl) return;
  let usable = curStages.filter(s => s.status !== 'unavailable').map(s => s.stage);
  if (tpl.exclude) usable = usable.filter(k => !tpl.exclude.includes(k));
  const stages = tpl.stages ? tpl.stages.filter(k => usable.includes(k)) : usable;
  if (!stages.length) { alert(t('pp.tplNone', '模板所需阶段当前不可用')); return; }
  runStages(sample, stages);
}

let curBranch = '';   // 当前展开的分支节点（fan-out 详情卡）
let cardIdx = 0;      // 阶段卡片序号（renderPipe 每次渲染前重置）

function toggleBranch(stage) {
  curBranch = curBranch === stage ? '' : stage;
  document.querySelectorAll('#pipe .pipe-branch-details > .stage-card').forEach(el => {
    el.style.display = el.dataset.stage === curBranch ? '' : 'none';
  });
  document.querySelectorAll('#pipe .pipe-node').forEach(el =>
    el.classList.toggle('on', el.dataset.stage === curBranch));
}

function renderPipe(d) {
  const stMap = {done: t('pp.done'), ready: t('pp.ready'),
                 blocked: t('pp.blocked'), unavailable: t('pp.unavailable'),
                 running: t('pp.running'), skipped: t('pp.skipped')};
  curStages = d.stages;
  cardIdx = 0;                     // 每次渲染重置序号
  const byKey = {}; d.stages.forEach(s => byKey[s.stage] = s);
  const saved = collectParams();   // 重渲染前保存参数值
  const gmap = {};
  (d.groups || []).forEach(([g, ks]) => ks.forEach(k => gmap[k] = g));

  const card = (s, hidden) => {
    const i = cardIdx++;
    const canRun = s.status === 'ready' || s.status === 'done'
                || s.status === 'skipped';
    const isFresh = s.status === 'ready' || s.status === 'skipped';
    const btns = canRun ? `
      <button class="btn small ${isFresh ? 'primary' : ''}"
              data-sample="${esc(d.sample)}"
              onclick="runStages(this.dataset.sample, ['${s.stage}'])">
        ${s.status === 'done' ? t('pp.rerun') : t('pp.runThis')}</button>
      <button class="btn small" data-sample="${esc(d.sample)}"
              onclick="runUpTo(this.dataset.sample, '${s.stage}')">
        ${t('pp.runTo')}</button>` :
      (s.status === 'unavailable' ?
        `<span class="hint" style="margin:0">${t('pp.installHint')}</span>` : '');
    const viewBtn = s.view
      ? ` <button class="btn small" data-sample="${esc(d.sample)}" data-dir="${esc(s.dir)}" data-view="${esc(s.view.split('/').pop())}" data-stage="${esc(s.stage)}"
              onclick="previewStageFile(this.dataset.sample,this.dataset.dir,this.dataset.view,this.dataset.stage)">📊 ${t('c.view')}</button>` : '';
    const files = (s.outputs || []).map(o =>
      `<span>📄 ${esc(o.name.split('/').pop())} · ${fmtSize(o.size)}</span>`).join('');
    const params = renderStageParams(s.stage, saved);
    return `<div class="stage-card ${s.status}" data-stage="${s.stage}"${hidden ? ' style="display:none"' : ''}>
      <div class="stage-head"><span class="no">${i + 1}</span>
        <span class="nm">${esc(s.name)}</span>
        <span class="sbadge ${s.status}">${stMap[s.status] || s.status}</span></div>
      <div class="stage-sum">${esc(s.summary || t('pp.notRun'))}</div>
      ${files ? `<div class="stage-files">${files}</div>` : ''}
      ${params}
      <div class="stage-btns">${btns}${viewBtn}</div>
      <div class="stage-log" id="log-${s.stage}"></div></div>`;
  };
  const arrow = () => `<div class="pipe-arrow">↓</div>`;

  // 依赖分层：预处理链 → ②b 已知病毒识别与定量 → ③组装 → 下游并行分支 → ⑩报告；
  // 未来新增的未知阶段兜底追加在报告前。
  // 注意：② 病毒筛查（kraken2 分类）已于 2026-09-10 退役，阶段键由 'virus'
  // 换成 'kvsuite'；这里曾漏改，导致 ②b 卡片既不匹配 byKey.virus、
  // 也不在 known 集合里，被当成 extras 追加到 ⑩报告**之后**（顺序错乱）。
  const pre = ((d.groups || [])[0] || [null, []])[1].filter(k => byKey[k]).map(k => byKey[k]);
  const fanout = PIPE_FANOUT.map(k => byKey[k]).filter(Boolean);
  const known = new Set([...pre.map(s => s.stage), 'kvsuite', 'assembly', 'report', ...PIPE_FANOUT]);
  const extras = d.stages.filter(s => !known.has(s.stage));

  let html = `
    <div style="display:flex;justify-content:space-between;align-items:center;
                flex-wrap:wrap;gap:8px;margin-bottom:8px">
      <div><b style="font-size:17px;color:var(--green-900)">🧪 ${esc(d.sample)}</b>
        <div class="hint" style="margin:4px 0 0">${t('pp.input')}${esc(d.r1 || t('pp.none'))}
          ${d.r2 ? ' ＋ ' + esc(d.r2) : ` ${t('pp.single')}`}</div></div>
      <button class="btn primary" data-sample="${esc(d.sample)}"
              onclick="runStages(this.dataset.sample, null)">
        ${t('pp.runAll')}</button>
    </div>
    <div class="pipe-templates">
      <span class="hint" style="margin:0">${t('pp.tplHint', '分析模板：')}</span>
      ${PIPE_TEMPLATES.map(tpl =>
        `<button class="btn small" title="${esc(tpl.tip)}"
                 data-sample="${esc(d.sample)}" onclick="runTemplate(this.dataset.sample, '${tpl.id}')">${esc(tpl.label)}</button>`).join('')}
    </div>`;

  if (pre.length) {
    html += `<div class="group-title">${esc(gmap[pre[0].stage] || '')}</div>` +
      pre.map(s => card(s)).join(arrow()) + arrow();
  }
  if (byKey.kvsuite) {
    html += `<div class="group-title">${esc(gmap.kvsuite || '')}</div>` +
      card(byKey.kvsuite) + arrow();
  }
  if (byKey.assembly) {
    html += `<div class="group-title">${esc(gmap.assembly || '')}</div>` + card(byKey.assembly);
  }
  if (fanout.length) {
    html += `<div class="group-title">${esc(gmap.orf || '')} ·
        ${t('pp.branchHint', '并行分支（互不依赖，点节点展开参数与日志）')}</div>
      <div class="pipe-branch-row${fanout.length > 1 ? ' fanned' : ''}">
        ${fanout.map(s => `
          <div class="pipe-node ${s.status}" data-stage="${s.stage}"
               onclick="toggleBranch('${s.stage}')">
            <b>${esc(s.name)}</b>
            <span class="sbadge ${s.status}">${stMap[s.status] || s.status}</span>
            ${(s.status === 'ready' || s.status === 'done' ||
               s.status === 'skipped') ? `
              <button class="btn small" title="${t('pp.runThis')}"
                onclick="event.stopPropagation();if(curBranch!=='${s.stage}')toggleBranch('${s.stage}');
                         runStages('${esc(d.sample)}', ['${s.stage}'])">▶</button>` : ''}
          </div>`).join('')}
      </div>
      <div class="pipe-branch-details">
        ${fanout.map(s => card(s, true)).join('')}
      </div>` + arrow();
  }
  if (byKey.report) {
    html += `<div class="group-title">${esc(gmap.report || '')}</div>` + card(byKey.report);
  }
  extras.forEach(s => { html += arrow() + card(s); });
  $('pipe').innerHTML = html;
}

// 各阶段专属参数（渲染进对应卡片；label 为 i18n 键 pp.<key>）
const STAGE_PARAMS = {
  subsample: [
    { id: 'subsample', label: 'pp.subPairs', type: 'number', def: 100000 },
  ],
  fastp: [
    { id: 'fastp_dedup', label: 'pp.fastp_dedup', type: 'chk', def: false },
  ],
  fq2fa: [
    { id: 'do_fq2fa', label: 'pp.do_fq2fa', type: 'chk', def: true },
  ],
  host: [
    { id: 'db_host', label: 'pp.db_host', type: 'dir', def: '' },
  ],
  /* 病毒参考库目录挂在 ②b 上。以前它挂在已退役的 'virus' 阶段键下，
     而 pipeline_overview 永远不会产出 'virus' 卡片 → 输入框从不渲染，
     collectParams 取到 null，用户无法在管道页指定病毒库（只能用默认值）。 */
  kvsuite: [
    { id: 'db_virus', label: 'pp.db_virus', type: 'dir', def: '' },
  ],
  assembly: [
    { id: 'assembly_mode', label: 'pp.assembly_mode', type: 'select', def: 'metaviral',
      opts: [['metaviral', 'metaviral'], ['rna', 'rna'], ['meta', 'meta'],
             ['isolate', 'isolate']] },
    { id: 'assembly_input', label: 'pp.assembly_input', type: 'select', def: 'virus',
      opts: [['virus', '② virus'], ['kept', '① host-free'], ['raw', 'raw']] },
    { id: 'memory', label: 'pp.memory', type: 'number', def: 64 },
    { id: 'min_contig_len', label: 'pp.min_contig_len', type: 'number', def: 200 },
  ],
  orf: [
    { id: 'min_orf_aa', label: 'pp.min_orf_aa', type: 'number', def: 100 },
  ],
  verify: [
    { id: 'verify_host', label: 'pp.verify_host', type: 'select', def: 'all',
      opts: [['all', 'all'], ['plants', 'plants'], ['fungi', 'fungi'],
             ['bacteria', 'bacteria'], ['invertebrates', 'invertebrates'],
             ['vertebrates', 'vertebrates'], ['algae', 'algae'],
             ['protozoa', 'protozoa'], ['archaea', 'archaea']] },
    { id: 'verify_methods', label: 'pp.verify_methods', type: 'multichk',
      def: ['blastx', 'cdd'],
      opts: [['blastx', 'blastx'], ['cdd', 'CDD']] },
    { id: 'verify_combine', label: 'pp.verify_combine', type: 'select',
      def: 'union',
      opts: [['union', 'union'], ['intersect', 'intersect']] },
  ],
  phylo: [
    { id: 'do_trim', label: 'pp.do_trim', type: 'chk', def: true },
    { id: 'top_n_refs', label: 'pp.top_n_refs', type: 'number', def: 10 },
    { id: 'tree_tool', label: 'pp.tree_tool', type: 'select', def: 'fasttree',
      opts: [['fasttree', 'FastTree'], ['nj', 'NJ（快速）'], ['iqtree', 'IQ-TREE']] },
    { id: 'tree_sampling', label: 'pp.tree_sampling', type: 'select', def: 'blast',
      opts: [['blast', 'blast'], ['macro', 'macro'], ['genus', 'genus'],
             ['lineage', 'lineage']] },
    { id: 'ncbi_refs', label: 'pp.ncbi_refs', type: 'text', def: '' },
  ],
  primer: [
    { id: 'primer_mode', label: 'pp.primer_mode', type: 'select', def: 'conserved',
      opts: [['conserved', 'conserved'], ['plain', 'plain']] },
    { id: 'specificity', label: 'pp.specificity', type: 'chk', def: false },
  ],
  gbdraw: [
    { id: 'gbdraw_max', label: 'pp.gbdraw_max', type: 'number', def: 12 },
    { id: 'plot_engine', label: 'pp.plot_engine', type: 'select', def: 'auto',
      opts: [['auto', 'auto'], ['gbdraw', 'gbdraw'], ['dfv', 'DFV']] },
    { id: 'gbdraw_fasta', label: 'pp.gbdraw_fasta', type: 'file', def: '' },
    { id: 'gbdraw_ann', label: 'pp.gbdraw_ann', type: 'file', def: '' },
  ],
  report: [],
};

function renderStageParams(stage, saved) {
  const defs = STAGE_PARAMS[stage] || [];
  if (!defs.length) return '';
  const items = defs.map(p => {
    // 初值优先级：页面已填 > 设置页默认 > 代码缺省
    const dv = defVal(p.id, p.def);
    const cur = saved[p.id] !== undefined && saved[p.id] !== null ? saved[p.id] : dv;
    if (p.type === 'select') {
      const opts = p.opts.map(([v, txt]) =>
        `<option value="${v}" ${String(cur) === String(v) ? 'selected' : ''}>${txt}</option>`).join('');
      return `<div><label>${t(p.label)}</label><select id="${p.id}">${opts}</select></div>`;
    }
    if (p.type === 'dir') {
      const ph = { db_host: t('pp.dbHostPh'), db_virus: t('pp.dbVirusPh') }[p.id]
                 || t('pp.defPh');
      return `<div style="grid-column:1/-1"><label>${t(p.label)}</label>
        <div class="filerow">
          <input id="${p.id}" type="text" value="${cur}" placeholder="${ph}">
          <button class="btn small" onclick="browseDir('${p.id}')">📁</button>
        </div></div>`;
    }
    if (p.type === 'file') {
      const ph = { gbdraw_fasta: t('pp.gFastaPh'),
                   gbdraw_ann: t('pp.gAnnPh') }[p.id] || '';
      return `<div style="grid-column:1/-1"><label>${t(p.label)}</label>
        <div class="filerow">
          <input id="${p.id}" type="text" value="${cur}" placeholder="${ph}">
          <button class="btn small" onclick="browse('${p.id}')">📁</button>
        </div></div>`;
    }
    if (p.type === 'chk') {
      const on = saved[p.id] !== undefined ? saved[p.id] : !!dv;
      return `<label class="chk" style="align-self:end;margin-bottom:8px">
        <input type="checkbox" id="${p.id}" ${on ? 'checked' : ''}> ${t(p.label)}</label>`;
    }
    if (p.type === 'multichk') {
      // 多选（如验证证据方法）：name=p.id，值取勾选项；全不勾时 collectParams 回传 undefined，
      // 服务端回退默认值。
      const vals = Array.isArray(cur) ? cur.map(String)
                 : String(cur || '').split(/[,;]/).filter(Boolean);
      const boxes = p.opts.map(([v, txt]) =>
        `<label class="chk" style="margin-right:14px">
          <input type="checkbox" name="${p.id}" value="${v}"
            ${vals.includes(String(v)) ? 'checked' : ''}> ${txt}</label>`).join('');
      return `<div style="grid-column:1/-1"><label>${t(p.label)}</label>
        <div>${boxes}</div></div>`;
    }
    if (p.type === 'text') {
      return `<div style="grid-column:1/-1"><label>${t(p.label)}</label>
        <input id="${p.id}" type="text" value="${cur}" placeholder="${t('pp.ncbi_ph')}"></div>`;
    }
    return `<div><label>${t(p.label)}</label>
      <input id="${p.id}" type="number" value="${cur}"></div>`;
  }).join('');
  return `<div class="stage-params">${items}</div>`;
}

function collectParams() {
  return {
    threads: +($('threads')?.value) || undefined,
    confidence: +($('confidence')?.value) || 0,
    chunk_dir: ($('chunk_dir')?.value || '').trim() || null,
    subsample: +($('subsample')?.value) || undefined,
    db_host: ($('db_host')?.value || '').trim() || null,
    db_virus: ($('db_virus')?.value || '').trim() || null,
    assembly_mode: $('assembly_mode')?.value,
    assembly_input: $('assembly_input')?.value,
    memory: +($('memory')?.value) || undefined,
    min_contig_len: +($('min_contig_len')?.value) || undefined,
    min_orf_aa: +($('min_orf_aa')?.value) || undefined,
    do_trim: $('do_trim') === null ? undefined : !!($('do_trim')?.checked),
    top_n_refs: +($('top_n_refs')?.value) || undefined,
    tree_tool: $('tree_tool')?.value,
    tree_sampling: $('tree_sampling')?.value,
    ncbi_refs: ($('ncbi_refs')?.value || '').trim() || null,
    primer_mode: $('primer_mode')?.value,
    specificity: !!($('specificity')?.checked),
    fastp_dedup: !!($('fastp_dedup')?.checked),
    do_fq2fa: $('do_fq2fa') === null ? undefined : !!($('do_fq2fa')?.checked),
    gbdraw_max: +($('gbdraw_max')?.value) || undefined,
    plot_engine: $('plot_engine')?.value,
    gbdraw_fasta: ($('gbdraw_fasta')?.value || '').trim() || null,
    gbdraw_ann: ($('gbdraw_ann')?.value || '').trim() || null,
    force: !!($('force')?.checked),
    verify_host: $('verify_host')?.value,
    verify_methods: (() => {
      const els = document.querySelectorAll('input[name="verify_methods"]:checked');
      return els.length ? [...els].map(e => e.value) : undefined;
    })(),
    verify_combine: $('verify_combine')?.value,
  };
}

async function runStages(sample, stages) {
  const body = Object.fromEntries(
    Object.entries(collectParams()).filter(([_k, v]) => v !== undefined));
  if (stages) body.stages = stages;
  if (body.force && !confirm(t('pp.forceConfirm',
      '强制重跑会忽略断点标记，所选步骤将重新执行。继续？'))) return;
  try {
    const r = await fetch('/api/pipeline/' + encodeURIComponent(sample) + '/run', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body)});
    if (!r.ok) { alert(t('c.startFail', '启动失败') + ': ' + ((await r.json()).error || '')); return; }
    const d = await r.json();
    taskLogOpen.add(d.task);
    startPolling();
    const tb = $('tasks');
    if (tb) tb.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  } catch (e) { setConnBanner(true); alert(t('c.connFail', '无法连接平台服务') + ': ' + e); }
}

function runUpTo(sample, stage) {
  const effective = curStages.filter(s => s.status !== 'unavailable');
  const firstUndone = effective.findIndex(s => s.status !== 'done');
  const effOrder = effective.map(s => s.stage);
  const start = firstUndone < 0 ? effOrder.indexOf(stage) : firstUndone;
  const end = effOrder.indexOf(stage);
  const stages = effOrder.slice(Math.min(start, end), end + 1);
  if (!stages.length) { alert(t('pp.alreadyDone', '该步骤已完成（可用「重跑此步」单独重跑）')); return; }
  runStages(sample, stages);
}

async function createSample(btn) {
  return withBtn(btn, async () => {
    const r1 = $('r1').value.trim();
    const errBox = $('cErr');
    errBox.textContent = '';
    if (!r1) { errBox.textContent = t('pp.needR1', '请选择 R1 FASTQ 文件'); return; }
    const body = {
      sample: $('sample').value.trim(),
      r1, r2: $('r2').value.trim() || null,
      project: $('sampleProject')?.value.trim() || null,
      subsample: ($('subsample_on')?.checked)
        ? (+($('subsample')?.value) || defVal('subsample', 100000)) : 0,
    };
    const res = await apiCreateSample(body);
    if (!res.ok) {
      if (res.conn) setConnBanner(true);
      errBox.textContent = res.error; return;
    }
    $('r1').value = ''; $('r2').value = ''; $('sample').value = '';
    // 后端可能把样品名规范化过（中文/空格 → '_'）：显式告知实际登记名，
    // 否则用户以为建的是「样品A」，列表里却是「A」，无从对应。
    if (res.data && res.data.note) {
      errBox.textContent = res.data.note;
    }
    selectSample(res.data.sample);
    loadSamples();
  }, '⏳ 创建中…');
}

